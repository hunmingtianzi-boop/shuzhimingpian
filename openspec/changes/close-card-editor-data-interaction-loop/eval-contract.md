# Eval Contract

## Hard gates

1. FAQ blocks have no answer textarea/body persistence and resolve `all_published` or ordered selected canonical FAQ documents.
2. All selected records are company-scoped and revalidated as published/public/current before preview and public rendering.
3. One block order drives editor structure, directory, center canvas, draft, published snapshot and public page.
4. Identity is sortable and data-bound but cannot be hidden or deleted.
5. New enterprise/employee cards choose default/copy/customize before persistence; employee cards require an active employee.
6. Desktop editor panes scroll independently without an outer content void; narrow layouts retain all critical operations.
7. Center canvas and public page use the same visitor-visible renderer and preserve original count-aware mobile variants.
8. Employee avatar upload writes through to the linked employee profile.
9. Focused API/admin/card tests and both affected production builds pass.
10. Real browser evidence covers create, data selection, drag, isolated scroll, save, publish and public interaction with no related console/network error.

## Verification commands

- API: focused `pytest` for template, knowledge projection, creation and employee identity.
- Admin: focused Vitest for editor, cards flow and employee avatar.
- Card web: focused Vitest for shared renderer, FAQ and public interactions.
- Browser: Playwright at admin `4174`, card `4173`, API `38101` using current worktree runtime.

## Stop rule

Do not claim completion until every hard gate has current-run evidence. Older completion receipts are stale for this corrected contract. Avoid repeating full suites during implementation; run focused checks after each owned work package and affected builds plus one integrated browser pass at the end.
