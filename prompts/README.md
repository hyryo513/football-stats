# /prompts/

Versioned prompt templates. One prompt per file.

## File naming

`<id>.prompt.md` where `<id>` is `kebab-case` and matches the `id` in the
frontmatter (e.g. `code-review.prompt.md`).

## Required metadata

Every prompt file starts with YAML frontmatter:

```yaml
---
id: <kebab-case-id>          # stable identifier, matches filename
version: <semver>            # bump on every change; never reuse
model: <model-family-id>     # e.g. claude-sonnet-4, claude-opus-4
owner: <team-or-handle>
last-reviewed: YYYY-MM-DD
eval-ref: <path-under-/evals/>   # required; no eval => no prompt
description: <one-line summary>
inputs:                      # named template variables
  - name: <var-name>
    description: <what-it-is>
    required: true | false
---
```

## Body

The body is the prompt template itself. Use `{{var-name}}` for substitution.
Keep the template self-contained: include the role, task, constraints, and
output format inline. Avoid runtime concatenation with code-side strings.

## Conventions

- **Versioning**: `MAJOR.MINOR.PATCH`. Bump MAJOR on behavior-changing edits,
  MINOR on additions, PATCH on typo / wording polish. Never reuse a version.
- **Eval coupling**: Every prompt must reference an eval suite. A prompt
  without `eval-ref` will be rejected by review.
- **Model pinning**: `model` is the **family** identifier (`claude-opus-4`),
  not an exact patched version. The runtime picks the latest in that family.
- **No secrets**: Prompts must not contain credentials or API keys.

See [`code-review.prompt.md`](./code-review.prompt.md) for a template.
