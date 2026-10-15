# ADR-0004: Rules first, LLM optional

* Status: accepted
* Date: 2026-10-14

## Context
Business ledgers contain personal data (names, phone numbers, national IDs). Some users
cannot or will not send that data to a third party, and the product must work offline in
Docker. LLMs are still very good at labelling odd column headers ("Kim aldı?").

## Decision
* Every AI-assisted feature has a deterministic rule-based path, and that path is the default.
* LLM access goes through a provider protocol. `NullProvider` returns `None`, and callers
  treat `None` as "keep the rule result".
* The LLM receives only headers and a few sample values per column, never whole files.
* It may only *upgrade* columns whose rule confidence is below 0.6. Confident rule results
  are never overridden.
* Responses are parsed into Pydantic models (Claude structured outputs). Validation
  failures, API errors and refusals all fall back to rules.

## Consequences
* Benchmarks report rule-only and rule+LLM scores separately, so the LLM's contribution is
  measurable.
* The core is testable without network access or API keys.
