# derle (API)

FastAPI backend of [Derle](../../README.md): ingestion, Turkish normalization, entity
resolution, data quality, dashboards and natural-language queries over DuckDB.

```bash
pip install -e ".[dev,llm]"
pytest
uvicorn derle.main:app --reload --app-dir src
```

Configuration is read from `DERLE_*` environment variables; see `src/derle/config.py`.
