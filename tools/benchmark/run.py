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
START, END = "<!-- benchmark:start -->", "<!-- benchmark:end -->"

TEXT = {
    "en": {
        "intro": "Mean over {n} generated ledgers (seeds {seeds}); each has 6 files, ~{rows} rows "
        "and {customers} customers. Rules only, no LLM. Total runtime {seconds}s.",
        "norm": "**Normalization**",
        "norm_head": "| Rows recovered | Dates correct | Amounts correct | Duplicate removal F1 |",
        "er": "**Entity resolution** (pairwise, over records)",
        "er_head": "| Stage | Precision | Recall | F1 | Entities found |",
        "auto": "Automatic (rules)",
        "reviewed": "After answering {cards} review cards",
        "truth": "True customers",
        "blocking": "Blocking compared {done} of {all} possible name pairs.",
    },
    "tr": {
        "intro": "Üretilmiş {n} defterin ortalaması (seed {seeds}); her biri 6 dosya, ~{rows} "
        "satır ve {customers} müşteri. Yalnızca kurallar, LLM yok. Toplam süre {seconds} sn.",
        "norm": "**Normalizasyon**",
        "norm_head": "| Bulunan satır | Doğru tarih | Doğru tutar | Mükerrer ayıklama F1 |",
        "er": "**Müşteri eşleştirme** (kayıt çiftleri üzerinden)",
        "er_head": "| Aşama | Precision | Recall | F1 | Bulunan müşteri |",
        "auto": "Otomatik (kurallar)",
        "reviewed": "{cards} soru cevaplandıktan sonra",
        "truth": "Gerçek müşteri sayısı",
        "blocking": "Blocking ile {all} olası isim çiftinin yalnızca {done} tanesi "
        "karşılaştırıldı.",
    },
}
README_LANG = {"README.md": "en", "README.tr.md": "tr"}


def _avg(results: list[BenchmarkResult], get: Callable[[BenchmarkResult], float]) -> float:
    return statistics.mean(get(r) for r in results)


def render(results: list[BenchmarkResult], seconds: float, lang: str = "en") -> str:
    r = results
    t = TEXT[lang]
    seeds = ", ".join(str(x.seed) for x in r)

    def pct(get: Callable[[BenchmarkResult], float]) -> str:
        value = f"{_avg(r, get) * 100:.1f}"
        return f"%{value.replace('.', ',')}" if lang == "tr" else f"{value}%"

    def er_row(label: str, get: Callable[[BenchmarkResult], ERResult]) -> str:
        p = _avg(r, lambda x: get(x).pairwise.precision)
        rc = _avg(r, lambda x: get(x).pairwise.recall)
        f = _avg(r, lambda x: get(x).pairwise.f1)
        n = _avg(r, lambda x: get(x).entities)
        return f"| {label} | {p:.3f} | {rc:.3f} | **{f:.3f}** | {n:.1f} |"

    cards = f"{_avg(r, lambda x: x.cards_answered):.0f}"
    return "\n".join(
        [
            t["intro"].format(
                n=len(r),
                seeds=seeds,
                rows=f"{_avg(r, lambda x: x.rows):.0f}",
                customers=f"{_avg(r, lambda x: x.customers):.0f}",
                seconds=f"{seconds:.1f}",
            ),
            "",
            t["norm"],
            "",
            t["norm_head"],
            "|---|---|---|---|",
            f"| {pct(lambda x: x.rows_found)} | {pct(lambda x: x.date_accuracy)} "
            f"| {pct(lambda x: x.amount_accuracy)} | {_avg(r, lambda x: x.duplicates.f1):.3f} |",
            "",
            t["er"],
            "",
            t["er_head"],
            "|---|---|---|---|---|",
            er_row(t["auto"], lambda x: x.er_rules),
            er_row(t["reviewed"].format(cards=cards), lambda x: x.er_reviewed),
            f"| *{t['truth']}* | | | | *{_avg(r, lambda x: x.er_rules.true_entities):.0f}* |",
            "",
            t["blocking"].format(
                done=f"{_avg(r, lambda x: x.comparisons):.0f}",
                all=f"{_avg(r, lambda x: x.naive_comparisons):.0f}",
            ),
        ]
    )


def update_readmes(results: list[BenchmarkResult], seconds: float) -> None:
    for name, lang in README_LANG.items():
        path = ROOT / name
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        if START not in text or END not in text:
            continue
        head, rest = text.split(START, 1)
        _, tail = rest.split(END, 1)
        table = render(results, seconds, lang)
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
    seconds = time.perf_counter() - started
    print(render(results, seconds))
    if args.json:
        args.json.write_text(json.dumps([x.as_dict() for x in results], indent=2), encoding="utf-8")
    if args.update_readme:
        update_readmes(results, seconds)


if __name__ == "__main__":
    main()
