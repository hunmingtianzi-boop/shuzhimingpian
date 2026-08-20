# Eval Contract: built-in card plugin platform

## Hard Gates

1. A new sample card-block plugin can be registered without adding a case to a core frontend renderer switch or a field set to the centralized backend block model.
2. TypeScript and Python validate the same plugin manifest, v2 block and Render Plan fixtures with identical pass/fail outcomes.
3. Every newly published plugin block references an available exact plugin version, valid config and explicitly granted capabilities.
4. Existing v1 drafts and published snapshots remain readable through deterministic compatibility projection; a failed migration or publish preserves the current public snapshot.
5. Identity remains exactly one, visible and non-disableable; FAQ cannot resolve unpublished/cross-company knowledge; unsafe actions never reach the public Render Plan.
6. Company disablement, platform kill switch and missing optional plugin all produce the specified safe behavior and an audit/telemetry record.
7. The public H5 requests only chunks for plugins present in its Render Plan and stays within the agreed entry-bundle and interaction budgets.
8. Focused API, admin, card-web, contract, production-build and real mobile-browser verification all pass with no relevant console error.
9. Platform operators can assign a plan and override each optional feature, while required kernel features remain enabled and updates use optimistic company versions.
10. Enterprise navigation, direct routes, public card output and protected APIs resolve the same effective feature state; direct requests receive `FEATURE_NOT_ENTITLED` when disabled.
11. A plugin whose commercial feature is disabled cannot be enabled or published even if its installation record and capability grants otherwise allow it.

## Required Evidence

- Shared fixture parity report for manifest/config/Render Plan validation.
- Registry inventory showing identity, FAQ and action contributions on all required runtime surfaces.
- API receipts for grants, publish version pin, stale write, cross-company denial, enterprise disable and platform kill/restore.
- Commercial receipts for starter/professional/enterprise defaults, per-company open/close overrides, stale update, menu hiding and direct API/public denial.
- Browser screenshots and request trace for draft edit, publish, public rendering, action interaction, optional-plugin kill and restore.
- Legacy equivalence receipt for representative enterprise and employee cards.
- Bundle report proving an unused sample plugin chunk is not requested.
- Independent read-only checker verdict covering all hard gates.

## Suggested Commands

- `corepack pnpm contracts:check && corepack pnpm contracts:validate`
- focused API plugin/manifest/template/public tests through the repository Python runner
- focused admin plugin registry/editor tests and `corepack pnpm admin:build`
- focused card-web plugin renderer/compatibility tests and `corepack pnpm web:build`
- targeted Playwright runtime scenario for pilot edit, publish, public interaction and kill/restore

## Stop Rule

Do not claim completion while any hard gate lacks current direct evidence. Passing unit tests alone is insufficient without a real published pilot-card browser flow, cross-tenant negative proof and rollback rehearsal.
