# Execution Plan: close-employee-card-editor-flow

## Contract

- Goal: close the employee-source, employee-card creation, and public-contact visibility loop.
- Mode: Spec-Strict, direct implementation; shared API contract is frozen before UI work.
- Non-goals: generic free canvas, template propagation, port/auth changes and destructive duplicate cleanup.
- Run: `20260805-employee-card-closure`.

## Progress

- [x] 1. Freeze member/contact and employee-card API contracts with focused tests.
- [x] 2. Implement service-side owner selection, single-card guard, and public visibility projection.
- [x] 3. Implement enterprise-employee naming and employee-card create/edit UX.
- [ ] 4. Sync OpenAPI and run focused API/UI/build/browser verification.

## Verification

- API success/denial tests for member source, owner identity, duplicate card and visibility.
- Admin focused tests and production build.
- Public-card tests/build plus browser create/save/reload/public smoke.

## Failure / Rollback

- Do not delete or merge existing employee cards.
- Preserve absent old visibility settings as legacy-public behavior until a card is saved.
- On UI regression, retain the contract and restore only the editor presentation layer.
