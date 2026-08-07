# Execution Plan: normalize-enterprise-template-editor-mobile-shell

## Contract

- Goal: make the template editor and published template feel native to the existing mobile business card while preserving every original navigation and fixed module.
- Change: `normalize-enterprise-template-editor-mobile-shell`.
- Run: `20260804-mobile-style-normalization`.
- Mode: Spec-Strict visual normalization loop.
- Risk: public-card structure regression and editor interaction regression; no data/API migration.

## Progress

- [x] 1. Capture the current editor and original 390px mobile card baseline; locate the condition that hides the original directory and fixed modules.
- [x] 2. Add regression tests and normalize public rendering so templates extend the original shell.
- [x] 3. Rebuild the editor around fixed/free module directories and an original-shell preview.
- [x] 4. Normalize visual tokens and responsive behavior against the original mobile card.
- [x] 5. Run tests/builds, browser iteration, screenshot comparison and independent visual verification.

## Failure / Rollback

- Keep the existing template document and API untouched.
- If a visual refactor breaks editing, restore the previous editor interaction component while retaining the public-shell preservation fix.
- No destructive rollback or data deletion.

## Evidence

- Baseline screenshots: `output/playwright/editor-style-baseline.png` and `output/playwright/mobile-card-38080-reference.png`.
- Unit/component tests for fixed shell visibility and editor interactions.
- Real browser screenshots at 1440px and 390px after publish.

## Completion Evidence

- Public mobile regression: 18 files / 120 tests PASS; production build PASS.
- Admin editor component: 3 tests PASS; production build PASS.
- Admin full run: 33/34 files and 150/151 tests passed; the unrelated CatalogPage destructive-confirmation timing case passed immediately when rerun alone.
- Browser: 1440px editor and 390px public card have no console errors; editor has no horizontal document overflow.
- Structure: public card exposes the original seven-item directory and fixed intro/business/cases/trust/FAQ/AI sections together with optional blocks.
- Independent visual verdict: 92/100 PASS against the original 390px card reference.
- Scope hygiene: `git diff --check` PASS, with only the existing OpenAPI CRLF normalization warning.
