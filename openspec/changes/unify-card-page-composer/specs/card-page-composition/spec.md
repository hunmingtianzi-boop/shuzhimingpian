## ADDED Requirements

### Requirement: A card has one ordered page-block composition
The system SHALL store draft and published card-page compositions as an ordered list of versioned blocks. The public renderer, editor canvas and generated directory MUST consume the same order.

#### Scenario: Reordering a visible block
- **WHEN** an authorized editor moves a block from one position to another and saves the draft
- **THEN** the returned draft, editor structure list and draft canvas expose the new order.

#### Scenario: Publishing the composition
- **WHEN** an authorized editor publishes a valid draft
- **THEN** the public card renders its visible blocks in the published order and never reads the draft snapshot.

### Requirement: The identity block is data-bound but positionable
The system SHALL provide exactly one `identity` block for each enterprise or employee card composition. The block MUST resolve its display fields from the relevant enterprise or enterprise-employee data source, MUST be sortable with other blocks, and MUST be visible by default and not hideable through the editor.

#### Scenario: Moving the identity block
- **WHEN** an editor drags the identity block below a content block
- **THEN** the saved and public pages place the resolved identity presentation below that content block.

#### Scenario: Attempting to hide the identity block
- **WHEN** an editor submits a composition with the identity block hidden or absent
- **THEN** validation rejects the change with a deterministic field error.

### Requirement: Business material is referenced by content blocks
The system SHALL represent product, business and case collections as configurable content blocks that store eligible resource references rather than static copies of protected resource fields.

#### Scenario: Selecting a case collection
- **WHEN** an editor selects published cases from its company for a case block
- **THEN** the public page renders those cases as operable links to their existing detail behavior.

#### Scenario: Referenced material becomes unavailable
- **WHEN** a referenced resource is unavailable to the public renderer
- **THEN** the block degrades without exposing unavailable content and the remaining page stays operable.

### Requirement: Existing cards retain a compatible composition
The system SHALL derive a compatible default composition for cards that predate the page-block composition and SHALL preserve their publicly available content.

#### Scenario: Loading an existing enterprise card
- **WHEN** a public enterprise card has no saved page-block composition
- **THEN** the renderer derives a stable compatibility composition from the card's existing identity and content projections.
