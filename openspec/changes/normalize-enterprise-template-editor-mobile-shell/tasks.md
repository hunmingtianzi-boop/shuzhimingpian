# Stable Work Packages

## WP1 — Freeze original mobile shell and regression contract

- Scope: encode original header, directory, fixed sections, action bar and design tokens as immutable behavior around optional template blocks.
- Acceptance: tests fail when a published template hides any fixed directory or section.

## WP2 — Normalize public template rendering

- Scope: always render the original mobile shell; insert optional blocks into the original content flow; normalize block markup and styles to existing `bp-*` section language.
- Acceptance: a published template visibly extends the original page, 7 fixed directory items and all fixed paths remain available, and absent assets degrade safely.
- Depends on: WP1.

## WP3 — Rebuild editor information architecture

- Scope: retain current behaviors while separating fixed modules from free modules and replacing the custom phone theme with an original-shell preview.
- Acceptance: users can understand what is permanent versus editable, and can add/reorder/edit/delete free modules without losing original navigation or sections.
- Depends on: WP1.

## WP4 — Visual and responsive normalization

- Scope: inherit project colors, typography, spacing, chips, section headings, buttons and responsive rules across the editor canvas and preview.
- Acceptance: desktop editor and 390px preview are visually continuous with the original card and have no horizontal overflow.
- Depends on: WP2 and WP3.

## WP5 — Browser loop and regression verification

- Scope: rerun focused UI tests/builds, publish a template, inspect admin and public routes in a real browser, compare screenshots and complete independent visual review.
- Acceptance: every hard gate has current evidence and the visual rubric is at least 4/5 per dimension without functional regression.
- Depends on: WP2–WP4.
