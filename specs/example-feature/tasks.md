---
id: example-feature
title: User search (example template) — tasks
status: draft
owner: TODO(human): assign-owner
created: 2026-05-19
last-reviewed: 2026-05-19
related-prompts: []
related-tools: []
eval-ref: evals/example-eval.yaml
---

# Tasks — user search

> Template spec. Do not implement; replace contents when authoring a real
> feature.

Each task maps to one PR ≤ 500 lines. Tick items in order — later tasks
assume earlier ones have landed.

## Implementation

- [ ] **T-1** — Add `pg_trgm` index migration
      (`CREATE INDEX CONCURRENTLY users_display_name_trgm_idx ...`). Verify
      `pg_trgm` extension exists on all environments before rollout.
- [ ] **T-2** — Add `GET /api/v1/users/search` route handler in
      `search-service`. Input validation: `q` length ∈ [3, 64]; reject
      otherwise with 400. Excludes private profiles (`is_public = true`).
- [ ] **T-3** — Add per-user rate limit (60 req/min) using the existing
      token-bucket middleware. Return 429 with `Retry-After`.
- [ ] **T-4** — Emit `search.latency.p50/p95` histogram and
      `search.results.empty` counter. Confirm dashboards in the
      observability repo.
- [ ] **T-5** — Wire the search box in the navbar; 120 ms debounce, abort
      in-flight request on new keystroke, render up to 20 results.

## Eval & docs

- [ ] **T-6** — Author `/evals/user-search.yaml` with at least 20 cases
      (positive, negative, private-excluded, empty-results, short-query).
      Record initial baseline scores.
- [ ] **T-7** — Update `CHANGELOG.md` and product docs.

## Pre-launch

- [ ] **T-8** — Load test at 2× projected peak (target p95 < 200 ms).
- [ ] **T-9** — Privacy review: confirm raw queries are not logged and
      that private profiles are excluded end-to-end.
- [ ] **T-10** — Gradual rollout behind feature flag `users.search`;
      ramp 1% → 10% → 100% over 48 h.

## TODO(human)

- TODO(human): confirm whether T-6 should include an LLM-judge metric for
  result relevance or stay purely deterministic (exact / regex).
