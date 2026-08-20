# Execution Plan: introduce-card-plugin-platform

## Contract

- Goal: establish a safe built-in plugin kernel plus a server-authoritative commercial entitlement layer, proved with FAQ and action-collection card-block plugins.
- Change: `introduce-card-plugin-platform`.
- Mode: Spec-Strict; contract and compatibility gates must pass before UI/runtime migration.
- Scope boundary: trusted build-time plugins only; no remote code, marketplace or arbitrary plugin migrations.
- Primary risks: published-snapshot compatibility, cross-language contract drift, tenant authorization and public-card performance.

## Progress

- [ ] 1. Freeze plugin manifest, host API, capability grant and v2 page-block contracts.
- [ ] 2. Implement registries, startup/build validation and deterministic v1 compatibility projection.
- [ ] 3. Migrate identity, FAQ and action collection behind the plugin host with shared fixtures.
- [ ] 4. Add company enablement, permission grants, publish pinning, audit and emergency kill switch.
- [x] 5. Add commercial feature catalog, three plan defaults, company overrides, platform controls, enterprise navigation gating and server Feature Gates.
- [ ] 6. Enable the plugin path for a pilot company and complete API/UI/browser/security/performance evidence.

## Delivery Sequence

1. WP1 must land first because every other surface consumes the same plugin identity and serialized contract.
2. WP2 and WP3 may proceed in parallel only after shared cross-language fixtures pass.
3. WP4 starts after publish normalization is stable; it must not introduce code download or runtime package installation.
4. WP5 establishes commercial entitlements before pilot activation so plugin installation cannot bypass paid capability boundaries.
5. WP6 turns the feature flag on only for explicit pilot companies and expands after all hard gates pass.

## Failure / Rollback

- Existing v1 drafts and published snapshots remain authoritative until their card is explicitly saved/published through v2.
- A missing registry entry, invalid grant or incompatible version fails draft publication without changing the current public snapshot.
- Public optional plugins degrade by omission; identity uses a host-owned safe fallback.
- Rollback disables the plugin host and v2 writes but preserves plugin release, installation and audit records.
- No referenced plugin release is deleted during rollback.

## Evidence

- Contract: shared manifest fixtures validated by TypeScript and Pydantic tests.
- API: registry collision, invalid config, permission denial, cross-company resource, stale publish, version pin and kill-switch tests.
- Commercial: plan resolution, required capability, feature override, stale company version, navigation and direct API denial tests.
- UI: plugin editor discovery, enablement status, lazy renderer, missing-plugin fallback and legacy-card equivalence tests.
- Browser: edit FAQ/actions, publish, visit mobile card, exercise actions, kill and restore one optional plugin with no relevant console errors.
- Performance: public-card entry bundle regression within agreed budget; unused plugin chunks are not requested.
