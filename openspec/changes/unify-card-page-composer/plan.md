# Implementation Plan: unify-card-page-composer

## Contract

- Current change: `unify-card-page-composer`.
- Frozen user rule: the `identity` block is data-bound to enterprise or enterprise-employee information, is positionable through convenient drag handles, and is visible by default and cannot be hidden.
- Non-goals: no freeform visual/CSS builder, no catalogue snapshots, no change to system privacy or global route policy.
- Execution mode: Spec-Strict, direct. The shared page-block contract must be complete before renderer/editor work begins.
- Runtime: retain research-worktree API `38101` and admin Vite `4174`; no port contract change is planned.

## Progress

- [x] 1. Complete WP1 in `tasks.md`: contract, validation, compatibility and backend/API tests.
- [x] 2. Complete WP2 in `tasks.md`: public ordered renderer, identity projection, reference blocks and directory derivation.
- [x] 3. Complete WP3 in `tasks.md`: dnd-kit editor, real-page canvas, synchronized selection/order and real full preview.
- [x] 4. Complete WP4 in `tasks.md`: creation flow, visual inheritance, tests, builds and browser proof.

## Evidence Gate

| Acceptance criterion | Direct evidence |
| --- | --- |
| One composition changes every surface | API response plus editor/canvas/public-card browser screenshot after a drag and publish |
| Identity is movable but non-hideable | validation test and drag interaction test |
| Catalogue content is not dead/static | public case/product action opens existing detail route; unavailable item fallback test |
| Directory is derived | reorder and directory-target tests plus browser scroll observation |
| Preview is a real page | browser opens public route and performs a visitor interaction |
| No regression | focused API/UI tests, admin/card-web typechecks and production builds |

## Failure / Rollback

- Never destructively rewrite legacy card data. A missing new composition uses the compatibility builder.
- A draft/publish validation failure preserves the current published snapshot.
- If the new renderer causes a public regression, disable the new composition projection and retain existing snapshots until the compatibility issue is fixed.

## Run Records

- Harness run: `.codex/harness/runs/2026-08-06-统一名片页面编排器实施计划/`.
- Implementation receipts, browser screenshots and final proof will be stored under `openspec/changes/unify-card-page-composer/runs/` when execution starts.
