# Derle

> Turn scattered spreadsheets into a clean, persistent, explainable database.
> *Dağınık verini düzene sok.*

Small businesses keep their records in Excel files with a different layout every month,
semicolon CSVs from Turkish Excel, and notebook-style ledgers. Derle ingests them into one
versioned DuckDB database. It recognizes columns, normalizes Turkish dates, numbers, names
and phone numbers, removes duplicates, and keeps a link from every clean value back to the
exact file, row and original text it came from.

**Status:** feature-complete for v1: ingestion, Turkish normalization, entity resolution
with a review queue, before/after review with undo, provenance, data-quality score,
automatic dashboard, natural-language questions (with the SQL shown), version history with
restore, and Excel/CSV export. Packaging (Docker, CI, screenshots) is next.
See [docs/architecture.md](docs/architecture.md) and [docs/adr](docs/adr).

## Backend quick start

```bash
cd apps/api
python -m venv .venv && . .venv/Scripts/activate   # or .venv/bin/activate
pip install -e ".[dev,llm]"
pytest
uvicorn derle.main:app --reload
```

AI is optional. See [.env.example](.env.example).

## Web quick start

```bash
cd apps/web
npm install
npm run dev        # http://localhost:3000, proxies /api to http://localhost:8000
```

Click **Örnek veriyle dene** on the landing page to load a generated six-month ledger.

## Benchmark

`tools/benchmark/run.py` generates realistic, deliberately messy six-month ledgers with known
ground truth, pushes them through the real pipeline, and measures the result. A simulated
reviewer then answers the "are these the same?" cards using the ground truth, to show what
human-in-the-loop review adds.

<!-- benchmark:start -->
Mean over 5 generated ledgers (seeds 1, 2, 3, 4, 5); each has 6 files, ~324 rows and 40 customers. Rules only, no LLM. Total runtime 5.7s.

**Normalization**

| Rows recovered | Dates correct | Amounts correct | Duplicate removal F1 |
|---|---|---|---|
| 100.0% | 100.0% | 100.0% | 1.000 |

**Entity resolution** (pairwise, over records)

| Stage | Precision | Recall | F1 | Entities found |
|---|---|---|---|---|
| Automatic (rules) | 0.938 | 0.862 | **0.898** | 49.4 |
| After answering 11 review cards | 0.918 | 0.940 | **0.929** | 39.8 |
| *True customers* | | | | *40* |

Blocking compared 491 of 7673 possible name pairs.
<!-- benchmark:end -->

```bash
python tools/benchmark/run.py --update-readme
```

## License

MIT
