# ADR-0001: Single monorepo for API and web

* Status: accepted
* Date: 2026-10-14

## Context
The backend (Python) and frontend (TypeScript) change together: a new pipeline event or
transformation kind needs both a producer and a UI message. Keeping them in separate repos
would split CI, issues and the README.

## Decision
One repository with `apps/api` and `apps/web`. The OpenAPI schema produced by FastAPI is
the contract, and TypeScript types are generated from it.

## Consequences
* One `docker compose up` and one CI workflow with per-app jobs.
* Contract drift shows up as a type error in the web build, not at runtime.
* Two toolchains live side by side; each app keeps its own lockfile.
