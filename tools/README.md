# /tools/

Tool schemas. One JSON file per tool. Schemas follow the
[JSON Schema](https://json-schema.org) Draft 2020-12 dialect for `inputSchema`.

Files under this directory are tier **`risk:high`** — changes are gated by
human review.

## File naming

`<name>.json` where `<name>` is `kebab-case` and matches the `name` field
inside (e.g. `web-search.json`).

## Required fields

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "name": "<kebab-case-name>",
  "version": "<semver>",
  "description": "<one-line summary>",
  "owner": "<team-or-handle>",
  "lastReviewed": "YYYY-MM-DD",
  "inputSchema": { ... JSON Schema object ... },
  "outputSchema": { ... JSON Schema object ... },
  "permissionScope": {
    "filesystem": { "read": [], "write": [] },
    "network":    { "allowHosts": [] },
    "secrets":    [],
    "sideEffects": "none | read-only | mutating"
  },
  "evalRef": "<path-under-/evals/>"
}
```

## Conventions

- **Schemas are contracts**: a backwards-incompatible change to `inputSchema`
  or `outputSchema` requires a MAJOR version bump.
- **`sideEffects`** is the headline safety field. `mutating` tools are
  ineligible for auto-approval and must appear in agent allow-lists
  explicitly.
- **No business logic**: this directory holds *schemas*, not implementations.
  Implementations live with the MCP server that exposes the tool.
- **Eval required**: every tool needs an eval (`evalRef`).

See [`example-tool.json`](./example-tool.json) for a template.
