---
id: publish-mcp-server
title: Publish MCP server to GitHub Packages and consume it from Kiro — tasks
status: draft
owner: "TODO(human): assign-owner"
created: 2026-05-19
last-reviewed: 2026-05-19
related-prompts: []
related-tools:
  - tools/example-tool.json
eval-ref: evals/publish-mcp-server.yaml
---

# Tasks — publish MCP server

Split across two PRs.

## PR A — service, contract, consumption manifest

- [x] **A-1** — Author `/specs/publish-mcp-server/` (requirements,
      design, tasks).
- [x] **A-2** — Add `/services/example-server/` source tree
      (`Dockerfile`, `pyproject.toml`, `src/example_server/__main__.py`,
      `README.md`, `.dockerignore`).
- [x] **A-3** — Bump `mcp/example-server.yaml` to `version: 0.2.0`; add
      `artifact:` block and `transport.image`.
- [x] **A-4** — Add `.kiro/settings/mcp.json` pointing at
      `ghcr.io/<owner>/example-server:0.2.0`.
- [x] **A-5** — Extend `risk-tier.yml` `HIGH_RISK_GLOBS` to include any
      `Dockerfile`.
- [x] **A-6** — Update `mcp/README.md`, `CLAUDE.md`, and
      `.kiro/steering/conventions.md` for the new `/services/` directory
      and the `artifact` block.

## PR B — publish workflow + eval

- [ ] **B-1** — Add `.github/workflows/publish-mcp-server.yml`.
- [ ] **B-2** — Add `evals/publish-mcp-server.yaml` targeting the
      published image, reusing the four cases from
      `evals/example-eval.yaml` plus an `image-pullable` case.
- [ ] **B-3** — Append `target.image` documentation to
      `evals/README.md`.

## Deferred (follow-up PRs)

- [ ] **D-1** — Implement the eval-runner CLI so the workflow's eval
      step is real, not a placeholder.
- [ ] **D-2** — Add `verify-manifests.yml` CI that diffs the version in
      `mcp/<name>.yaml` against the tag inside `.kiro/settings/mcp.json`.
- [ ] **D-3** — Wire a `kiro-agent[bot]` auto-bump PR after each
      successful publish.
- [ ] **D-4** — Image signing (cosign) + SLSA provenance + SBOM.
- [ ] **D-5** — Multi-arch builds (`linux/arm64`).
- [ ] **D-6** — Capture image digest from `docker/build-push-action`
      and pin it into `mcp/<name>.yaml.artifact.digest`.

## TODO(human)

- TODO(human): assign owners before promoting `status: draft` to
  `status: active`.
- TODO(human): confirm the visibility flip endpoint (`/user/...` vs
  `/orgs/<org>/...`) before B-1 lands.
