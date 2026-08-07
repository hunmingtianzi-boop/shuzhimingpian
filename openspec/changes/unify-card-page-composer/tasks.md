## 1. Shared composition contract and compatibility

- [x] 1.1 Define the versioned `PageBlock` union, including sortable non-hideable `identity`, rich/media, FAQ/CTA/AI and catalogue-reference blocks in shared admin/public API types.
- [x] 1.2 Add server-side normalization and validation for block identity, order, visibility, directory settings and company-scoped content references.
- [x] 1.3 Add an additive compatibility builder that projects existing enterprise-card content into a stable ordered composition.
- [x] 1.4 Cover contract validation, identity visibility, stale-write and public-draft separation with focused API tests.

## 2. Ordered public page renderer and derived directory

- [x] 2.1 Extract reusable ordered page-block rendering from the legacy fixed-slot public-card flow.
- [x] 2.2 Implement identity resolution from enterprise or enterprise-employee data and render it at its composition position.
- [x] 2.3 Implement catalogue-reference blocks with safe unavailable-resource fallback and existing detail actions.
- [x] 2.4 Derive directory labels, anchors and active section behavior solely from visible directory-enabled blocks.
- [x] 2.5 Add public-card tests for reordered identity, business/case links, directory navigation and legacy-card compatibility.

## 3. Real-page editor canvas and convenient dragging

- [x] 3.1 Add the approved sortable dependency and configure pointer, touch and keyboard sensors with dedicated drag handles.
- [x] 3.2 Replace the split fixed/free structure list with the unified composition list, including clear drop indicator and selection synchronization.
- [x] 3.3 Render the public page renderer in the editor canvas with edit affordances that do not intercept visitor controls.
- [x] 3.4 Implement shared ordering state so structure list, canvas and directory preview update together before draft save.
- [x] 3.5 Add data-source inspector for the identity block and prevent hiding it while retaining sortable interaction.
- [x] 3.6 Make full preview open the actual public-card route for the draft or published snapshot.

## 4. Creation flow, styling and regression verification

- [x] 4.1 Update enterprise and employee card creation to choose a default composition, copy an existing card composition, or enter the composer before final creation.
- [x] 4.2 Align editor affordances and canvas styling with the existing mobile-card visual system rather than introducing a separate dashboard language.
- [x] 4.3 Add admin unit/integration tests for pointer and keyboard reordering, directory synchronization, identity constraints and preview route selection.
- [x] 4.4 Run focused API tests, admin/card-web test suites, typechecks and production builds.
- [x] 4.5 Perform real-browser desktop editor and mobile public-card verification: drag, save, publish, directory navigation, case opening, contact/AI interaction and zero relevant console errors.
