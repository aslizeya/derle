"""Measure the pipeline against the generated ledger's ground truth.

Reported metrics:

* **normalization:** share of non-duplicate rows whose date / amount came out exactly right
* **duplicates:** precision / recall of exact-duplicate removal
* **entity resolution:** pairwise precision / recall / F1 over records, before review and
  after a simulated reviewer answers the queue using the ground truth (human-in-the-loop)
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from datetime import date
from decimal import Decimal
from math import comb
from typing import Any

from derle.demo.sample_ledger import SampleLedger, TruthRow, generate
from derle.matching.blocking import candidate_pairs
from derle.matching.profiles import build_profiles
from derle.services import entities
from derle.services.ingest import ingest_file
from derle.storage import repo
from derle.storage.db import Database

TODAY = date(2026, 7, 1)


@dataclass(slots=True)
class PRF:
    precision: float
    recall: float
    f1: float

    @classmethod
    def from_counts(cls, tp: int, fp: int, fn: int) -> PRF:
        p = tp / (tp + fp) if tp + fp else 1.0
        r = tp / (tp + fn) if tp + fn else 1.0
        f = 2 * p * r / (p + r) if p + r else 0.0
        return cls(round(p, 4), round(r, 4), round(f, 4))


@dataclass(slots=True)
class ERResult:
    pairwise: PRF
    entities: int
    true_entities: int
    pending: int


@dataclass(slots=True)
class BenchmarkResult:
    seed: int
    files: int
    rows: int
    customers: int
    date_accuracy: float
    amount_accuracy: float
    rows_found: float
    duplicates: PRF
    er_rules: ERResult
    er_reviewed: ERResult
    cards_answered: int
    comparisons: int
    naive_comparisons: int
    extra: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def pairwise_prf(predicted: dict[int, Any], truth: dict[int, str]) -> PRF:
    """Pairwise P/R/F1 computed from cluster contingency counts (no O(n²) pair listing)."""
    keys = [k for k in truth if k in predicted]
    joint = Counter((predicted[k], truth[k]) for k in keys)
    pred_sizes = Counter(predicted[k] for k in keys)
    true_sizes = Counter(truth[k] for k in keys)
    tp = sum(comb(n, 2) for n in joint.values())
    pred_pairs = sum(comb(n, 2) for n in pred_sizes.values())
    true_pairs = sum(comb(n, 2) for n in true_sizes.values())
    return PRF.from_counts(tp, pred_pairs - tp, true_pairs - tp)


def _record_index(db: Database) -> dict[tuple[str, str | None, int], tuple[int, str]]:
    with db.read() as cur:
        rows = cur.execute(
            "SELECT u.filename, t.sheet, r.row_index, r.id, r.status FROM records r "
            "JOIN upload_tables t ON t.id = r.table_id JOIN uploads u ON u.id = t.upload_id "
            "WHERE r.version_to IS NULL"
        ).fetchall()
    return {(f, s, int(ri)): (int(rid), st) for f, s, ri, rid, st in rows}


def _values(db: Database) -> dict[int, tuple[str | None, Decimal | None]]:
    """record -> (date, money) where money is the first of debit/credit/amount present."""
    out: dict[int, dict[str, Any]] = defaultdict(dict)
    with db.read() as cur:
        for rid, role, num, day in cur.execute(
            "SELECT c.record_id, f.role, c.value_num, c.value_date FROM cells c "
            "JOIN fields f ON f.id = c.field_id WHERE c.version_to IS NULL "
            "AND f.role IN ('date', 'amount', 'debit', 'credit')"
        ).fetchall():
            if role == "date" and day is not None:
                out[int(rid)]["date"] = day.isoformat()
            elif num is not None:
                out[int(rid)].setdefault("money", abs(Decimal(num)))
    return {rid: (v.get("date"), v.get("money")) for rid, v in out.items()}


def _entity_map(db: Database) -> dict[int, int]:
    with db.read() as cur:
        rows = cur.execute(
            "SELECT record_id, entity_id FROM entity_members WHERE version_to IS NULL"
        ).fetchall()
    return {int(r): int(e) for r, e in rows}


def _er(db: Database, workspace_id: int, record_truth: dict[int, str]) -> ERResult:
    predicted = _entity_map(db)
    with db.read() as cur:
        _, pending = entities.list_candidates(cur, workspace_id, limit=1)
    return ERResult(
        pairwise=pairwise_prf(predicted, record_truth),
        entities=len({predicted[k] for k in record_truth if k in predicted}),
        true_entities=len(set(record_truth.values())),
        pending=pending,
    )


def simulate_reviewer(
    db: Database, workspace_id: int, record_truth: dict[int, str], budget: int = 500
) -> int:
    """Answer cards like a careful shopkeeper: "same" if both entities are mostly the same
    real customer. Returns how many cards were answered."""
    answered = 0
    while answered < budget:
        with db.read() as cur:
            cards, _ = entities.list_candidates(cur, workspace_id, limit=1)
        if not cards:
            break
        card = cards[0]
        sides = []
        for side in ("left", "right"):
            entity = card[side]["entity"]
            with db.read() as cur:
                members = cur.execute(
                    "SELECT record_id FROM entity_members WHERE entity_id = ? "
                    "AND version_to IS NULL",
                    [entity["id"]],
                ).fetchall()
            votes = Counter(record_truth.get(int(m[0])) for m in members)
            sides.append(votes.most_common(1)[0][0])
        decision = "same" if sides[0] == sides[1] else "different"
        with db.transaction() as cur:
            entities.decide(cur, card["id"], decision)
        answered += 1
    return answered


def run_benchmark(
    ledger: SampleLedger | None = None, *, review_budget: int = 500
) -> BenchmarkResult:
    ledger = ledger or generate()
    db = Database(":memory:")
    with db.transaction() as cur:
        workspace_id = repo.ensure_default_workspace(cur)
    for f in ledger.files:
        ingest_file(db, workspace_id=workspace_id, data=f.data, filename=f.name, today=TODAY)

    index = _record_index(db)
    values = _values(db)
    originals = [t for t in ledger.truth if t.duplicate_of_row is None]

    found = date_ok = amount_ok = 0
    record_truth: dict[int, str] = {}
    for t in originals:
        hit = index.get((t.file, t.sheet, t.row))
        if hit is None:
            continue
        found += 1
        record_id, status = hit
        day, money = values.get(record_id, (None, None))
        date_ok += day == t.date
        amount_ok += money == Decimal(t.amount)
        if status == "active":
            record_truth[record_id] = t.customer_id

    duplicates = _duplicate_prf(ledger.truth, index)
    before = _er(db, workspace_id, record_truth)
    with db.read() as cur:
        profiles = build_profiles(entities.load_mentions(cur, workspace_id))
    comparisons = len(candidate_pairs(profiles))
    answered = simulate_reviewer(db, workspace_id, record_truth, budget=review_budget)
    after = _er(db, workspace_id, record_truth)
    db.close()

    n = len(originals)
    return BenchmarkResult(
        seed=ledger.seed,
        files=len(ledger.files),
        rows=len(ledger.truth),
        customers=len(ledger.customers),
        date_accuracy=round(date_ok / n, 4),
        amount_accuracy=round(amount_ok / n, 4),
        rows_found=round(found / n, 4),
        duplicates=duplicates,
        er_rules=before,
        er_reviewed=after,
        cards_answered=answered,
        comparisons=comparisons,
        naive_comparisons=comb(len(profiles), 2),
    )


def _duplicate_prf(
    truth: Iterable[TruthRow], index: dict[tuple[str, str | None, int], tuple[int, str]]
) -> PRF:
    tp = fp = fn = 0
    for t in truth:
        hit = index.get((t.file, t.sheet, t.row))
        predicted = hit is not None and hit[1] == "duplicate"
        actual = t.duplicate_of_row is not None
        tp += predicted and actual
        fp += predicted and not actual
        fn += actual and not predicted
    return PRF.from_counts(tp, fp, fn)
