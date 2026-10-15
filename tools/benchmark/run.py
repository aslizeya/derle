"""Run the Derle benchmark over several generated ledgers and print a Markdown report.

    python tools/benchmark/run.py                  # 5 seeds, Markdown to stdout
    python tools/benchmark/run.py --seeds 1 2 3 --json results.json
    python tools/benchmark/run.py --update-readme  # rewrite the table between the markers

Requires the API package on the path (``pip install -e apps/api``).
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections.abc import Callable
from pathlib import Path

from derle.demo.benchmark import BenchmarkResult, ERResult, run_benchmark
from derle.demo.sample_ledger import generate

ROOT = Path(__file__).resolve().parents[2]
README_FILES = [ROOT / "README.md", ROOT / "README.tr.md"]
START, END = "<!-- benchmark:start -->", "<!-- benchmark:end -->"


def _avg(results: list[BenchmarkResult], get: Callable[[BenchmarkResult], float]) -> float:
    return statistics.mean(get(r) for r in results)


def render(results: list[BenchmarkResult], seconds: float) -> str:
    r = results
    seeds = ", ".join(str(x.seed) for x in r)

    def pct(get: Callable[[BenchmarkResult], float]) -> str:
        return f"{_avg(r, get) * 100:.1f}%"

    def er_row(label: str, get: Callable[[BenchmarkResult], ERResult]) -> str:
        p = _avg(r, lambda x: get(x).pairwise.precision)
        rc = _avg(r, lambda x: get(x).pairwise.recall)
        f = _avg(r, lambda x: get(x).pairwise.f1)
        n = _avg(r, lambda x: get(x).entities)
        return f"| {label} | {p:.3f} | {rc:.3f} | **{f:.3f}** | {n:.1f} |"

    cards = _avg(r, lambda x: x.cards_answered)
    return "\n".join(
        [
            f"Mean over {len(r)} generated ledgers (seeds {seeds}); each has 6 files, "
            f"~{_avg(r, lambda x: x.rows):.0f} rows and {_avg(r, lambda x: x.customers):.0f} "
            f"customers. Rules only, no LLM. Total runtime {seconds:.1f}s.",
            "",
            "**Normalization**",
            "",
            "| Rows recovered | Dates correct | Amounts correct | Duplicate removal F1 |",
            "|---|---|---|---|",
            f"| {pct(lambda x: x.rows_found)} | {pct(lambda x: x.date_accuracy)} "
            f"| {pct(lambda x: x.amount_accuracy)} | {_avg(r, lambda x: x.duplicates.f1):.3f} |",
            "",
            "**Entity resolution** (pairwise, over records)",
            "",
            "| Stage | Precision | Recall | F1 | Entities found |",
            "|---|---|---|---|---|",
            er_row("Automatic (rules)", lambda x: x.er_rules),
            er_row(f"After answering {cards:.0f} review cards", lambda x: x.er_reviewed),
            f"| *True customers* | | | | *{_avg(r, lambda x: x.er_rules.true_entities):.0f}* |",
            "",
            f"Blocking compared {_avg(r, lambda x: x.comparisons):.0f} of "
            f"{_avg(r, lambda x: x.naive_comparisons):.0f} possible name pairs.",
        ]
    )


def update_readmes(table: str) -> None:
    for path in README_FILES:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        if START not in text or END not in text:
            continue
        head, rest = text.split(START, 1)
        _, tail = rest.split(END, 1)
        path.write_text(f"{head}{START}\n{table}\n{END}{tail}", encoding="utf-8")
        print(f"updated {path.relative_to(ROOT)}", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3, 4, 5])
    parser.add_argument("--customers", type=int, default=40)
    parser.add_argument("--json", type=Path, help="also write raw results as JSON")
    parser.add_argument("--update-readme", action="store_true")
    args = parser.parse_args()

    started = time.perf_counter()
    results = [run_benchmark(generate(seed, args.customers)) for seed in args.seeds]
    table = render(results, time.perf_counter() - started)
    print(table)
    if args.json:
        args.json.write_text(json.dumps([x.as_dict() for x in results], indent=2), encoding="utf-8")
    if args.update_readme:
        update_readmes(table)


if __name__ == "__main__":
    main()
