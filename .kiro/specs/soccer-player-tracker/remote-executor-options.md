# Remote Executor Options (Accuracy-First)

## Context

This document saves the approved hybrid cloud direction in the local repository and explores practical remote-executor options.

- Deployment model: hybrid (local UI/API, remote GPU analysis worker)
- Data policy: no persistent cloud storage (process and delete)
- Priority: preserve tracking/stat accuracy, then reduce runtime and keep maintenance manageable

## Saved Plan Snapshot

### Objective

Move compute-heavy analysis from local i9 CPU to cloud GPU while preserving current model behavior and avoiding persistent cloud video retention.

### Core phases

1. Add local-vs-remote execution boundary in `backend/main.py`.
2. Package stateless GPU worker for `tracker/analyzer/report_builder`.
3. Add secure one-time ingress and strict cleanup lifecycle.
4. Validate cloud parity vs local outputs before cutover.
5. Roll out behind feature flag, then switch default when quality and runtime targets are met.

### Success metrics

- Meaningful runtime reduction versus local CPU baseline.
- No regression in core stats outputs.
- Zero retained video artifacts after completion/failure.

## Remote Executor Options

### Option A: Single managed GPU VM + worker process

Best for starting quickly with low operational complexity.

- **How it works**
  - Run one worker service on a GPU VM.
  - Local API uploads video directly to worker ingress (or streams chunks), worker returns `StatsReport`.
  - Worker writes only to ephemeral disk and deletes files at completion/failure.
- **Pros**
  - Fastest path to production.
  - Easiest debugging and observability.
  - Lowest maintenance burden initially.
- **Cons**
  - Limited elasticity unless you manually scale.
  - Idle-cost risk if VM is always on.
- **Cost profile**
  - Predictable monthly baseline, can be optimized with schedule/auto-stop.
- **Accuracy risk**
  - Low, if model/version/thresholds match local baseline.

### Option B: Queue + autoscaled GPU workers (container service)

Best for variable load and growth after initial validation.

- **How it works**
  - Local API submits jobs to queue.
  - Autoscaled GPU workers pull jobs, process, return results.
  - Job payloads and temp files are ephemeral only; strict TTL cleanup.
- **Pros**
  - Better throughput and burst handling.
  - Better cost-efficiency at uneven demand.
  - Cleaner long-term scaling model.
- **Cons**
  - More moving parts (queue, orchestration, retries, dead-letter handling).
  - Higher maintenance and operational complexity.
- **Cost profile**
  - Lower idle cost, but more platform complexity cost.
- **Accuracy risk**
  - Low, if worker image is pinned and versioned.

### Option C: Kubernetes GPU cluster

Best only when team size and workload justify platform ownership.

- **How it works**
  - Dedicated k8s cluster with GPU node pools and internal job orchestration.
- **Pros**
  - Maximum control and portability.
  - Strong long-term scaling and multi-workload flexibility.
- **Cons**
  - Highest ops burden and maintenance.
  - Slowest time-to-value for current project size.
- **Cost profile**
  - Potentially efficient at high sustained scale; expensive in engineering time.
- **Accuracy risk**
  - Low in theory, but higher deployment complexity increases operational risk.

## Recommendation

Start with **Option A** now, designed so it can evolve to **Option B** without changing frontend contracts.

- Keep API contract stable (`/sessions`, `/progress`, report schema).
- Add `REMOTE_EXECUTOR_ENABLED` feature flag in local API.
- Define strict parity gate before defaulting cloud path:
  - exact/near-exact core stat comparison
  - tracking stability checks
  - runtime target checks

## Security and Data Handling Guardrails

- Do not persist source videos in cloud object storage.
- Use short-lived signed upload tokens and TLS only.
- Store only metadata logs (session id, durations, status, error class).
- Enforce forced cleanup on:
  - success
  - failure
  - cancellation
  - worker restart recovery (startup sweep of stale temp files)

## Initial Build Scope (2-3 iterations)

1. Extract executor interface in `backend/main.py` (`local` and `remote` implementations).
2. Build one stateless GPU worker container mirroring current local pipeline defaults.
3. Add remote job lifecycle endpoints and status polling/stream mapping.
4. Add parity benchmark script and acceptance thresholds.
5. Add docs in `README.md` and `.kiro` once parity passes.
