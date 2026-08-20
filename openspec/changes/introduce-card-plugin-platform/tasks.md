# Stable Work Packages

## WP1 — Shared plugin and page-document contracts

- Scope: define manifest schema, host API version, plugin/contribution identity, capability declarations, v2 plugin block document and normalized Render Plan.
- Files: new shared contract/runtime packages, OpenAPI/JSON Schema artifacts, Pydantic request/response models and common fixture directory.
- Acceptance: TypeScript and Python accept/reject the same fixtures; IDs and versions are canonical; core block fields are separated from plugin config; identity invariants remain explicit.
- Depends on: approved proposal/design/specs.

## WP2 — Registry, discovery and compatibility host

- Scope: add frontend build-time discovery, backend explicit registry, duplicate/compatibility/parity validation, and deterministic v1 page-block adaptation.
- Files: card renderer registry, admin registry, API plugin host, build/startup checks and compatibility tests.
- Acceptance: an unknown or duplicate contribution fails deterministically; v1 documents remain readable; adding a test plugin requires no core render switch modification.
- Depends on: WP1.

## WP3 — Identity, FAQ and action sample plugins

- Scope: register identity as a required system contribution; move FAQ and action collection validation, defaults, editing, resolution and rendering into plugin implementations.
- Files: public/admin plugin modules, API plugin modules, shared fixtures and focused component/service tests.
- Acceptance: FAQ uses only published same-company knowledge; actions preserve URL/path/phone safety; both can be enabled independently; identity cannot be hidden, removed or disabled.
- Depends on: WP1 and WP2.

## WP4 — Tenant lifecycle, publish pinning and operations

- Scope: add platform plugin releases, company installations/grants, optimistic updates, audit events, publish-time version pinning, enterprise disablement and platform kill switch.
- Files: additive migration/model/store/API, admin enablement surface, public resolver and operations telemetry.
- Acceptance: disabled or ungranted plugins cannot be newly published; existing fixed snapshots remain stable after enterprise disablement; platform kill switch causes safe public degradation and is auditable.
- Depends on: WP2 and WP3 contracts.

## WP5 — Commercial plans, company feature entitlements and quotas

- Scope: add stable commercial feature and quota IDs, starter/professional/enterprise defaults, company overrides, contract metadata, platform editing, enterprise read model and server-authoritative Feature Gates.
- Files: entitlement resolver/schema/store/API, platform enterprise drawer, auth bootstrap, menu/direct-route guards, public/admin service gates and plugin-to-feature mapping.
- Acceptance: platform can change plan, individual features and quota overrides with optimistic concurrency; enterprise UI updates from effective rights; disabled functions return `FEATURE_NOT_ENTITLED`; a disabled paid feature cannot be re-enabled through plugin installation; quota values distinguish follow-plan, custom and unlimited states.
- Depends on: WP1 and WP4 identity/lifecycle contracts.

## WP6 — Pilot migration and full verification

- Scope: feature-flagged pilot activation, compatibility comparison, API/frontend/build tests, mobile browser proof, performance budget and security review.
- Acceptance: FAQ/action edit-to-public flow works on a pilot company; legacy cards are visually/functionally equivalent; unused chunks are not loaded; no cross-tenant or permission bypass is possible; rollback rehearsal succeeds.
- Depends on: WP1–WP5.

## Deferred Work — Not part of this change

- Dynamic third-party frontend or backend code installation.
- Module Federation, remote ESM, iframe plugin SDK and plugin marketplace.
- Generic admin route, FastAPI Router, Worker task, AI Provider or external integration contributions.
- Online payment, invoicing, trials, automatic renewal/expiry, coupons and third-party signing infrastructure.
