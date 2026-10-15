"""Regression guard: the benchmark numbers in the README must not silently get worse."""

import pytest

from derle.demo.benchmark import PRF, pairwise_prf, run_benchmark
from derle.demo.sample_ledger import generate
from derle.ingest import read_grids


def test_generator_is_deterministic() -> None:
    a, b = generate(seed=3), generate(seed=3)
    assert a.truth == b.truth
    # xlsx bytes embed a save timestamp, so compare what the reader sees instead.
    for fa, fb in zip(a.files, b.files, strict=True):
        assert [r.cells for g in read_grids(fa.data, fa.name) for r in g.rows] == [
            r.cells for g in read_grids(fb.data, fb.name) for r in g.rows
        ]
    assert generate(seed=4).truth != a.truth


def test_generator_covers_the_messy_cases() -> None:
    ledger = generate(seed=7)
    assert [f.name.split("_")[0] for f in ledger.files] == [
        "ocak", "subat", "mart", "nisan", "mayis", "haziran",
    ]  # fmt: skip
    written = {t.written_name for t in ledger.truth}
    assert any(n.endswith(("bey", "hanım")) for n in written)
    assert any(". " in n for n in written)  # initials
    assert any("," in n for n in written)  # "Yılmaz, Ahmet"
    assert any(t.duplicate_of_row for t in ledger.truth)
    assert ledger.files[1].data.decode("cp1254")  # Şubat really is Windows-1254


def test_pairwise_prf_from_contingency() -> None:
    truth = {1: "a", 2: "a", 3: "b", 4: "b"}
    assert pairwise_prf({1: 1, 2: 1, 3: 2, 4: 2}, truth) == PRF(1.0, 1.0, 1.0)
    over_merged = pairwise_prf({1: 1, 2: 1, 3: 1, 4: 1}, truth)
    assert over_merged.recall == 1.0
    assert over_merged.precision == pytest.approx(2 / 6, abs=1e-3)
    assert pairwise_prf({1: 1, 2: 2, 3: 3, 4: 4}, truth).recall == 0.0


def test_benchmark_floor() -> None:
    result = run_benchmark(generate(seed=7))
    assert result.rows_found == 1.0
    assert result.date_accuracy >= 0.99
    assert result.amount_accuracy >= 0.99
    assert result.duplicates.f1 >= 0.95
    assert result.er_rules.pairwise.f1 >= 0.90
    assert result.er_reviewed.pairwise.f1 >= 0.93
    assert result.er_reviewed.pending == 0
    assert result.cards_answered <= 40
    assert result.comparisons < result.naive_comparisons / 5
