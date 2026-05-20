---
id: publish-mcp-server
title: Publish MCP server to GitHub Packages and consume it from Kiro — design
status: draft
owner: "TODO(human): assign-owner"
created: 2026-05-19
last-reviewed: 2026-05-19
related-prompts: []
related-tools:
  - tools/example-tool.json
eval-ref: evals/publish-mcp-server.yaml
---

# Design — publish MCP server

## Overview

A new directory `/services/<name>/` holds MCP server implementations.
A new workflow `.github/workflows/publish-mcp-server.yml` builds them
into container images and pushes them to `ghcr.io`. `/mcp/<name>.yaml`
remains the *contract* (risk:high); `/services/<name>/` is the
*implementation*. `.kiro/settings/mcp.json` is the *consumption pointer*
Kiro reads.

```
            +--------- developer in Kiro -----------+
            |                                       |
            v                                       |
[ /specs/<feature>/ ] --commit--+                   |
[ /services/<name>/ ]           |                   |
[ /mcp/<name>.yaml ]            |                   |
                                |                   |
                                v                   |
                          PR + GHA gates            |
                                |                   |
                                v                   |
                     publish-mcp-server.yml         |
                                |                   |
                                v                   |
                    ghcr.io/<owner>/<name>:<tag>    |
                                |                   |
                                v                   |
                  .kiro/settings/mcp.json points    |
                  Kiro at the image --- docker run -+
```

## Architecture

### Source layout

```
/services/
  <server-name>/
    Dockerfile
    pyproject.toml
    src/<package>/__main__.py
    README.md
    .dockerignore
/mcp/
  <server-name>.yaml          # contract; references ghcr.io image
.kiro/settings/mcp.json        # consumption pointer
```

### Tag strategy

`mcp/<name>.yaml`'s `version` field is the source of truth. The publish
workflow reads it and pushes three tags:

- `:<version>` — primary semver tag.
- `:sha-<commit>` — immutable audit tag.
- `:latest` — convenience; **not** referenced by `.kiro/settings/mcp.json`.

### Version propagation

For this prototype, propagation is **manual**: the same PR that bumps
`version` in `mcp/<name>.yaml` must also update the tag inside
`.kiro/settings/mcp.json`. A follow-up `verify-manifests.yml` CI check
that diffs the two and a `kiro-agent[bot]`-authored auto-bump PR are
both deferred (see "Deferred" below).

### Registry visibility

The package is created public on first push. The workflow calls
`PATCH /user/packages/container/<name>/visibility` (or the org
equivalent) once; the call is idempotent.

### Consumption from Kiro

`.kiro/settings/mcp.json` uses the widely-adopted `mcpServers` shape:

```json
{
  "mcpServers": {
    "example-server": {
      "command": "docker",
      "args": ["run", "--rm", "-i", "ghcr.io/<owner>/example-server:0.2.0"],
      "env": {},
      "disabled": false,
      "autoApprove": []
    }
  }
}
```

`TODO(human):` confirm Kiro's actual config path and schema.

## Alternatives considered

1. **npm via GitHub Packages.** Rejected. Forces a JS-only runtime
   contract before any real server exists, and consumers need `.npmrc`
   + scope configuration. ghcr.io is registry-agnostic on the consumer
   side (just `docker run`).
2. **PyPI via GitHub Packages.** Rejected. Same coupling issue. Twine +
   token setup is heavier than `docker/login-action`.
3. **Plain GitHub Release assets** (tarballs / wheels attached to a
   tag). Rejected. Not a package; Kiro would have to fetch + extract +
   exec, which is far from "developer never leaves the editor".
4. **No registry — Kiro builds locally on each consume.** Rejected.
   Defeats the "delivered code artifact" requirement and makes
   reproducibility worse, not better.

## Risks

- **Registry visibility flip fails silently.** Mitigation: the
  visibility step is idempotent and the workflow log will show the API
  response. A follow-up `verify-package-visibility` check could gate
  this; deferred.
- **Base-image CVE in `python:3.12-slim`.** Mitigation: pin to a digest
  and add Dependabot in a follow-up PR.
- **Image tag and Kiro manifest drift.** Mitigation: a follow-up
  `verify-manifests.yml` CI step. For now, drift is detected only on
  next consume.

## Deferred (explicitly out of scope)

- Image signing (cosign keyless / OIDC).
- SLSA provenance attestations and SBOM.
- Multi-architecture builds.
- Image-digest pinning in `mcp/<name>.yaml`.
- `verify-manifests.yml` CI gate.
- `kiro-agent[bot]` auto-bump PR after publish.
- Eval-runner CLI implementation.
- Dependabot for base images and action versions.

## TODO(human)

- TODO(human): confirm `python:3.12-slim` digest pin at PR time.
- TODO(human): confirm Kiro MCP-config path and schema.
- TODO(human): decide whether the visibility flip should target a user
  or an org endpoint (`/user/packages/...` vs `/orgs/<org>/packages/...`).
