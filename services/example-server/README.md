# services/example-server

Minimal MCP server implementing the `example-tool` echo contract from
[`/tools/example-tool.json`](../../tools/example-tool.json).

Published as a container image to
`ghcr.io/<owner>/example-server:<version>` by
[`.github/workflows/publish-mcp-server.yml`](../../.github/workflows/publish-mcp-server.yml)
on every merge to `main` that touches `services/**` or `mcp/**`.

## Run locally

```bash
docker run --rm -i ghcr.io/<owner>/example-server:0.2.0
```

Then send an MCP `tools/call` JSON-RPC frame on stdin; the response
appears on stdout.

## Develop locally

```bash
cd services/example-server
python -m venv .venv && . .venv/bin/activate
pip install -e .
example-mcp-server
```

## How Kiro consumes it

`.kiro/settings/mcp.json` at the repo root points Kiro at the published
image. After the publish workflow promotes a new tag, bump the tag in
that file (manual for the prototype; see
[`/specs/publish-mcp-server/design.md`](../../specs/publish-mcp-server/design.md)).
