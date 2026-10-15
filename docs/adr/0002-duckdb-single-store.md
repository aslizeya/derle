# ADR-0002: DuckDB as the only store, with a long cell table and wide views

* Status: accepted
* Date: 2026-10-14

## Context
Derle needs (a) cell-level provenance and undo, and (b) fast analytical queries for
dashboards and natural-language SQL. The target user runs it locally or self-hosts it for
one business.

## Decision
* A single embedded DuckDB file holds both metadata and data.
* Values live in a long `cells` table (record × field) with `raw_value`, `src_cols` and
  version columns, which gives provenance and history.
* Each dataset gets a generated view `ds_<id>` with one typed column per field, which gives
  ergonomic analytics.

## Alternatives considered
* **SQLite for metadata + DuckDB for analytics**: two databases, two transaction scopes
  and cross-database consistency issues, with no benefit at this scale.
* **Wide physical tables per dataset**: simpler queries, but schema changes on every new
  column and no natural place for per-cell provenance.
* **Postgres**: an extra service for a single-user local tool. Revisit if the product
  becomes multi-tenant SaaS.

## Consequences
* One writer process per database file. The API serializes writes with a lock (fine for
  one business, not for many concurrent tenants).
* View pivots cost a GROUP BY. Acceptable at ledger scale (≤10⁶ cells). Materialize as
  tables later if needed.
