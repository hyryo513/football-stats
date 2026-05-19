# /specs/

Kiro-style specifications. Each feature gets its own subdirectory containing
three files:

| File              | Purpose                                                |
| ----------------- | ------------------------------------------------------ |
| `requirements.md` | What the feature must do. User stories + acceptance.   |
| `design.md`       | How it will work. Architecture, data flow, trade-offs. |
| `tasks.md`        | Ordered task list with checkboxes; one PR per task.    |

## Layout

```
/specs/
  <feature-slug>/
    requirements.md
    design.md
    tasks.md
```

`<feature-slug>` is `kebab-case` and stable: it appears in commit trailers
(`Spec-Hash`) and branch names, so renaming is expensive.

## Required metadata

Every spec file starts with YAML frontmatter:

```yaml
---
id: <feature-slug>          # matches the directory name
title: <human-readable title>
status: draft | active | shipped | archived
owner: <team-or-handle>
created: YYYY-MM-DD
last-reviewed: YYYY-MM-DD
related-prompts: []         # paths under /prompts/, may be empty
related-tools: []           # paths under /tools/, may be empty
eval-ref: <path-under-/evals/-or-NONE>
---
```

## Conventions

- Specs are authored by humans **or** by agents proposing a feature; either
  way a human must mark `status: active` before implementation begins.
- `requirements.md` uses the **EARS** notation for acceptance criteria where
  practical (`WHEN <trigger>, THE SYSTEM SHALL <response>`).
- `design.md` includes at least one "Alternatives considered" section.
- `tasks.md` is a checklist; each item should map cleanly to a PR ≤500 lines.
- Update `last-reviewed` whenever a human re-reads and re-confirms a spec.

## Linking

- Reference a spec from a commit via the `Spec-Hash` trailer.
- Reference a spec from a prompt or tool via its `id`.

See [`example-feature/`](./example-feature/) for a template.
