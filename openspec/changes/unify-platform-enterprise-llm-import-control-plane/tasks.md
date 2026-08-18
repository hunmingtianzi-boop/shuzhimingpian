# Stable Work Packages

## WP0 — Shared contracts and feature design delta

- Scope: freeze platform/enterprise/public route map, role/permission matrix, platform field allowlist, LLM profile contract, ordinary import invariants, document-assisted onboarding session/tenant boundaries, responsive rules and environment-specific runtime/base-path contract.
- Expected files: `apps/admin-web/src/routing.ts`, `apps/admin-web/src/auth/permissions.ts` or current equivalent, `apps/admin-web/src/api/types.ts`, `services/api/app/api/platform_schemas.py`, `.codex/harness/contracts/runtime-ports.json`, this change's `design.md` and specs.
- Acceptance: current `/c/admin/` base-path behavior and `/c/:slug` public route are preserved; enterprise roles cannot enter platform routes; the current ordinary `knowledge_import` API and limits are explicitly unchanged; platform onboarding can target only the temporary scope bound to its server-side session.
- Depends on: approved proposal/design/specs.
- Verification: route/permission contract review and current Compose/production configuration inspection.
- Rollback: contract-only changes can be reverted without data impact.

## WP1 — Platform LLM profile persistence and secure API

- Scope: add a clean migration from the current head for final multi-profile `chat_main` configuration; implement list/create/update/test/activate APIs, optimistic versions, unique active profile, encrypted key, masked reads, URL/SSRF safety and secret-free audit.
- Expected files: one or two new current-head migrations under `services/api/migrations/versions/`, `services/api/app/db/models.py`, `services/api/app/api/platform_schemas.py`, `services/api/app/api/routes/platform.py` or a narrowly split platform settings route, new `services/api/app/services/platform_llm_*.py`, focused API/security tests.
- Acceptance: zero profiles permit environment fallback; one or more profiles have exactly one active row; empty key updates preserve the profile key; stale writes return 409; enterprise roles receive 403; no response/log/audit contains the key.
- Depends on: WP0 field names and permission matrix.
- Verification: focused migration/model/route/security tests plus one bounded `/models` success or safe failure probe.
- Rollback: disable new routes/resolver while retaining encrypted rows; environment configuration remains usable when no database profile is active by the rollback path.

## WP2 — Runtime LLM activation and platform configuration UI

- Scope: make public Chat and `ai_assistant.available` resolve the active profile consistently without process restart; add platform readiness, profile list, create/edit drawer, per-profile test and confirmed activation.
- Expected files: `services/api/app/services/ai_runtime.py` and/or current provider/orchestrator factory, public conversation/catalog call sites, `apps/admin-web/src/api/platformApi.ts`, shared types, `PlatformLlmSettingsPage.tsx`, routing/shell/styles and focused tests.
- Acceptance: save → test → activate is explicit; switching changes a subsequent real Chat without restart; disabled active profile produces a clear unavailable state; the UI never repopulates a secret and works at desktop and 390px.
- Depends on: WP1.
- Verification: focused runtime/API/admin tests, admin build, one real connection test and one real Chat smoke.
- Rollback: hide settings route and restore environment-only resolver without deleting profile data.

## WP3 — Platform operations backend and governance projections

- Scope: add overview, searchable enterprise list/detail, onboarding progress, employee/visitor aggregates, task read model, audit feed, service probes and narrowly audited active/suspended lifecycle operations.
- Expected files: `services/api/app/api/platform_schemas.py`, `services/api/app/api/routes/platform.py`, `services/api/app/services/platform_store.py`, optional narrow health/settings modules, current-head migration/RLS functions only where required, focused API/PostgreSQL tests.
- Acceptance: all endpoints require platform role; response schemas exclude PII/private content; task center is read-only until a separate idempotent retry contract exists; service probes are bounded and independently report failure; lifecycle mutations require reason/version and audit.
- Depends on: WP0, with WP1 APIs available for readiness projection.
- Verification: focused route/store/RLS/forbidden-field tests and one platform API success/403 smoke.
- Rollback: disable added routes; existing enterprise create/list remains compatible.

