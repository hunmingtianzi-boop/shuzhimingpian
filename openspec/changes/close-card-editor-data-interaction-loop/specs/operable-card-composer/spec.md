## ADDED Requirements

### Requirement: The editor uses one operable page composition
The structure list, center page, inspector, directory, saved draft, published snapshot and public page SHALL consume the same ordered block document.

#### Scenario: Reorder any block
- **WHEN** an editor drags the identity or another block from a dedicated handle
- **THEN** structure, directory and center page update immediately and the saved/public order matches after publish.

#### Scenario: Attempt to hide identity
- **WHEN** an editor attempts to hide or delete the identity block
- **THEN** the UI prevents it and server validation rejects a forged invalid document.

### Requirement: Editor panes have isolated scroll ownership
The desktop editor SHALL provide left structure/library, center operable page and right inspector panes with independent vertical scrolling and no nested outer-page scroll ownership.

#### Scenario: Scroll the inspector
- **WHEN** the selected block has a long inspector form
- **THEN** only the right pane moves while the structure and center page retain their positions.

### Requirement: Preview and public page share visual components
The center canvas SHALL use the same visitor-visible module renderer and tenant tokens as the public page while adding editor-only selection and drag affordances.

#### Scenario: Operate preview content
- **WHEN** the editor activates a safe case, contact, directory or AI control in preview mode
- **THEN** it performs the corresponding visitor interaction or an explicit edit-safe equivalent instead of acting as a static mock.
