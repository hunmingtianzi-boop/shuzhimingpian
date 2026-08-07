# Change: close-card-editor-data-interaction-loop

## Why

The current editor is marked complete by older run artifacts, but the current source still violates the agreed product contract: FAQ is edited as free text instead of binding published knowledge, the admin preview maintains a simplified visual renderer separate from the public card, the directory and page blocks can drift, nested scroll containers make the workspace unstable, and card creation still exposes post-create editing semantics.

Those are one systemic defect, not independent polish tasks. The product needs one data-bound page composition from creation through editing, publishing and public use.

## What Changes

- Make enterprise/company and enterprise-employee records the identity sources for enterprise and employee cards.
- Make business, case and FAQ blocks reference live company-scoped published records; remove FAQ answer authoring from the card editor.
- Support FAQ `all_published` and `selected` modes with canonical knowledge-document IDs.
- Make company-owned enterprise/employee default configurations the creation baseline, with optional copy-from-card and customize-before-create flows.
- Use one ordered page-block document for structure, directory, editor canvas, draft, published snapshot and public rendering.
- Replace the nested dialog scroller with a viewport-bound editor: left structure/library, center operable page, right selected-block inspector; each pane owns its scroll.
- Reuse the public mobile-card renderer and restore its count-aware module variants instead of generic preview cards.
- Keep the identity block sortable, visible by default and non-hideable/non-deletable.
- Let an employee-card avatar update explicitly write through to the linked enterprise-employee profile.

## Impact

- Admin card creation/editor UI and styles.
- Shared page renderer and public mobile card rendering.
- Template schemas, admin/public projection and OpenAPI contract.
- Focused API, component and real-browser regression evidence.

## Superseded Evidence

Completion evidence from `enterprise-card-template-block-editor` and `unify-card-page-composer` is historical only. It cannot prove this change because the present workspace demonstrably fails the FAQ binding, single-renderer and scroll-ownership gates.
