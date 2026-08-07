# Eval Contract: unified card page composer

## Hard gates

1. The page model contains exactly one visible `identity` block. It can be reordered, but the editor cannot hide or delete it.
2. Draft save, publish projection, directory navigation, editor preview and public page use the same ordered block contract.
3. `business_collection` and `case_collection` persist explicit catalogue references and public rendering resolves the selected live records.
4. The editor exposes an operable actual-page preview; public product and case cards open their existing detail routes.
5. The affected API, admin and card test groups pass, both web production builds pass, and the public page has no console errors.

## Evidence

- Automated receipts are recorded in `runs/20260806-card-page-composer/verification/evaluator-receipt.json`.
- Browser screenshots and interaction observations are indexed by `artifact-manifest.json`.
- An independent read-only checker records the final verdict in `checker-receipt.md`.

## Stop rule

The change is complete only after every hard gate is PASS and the independent checker reports PASS. Existing non-blocking development warnings may remain when they are unrelated to the composer and are explicitly recorded.
