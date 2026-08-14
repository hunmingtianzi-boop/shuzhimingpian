# Codex Native Implementation Plan

## Control Pointers

- Change: `unify-platform-enterprise-llm-import-control-plane`
- Stable work packages: `tasks.md`
- Requirements: `specs/*/spec.md`
- Technical design: `design.md`
- Evidence contract: `eval-contract.md`
- Review: `multi-lens-review.md`
- Progress truth: this file only

Implementation MUST start in a new exact run under `openspec/changes/unify-platform-enterprise-llm-import-control-plane/runs/<run-id>/`. That run must bind the current user message, change ID, allowed project root, implementation operation and non-goals. Existing untracked Harness/Design/OpenSpec files belong to the current project setup and must not be discarded. No commit or push is authorized by this plan.

## 0. Run and shared-contract freeze

- [x] 0.1 Create the exact implementation run/authority receipt, record `git status`, current migration head and runtime/base-path snapshot; expected result: implementation scope is limited to this project and this change. Verify with `harness-cli status ... --change ... --run ...` or the current exact-run status mechanism.
- [x] 0.2 Finalize the role/permission matrix, provisional-onboarding scope rules and platform response allowlist in `platform_schemas.py` plus focused contract tests before UI/API parallel work; expected result: platform, onboarding, enterprise and public fields have one shared contract. Verify with the new schema/forbidden-field tests only.
- [x] 0.3 Populate `.codex/harness/contracts/runtime-ports.json` from current source facts for dev, Local Compose and production gateway/base paths; do not alter ports. Verify by inspecting `package.json`, `infra/compose.yaml`, gateway/production config and running the narrow port-contract check.
- [x] 0.4 Add a Feature DESIGN Delta inside this change or its exact run that freezes platform amber, enterprise blue, grouped IA, full-width mobile detail, record-card mobile tables and anti-patterns; do not rewrite root `DESIGN.md`. Evidence: review against `design.md` and current tokens.

## 1. LLM profiles — persistence and secure API first

- [x] 1.1 Add focused failing tests for profile invariants, encrypted/masked key, empty-key retention, optimistic 409, platform-only 403, safe URL/test behavior and zero-profile environment fallback. Files: new API/model tests plus existing security fixtures. Expected result: tests fail only for missing new capability.
- [x] 1.2 Add one clean migration after current head `20260715_0015` and the final platform LLM profile model; do not copy reference migration IDs or singleton intermediate schema. Expected result: zero profiles/zero active or one+ profiles/exactly one active, preserved downgrade guard and no plaintext field. Verify with focused migration/model tests.
- [x] 1.3 Implement platform profile list/create/update/activate/test services and routes with advisory/transaction locking, `expected_version`, expected active ID, encrypted key and secret-free audit. Expected result: stale writes 409, enterprise access 403, responses only contain key status/hint. Verify with focused route/service/security tests.
- [x] 1.4 Implement one bounded OpenAI-compatible `/models` probe with no redirect/retry and production URL/DNS/HTTPS rules. Expected result: safe success/failure metadata only. Verify with mocked safety cases and one real configured probe during smoke.

## 2. LLM runtime activation and UI readiness

- [x] 2.1 Refactor the current Chat provider/orchestrator construction behind one effective-config resolver used by public Chat, onboarding suggestion generation and `ai_assistant.available`; keep ordinary import parsing independent. Expected result: selected profile takes effect without process restart, disabled active profile does not silently fall back, and parsed onboarding drafts remain usable when LLM is unavailable. Verify with focused `test_ai_runtime.py` and new active-profile tests.
- [x] 2.2 Extend `platformApi.ts`, shared types and route guards for profile operations; add normalization tests that prove key fields never enter client state. Expected result: typed profile API with explicit conflict/error handling.
- [x] 2.3 Implement `PlatformLlmSettingsPage.tsx` as current-profile summary + profile list + create/edit drawer + test + confirmed activation, with advanced settings secondary. Expected result: save/test/activate have distinct states, failed/stale/unconfigured states are actionable, secret input clears after save.
- [x] 2.4 Add platform overview LLM readiness entry and 390px layout rules without exposing enterprise-facing secrets. Verify with focused page tests, admin build and one desktop/390px browser spot-check.
- [x] 2.5 Run the AC1 real smoke: create/update → test → activate → one public Chat; record profile ID/version/model and latency but never key/upstream body. Stop and repair before continuing if activation requires restart or availability disagrees.
- [x] 2.6 Extend each platform LLM profile with default-off `allow_general_answers` and `faq_fast_path_enabled`, expose them only through the platform API, and map them into request-local runtime settings. Verify migration/model/schema/route/runtime focused tests and preserve optimistic version/audit behavior.
- [x] 2.7 Add both controls to the existing platform LLM profile editor with clear scope and risk copy; values must survive save and refresh at desktop and 390 px without adding an enterprise control surface. Verify API normalization/page tests and admin build.
- [x] 2.8 Run the behavior-control smoke without restarting between saves and requests: low-risk general answer off/on, high-risk gate unchanged, FAQ fast path on with no model call, then restore both controls to off. Record API container identity before and after.

