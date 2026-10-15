# ADR-0006: Transparent, read-only natural-language queries

* Status: accepted
* Date: 2026-10-15

## Context
"Geçen ay en çok kim borçlandı?" should just work, but a shopkeeper must be able to trust
the answer, and user-influenced SQL running next to their only copy of the data is a real
risk, whether it comes from templates or an LLM.

## Decision
1. **Rules first.** A small Turkish intent parser (`nlq/rules.py`) covers the common ledger
   questions: metric (borç / ödeme / bakiye / sayı), grouping (müşteri / ay / gün), order
   and top-N, periods ("geçen ay", "Mart", "son 30 gün", "2025"), and a customer named in
   the question. The LLM is only asked when the rules return nothing and AI is enabled.
2. **No silent wrong answers.** If the question names a person ("Ahmet Demir'in…") who is
   not a known customer, the answer is an error, never the total for everybody. If the data
   ends long before today, relative periods are anchored to the last date in the data and
   the answer says so.
3. **One money model.** `analytics/schema.py` defines sales, payments and balance once, for
   whatever mix of `amount` / `debit` / `credit` columns a dataset has. Dashboards, quality
   checks, rule SQL and the LLM prompt all use the same expressions.
4. **Two independent safety layers.**
   * `nlq/guard.py` parses the SQL with sqlglot and allows exactly one query that reads only
     the dataset's `ds_<id>` view (or its own CTEs). Table functions and file or system
     functions are rejected, and a LIMIT is always present.
   * The DuckDB connection runs with `enable_external_access = false` and a locked
     configuration, so even SQL that slipped past the guard cannot read files.
   Queries also run with a time limit (interrupt) and a row cap.
5. **Show the work.** Every answer and every dashboard widget ships the exact SQL that ran,
   plus which engine produced it and how the question was read (metric, period, customer).
   Every question is logged (`query_log`).

## Consequences
* The rule parser handles a deliberately narrow, well-tested language. Anything else
  depends on the LLM (optional) or gets a helpful "not understood" with examples.
* The LLM sees only the schema and three sample values per non-personal column, never
  phone numbers or national IDs.
* Adding a new metric means adding it to the money model once; every consumer picks it up.