## WP3A — Document-assisted enterprise onboarding

- Scope: add a versioned platform onboarding session and an isolated non-login/non-public provisional enterprise scope; route supported files through the current `knowledge_import` store/parser/Worker; use the active `chat_main` profile only on parsed drafts to propose sourced enterprise/profile/card fields; require human review and idempotent atomic confirmation.
- Expected files: one current-head migration and model only if needed, `services/api/app/api/platform_schemas.py`, `services/api/app/api/routes/platform.py` or a narrow onboarding route, `services/api/app/services/platform_store.py` plus a narrow onboarding/synthesis service, existing `knowledge_import` service adapters without parser replacement, `apps/admin-web/src/api/platformApi.ts`, a platform onboarding wizard/page and focused frontend/API/Worker tests.
- Acceptance: enterprise roles receive 403; the client cannot choose an arbitrary target tenant; provisional credentials cannot log in and provisional cards cannot be public; supported files use current format/limit/Worker behavior; every LLM suggestion has source/version and remains editable; LLM failure falls back to manual input; confirmed `expected_version` creates exactly one active enterprise/admin and one employee-independent `enterprise` draft card; selected valid candidates are materialized through the existing review service as traceable unpublished enterprise/product/case/FAQ content; repeated confirmation is idempotent and stale confirmation returns 409; temporary credentials can be regenerated only before first password change; tasks have optimistic human-readable names; unconfirmed sessions expire after 24 hours and are cleaned after a 30-day history window.
- Depends on: WP0, WP1/WP2 effective LLM configuration, existing enterprise-create invariants in WP3, and the WP6 import baseline.
- Verification: focused onboarding schema/store/route/security/idempotency/prompt-injection tests, focused admin wizard tests/build, one small-file document-assisted onboarding smoke and one cross-session/role failure.
- Rollback: hide the onboarding route and lock unfinished sessions; retain ordinary enterprise creation/import, never delete confirmed enterprises or existing import batches, and do not enable provisional credentials.

## WP4 — Platform control console

- Scope: implement grouped platform navigation, action-oriented overview, enterprise center, separate onboarding/delivery page with document-assisted enterprise wizard, enterprise detail, employees/visitors, task/audit/health pages and LLM readiness entry.
- Expected files: `apps/admin-web/src/routing.ts`, `App.tsx`, `components/AppShell.tsx`, `styles.css`, `api/platformApi.ts`, new/updated `Platform*Page.tsx`, `PlatformEnterpriseDrawer.tsx` and focused tests.
- Acceptance: platform list → enterprise detail → every card → published public page works; the onboarding wizard shows initialization/upload/suggestion/review/complete states without activating unconfirmed data; platform cannot impersonate or edit enterprise private content after confirmation; mobile detail is full-width and audit/tasks use business labels without clipped columns; zero data uses compact empty states.
- Depends on: WP2, WP3 and WP3A shared contracts.
- Verification: focused component/API tests, admin build, desktop platform smoke and 390px spot-check on enterprise detail/audit.
- Rollback: remove new routes/pages while retaining the existing enterprise onboarding page and APIs.

## WP5 — Enterprise console organization and card/public bridge

- Scope: regroup existing enterprise navigation without renaming stable routes; add AI/import readiness on overview, improve state handling, introduce an explicit `enterprise` versus `employee` card contract, separate enterprise-card publishing from employee-card management, make per-card public preview a primary action, and preserve owner/admin scope.
- Expected files: `apps/admin-web/src/components/AppShell.tsx`, `OverviewPage.tsx`, `CardsPage.tsx`, relevant shared API/types/styles/tests; platform card projection schemas/store where necessary.
- Acceptance: enterprise and card-owner navigation reflects permissions; enterprise cards do not require an employee owner while employee cards do; the enterprise console exposes separate enterprise-card and employee-card areas with explicit create/edit/publish actions; published cards use API `share_url`; draft/disabled cards have no fabricated public link; desktop and 390px retain main actions; platform and enterprise open the same public page.
- Depends on: WP0 and WP3 card projection; may proceed alongside later WP4 pages after contracts freeze.
- Verification: focused AppShell/Cards/Overview tests, admin build and one enterprise browser smoke.
- Rollback: restore prior grouping and share-dialog-only entry without data changes.

