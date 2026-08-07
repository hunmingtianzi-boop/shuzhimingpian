# Design: one data-bound card composition loop

## Context

The product is a multi-enterprise digital business-card platform. Enterprise administrators create company and employee cards; visitors use the resulting mobile H5 as an actual page, not a design screenshot. The approved visual direction is inherited: restrained, clear and credible, preserving the original mobile-card language and tenant theming.

## Goals

- One source of identity and catalogue truth.
- One ordered page composition and one visual renderer.
- A fast editor whose three work areas scroll independently.
- Creation that chooses a baseline before the card is persisted.
- Published/public filtering that never leaks draft, internal or cross-company content.

## Non-goals

- Arbitrary CSS, absolute-position canvas or a generic website builder.
- Copying employee, FAQ, business or case bodies into template blocks.
- Redesigning global brand/navigation or changing runtime ports.
- Making knowledge editing available inside the card editor.

## Decisions

### 1. One additive page-block contract

Keep the existing compatible schema and extend data-bound blocks additively. Every document contains exactly one visible `identity` block. All surfaces order the same `blocks[]` once. The directory is a pure projection of visible, directory-enabled blocks.

### 2. FAQ is a live reference block

The FAQ block stores `faq_mode` (`all_published` or `selected`) and ordered `faq_document_ids`. It never stores question/answer text in `body`. Resolution uses canonical `KnowledgeDocument.id`, company scope, `source_type=faq`, current version, published status and public visibility. `all_published` follows newly published FAQ automatically; `selected` preserves chosen order and silently removes unavailable records.

### 3. Default configuration is a factory baseline

Each company owns one enterprise-card and one employee-card default composition. A new card chooses default, an existing card baseline or customize-before-create. Default configuration copies layout/configuration only; data-bound content resolves live. Existing cards do not change when the default changes.

### 4. Identity remains single-source

Enterprise identity resolves from company profile. Employee identity resolves from active company membership/user data. Name, company, department, title and avatar are not editable duplicates in the template. An avatar action exposed during employee-card work writes to the linked employee profile with explicit scope feedback.

### 5. The public component is the center canvas

Extract the visitor-visible module rendering into a shared component boundary consumed by admin and card-web. The editor adapter adds selection, drag handles and safe action interception but does not restyle module contents. A full-preview action opens the actual draft/published page route.

### 6. Viewport-bound three-pane workspace

Use a dedicated full-screen editor surface with a fixed header and a body sized to the remaining viewport. Left structure/library, center page canvas and right inspector each use `min-height: 0` and own `overflow-y: auto`. The outer dialog/page does not scroll. At narrower widths, the inspector becomes a drawer/tab without removing critical operations.

### 7. Restore visual variants, not generic cards

Public business, cases, images and FAQ retain count-aware variants and existing tenant tokens. Editor chrome uses flat grouping, separators and spacing hierarchy; it does not wrap every control in a rounded card. No decorative side-stripe or new brand style is introduced.

## Failure and rollback

- Changes remain additive; legacy template documents are normalized through compatibility defaults.
- A failed publish preserves the previous published snapshot.
- Unavailable selected content degrades to the remaining eligible records.
- If the shared renderer regresses public output, keep stored documents and switch the projection back while fixing the renderer; do not delete data.