## 3. Platform operations backend

- [x] 3.1 Add focused tests for overview, enterprise search/detail, card projection, delivery progress, employee/visitor aggregates, task/audit/health projections, lifecycle transitions, platform 403 and forbidden fields. Expected result: tests define narrow cross-tenant boundaries before implementation.
- [x] 3.2 Extend `platform_schemas.py`, `platform_store.py` and `/api/v1/platform/*` routes with explicit allowlisted projections; add current-head migration/RLS helper only if ordinary platform queries cannot meet the contract. Verify with focused API/PostgreSQL/RLS tests.
- [x] 3.3 Implement enterprise active/suspended transition with reason/version/confirmation contract and audit. Do not add delete or impersonation. Verify allowed and rejected transitions.
- [x] 3.4 Implement task center as a read-only PostgreSQL/outbox/knowledge-import projection, business-safe audit feed and bounded API/DB/Redis/MinIO/Worker probes. Do not implement reference `document_import` retry. Verify individual probe failure does not fail the whole response.

## 3A. Document-assisted enterprise onboarding

- [x] 3A.1 Add focused failing tests for platform-only start/read/update/cancel/confirm, server-bound provisional tenant scope, disabled provisional credentials, non-public provisional cards, current-import reuse, sourced suggestions, LLM-unavailable fallback, prompt-injection isolation, optimistic 409 and idempotent confirmation. Expected result: tests define the lifecycle and security boundary before implementation.
- [x] 3A.2 Add one current-head migration/model for versioned onboarding sessions and the minimum provisional-resource state needed to keep tenant/company/admin/card unavailable until confirmation; do not create a second document/source-unit schema. Expected result: unfinished sessions are excluded from ordinary list/login/public queries and cancel/expiry cannot activate resources. Verify migration/model/state-transition tests.
- [x] 3A.3 Implement platform onboarding start/upload/status/cancel endpoints and a narrow adapter that derives tenant/company only from the server-owned onboarding session before invoking the current `knowledge_import` validation, object storage, parser/store and Worker. The client must never supply an authorization target tenant, and the platform actor must not receive an enterprise session. Verify role, cross-session, format/limit and partial-file-failure tests.
- [x] 3A.4 Implement structured onboarding suggestion generation from successful parsed drafts through the active `chat_main` resolver. Persist per-field source draft/file, confidence hint and generation version; treat document text as untrusted data, disable tools/external fetches, and never activate/publish from model output. Expected result: LLM failure leaves drafts intact and manual completion available. Verify schema, sanitization, injection and unavailable-provider tests.
- [x] 3A.5 Implement the platform onboarding wizard: initialize → upload/process → sourced suggestions/manual fields → review → confirmed result. Confirm requires `expected_version` and explicit enterprise/admin/card review; the backend atomically and idempotently activates exactly one enterprise/admin and one employee-independent `enterprise` draft card while imported knowledge stays draft. Verify focused wizard/API tests, admin build, desktop/390px behavior and the AC6 real smoke.
- [x] 3A.6 Close the phase-two assisted-onboarding handoff agreed in Q1–Q85: the platform generates a one-time temporary credential instead of asking an operator to invent one; the enterprise administrator remains an account/membership and is not materialized as an employee; the onboarding review reuses the enterprise import candidate navigation/card interaction with category filters, previous/next navigation, draft autosave semantics and source evidence; accepted and unresolved candidates remain bound to the onboarding task and transfer to the confirmed enterprise as drafts/history. Verification: focused API/UI tests plus two website-only browser journeys (document-assisted and manual/skip-upload), with screenshots for every key action. Local commit is authorized; push is explicitly forbidden until separate user confirmation.
- [ ] 3A.7 Extend final confirmation with an explicit selected-candidate contract. Reuse `ContentImportReviewService.accept_candidate`; selected complete candidates become traceable unpublished enterprise/product/case/FAQ content before activation, while ignored/unselected/unclassified candidates remain history. A materialization failure must keep the enterprise provisional and retry must not duplicate targets. Verify focused service/route/PostgreSQL tests for all four categories, partial failure and idempotency.
- [ ] 3A.8 Add platform-only temporary credential regeneration for confirmed sessions while `must_change_password=true`: invalidate the old hash, return the new password once, refresh seven-day expiry and audit metadata only. Reject completed-first-change, disabled or non-platform cases. Verify old/new login behavior and response secret boundaries.
- [ ] 3A.9 Add human-readable onboarding task names and align knowledge import defaults to `企业名称·资料导入·YYYY-MM-DD·第 N 次`; expose optimistic rename in the platform wizard/list while preserving existing enterprise rename behavior and UUID as secondary metadata. Verify create/default/rename/stale-version cases in API and UI.
- [ ] 3A.10 Implement two-stage retention: eagerly project open sessions past 24 hours to `expired`; a restricted Worker beat job cleans provisional upload/content/resources only for cancelled/failed/expired sessions older than 30 days and retains a secret-free audit summary. Confirmed enterprises are a hard exclusion. Verify repository, schedule and PostgreSQL integration cases.

