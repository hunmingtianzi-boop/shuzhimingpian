# Execution Plan: enterprise-card-template-block-editor

## Contract

- Goal: ship a usable, controlled enterprise-card template editor while making employee identity single-source.
- Change: `enterprise-card-template-block-editor`.
- Mode: Spec-Strict / sync-then-parallel after WP1/WP2 contract tests pass.
- Risk: data migration, public contract, RLS and mobile rendering.

## Progress

- [x] 1. Freeze typed template/member-profile contract and add migration/backfill tests.
- [x] 2. Implement service validation, draft/preview/publish API and public projections.
- [x] 3. Implement reusable admin block-editor workspace and identity-aware employee form.
- [x] 4. Implement public block renderer and AI-related section projection.
- [x] 5. Run focused API/UI tests, OpenAPI sync, mobile browser smoke and scope/security review.

## Failure / Rollback

- Migration must be additive and preserve existing public cards through a compatibility default.
- A failed or stale publish must leave the previous public snapshot untouched.
- No destructive rollback: disable new editor routes/projections first; retain template/member data.

## Evidence

- API: schema, migration, company-scope, stale-write, draft/public separation and media failure tests.
- UI: unit tests for block manipulation and member identity rendering; admin build.
- Browser: real 390px preview, publish, then public-card render with no console errors.

## Completion Evidence

- API non-integration test suite: PASS.
- Admin web: 34 files / 151 tests PASS; production build PASS.
- Card web: 18 files / 119 tests PASS; production build PASS.
- Ruff: PASS.
- OpenAPI: synchronized and valid (144 paths, 183 operations, 262 schemas).
- Browser: draft save, publish/republish, public rendering, case navigation and AI assistant opening PASS.
- Independent checker: PASS across AC1-AC5 after the employee business-summary projection and absolute-URL asset boundary fixes.
- Visual evidence: `output/playwright/enterprise-template-editor-desktop.png` and `output/playwright/enterprise-card-public-mobile-top.png`.
