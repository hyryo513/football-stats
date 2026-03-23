# Superpowers Workflow (Spec to Code)

Use this checklist when implementing new features or major changes.

## A. Discovery

- Confirm the target requirements in `requirements.md`.
- Confirm architecture and interfaces in `design.md`.
- Confirm implementation scope/status in `tasks.md`.

## B. Plan Slice

- Define one vertical slice with clear user-visible value.
- List touched files (backend, frontend, tests, docs).
- Define acceptance checks before writing code.

## C. Implement

- Update schema/contracts first (`models`, request/response payloads).
- Update core logic (`tracker`, `analyzer`, orchestration).
- Update integration paths (`main.py`, `frontend/app.js`).

## D. Verify

- Validate behavior with unit/e2e tests.
- Check backward compatibility on existing endpoints.
- Confirm docs reflect the final behavior.

## E. Ship Readiness

- `README.md` matches real user flow.
- `.kiro` docs match implementation.
- `tasks.md` status is updated and accurate.

