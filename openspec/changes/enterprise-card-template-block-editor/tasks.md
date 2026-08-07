# Stable Work Packages

## WP1 — Shared domain contract and migration

- Scope: introduce member profile fields and a versioned enterprise-template draft/published snapshot; preserve all existing card identifiers, RLS scopes and optimistic versions.
- Files: current-head migration, `models.py`, Pydantic schemas, API types and migration tests.
- Acceptance: existing enterprise cards obtain a valid compatible template; employee identity is owned by user/membership projection; malformed blocks and stale writes fail deterministically.
- Depends on: approved proposal/design/specs.

## WP2 — Template service and secure API

- Scope: normalize/validate controlled blocks, project draft/published templates, verify assets/video links/case references and expose edit/preview/publish operations.
- Files: catalog/public stores, admin/public routes, schemas, API tests.
- Acceptance: only current-company resources are allowed; published reads never see drafts; publish check reports missing fields; no public draft leak.
- Depends on: WP1.

## WP3 — Admin editor and identity-aware card form

- Scope: replace the enterprise fixed-field editor with a reusable block editor, basic settings inspector, mobile preview and publish readiness; make employee identity presentation read-only and member-sourced.
- Files: admin API/types, Cards page, new editor components/styles/tests.
- Acceptance: keyboard-accessible add/remove/reorder, upload images, enter approved video link, select existing cases, preview draft and publish.
- Depends on: WP2 contract.

## WP4 — Public renderer and AI projection

- Scope: render published enterprise template blocks in the existing mobile public experience; preserve AI/public-card contracts and hide unavailable references.
- Files: public store/API projection, card-web renderer/tests.
- Acceptance: published order matches preview, unavailable references degrade safely, employee cards use member identity projection.
- Depends on: WP2 and WP3 shared renderer contract.

## WP5 — Verification and compatibility

- Scope: focused backfill/migration, API, frontend, accessibility, mobile browser, publish/preview and scope tests; update OpenAPI when the contract changes.
- Acceptance: every spec scenario has current direct evidence and no existing card/public route regresses.
- Depends on: WP1–WP4.
