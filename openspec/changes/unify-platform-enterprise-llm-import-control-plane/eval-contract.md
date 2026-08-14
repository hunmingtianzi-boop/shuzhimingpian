# Eval Contract

## Responsibility Contract

- Change: `unify-platform-enterprise-llm-import-control-plane`
- Product surfaces: platform console, document-assisted enterprise onboarding, enterprise console, public card page, Chat runtime, current knowledge import.
- Evidence principle: focused automated tests plus a few real end-to-end smokes. Do not substitute test volume for the high-risk secret, permission, runtime-switch and import boundaries.
- Stop rule: any secret exposure, cross-tenant/cross-onboarding-session access, provisional login/public exposure, role bypass, base-path break, import regression, duplicate confirmation or active-profile inconsistency is a hard failure.

## Hard Gates

### AC1 — LLM configuration is secure and actually active

- Platform admin can create/edit/test/activate named `chat_main` profiles.
- API key is encrypted, never returned, logged or audited in plaintext.
- Stale edits/activation return 409; enterprise role returns 403.
- A real Chat after activation uses the selected profile without service restart.
- Public `ai_assistant.available` matches the same effective configuration.
- Platform admin can independently control low-risk general answers and published high-confidence FAQ fast answers on each profile; enterprise roles cannot change them.
- Saving either control affects the next Chat request without a container restart. General-answer mode does not weaken high-risk/pricing gates, and FAQ fast answers do not invoke the model.

Evidence:

- focused migration/model/route/security/runtime tests;
- one bounded real `/models` test;
- one real public Chat before/after activation state observation;
- real before/after behavior-control requests with unchanged API container identity, including one no-model FAQ fast-path receipt;
- response/log/diff secret scan.

### AC2 — Platform and enterprise workspaces are role isolated

- Platform accounts only see and enter platform routes.
- Enterprise accounts/card owners only see and enter allowed enterprise routes.
- Direct URL and API access across workspaces produce a clear frontend forbidden state and backend 403.

Evidence:

- routing/AppShell tests;
- focused auth/API tests;
- one direct-URL smoke per role.

### AC3 — Platform enterprise operations and public-card bridge work

- Platform overview exposes actionable readiness/operations rather than private content.
- Enterprise center supports list/search/detail and shows allowlisted aggregates, delivery progress and all cards.
- Only published cards with server `share_url` open a new real public page.
- Platform response schemas exclude PII, conversation/lead/knowledge body and secrets.

Evidence:

- platform schema/store/route and forbidden-field tests;
- desktop enterprise-detail browser smoke;
- 390px enterprise-detail/audit spot-check;
- public page opened from returned URL.

### AC4 — Enterprise console preserves existing business capability

- Existing stable routes remain addressable under current base path.
- Navigation is regrouped by work goal without granting new permissions.
- Enterprise official cards and employee cards are explicit types: official cards are employee-independent, employee cards require an active enterprise member, and the enterprise console separates their create/edit/publish flows.
- Published card direct preview, LLM readiness and import readiness are visible; loading/empty/error/success are explicit.

Evidence:

- focused AppShell/Overview/Cards tests;
- admin production build;
- one enterprise desktop/390px smoke.

### AC5 — Current knowledge_import remains the only and working import path

- Existing endpoints, format/limit contract, async Worker, default draft and tenant isolation remain intact.
- One small supported file reaches a visible draft; one invalid/unsupported upload fails clearly; one cross-tenant access is denied.
- No `document_import`, Docling/OCR service, second raw-document parser/Worker, rejected migration or new import dependency appears in the diff. Onboarding synthesis may only consume current parsed drafts.

Evidence:

- focused KnowledgeImportPanel/API/security/Worker tests;
- one real small-file import smoke;
- diff/dependency/migration scope check.

### AC6 — Document-assisted onboarding creates one reviewed enterprise safely

