# P0/P1 Implementation Tasks

> 本文件满足 OpenSpec 1.5 apply 的任务格式；`plan.md` 仍是执行进度与证据的唯一真源。既有已上线能力作为基线，不在本轮重复施工。

## 1. Freeze P0/P1 shared contracts

- [x] 1.1 Freeze separate platform-admin and enterprise-admin IA, dynamic detail routes, compatibility redirects, permission and entitlement mappings.
- [x] 1.2 Freeze enterprise identity, cardless provisioning, operational metrics, operational-task and settings-split API schemas with forbidden-field allowlists.
- [x] 1.3 Update the current change design, specs, eval contract and multi-lens review without creating another progress source.

## 2. Enterprise identity and cardless provisioning

- [ ] 2.1 Add current-head additive migration and ORM contracts for legal identity, short name, subject type, unique business tenant identifier and nullable legacy onboarding initial-card linkage.
- [ ] 2.2 Refactor direct and document-assisted enterprise provisioning to create tenant/company/admin/temp credential/default entitlements without creating a card, card slug or public URL.
- [ ] 2.3 Preserve existing confirmed/provisional sessions, cleanup paths, RLS, idempotency, one-time credential regeneration and selected-candidate draft materialization.
- [ ] 2.4 Split enterprise identity update from AI, notification and privacy settings with optimistic versioning, uniqueness checks and audit.

## 3. Platform operations read models and APIs

- [ ] 3.1 Replace platform overview/list/detail read models with one shared metric vocabulary for enterprise state, 30-day activity, visits, unique visitors, conversations, consented leads, cards, tasks and service risk.
- [ ] 3.2 Add enterprise list filters/sorts and independent detail projections for overview, operations, members/cards, content, recent tasks, AI status, entitlements and activity.
- [ ] 3.3 Replace outbox-heavy task projection with normalized actionable operations sourced from onboarding, imports, content review, enterprise risk and service-validity risk.
- [ ] 3.4 Add timeline/company task views and shared company/status/type/time filters while preserving audit and service-health diagnostics.

## 4. Platform console UI

- [ ] 4.1 Remove employee overview, visitor overview and audit from daily navigation; preserve compatibility redirects and audit deep-link access.
- [ ] 4.2 Replace the enterprise detail drawer with refreshable `/platform/enterprises/:companyId/:section` pages and eight truthful sections.
- [ ] 4.3 Rebuild platform overview and enterprise list on server metrics, filters, risk states and compact zero-data states.
- [ ] 4.4 Implement task timeline/company views and enterprise-scoped recent-task navigation without raw event codes.

## 5. Enterprise workspace IA and object journeys

- [ ] 5.1 Reorganize AppShell into Workbench, Customer Growth, Content and Intelligence, Enterprise Governance and More Tools; only the active work domain is expanded.
- [ ] 5.2 Add visit detail, visitor profile, conversation, opportunity, contextual lead and product create/detail routes while preserving object permissions and entitlements.
- [ ] 5.3 Add real cross-object navigation for visit/profile/conversation/opportunity/consented-lead and import/content/card-reference journeys.
- [ ] 5.4 Keep product/case/FAQ as master data, expose server-derived card-reference counts and preserve card-level display overrides.

## 6. Settings separation and notification noise control

- [ ] 6.1 Keep company profile limited to identity and outward presentation; move answer boundaries to `/ai/answer-policy` and reserve enterprise model access for deferred P2.
- [ ] 6.2 Move visit/WeCom recipients and delivery preferences to notification settings; move personalization consent/version/retention to data and privacy.
- [ ] 6.3 Notify consented leads and high-intent activity in real time, aggregate ordinary visits daily, and retain idempotent in-app/WeCom delivery with explicit recipient scope.

## 7. Verification and release evidence

- [ ] 7.1 Run focused migrations, API/RLS/security, worker, OpenAPI, admin tests/build and scope review with no secret or forbidden-field regression.
- [ ] 7.2 Run real platform and enterprise website journeys at desktop and 390px, including cardless provisioning, detail deep links, task views, visit/product journeys and settings separation.
- [ ] 7.3 Map AC receipts into the current run proof pack, perform independent Checker review, and report remaining P2-P4 deferrals without committing or pushing unless separately authorized.

## 8. Enterprise model access (P2)

- [ ] 8.1 Reuse enabled platform LLM profiles as the provider/model whitelist and active default; add company-scoped managed/BYOK configuration with encrypted keys, budget ceiling and optimistic versioning.
- [ ] 8.2 Route company Chat/import runtime through the effective company configuration, add self-service and delegated APIs, audit every change and notify the affected enterprise without impersonation.
- [ ] 8.3 Add a separate enterprise model-access UI and verify all secret, whitelist, budget, stale-write and fallback boundaries.

## 9. Association governance extension point (P3)

- [ ] 9.1 Model association memberships as cross-company references without parent-tenant semantics or changes to company RLS ownership.
- [ ] 9.2 Add platform-only aggregate membership management with tier, seat and benefit allocation fields; defer association actors, formal permission matrices and billing.
- [ ] 9.3 Verify type constraints, duplicate prevention, platform-only access and absence of member-company private data.