## WP6 — Current knowledge import assurance

- Scope: keep the current `KnowledgeImportPanel` → `/admin/knowledge/imports` → `knowledge_import` store/parser → Worker flow; connect overview/readiness and expose a narrow server-side adapter for provisional onboarding scopes without changing the parser, Worker, ordinary endpoint or ordinary membership semantics.
- Expected files: no parser/Worker fork; focused changes may include `KnowledgeImportPanel.tsx`, `knowledgeImportsApi.ts`, knowledge page/overview status presentation, a narrow server-side onboarding authorization adapter and their tests. Shared parser/Worker behavior changes are allowed only for a reproduced regression in the current chain.
- Acceptance: existing supported formats and 5 files/10 MiB/25 MiB limits remain; one real small supported file reaches draft in both ordinary enterprise and provisional onboarding scopes; default remains manual review; one invalid/unsupported path returns a stable error; cross-tenant and cross-onboarding-session batch access are denied; no `document_import`/Docling/OCR or second raw-document parser/Worker is added.
- Depends on: enterprise navigation shell from WP5; the ordinary baseline is independent from LLM activation, while onboarding synthesis depends on WP2.
- Verification: focused frontend/API/Worker import tests and one small real import smoke. No 19 MiB Docling or reference-repo validation.
- Rollback: remove the onboarding adapter and revert presentation changes; current parser/store/Worker behavior and existing batches remain untouched.

### WP6A — Progressive content classification and global task dock

- Scope: add progress and lease fields to the existing content import run/candidate tables, enqueue classification for the current Worker, discover a compact source-backed candidate directory, enrich only relevant categories, and surface the same run through the import workbench and AppShell task dock.
- Expected files: one current-head migration/model/schema/service increment, focused Worker claim/executor changes, `knowledgeImportsApi.ts`, `KnowledgeImportPanel.tsx`, one global dock component, AppShell/routing styles and focused tests.
- Acceptance: enqueue returns before model completion; stale leases recover without duplicates; optional field grounding failures degrade only that field; candidates appear progressively; the dock is tenant-scoped, keyboard/mobile accessible and returns to the exact run.
- Depends on: current LLM resolver and WP6 parser/import baseline. No second parser, raw-document store or permission model is introduced.
- Verification: focused API/Worker/admin tests, admin build, migration/claim smoke and one real website PDF journey with cross-page dock screenshots.
- Rollback: stop claiming queued content runs and hide the dock while preserving existing batches, runs and candidates; no user content is deleted.

## WP7 — Contract sync and proportional integrated evidence

- Scope: sync OpenAPI when API contracts change; run focused tests/build; execute the six high-value browser/runtime smokes; review diff for secrets, rejected import components, provisional-resource leaks, ports/base path and unintended migrations.
- Expected files: OpenAPI artifact if generated by the current repository, current change run receipts/proof, `PROJECT_PANORAMA.md` and `SESSION_BRIEF.md` only if implementation changes project truth.
- Acceptance: each Eval Contract hard gate has current direct evidence; no key appears in response/log/diff; no provisional credential/public resource is usable before confirmation; no port/base-path drift; no rejected document import component; known gaps are reported rather than hidden.
- Depends on: WP1–WP6 and WP3A.
- Verification: focused commands listed in `eval-contract.md`; no full performance, release, RAG benchmark, all-page screenshot or reference-repo suite unless a focused failure expands scope.
- Rollback: do not declare completion while any hard gate fails; roll back the failing work package without deleting user data.
