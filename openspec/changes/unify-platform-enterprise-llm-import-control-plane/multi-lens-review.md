# Multi-lens Review

## Product / CEO — PASS

The plan preserves the actual product loop from the three requirement documents while prioritizing the user's requested platform console, early LLM readiness and document-assisted enterprise creation. The platform can initialize an enterprise from reviewed source material without becoming an impersonation console after activation.

Adjustment adopted: move LLM configuration to the first business package; add a provisional, reviewed onboarding flow after LLM readiness; keep overview focused on readiness, delivery and exceptions rather than generic KPI decoration.

## Engineering — PASS

The current repository remains the only implementation trunk. Shared contracts freeze before parallel UI/API work; final multi-profile schema is created directly from the current migration head; current base-path helpers and server share URLs are preserved. Document-assisted onboarding reuses the current import parser/store/Worker through a server-bound provisional scope instead of creating a second importer.

Adjustment adopted: rewrite routing, migrations, onboarding lifecycle and task projections for the current repository instead of copying reference files. Keep the first task center read-only and keep the provisional lifecycle explicit/idempotent.

## QA — PASS

Acceptance criteria map to focused tests and six high-value real smokes. This is lighter than a full regression but still covers the major failure surfaces: active runtime configuration, secret handling, provisional activation/idempotency, role/tenant/session isolation, public-card links and current import.

Adjustment adopted: no full performance/RAG/release suite and no all-page visual matrix. Verification expands only from a focused failure.

## Security / CSO — PASS

The plan uses encrypted write-only keys, strict outbound URL rules, no silent failover, optimistic concurrency, narrow platform projections, backend 403 and server-generated public URLs. Provisional enterprises cannot log in or publish, and onboarding target scope is derived from a server-owned session rather than client tenant IDs.

Adjustment adopted: platform cannot view visitor PII/private content or impersonate enterprises; the only private-content exception is the creating platform admin's unfinished onboarding session, and that access ends on confirmation/cancel. Document text is untrusted, LLM tools/external fetches are disabled, and every generated field requires review.

## Context Engineer — PASS

Source authority is explicit: current source and runtime contracts first, three documents for business scope, reference repository for selected platform/LLM interaction patterns only. Dirty reference import work cannot enter the change.

Adjustment adopted: any reference code extraction must come from committed HEAD `f625ec8`, and all import experiment modules are reject-listed.

## Frontend Developer — PASS

The plan preserves current paths/components where possible, adds grouped navigation, full-width mobile detail, business labels and action-oriented states, and avoids copying the reference stylesheet wholesale.

Adjustment adopted: audit/tasks become record cards on narrow screens; mobile overview removes zero-value long tables; card actions are prioritized.

## Backend Developer — PASS

Platform LLM profiles and platform read projections are separate narrow services. The import parser/store/Worker remain the single implementation. A narrow onboarding adapter may bind them to a provisional tenant derived from the server-side session; raw parsing is not forked.

Adjustment adopted: no reuse of enterprise `model_configs` as the platform secret store; no raw-document extraction capability binding. The active `chat_main` profile may synthesize suggestions only from successful parsed drafts.

## Full-stack Developer — PASS

UI, API, runtime and public availability use one effective configuration rule. The same resolver supplies optional onboarding suggestions, while import completion remains independent. Platform/enterprise card links use one server-produced `share_url`. Environment-specific port/base-path behavior is a hard gate.

Adjustment adopted: retain `APP_BASE_PATH/appHref` and production `/c/admin/` routing rather than importing reference `href={item.path}` behavior.

## Personal Developer — PASS

Work is divided into reversible packages with LLM first, the current import baseline before onboarding, and document-assisted creation as a separately disableable package. The verification set is small enough for routine local work but includes direct evidence for the risky parts.

## Knowledge Steward — PASS

The repeated user correction has been applied as a run-local rule: current repository import only; reference repository is for control-console/LLM design. The latest product decision adds document-assisted enterprise creation on top of current parsed drafts, not a replacement importer. No global memory write is authorized.

## Feedback-to-Adjustment Ledger

| Feedback | Adjustment | Target | Evidence | Status |
| --- | --- | --- | --- | --- |
| LLM configuration must be ready early | WP1/WP2 are the first business implementation packages | `design.md`, `tasks.md`, `plan.md` | plan order and AC1 | adopted |
| Import must use this project | Current `knowledge_import` is the only allowed path; all reference document import work rejected | proposal/spec/design/WP6 | AC5 and scope check | adopted |
| Importing material must be able to generate an enterprise | Add server-bound provisional onboarding, reuse current import, generate sourced suggestions, require human/idempotent activation | onboarding spec/design/WP3A/plan | AC6 and real onboarding smoke | adopted |
| Platform and enterprise consoles both need to be good | Grouped IA, shared component language, role-safe routes, representative desktop/mobile AC | console specs/WP4/WP5 | AC2–AC4 | adopted |
| Verification should not be too heavy | Focused tests + six real smokes; expansion only on failure | `eval-contract.md` | final run receipts | adopted |
| Reference UI has mobile overflow/raw event problems | Full-width mobile detail, record cards, business labels and compact empty states | `design.md`, platform spec | 390px spot-check | adopted |

## Verdict

No unresolved BLOCK. The change is plan-ready after the document-assisted onboarding artifacts, `tasks.md`, `plan.md` and OpenSpec strict validation are complete.

## 2026-08-23 P0/P1 review

- Product / CEO: **PASS** — platform and enterprise IA are separated; cardless provisioning removes platform overreach; real customer/content objects remain linked without inventing billing.
- Engineering: **NEEDS FIX until WP1 completes** — `initial_card_id`, duplicated provisioning and mixed company settings are hard coupling points; shared migration/schema must land first.
- QA: **NEEDS FIX until runtime evidence exists** — desktop/390px, 403/409 and upgrade/rollback checks are hard gates.
- Security / CSO: **PASS with hard gates** — UUID RLS stays authoritative; keys, PII and private bodies remain forbidden; business-key changes are audited.
- Frontend: **PASS** — typed dynamic routes and progressive disclosure fit the current SPA/Fluent language.
- Backend: **NEEDS FIX until metric/task source freezes** — list/detail/overview need one vocabulary and successful outbox must leave tasks.
- Full-stack: **PASS** — no new ports, services or base paths.
- Knowledge Steward: **PASS** — P2 BYOK, P3 associations and P4 billing remain explicit deferrals.
