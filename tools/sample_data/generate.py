"""Write the messy sample ledger and its ground truth to a folder.

    python tools/sample_data/generate.py                 # -> data/sample/
    python tools/sample_data/generate.py --seed 3 --out /tmp/ledger

Produces six monthly files in different layouts plus ``ground_truth.json`` (true customer,
date and amount for every data row, and which rows are accidental duplicates).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from derle.demo.sample_ledger import generate

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--customers", type=int, default=40)
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "sample")
    args = parser.parse_args()

    ledger = generate(args.seed, args.customers)
    args.out.mkdir(parents=True, exist_ok=True)
    for f in ledger.files:
        (args.out / f.name).write_bytes(f.data)
    (args.out / "ground_truth.json").write_text(
        json.dumps(ledger.truth_json(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"{len(ledger.files)} files, {len(ledger.truth)} rows, "
          f"{len(ledger.customers)} customers -> {args.out}")  # fmt: skip


if __name__ == "__main__":
    main()
