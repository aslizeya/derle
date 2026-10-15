"""Entity resolution use cases: run matching, persist entities, handle review decisions.

Entities are *derived* from (current records + active decisions). Every run recomputes
the clustering, then writes only the difference as temporal ``entity_members`` rows. Entity
ids stay stable because each new cluster inherits the id most of its records already had.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from typing import Any

from derle.matching.profiles import Mention, Profile, build_profiles
from derle.matching.resolve import Decision, Resolution, pair_key, resolve
from derle.normalize.tr.text import fold
from derle.storage import repo
from derle.storage.repo import Cursor

DECISION_STATUS = {"same": "accepted", "different": "rejected", "skip": "skipped"}


class MatchError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(slots=True)
class ResolutionSummary:
    entities: int
    auto_merges: int
    pending: int
    comparisons: int


def load_mentions(cur: Cursor, workspace_id: int) -> list[Mention]:
    rows = cur.execute(
        """
        WITH active AS (
            SELECT r.id, r.dataset_id FROM records r
            JOIN datasets d ON d.id = r.dataset_id
            WHERE d.workspace_id = ? AND r.version_to IS NULL AND r.status = 'active'
        )
        SELECT a.id, pc.value_text, ph.value_text
        FROM active a
        JOIN fields pf ON pf.dataset_id = a.dataset_id AND pf.role = 'party'
        JOIN cells pc ON pc.record_id = a.id AND pc.field_id = pf.id AND pc.version_to IS NULL
        LEFT JOIN fields hf ON hf.dataset_id = a.dataset_id AND hf.role = 'phone'
        LEFT JOIN cells ph ON ph.record_id = a.id AND ph.field_id = hf.id
                          AND ph.version_to IS NULL
        WHERE pc.value_text IS NOT NULL
        ORDER BY a.id
        """,
        [workspace_id],
    ).fetchall()
    return [Mention(record_id=int(r[0]), name=r[1], phone=r[2]) for r in rows]


def load_decisions(cur: Cursor, workspace_id: int) -> list[Decision]:
    rows = cur.execute(
        "SELECT profile_a, profile_b, decision FROM match_decisions "
        "WHERE workspace_id = ? AND revoked_version IS NULL ORDER BY id",
        [workspace_id],
    ).fetchall()
    return [Decision(a, b, d) for a, b, d in rows]


def canonical_name(profiles: list[Profile]) -> str:
    """Pick the display name for a cluster.

    Preference: no initials → more name parts → written more often → seen with a phone →
    longer spelling (a slip usually drops a letter: "Yılmz") → seen first.
    """
    candidates: dict[str, tuple[bool, int, int, bool, int, int]] = {}
    for p in profiles:
        first_seen = min(p.record_ids)
        for name, count in p.names.items():
            tokens = name.split()
            rank = (
                not any(len(t.rstrip(".")) == 1 for t in tokens),
                len(tokens),
                count,
                p.phone is not None,
                len(name),
                -first_seen,
            )
            if name not in candidates or rank > candidates[name]:
                candidates[name] = rank
    return max(candidates, key=lambda n: candidates[n])


def resolve_workspace(cur: Cursor, workspace_id: int, version_id: int) -> ResolutionSummary:
    profiles = build_profiles(load_mentions(cur, workspace_id))
    result = resolve(profiles, load_decisions(cur, workspace_id))
    entity_of_cluster = _persist_entities(cur, workspace_id, version_id, profiles, result)
    pending = _persist_candidates(
        cur, workspace_id, version_id, profiles, result, entity_of_cluster
    )
    return ResolutionSummary(
        entities=len(result.clusters),
        auto_merges=result.auto_merges,
        pending=pending,
        comparisons=result.comparisons,
    )


def _persist_entities(
    cur: Cursor,
    workspace_id: int,
    version_id: int,
    profiles: list[Profile],
    result: Resolution,
) -> dict[int, int]:
    current: dict[int, int] = dict(
        cur.execute(
            "SELECT em.record_id, em.entity_id FROM entity_members em "
            "JOIN entities e ON e.id = em.entity_id "
            "WHERE e.workspace_id = ? AND em.version_to IS NULL",
            [workspace_id],
        ).fetchall()
    )

    entity_of_cluster: dict[int, int] = {}
    taken: set[int] = set()
    new_membership: dict[int, int] = {}
    order = sorted(range(len(result.clusters)), key=lambda c: -len(result.clusters[c]))
    for c in order:
        members = [profiles[i] for i in result.clusters[c]]
        record_ids = [r for p in members for r in p.record_ids]
        previous = Counter(current[r] for r in record_ids if r in current)
        entity_id = next((e for e, _ in previous.most_common() if e not in taken), None)
        name = canonical_name(members)
        if entity_id is None:
            entity_id = repo.insert_returning_id(
                cur,
                "INSERT INTO entities (workspace_id, canonical_name, created_version) "
                "VALUES (?, ?, ?)",
                [workspace_id, name, version_id],
            )
        else:
            cur.execute("UPDATE entities SET canonical_name = ? WHERE id = ?", [name, entity_id])
        taken.add(entity_id)
        entity_of_cluster[c] = entity_id
        for record_id in record_ids:
            new_membership[record_id] = entity_id

    changed = [r for r, e in current.items() if new_membership.get(r) != e]
    if changed:
        cur.execute(
            "UPDATE entity_members SET version_to = ? "
            "WHERE version_to IS NULL AND record_id IN (SELECT unnest(?::BIGINT[]))",
            [version_id, changed],
        )
    added = [(r, e) for r, e in new_membership.items() if current.get(r) != e]
    repo.bulk_insert(
        cur,
        "entity_members",
        {
            "record_id": [r for r, _ in added],
            "entity_id": [e for _, e in added],
            "version_from": [version_id] * len(added),
        },
        {"record_id": "BIGINT", "entity_id": "BIGINT", "version_from": "BIGINT"},
    )
    return entity_of_cluster


def _persist_candidates(
    cur: Cursor,
    workspace_id: int,
    version_id: int,
    profiles: list[Profile],
    result: Resolution,
    entity_of_cluster: dict[int, int],
) -> int:
    existing = {
        row[0]: (int(row[1]), row[2])
        for row in cur.execute(
            "SELECT pair_key, id, status FROM match_candidates WHERE workspace_id = ?",
            [workspace_id],
        ).fetchall()
    }
    live: set[str] = set()
    for pair in result.review:
        a, b = profiles[pair.a], profiles[pair.b]
        key = pair_key(a.id, b.id)
        live.add(key)
        evidence = repo.to_json(
            [{"code": e.code, "weight": e.weight, "value": e.value} for e in pair.match.evidence]
        )
        values = [
            entity_of_cluster[result.cluster_of[pair.a]],
            entity_of_cluster[result.cluster_of[pair.b]],
            pair.match.score,
            evidence,
        ]
        if key not in existing:
            cur.execute(
                "INSERT INTO match_candidates (entity_a, entity_b, score, evidence, workspace_id, "
                "pair_key, profile_a, profile_b, status, created_version) "
                "VALUES (?, ?, ?, CAST(? AS JSON), ?, ?, ?, ?, 'pending', ?)",
                [*values, workspace_id, key, a.id, b.id, version_id],
            )
        elif existing[key][1] in {"pending", "superseded"}:
            cur.execute(
                "UPDATE match_candidates SET entity_a = ?, entity_b = ?, score = ?, "
                "evidence = CAST(? AS JSON), status = 'pending' WHERE id = ?",
                [*values, existing[key][0]],
            )

    stale = [
        cid for key, (cid, status) in existing.items() if status == "pending" and key not in live
    ]
    if stale:
        cur.execute(
            "UPDATE match_candidates SET status = 'superseded' "
            "WHERE id IN (SELECT unnest(?::BIGINT[]))",
            [stale],
        )
    return len(live)


# --- review decisions -----------------------------------------------------------------------


def decide(cur: Cursor, candidate_id: int, decision: str) -> tuple[int, ResolutionSummary]:
    if decision not in DECISION_STATUS:
        raise MatchError("invalid_decision")
    row = cur.execute(
        "SELECT workspace_id, profile_a, profile_b, status, entity_a, entity_b "
        "FROM match_candidates WHERE id = ?",
        [candidate_id],
    ).fetchone()
    if row is None:
        raise MatchError("candidate_not_found")
    workspace_id, profile_a, profile_b, status, entity_a, entity_b = row
    if status != "pending":
        raise MatchError("candidate_not_pending")

    names = dict(
        cur.execute(
            "SELECT id, canonical_name FROM entities WHERE id IN (?, ?)", [entity_a, entity_b]
        ).fetchall()
    )
    version_id = repo.create_version(
        cur,
        workspace_id,
        "match_decision",
        f"{decision}: {profile_a} ~ {profile_b}",
        {"decision": decision, "a": names.get(entity_a), "b": names.get(entity_b)},
    )
    cur.execute(
        "INSERT INTO match_decisions (workspace_id, candidate_id, profile_a, profile_b, decision, "
        "version_id) VALUES (?, ?, ?, ?, ?, ?)",
        [workspace_id, candidate_id, profile_a, profile_b, decision, version_id],
    )
    cur.execute(
        "UPDATE match_candidates SET status = ?, decided_version = ? WHERE id = ?",
        [DECISION_STATUS[decision], version_id, candidate_id],
    )
    return version_id, resolve_workspace(cur, workspace_id, version_id)


def undo_last_decision(cur: Cursor, workspace_id: int) -> tuple[int, int, ResolutionSummary]:
    """Revoke the most recent decision. Returns ``(version_id, candidate_id, summary)``."""
    row = cur.execute(
        "SELECT id, candidate_id FROM match_decisions "
        "WHERE workspace_id = ? AND revoked_version IS NULL ORDER BY id DESC LIMIT 1",
        [workspace_id],
    ).fetchone()
    if row is None:
        raise MatchError("nothing_to_undo")
    decision_id, candidate_id = row
    version_id = repo.create_version(
        cur, workspace_id, "undo", f"undo decision {decision_id}", {"target": "decision"}
    )
    cur.execute(
        "UPDATE match_decisions SET revoked_version = ? WHERE id = ?", [version_id, decision_id]
    )
    cur.execute(
        "UPDATE match_candidates SET status = 'pending', decided_version = NULL WHERE id = ?",
        [candidate_id],
    )
    return version_id, int(candidate_id), resolve_workspace(cur, workspace_id, version_id)


# --- read side ------------------------------------------------------------------------------

_SUMMARY_ROLES = ("date", "amount", "debit", "credit")


def _record_facts(cur: Cursor, record_ids: list[int]) -> dict[int, dict[str, Any]]:
    """Date, party name, money fields and source location for each record."""
    if not record_ids:
        return {}
    facts: dict[int, dict[str, Any]] = {
        int(rid): {"record_id": int(rid), "filename": fn, "sheet": sh, "row": ri}
        for rid, fn, sh, ri in cur.execute(
            "SELECT r.id, u.filename, t.sheet, r.row_index FROM records r "
            "JOIN upload_tables t ON t.id = r.table_id JOIN uploads u ON u.id = t.upload_id "
            "WHERE r.id IN (SELECT unnest(?::BIGINT[])) AND r.version_to IS NULL",
            [record_ids],
        ).fetchall()
    }
    for rid, role, text, num, day in cur.execute(
        "SELECT c.record_id, f.role, c.value_text, c.value_num, c.value_date FROM cells c "
        "JOIN fields f ON f.id = c.field_id "
        "WHERE c.record_id IN (SELECT unnest(?::BIGINT[])) AND c.version_to IS NULL "
        "AND f.role IN ('party', 'date', 'amount', 'debit', 'credit')",
        [record_ids],
    ).fetchall():
        target = facts.setdefault(int(rid), {"record_id": int(rid)})
        if role == "party":
            target["name"] = text
        elif role == "date" and day is not None:
            target["date"] = day.isoformat()
        elif num is not None:
            target[role] = float(num)
    return facts


def entity_summary(cur: Cursor, entity_id: int, *, samples: int = 3) -> dict[str, Any] | None:
    row = cur.execute(
        "SELECT id, workspace_id, canonical_name FROM entities WHERE id = ?", [entity_id]
    ).fetchone()
    if row is None:
        return None
    record_ids = [
        int(r[0])
        for r in cur.execute(
            "SELECT record_id FROM entity_members WHERE entity_id = ? AND version_to IS NULL "
            "ORDER BY record_id",
            [entity_id],
        ).fetchall()
    ]
    facts = _record_facts(cur, record_ids)
    phones = cur.execute(
        "SELECT DISTINCT c.value_text FROM cells c JOIN fields f ON f.id = c.field_id "
        "WHERE f.role = 'phone' AND c.version_to IS NULL AND c.value_text IS NOT NULL "
        "AND c.record_id IN (SELECT unnest(?::BIGINT[])) ORDER BY 1",
        [record_ids],
    ).fetchall()
    aliases = Counter(f["name"] for f in facts.values() if f.get("name"))
    dates = sorted(f["date"] for f in facts.values() if f.get("date"))
    totals = {
        role: round(sum(f.get(role, 0.0) for f in facts.values()), 2)
        for role in _SUMMARY_ROLES[1:]
        if any(role in f for f in facts.values())
    }
    ordered = sorted(facts.values(), key=lambda f: f.get("date") or "", reverse=True)
    return {
        "id": row[0],
        "workspace_id": row[1],
        "name": row[2],
        "record_count": len(record_ids),
        "aliases": [{"name": n, "count": c} for n, c in aliases.most_common()],
        "phones": [p[0] for p in phones],
        "first_date": dates[0] if dates else None,
        "last_date": dates[-1] if dates else None,
        "totals": totals,
        "samples": ordered[:samples],
    }


def list_candidates(
    cur: Cursor, workspace_id: int, *, status: str = "pending", limit: int = 20
) -> tuple[list[dict[str, Any]], int]:
    total_row = cur.execute(
        "SELECT count(*) FROM match_candidates WHERE workspace_id = ? AND status = ?",
        [workspace_id, status],
    ).fetchone()
    rows = cur.execute(
        "SELECT id, profile_a, profile_b, entity_a, entity_b, score, evidence, status "
        "FROM match_candidates WHERE workspace_id = ? AND status = ? "
        "ORDER BY score DESC, id LIMIT ?",
        [workspace_id, status, limit],
    ).fetchall()
    cards = []
    for cid, pa, pb, ea, eb, score, evidence, st in rows:
        cards.append(
            {
                "id": cid,
                "score": score,
                "status": st,
                "evidence": json.loads(evidence) if isinstance(evidence, str) else evidence,
                "left": {"profile": pa, "entity": entity_summary(cur, ea)},
                "right": {"profile": pb, "entity": entity_summary(cur, eb)},
            }
        )
    return cards, int(total_row[0]) if total_row else 0


def list_entities(
    cur: Cursor, workspace_id: int, *, limit: int, offset: int, query: str | None = None
) -> tuple[list[dict[str, Any]], int]:
    where = "e.workspace_id = ?"
    params: list[Any] = [workspace_id]
    if query:
        # Fold like the rest of the app: "yilmaz" must find "Yılmaz" (ı is not an accent).
        where += " AND strip_accents(lower(translate(e.canonical_name, 'ıİ', 'iI'))) LIKE ?"
        params.append(f"%{fold(query)}%")
    base = (
        f"FROM entities e JOIN entity_members em ON em.entity_id = e.id AND em.version_to IS NULL "
        f"WHERE {where}"
    )
    total_row = cur.execute(f"SELECT count(DISTINCT e.id) {base}", params).fetchone()
    rows = cur.execute(
        f"SELECT e.id, e.canonical_name, count(*) AS records {base} "
        "GROUP BY e.id, e.canonical_name ORDER BY records DESC, e.id LIMIT ? OFFSET ?",
        [*params, limit, offset],
    ).fetchall()
    return (
        [{"id": r[0], "name": r[1], "record_count": r[2]} for r in rows],
        int(total_row[0]) if total_row else 0,
    )
