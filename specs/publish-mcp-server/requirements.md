---
id: publish-mcp-server
title: Publish MCP server to GitHub Packages and consume it from Kiro
status: draft
owner: "TODO(human): assign-owner"
created: 2026-05-19
last-reviewed: 2026-05-19
related-prompts: []
related-tools:
  - tools/example-tool.json
eval-ref: evals/publish-mcp-server.yaml
---

# Requirements — publish MCP server

## Background

The foundation PR introduced the directory structure for AI-native
artifacts but did not deliver any. There is no path today for a developer
working in Kiro to take an MCP server idea from "spec" to "running
locally inside my editor" without leaving Kiro to run shell commands.

This change closes that loop by:

1. Adding a real (minimal) MCP server under `/services/example-server/`.
2. Building it as a container image and publishing it to
   `ghcr.io/<owner>/example-server` on every merge to `main`.
3. Pointing Kiro at the published image via `.kiro/settings/mcp.json`.

The published image is the *deliverable*; everything else is plumbing.

## User stories

- **US-1** — As a developer in Kiro, I want to describe a new MCP
  capability in a spec and have it published as a container image
  without leaving the editor, so that the SDLC loop stays inside one
  surface.
- **US-2** — As a developer in Kiro, I want the published image to
  appear as an MCP server I can call from chat, so that I can consume
  what I just shipped.
- **US-3** — As a reviewer, I want any change to a `Dockerfile` to be
  labelled `risk:high` so it cannot bypass human review.

## Acceptance criteria (EARS)

- **AC-1** — WHEN a PR that changes `services/**` or `mcp/**` merges to
  `main`, THE SYSTEM SHALL build and push a container image to
  `ghcr.io/<owner>/<server-name>` tagged with both the `version` from
  `mcp/<server-name>.yaml` and `sha-<commit>`.
- **AC-2** — WHEN the first image for a server is pushed, THE SYSTEM
  SHALL mark the GitHub Packages container as **public**.
- **AC-3** — WHEN the `version` field of `mcp/<server-name>.yaml` is
  unchanged from a prior release, THE SYSTEM SHALL still publish a fresh
  `sha-<commit>` tag but SHALL NOT overwrite the immutable semver tag's
  digest if it already exists.
- **AC-4** — WHEN any file matching `**/Dockerfile` changes, THE
  `risk-tier` workflow SHALL label the PR `risk:high`.
- **AC-5** — WHILE `.kiro/settings/mcp.json` references
  `ghcr.io/<owner>/example-server:<tag>`, THE Kiro client SHALL be able
  to invoke the `example-tool` defined in `tools/example-tool.json` via
  a `docker run -i` of that image.

## Non-goals

- Image signing (cosign / SLSA provenance) — deferred.
- Multi-architecture builds — `linux/amd64` only.
- An automated PR that bumps `.kiro/settings/mcp.json` after publish —
  deferred until the `kiro-agent[bot]` GitHub App identity is settled.
- Eval-runner CLI — referenced as a placeholder step only.

## Open questions

- TODO(human): confirm Kiro's MCP-config exact path
  (`.kiro/settings/mcp.json` vs `.kiro/mcp.json`) and whether Kiro
  auto-reloads on file change.
- TODO(human): confirm whether `kiro-agent[bot]` is a real GitHub App
  or aspirational. Auto-bump propagation depends on it.
