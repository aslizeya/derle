# ADR-0003: Temporal rows instead of destructive updates

* Status: accepted
* Date: 2026-10-14

## Context
Users must be able to undo any single transformation, roll back a whole upload and restore
the workspace to an earlier point, and they must trust that the original data is never lost.

## Decision
Every mutating operation creates a row in `versions`. Mutable tables (`records`, `cells`, and
later the entity tables) carry `version_from` and `version_to`:

* current state: `version_to IS NULL`
* state at version *v*: `version_from <= v AND (version_to IS NULL OR version_to > v)`

A change closes the old row (`version_to = new_version`) and inserts a new one. Restoring
version *v* is itself a new version that re-opens the rows valid at *v*. History stays linear
and append-only.

## Consequences
* Point-in-time queries and diffs between versions are plain SQL.
* Storage grows with edits. Ledger-sized data makes this negligible.
* Every query must filter on `version_to IS NULL`. The `ds_<id>` views centralize this.
