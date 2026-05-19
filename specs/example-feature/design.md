---
id: example-feature
title: User search (example template) — design
status: draft
owner: TODO(human): assign-owner
created: 2026-05-19
last-reviewed: 2026-05-19
related-prompts: []
related-tools: []
eval-ref: evals/example-eval.yaml
---

# Design — user search

> Template spec. Do not implement; replace contents when authoring a real
> feature.

## Overview

Add a single `GET /api/v1/users/search?q=<query>` endpoint, backed by a
Postgres trigram index on the `users.display_name` column. The frontend
debounces input by 120 ms and issues one in-flight request at a time.

## Architecture

```
[ Browser ] --debounced GET--> [ API gateway ]
                                    │
                                    ▼
                              [ search-service ]
                                    │
                              SELECT ... ILIKE / similarity()
                                    ▼
                              [ Postgres: users ]
```

- No new service; reuse the existing `search-service` process.
- No new datastore; reuse the existing `users` table with one added index.

## Data

### Schema change

```sql
CREATE INDEX CONCURRENTLY users_display_name_trgm_idx
  ON users
  USING gin (display_name gin_trgm_ops);
```

- `CONCURRENTLY` avoids a long lock; the migration runs out-of-band.
- `pg_trgm` extension is already enabled in prod (see infra repo).

### Query

```sql
SELECT id, handle, display_name
FROM users
WHERE is_public = true
  AND display_name % $1            -- trigram similarity
ORDER BY similarity(display_name, $1) DESC
LIMIT 20;
```

## API

```
GET /api/v1/users/search?q=<query>

200 OK
{
  "results": [
    { "id": "...", "handle": "...", "displayName": "..." }
  ]
}

400 — q missing or length < 3
401 — unauthenticated
429 — rate-limited
```

Rate limit: 60 req/min per user.

## Observability

- Metric `search.latency.p50` / `p95` — histogram, label `route=user-search`.
- Metric `search.results.empty` — counter, sampled.
- Log fields: `user_id`, `query_length` (not the query itself), `result_count`,
  `latency_ms`.

**Privacy**: never log the raw query string; it can contain PII.

## Alternatives considered

1. **Elasticsearch cluster**. Rejected: introduces a new datastore + ops
   burden for a feature that fits inside Postgres for the foreseeable
   future. Revisit if QPS > 500.
2. **Materialised view refreshed every minute**. Rejected: introduces
   staleness with no clear win over the trigram index on the live table.
3. **Application-side filtering after `LIKE 'q%'`**. Rejected: misses
   matches in the middle of the display name (e.g. "John Doe" for query
   "doe").

## Risks

- **Index build time** on the production `users` table (≈ 12M rows). Run
  during low-traffic window; `CONCURRENTLY` mitigates locking.
- **Result quality** for very short queries (3 chars). Mitigation:
  rate limit + frontend debounce.

## TODO(human)

- TODO(human): confirm `pg_trgm` is enabled in the staging cluster too.
- TODO(human): decide whether to expose `displayName` exactly as stored
  or to highlight match spans.
