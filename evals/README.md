# /evals/

Eval suites and datasets. An eval is the test surface for any AI-native
artifact — prompts, agents, MCP tools. Every prompt or tool must reference
an eval.

## File naming

`<id>.yaml` for the suite definition. Companion datasets live in a
sibling directory `<id>.data/` or in a single `<id>.jsonl` file.

## Required fields

```yaml
id: <kebab-case-id>
version: <semver>
description: <one-line summary>
owner: <team-or-handle>
last-reviewed: YYYY-MM-DD

# What this suite evaluates. Exactly one of prompt / tool / agent / image
# must be set. `image` runs the eval against a published container image
# (typically built by publish-mcp-server.yml) and exercises whatever MCP
# tool-surface it exposes; pair it with `tool` to constrain the contract.
target:
  prompt: <path-under-/prompts/>      # OR
  tool:   <path-under-/tools/>        # OR
  agent:  <agent-id>                  # OR
  image:  <registry>/<name>:<tag>     # e.g. ghcr.io/owner/example-server:0.2.0

# How runs are scored.
metrics:
  - name: <metric-name>
    type: exact-match | regex | llm-judge | numeric | custom
    weight: <0.0..1.0>             # weights across metrics sum to 1.0

# Pass/fail bar for CI.
success-criteria:
  min-score: <0.0..1.0>
  min-pass-rate: <0.0..1.0>        # fraction of cases that must pass

# Test cases (inline) or pointer to dataset.
cases: []                          # OR
dataset: <id>.jsonl

# Baseline scores from the most recent run on `main`.
baseline:
  score: <0.0..1.0>
  pass-rate: <0.0..1.0>
  run-date: YYYY-MM-DD
  run-id: <ci-run-id-or-NONE>
```

## Conventions

- **Reproducibility**: every case is deterministic given the prompt + inputs.
  Stochastic checks (e.g. LLM judges) must include `temperature: 0` and a
  fixed `seed` if supported.
- **Regression gate**: PRs touching a prompt or tool re-run the referenced
  eval. Score drops below `baseline.score - 0.02` block the PR.
- **Bias the dataset**: include negative and edge cases, not just happy path.
- **PII**: real user data never goes in `cases` or `dataset`. Use synthetic
  or fully anonymised data.

See [`example-eval.yaml`](./example-eval.yaml) for a template.