- A platform admin can start a provisional onboarding session, upload a supported file through current `knowledge_import`, and receive sourced/editable enterprise and initial-card suggestions.
- Provisional credentials cannot log in, provisional cards cannot be public, enterprise roles receive 403, and a session cannot access another session's tenant/import data.
- LLM failure preserves parsed drafts and allows manual completion; document text is treated as untrusted and cannot trigger tools, external URLs, secret access or automatic activation/publication.
- Confirm with the current `expected_version` is idempotent and produces exactly one active enterprise/admin plus one employee-independent enterprise official draft card. Selected valid candidates materialize through the existing review service into traceable unpublished enterprise/product/case/FAQ content; invalid, ignored and unselected candidates remain review history. Stale confirmation returns 409.
- A one-time temporary password can be regenerated only while first password change is still required; the old password is invalid immediately and plaintext appears in one response only.
- Platform onboarding/import tasks use editable human-readable names with optimistic conflict handling. Open sessions expire after 24 hours; cancelled/failed/expired provisional resources are cleaned only after 30 days and confirmed enterprises are excluded.

Evidence:

- focused onboarding model/schema/store/route/security/idempotency/prompt-injection tests;
- focused platform onboarding wizard tests and admin build;
- one real small-file onboarding smoke from upload through reviewed confirmation;
- database/API observation before and after confirmation plus cross-session/role denial;
- focused regenerate-password success/rejection, rename conflict, expiry and retention-cleanup tests.

### AC7 — Runtime ports and deployment base paths do not drift

- Dev, Local Compose and production gateway contracts match `design.md` and the machine-readable port contract.
- `/c/`, `/c/admin/` and `/c/api/` continue to resolve in the production-like route configuration.

Evidence:

- configuration inspection/contract test;
- one production-like direct path smoke when the local gateway is available.

### AC8 — Changed contracts build and validate

- Focused frontend, API and Worker tests pass.
- Admin build passes.
- OpenAPI check/validation passes when API shapes change.
- OpenSpec change remains strict-valid.

## Focused Command Set

Use the repository's actual virtual environments; if a listed test file is introduced during implementation, include it in the focused invocation.

```powershell
corepack pnpm --filter @cf/admin-web test -- platformApi.test.ts AppShell.test.ts PlatformEnterpriseOnboardingPage.test.tsx KnowledgeImportPanel.test.tsx CardsPage.test.tsx
corepack pnpm --filter @cf/admin-web build
```

```powershell
services/api/.venv/Scripts/python -m pytest `
  services/api/tests/test_ai_runtime.py `
  services/api/tests/test_knowledge_import_routes.py `
  services/api/tests/test_knowledge_import_security.py `
  services/api/tests/test_platform_postgres_integration.py `
  services/api/tests/test_platform_llm_profiles.py `
  services/api/tests/test_platform_operations.py `
  services/api/tests/test_platform_enterprise_onboarding.py
```

```powershell
services/worker/.venv/Scripts/python -m pytest `
  services/worker/tests/test_knowledge_imports.py
```

```powershell
corepack pnpm contracts:check
corepack pnpm contracts:validate
openspec validate unify-platform-enterprise-llm-import-control-plane --strict
```

## Real Smoke Set

1. Platform admin: create/update profile → test → activate → complete one real Chat; verify secret is not returned.
2. Platform admin: start document-assisted onboarding → upload one small supported file through current `knowledge_import` → generate or manually complete sourced suggestions → confirm once → observe one enterprise/admin and one employee-independent enterprise official draft card.
3. Platform admin: enterprise list → detail → all cards → open a published public page.
4. Enterprise admin: create/edit/publish one enterprise official card without selecting an employee, open the same card from enterprise card management, and verify employee-card management stays separate; draft/disabled cards have no public link.
5. Enterprise admin: upload one small supported file → wait for Worker → see draft → keep draft or publish one item explicitly.
6. Failure/permission: one unsupported file error plus one cross-role, cross-tenant or cross-onboarding-session denial; observe that an unconfirmed provisional credential cannot log in.

Visual evidence is limited to representative LLM desktop, onboarding review desktop/390px, enterprise detail desktop/390px, enterprise cards desktop and import 390px screenshots. Add one keyboard-focus spot-check; do not run pixel-diff or full a11y/performance suites unless a focused failure requires expansion.
