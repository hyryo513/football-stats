# /mcp/

[Model Context Protocol](https://modelcontextprotocol.io) server definitions.
One YAML file per server.

Files under this directory are tier **`risk:high`** — changes are gated by
human review. Agents may propose; humans approve.

## File naming

`<id>.yaml` where `<id>` is `kebab-case` and matches the `name` in the file
(e.g. `github-readonly.yaml`).

## Required fields

```yaml
name: <kebab-case-id>           # stable identifier, matches filename
version: <semver>               # bump on every change
description: <one-line summary>
owner: <team-or-handle>
last-reviewed: YYYY-MM-DD

transport:
  type: stdio | sse | http      # how the server is reached
  command: <executable>         # for stdio
  args: []                      # for stdio
  url: <https-url>              # for sse / http

tool-surface:                   # tools this server exposes
  - name: <tool-name>           # must exist under /tools/
    ref: tools/<tool-name>.json # path to the tool schema

permissions:                    # explicit allow-list; empty means none
  filesystem: { read: [], write: [] }
  network:    { allow-hosts: [] }
  secrets:    []                # named secrets the server may read
  env:        []                # env vars the server may read
```

## Conventions

- **Least privilege**: leave `permissions.*` empty by default. Add entries
  only with a justification comment.
- **No inline secrets**: reference secrets by *name* only. Resolution happens
  at runtime via the host's secret store.
- **Pin the version** in any consumer config (e.g. agent runtime).
- **Tool surface integrity**: every entry in `tool-surface` must point at a
  schema under `/tools/`. The eval CI verifies this.

See [`example-server.yaml`](./example-server.yaml) for a template.
