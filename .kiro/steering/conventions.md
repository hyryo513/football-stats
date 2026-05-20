---
inclusion: always
description: >
  Repo-wide conventions, agent constraints, and commit format. Mirrors
  /CLAUDE.md so Kiro agents pick up the same rules without an extra read.
owner: platform
last-reviewed: 2026-05-19
---

# Conventions (Kiro steering)

This file is the Kiro-format mirror of [`/CLAUDE.md`](../../CLAUDE.md). When
the two disagree, **`/CLAUDE.md` is authoritative** — fix this file to match.

## Repo layout

- `/specs/` — Kiro-style specs (requirements / design / tasks).
- `/prompts/` — versioned prompt templates.
- `/mcp/` — MCP server definitions (contracts).
- `/services/` — MCP server implementations (one directory per server).
- `/tools/` — tool schemas.
- `/evals/` — eval suites and datasets.
- `/.kiro/steering/` — steering files (this directory).
- `/.kiro/settings/` — Kiro client config (MCP servers, etc.).
- `/.github/workflows/` — CI and agent automation.

Each directory has a `README.md` describing required metadata for artifacts
inside. Read it before adding a new artifact.

## Code style

- YAML: 2-space indent, `kebab-case` keys unless an upstream schema requires
  otherwise.
- JSON: 2-space indent, `camelCase` keys unless an external schema requires
  otherwise.
- Markdown: ATX headers, ~80-column wrap, fenced code blocks with language
  tags.
- Filenames: `kebab-case` except where tools require uppercase
  (`README.md`, `CLAUDE.md`).

## Test patterns

- Application tests live next to the package they cover; AAA pattern.
- Prompts, agents, and MCP tools are tested via eval suites under `/evals/`.
- Every prompt or tool change must reference an eval (`eval-ref`).

## Branch naming

- `claude/<slug>-<id>` for Claude Code agents.
- `kiro/<slug>-<id>` for Kiro agents.
- `human/<slug>` for humans.
- `feat/<slug>`, `fix/<slug>`, `chore/<slug>` when the agent prefix is not
  relevant.

Branch off `main`. Open PRs against `main`.

## Agent constraints

Agents MUST NOT:

1. Touch secrets. No reading, writing, logging, or echoing of `*.env`,
   `*.pem`, `*.key`, `*credentials*`, or anything under a `secrets/`
   directory. Reference secrets only via `${{ secrets.NAME }}`.
2. Modify `/.github/workflows/`, `/.github/actions/`, `/mcp/`, `/tools/`,
   or any `Dockerfile` without human review. Agents may propose changes;
   humans approve them.
3. Open PRs larger than 500 changed lines (excluding lockfiles and generated
   files) without an explicit `## Size justification` section in the PR body.
4. Bypass review for paths labelled `risk:high` by `risk-tier.yml`.
5. Reuse a `version` string when updating a versioned artifact.
6. Skip hooks or bypass signing unless a human explicitly requested it.
7. Push directly to `main`.

Agents MAY:

- Read any non-secret file.
- Create artifacts under `/specs/`, `/prompts/`, `/evals/`.
- Edit application code on a feature branch with a paired spec.
- Leave `TODO(human):` comments when an ambiguity needs human input.

## Commit format

Every commit must end with these git trailers (blank line above):

```
Spec-Hash: <12-char-sha-of-spec-or-NONE>
Agent: <agent-name-or-human>
Model: <model-family-id-or-NA>
```

- Compute `Spec-Hash` with `git hash-object <spec-file>` and take the first
  12 characters. Use `NONE` for non-spec-driven changes.
- `Agent` examples: `claude-code`, `kiro-agent`, `human`.
- `Model` is a family identifier (`claude-opus-4`, `claude-sonnet-4`) or
  `NA` for humans. No exact patched versions.

Subject line: imperative mood, ≤72 chars, lowercase type prefix.
