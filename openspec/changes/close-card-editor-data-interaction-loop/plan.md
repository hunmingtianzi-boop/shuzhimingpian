# Implementation Plan: close-card-editor-data-interaction-loop

## Contract

- Mode: ordinary Spec-Strict execution. The user explicitly cancelled GOAL usage; no scoring loop or native GOAL state is used.
- Strategy: sync-then-parallel. WP1 freezes shared schema and projection; only then may backend, shared renderer and creation/editor workers proceed in non-overlapping files.
- Runtime: retain API `38101`, admin `4174`, card web `4173`; no port change.
- Source authority: current user message `可以 搞吧`, scoped to this worktree and change.

## Progress

- [ ] 1. WP1: freeze the additive FAQ/data projection contract, add evaluator and record failing baseline.
- [ ] 2. WP2: implement canonical FAQ/identity/catalogue resolution and creation services with negative tests.
- [ ] 3. WP3: implement one shared visitor-visible renderer and restore mobile/count-aware variants.
- [ ] 4. WP4: implement viewport-bound three-pane editor, synchronized selection/drag/directory and data inspectors.
- [ ] 5. WP5: close default/copy/customize-before-create and employee avatar write-through flows.
- [ ] 6. WP6: integrate, run focused verification/builds/browser evidence, independent check and preflight.

## Parallel contract

- Frozen shared fields: `faqMode` / `faq_mode`, `faqDocumentIds` / `faq_document_ids`, modes `all_published|selected`, canonical key `KnowledgeDocument.id`.
- Backend owns Python schemas/stores/routes/tests; shared renderer owns `packages/card-page-renderer` and card-web module presentation; admin owns editor/cards components and admin styles/tests.
- Do not edit the same shared type/schema concurrently. Lead integrates API types/OpenAPI and all CSS.
- Workers must preserve existing dirty changes and never revert another worker.

## Evidence and rollback

- Run records: `openspec/changes/close-card-editor-data-interaction-loop/runs/20260807-standard-execution/`.
- Focused evidence follows `eval-contract.md`; no repeated broad suites during iteration.
- All model changes are additive. A failed save/publish leaves the prior published snapshot intact. No destructive migration or reset is allowed.
