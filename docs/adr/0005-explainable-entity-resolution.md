# ADR-0005: Explainable, constraint-aware entity resolution

* Status: accepted
* Date: 2026-10-14

## Context
One customer appears as "Ahmet Yılmaz", "ahmet bey", "A. Yılmaz", "AHMET YILMAZ" and "Ahmet
Yılmz". Users must be able to trust a merge before it affects their balances. Some cases
cannot be decided from the data alone ("M. Yılmaz" when both Mehmet and Murat Yılmaz exist),
so a person has to decide them, once.

## Decision
* **Profiles, not records.** Matching runs on distinct (folded name, phone) profiles.
  Identical spellings collapse up front, and a decision about a profile applies to every
  current and future record with that spelling.
* **Blocking** on 3-letter token prefixes and phone numbers. Initials still meet their full
  names through the surname block.
* **Additive evidence → logistic score.** Name similarity (centred at 0.8), typo (one slip),
  initials, first-name-only, same/different phone, first-name and surname conflicts. Every
  card shows the evidence with its weight, so the score is never a black box.
* **Two thresholds.** ≥ 0.90 merges automatically; 0.50–0.90 becomes a review card;
  anything below is treated as different.
* **Unique completion.** A partial name ("Elif", "D. Demir") whose only plausible owner is
  one cluster merges automatically. Clustering is recomputed from scratch on every run, so
  this is reconsidered as soon as a second candidate appears.
* **Human decisions are constraints.** "Same" is a must-link and "different" is a cannot-link,
  both enforced transitively by a constrained union-find. They are stored per profile pair,
  versioned, and revocable (undo).
* **Stable ids.** Each recomputed cluster inherits the entity id held by most of its records.
  Membership changes are written as temporal rows.

## Alternatives considered
* **Trained classifier (e.g. logistic regression on labelled pairs).** Slightly better
  numbers possible, but the weights would be opaque to the shopkeeper and there is no
  per-business training data at the start. Hand-set weights are tuned on the generated
  benchmark and documented in `matching/scoring.py`.
* **Splink / dedupe libraries.** Heavy dependencies built for millions of records; their
  explanations are less natural for Turkish name patterns (honorifics, initials, folding).

## Consequences
* The benchmark reports both automatic F1 and F1 after a simulated reviewer, plus how many
  cards that took. The human-in-the-loop cost is part of the metric.
* Known limit: two different customers written with the *same* first name only and no phone
  ("Mehmet abi") share one profile and cannot be told apart. This is the main remaining
  precision loss. Splitting a profile by context (date range, items bought) is future work.
