# CLAUDE.md

Operating manual for AI agents (Claude Code, Kiro, etc.) working in this
repository. Human contributors should follow it too. Read this file in full
before making changes.

This repository is an **AI-enabled SDLC prototype**. Most artifacts here are
designed to be authored or modified by AI agents, then reviewed by humans.

---

## 1. Repo conventions

### Layout

| Path                  | Purpose                                    |
| --------------------- | ------------------------------------------ |
| `/specs/`             | Kiro-style specs (requirements/design/tasks) |
| `/prompts/`           | Versioned prompt templates                 |
| `/mcp/`               | MCP server definitions                     |
| `/tools/`             | Tool definitions / schemas                 |
| `/evals/`             | Eval suites + datasets                     |
| `/.kiro/steering/`    | Kiro steering files (mirrors this doc)     |
| `/.github/workflows/` | CI / agent automation                      |

Each directory above contains a `README.md` describing its purpose and the
required metadata fields for artifacts inside it. Read the directory README
before adding a new artifact.

### Code style

- **YAML**: 2-space indent, no tabs, keys in `kebab-case` unless an upstream
  schema (e.g. GitHub Actions) requires otherwise.
- **JSON**: 2-space indent, trailing newline, keys in `camelCase` unless an
  external schema (e.g. JSON Schema, MCP) requires otherwise.
- **Markdown**: ATX headers (`#`), wrap prose at ~80 columns, fenced code
  blocks with language tags.
- **Filenames**: `kebab-case` for everything except files that tools require
  to be uppercased (`README.md`, `CLAUDE.md`).

### Test patterns

- Application code is intentionally out of scope for this prototype phase, so
  no language-level test framework is wired up yet. When code lands, tests
  live next to the package they cover (`<package>/tests/` or `tests/<package>/`)
  and follow the AAA pattern (Arrange / Act / Assert).
- Eval suites under `/evals/` are the test surface for prompts, agents, and
  MCP tools. Every prompt or tool change must reference an eval (`eval-ref`).

### Branch naming

- `claude/<short-slug>-<id>` — branches authored by Claude Code agents.
- `kiro/<short-slug>-<id>` — branches authored by Kiro agents.
- `human/<short-slug>` — branches authored by humans.
- `feat/<slug>`, `fix/<slug>`, `chore/<slug>` — short-lived branches for
  any author when the agent prefix is not relevant.

Branch off `main`. Open PRs against `main`.

---

## 2. Agent constraints

AI agents working in this repo **MUST NOT**:

1. **Touch secrets.** Never read, write, log, or echo the contents of files
   matching `*.env`, `*.pem`, `*.key`, `*credentials*`, or anything inside a
   directory named `secrets/`. Reference secrets only via
   `${{ secrets.NAME }}` in workflows.
2. **Modify CI without review.** Changes under `/.github/workflows/`,
   `/.github/actions/`, or `/mcp/` and `/tools/` are tier `risk:high` and
   require a human reviewer. Agents may *propose* changes but must not
   self-approve or auto-merge them.
3. **Open oversized PRs.** PRs larger than **500 changed lines** (additions +
   deletions, excluding lockfiles and generated files) require an explicit
   justification in the PR body under a `## Size justification` heading.
   Prefer splitting into smaller PRs.
4. **Bypass review for high-risk paths.** Any path matched by `risk-tier.yml`
   as `risk:high` must have a human reviewer. Auto-merge is restricted to
   `risk:low` PRs from approved bot authors.
5. **Invent prompt or tool versions.** When updating a versioned artifact,
   bump the `version` field explicitly; never reuse a version string.
6. **Skip hooks or bypass signing** unless a human has explicitly asked for it
   in the conversation triggering the change.
7. **Push to `main` directly.** Always open a PR.

Agents **MAY**:

- Read any non-secret file in the repo.
- Create new artifacts under `/specs/`, `/prompts/`, `/evals/`.
- Edit application code on a feature branch with a paired spec.
- Leave `TODO(human):` comments anywhere an ambiguity needs human input.

---

## 3. Commit format

Every commit (agent-authored or human-authored) must end with the following
git trailers, separated from the body by a blank line:

```
Spec-Hash: <sha-of-related-spec-or-NONE>
Agent: <agent-name-or-human>
Model: <model-family-id-or-NA>
```

Rules:

- `Spec-Hash` — short SHA of the spec file driving this change, or `NONE` if
  the change is not spec-driven (chores, docs, dependency bumps). Compute with
  `git hash-object <spec-file>` and take the first 12 characters.
- `Agent` — one of `claude-code`, `kiro-agent`, `human`, or a named custom
  agent. Lowercase, hyphenated.
- `Model` — model family identifier (e.g. `claude-opus-4`, `claude-sonnet-4`)
  or `NA` for human-authored commits. Do **not** include exact patched
  versions; the family is enough for audit.

Subject line: imperative mood, ≤72 characters, lowercase type prefix
(`feat:`, `fix:`, `chore:`, `prototype:`, `docs:`, `refactor:`).

Example:

```
feat: add user-search spec and stub endpoint

Closes the requirements/design/tasks loop for the example feature.

Spec-Hash: 8c4a1f2d3b9e
Agent: claude-code
Model: claude-opus-4
```

---

## 4. Pointers

- **Specs** → [`/specs/README.md`](./specs/README.md)
- **Prompts** → [`/prompts/README.md`](./prompts/README.md)
- **MCP servers** → [`/mcp/README.md`](./mcp/README.md)
- **Tools** → [`/tools/README.md`](./tools/README.md)
- **Evals** → [`/evals/README.md`](./evals/README.md)
- **Kiro steering (mirror of this file)** →
  [`/.kiro/steering/conventions.md`](./.kiro/steering/conventions.md)