## 4. Platform control-console UI

- [x] 4.1 Preserve current `APP_BASE_PATH/appHref` and add role-safe grouped platform navigation/routes: overview, enterprises, onboarding/delivery with document-assisted creation, employees, visitors, tasks, audit, health and LLM settings. Verify platform/enterprise direct-URL route tests and `/c/admin/` build behavior.
- [x] 4.2 Redesign `PlatformOverviewPage` around readiness, pending work, provisional/onboarding progress, published cards and exceptions; replace zero-value 30-day mobile rows with compact empty/trend state. Verify focused state tests.
- [x] 4.3 Split enterprise center from onboarding/delivery; implement search/filter and `PlatformEnterpriseDrawer` with allowlisted metrics, progress and every card. Desktop uses wide drawer; <=720px uses full-width sheet/records. Verify focus return, no horizontal page overflow and no private fields.
- [x] 4.4 Implement employees/visitors, task/audit/health pages using business labels and narrow-screen record cards. Internal event codes stay secondary. Verify one 390px audit/task spot-check.
- [x] 4.5 Run the AC2/AC3 platform smoke: platform login → enterprise list/detail → all cards → published `share_url`; direct enterprise-role platform access must be forbidden.

## 5. Enterprise console and public-card bridge

- [x] 5.1 Regroup existing `AppShell` navigation into workbench, customer operations, AI/knowledge, content/cards and governance without changing stable route URLs or permissions. Notifications move to the header entry if current behavior permits. Verify role-specific AppShell tests.
- [x] 5.2 Update enterprise overview using existing APIs to surface actionable leads, knowledge gaps/import failures, unpublished cards and LLM readiness; retain explicit loading/empty/error/success states. Verify focused Overview tests.
- [x] 5.3 Make “open public page” a primary per-row action in `CardsPage`; keep edit primary, move lower-frequency share/disable actions into the existing secondary pattern where needed. Only API `share_url` is clickable. Verify published/draft/disabled tests and new-tab safety.
- [ ] 5.4 Run the revised AC4 browser smoke at desktop and 390px: enterprise login → create/edit/publish an employee-independent enterprise official card → open the same public page used by platform; verify employee cards remain separately managed, no platform navigation and no lost mobile action.
- [ ] 5.5 Add the frozen `enterprise`/`employee` card type through the current migration head, ORM constraints, allowlisted API projections, catalog permissions and enterprise UI. Existing cards migrate conservatively as `employee`; document-assisted onboarding creates `enterprise`. Verify company-card owner nullability, employee owner validity, card-owner isolation, platform grouping and focused UI/API tests.

## 6. Current knowledge_import assurance and controlled onboarding reuse

