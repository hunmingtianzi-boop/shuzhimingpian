## ADDED Requirements

### Requirement: The content directory is derived from page blocks
The system SHALL generate the public card directory from the visible blocks that opt into directory navigation. It MUST NOT persist an independent manual directory order.

#### Scenario: Reordering a directory-enabled block
- **WHEN** an editor changes the block order
- **THEN** the directory labels and targets update to the same order in the draft canvas and published page.

#### Scenario: Opting a block out of the directory
- **WHEN** an editor disables directory visibility for a visible block
- **THEN** the block remains on the page but is absent from the generated directory.

### Requirement: Directory navigation targets rendered blocks
The system SHALL associate each generated directory item with the corresponding rendered block and SHALL preserve scroll-to-section behavior.

#### Scenario: Activating a directory item
- **WHEN** a visitor activates a directory item
- **THEN** the public page scrolls to and focuses the matching block without changing the card's published composition.
