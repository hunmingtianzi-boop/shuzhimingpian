## ADDED Requirements

### Requirement: The editor has a real public-page canvas
The system SHALL render the editor's central canvas from the same public card component and draft page composition used by the public card. The canvas MUST retain safe visitor interactions such as opening a case detail, contact action and AI entry.

#### Scenario: Editing a selected block
- **WHEN** an editor selects a block in the structure list or on the canvas
- **THEN** the properties panel selects that same block and the canvas marks it without replacing the public-page rendering.

#### Scenario: Opening full preview
- **WHEN** an editor chooses full preview
- **THEN** the system opens the actual public-card route for the draft or published version rather than a static preview mock.

### Requirement: Blocks are conveniently sortable by drag handle
The system SHALL provide pointer and keyboard sortable controls on a dedicated drag handle for every positionable block. The user MUST receive a clear drop indicator and the interaction MUST not hijack links or buttons inside block content.

#### Scenario: Pointer drag in the structure list
- **WHEN** an editor drags a block handle to a new list position
- **THEN** the list, directory preview and public-page canvas reorder immediately before save.

#### Scenario: Keyboard reorder
- **WHEN** an editor uses the keyboard sortable control on a focused block handle
- **THEN** the block changes position with an announced result and the same synchronized surfaces update.

#### Scenario: Dragging from the page canvas
- **WHEN** an editor initiates a drag from the edit handle displayed for a canvas block
- **THEN** the composition reorders using the same block identifier and does not trigger the block's visitor action.
