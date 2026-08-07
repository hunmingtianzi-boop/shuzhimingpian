## Context

The completed enterprise-template editor introduced `blocks[]`, but its public renderer continues to divide those blocks into type-specific slots around legacy enterprise sections. The result is a decorative sort control rather than a real page composer. User confirmation fixes the product rule: the data-bound identity card is draggable; it is visible by default and cannot be hidden.

## Goals / Non-Goals

**Goals:**

- One ordered page composition drives draft editor, generated directory and published public card.
- Preserve original mobile-card visual language and visitor interactions.
- Make drag convenient, explicit and accessible from both structure list and canvas.
- Retain company/employee source-of-truth identity fields and existing card compatibility.

**Non-Goals:**

- A generic freeform design tool, arbitrary CSS authoring or changing global public-card actions.
- Copying catalogue content into card data or redesigning employee/company master-data management.

## Decisions

### A versioned, discriminated PageBlock contract is the sole composition source

Extend the existing template snapshot to include a required `identity` block and typed reference blocks. Every consumer sorts the same list once and derives its own view; no consumer may classify a block into fixed display slots. This replaces the previous hybrid shell/free-block model. A fully unconstrained document builder was rejected because it weakens recognizable card identity and makes operational content fragile.

### Identity is a source-projected, non-hideable block

The `identity` block stores only source metadata and display options, not a copy of employee/company name, position or avatar. The renderer resolves fields from enterprise or enterprise-employee projection at read time. It receives the same sortable ID and drag handles as other blocks, but validation requires exactly one visible identity block. This reconciles flexibility with a reliable public subject.

### Catalogue content uses reference blocks

Introduce a generic `catalog_collection` block (configured for products, cases or documents) or normalize the existing case collection into that shape. The payload contains allowed IDs and presentation settings; public resolution applies company scope and published-state filters. This prevents stale case/business copies and retains existing detail navigation.

### The public component becomes the editor canvas

Extract ordered page rendering, section anchors and directory derivation into a reusable card-page renderer. The public route uses it without editor affordances. The admin canvas uses the same renderer with an `editing` adapter that adds selectable outlines and a handle layer while allowing normal safe visitor navigation. “Full preview” targets a draft-preview public route/token or the published URL; it is never a screenshot.

### Use dnd-kit for sortable interactions

Use `@dnd-kit/core` plus its sortable preset for pointer and keyboard sensors, a drag overlay and screen-reader announcements. The official package supports sortable lists and keyboard accessibility; a native HTML5-only approach was rejected because it is inconsistent across touch/pointer use and lacks a robust keyboard model. Limit activation to drag handles so page links remain usable. Package versions will be pinned using the workspace package manager during execution.

### Directory is a pure block projection

`deriveDirectory(blocks)` filters visible `directoryEnabled` blocks and maps stable IDs to title/anchor. It drives both public sticky navigation and editor directory preview. There is no separate editable “original directory” list.

## Risks / Trade-offs

- [Legacy cards rely on hard-coded sections] → derive a compatibility composition and regression-test public output before removing slots.
- [Identity moves below long content] → allow it by explicit user decision, but keep identity visible and make directory position reflect it.
- [Drag conflicts with content interaction] → dedicated handle, activation distance and separate edit-mode overlay; visitor mode has no drag affordances.
- [Reference content is unpublished or cross-company] → validate on write and filter again on public read; report editable readiness issues without leaking details.
- [New dependency affects admin bundle] → constrain it to the editor route and verify production build plus keyboard behavior.

## Migration Plan

1. Add additive page-composition schema and deterministic compatibility builder; no destructive data migration.
2. Make API read/write validate the new contract while accepting old snapshots through compatibility projection.
3. Replace public renderer slotting with the reusable ordered renderer behind focused tests.
4. Replace editor list/canvas with dnd-kit-backed composer, then enable full public preview.
5. Validate draft/publish separation, existing card compatibility and browser interaction. Rollback disables the new editor route/projection while retaining additive snapshots.

## Open Questions

- System-level bottom actions and AI remain outside the first composition model unless a later product decision promotes them to page blocks.
