---
id: example-feature
title: User search (example template)
status: draft
owner: TODO(human): assign-owner
created: 2026-05-19
last-reviewed: 2026-05-19
related-prompts: []
related-tools: []
eval-ref: evals/example-eval.yaml
---

# Requirements — user search

> Template spec. Do not implement; replace contents when authoring a real
> feature.

## Background

The product needs a way for end users to find other users by name or handle.
Today there is no search; users must know exact URLs. This causes drop-off
in onboarding flows that depend on follow / invite actions.

## User stories

- **US-1** — As a signed-in user, I want to search for other users by
  display name, so that I can follow them without leaving the app.
- **US-2** — As a signed-in user, I want results to appear within 200 ms of
  typing the third character, so that the experience feels live.
- **US-3** — As a privacy-conscious user, I want users who set their
  profile to private to be excluded from search, so that my preferences
  are respected.

## Acceptance criteria (EARS)

- **AC-1** — WHEN a signed-in user submits a query of length ≥ 3, THE
  SYSTEM SHALL return up to 20 matching public profiles ranked by relevance.
- **AC-2** — WHEN a query matches a private profile, THE SYSTEM SHALL
  exclude that profile from results.
- **AC-3** — WHEN the median p50 server-side search latency exceeds 200 ms
  over a 5-minute window, THE SYSTEM SHALL emit a `search.latency.p50.high`
  alert.
- **AC-4** — WHILE a user is not signed in, THE SYSTEM SHALL return HTTP
  401 for any call to the search endpoint.

## Non-goals

- Full-text search of profile bios (deferred).
- Search ranking personalisation based on social graph (deferred).
- Fuzzy matching across non-Latin scripts (deferred; see TODO below).

## Open questions

- TODO(human): confirm whether organisation accounts should appear in
  user search or have a separate endpoint.
- TODO(human): confirm relevance signal — exact prefix only, or include
  trigram similarity?