- [x] 6.1 Run the existing focused `KnowledgeImportPanel`, API/security and Worker tests before changing import presentation; expected result: establish current-chain baseline. If baseline fails, diagnose the current project only.
- [x] 6.2 Connect enterprise overview/AI-and-knowledge navigation to the existing import panel and batch states without renaming `/admin/knowledge/imports` or changing ordinary limits/status enums. Expose only the narrow server-bound onboarding adapter required by 3A.3; do not fork the parser/store/Worker. Change shared import internals only if a current-chain regression is directly reproduced.
- [x] 6.3 Ensure UI distinguishes upload validation, async processing, draft/review/publish and failure; default auto-publish remains off and permission-gated. Verify focused component/API tests.
- [x] 6.4 Run the AC5 ordinary enterprise-import smoke: one small supported DOCX/PDF or TXT → Worker → visible draft; one unsupported/invalid file error; one cross-tenant denial. Do not run 19 MiB Docling/OCR validation.
- [x] 6.5 Scope-review dependencies, migrations and source tree for rejected reference components. Expected result: no `document_import`, Docling/MinerU, new OCR service, source-unit lifecycle or second raw-document parser/Worker was introduced; the only allowed LLM document use is 3A.4 over current parsed drafts.

## 7. Focused integration, evidence and handoff

- [x] 7.1 Run only the focused admin tests/build, focused API/Worker tests and OpenAPI checks listed in `eval-contract.md`; expand from a failure only when the failure surface requires it.
- [x] 7.2 Re-run the six real smokes and capture only the representative screenshots/receipts named in `eval-contract.md`, including one keyboard-focus spot-check. Confirm tested pages have no relevant unhandled console error or page-level horizontal overflow.
- [x] 7.3 Perform final diff/security/port review: no tracked secret, usable provisional credential/public resource, cross-session access, unexpected migration, rejected import module, base-path drift, unauthorized `.env` write, lockfile change or unrelated user-file modification. The user explicitly authorized the local ignored `.env` and `.env.local` LLM configuration in this run.
- [ ] 7.4 Map current receipts to AC1–AC8 in the exact run proof pack; update `PROJECT_PANORAMA.md`/`SESSION_BRIEF.md` only for project-truth changes. Independent Checker is required at completion because this is Strict; do not claim PASS with missing evidence.
- [x] 7.5 Present completion candidate with changed entries, direct evidence, unverified gaps and rollback notes. Commit/push only if separately authorized.
- [x] 7.6 For the Q1–Q85 increment, create a local commit only after focused tests/build, API success/failure evidence, both real browser journeys and scope review pass. Exclude Celery beat runtime files and all credentials. Do not push.
- [ ] 7.7 Run the follow-up website-only journey: named onboarding task → upload long-form PDF → edit/select candidates → confirm → observe real drafts in enterprise profile/core business/cases/FAQ → regenerate temporary password → prove old password rejected and new password reaches first-change gate → rename conflict/24h expiry checks. Capture key screenshots, console/network failures and database/API receipts; do not commit or push without separate authorization.

## Execution Strategy

- Start `sync-then-parallel`: complete 0.1–0.4 and freeze shared schemas/routes first.
- Implement 1.x and 2.x mostly sequentially because persistence, secret safety and runtime activation share one contract and LLM must be ready first.
- Run 6.1 immediately after shared-contract freeze so the current import baseline exists before any onboarding adapter work. Then implement 3A mostly sequentially across provisional lifecycle → import adapter → sourced synthesis → review/confirm UI.
- After WP0/WP1 contracts are frozen, platform backend (3.x) and enterprise UI organization (5.1–5.3) may use independent native subagents with disjoint files; 3A shared lifecycle/import contracts must be lead-integrated before platform UI 4.x and final smokes.
- Remaining import assurance 6.2–6.5 stays isolated; no worker/parser refactor runs in parallel without a reproduced current-chain defect.
- Final verification and proof are lead-owned. Worker self-reports are not completion evidence.

## Failure and Rollback Rules

- Secret exposure, role/tenant/onboarding-session bypass, provisional login/public exposure, duplicate confirmation, active-profile inconsistency, current import regression, production base-path break or migration data risk is a BLOCK, not a soft warning.
- Failed LLM activation rolls back the resolver/UI route while retaining encrypted profile rows; zero-profile environment fallback remains the recovery path.
- Failed platform pages can be route-hidden while existing onboarding/list endpoints remain available.
- Failed document-assisted onboarding is route-hidden and unfinished sessions are locked; ordinary enterprise creation/import remains available, confirmed enterprises are never deleted, and provisional credentials remain disabled.
- Failed enterprise navigation/card presentation reverts locally without data changes.
- Import changes reuse the current parser/Worker; never delete existing import batches/drafts, activate a provisional resource, or replace the parser/Worker to make a smoke pass.
