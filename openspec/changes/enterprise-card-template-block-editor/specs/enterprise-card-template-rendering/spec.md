## ADDED Requirements

### Requirement: Public enterprise cards render only published template content
The system SHALL render an enterprise public card from its published template snapshot and SHALL not expose draft-only blocks or media.

#### Scenario: Draft differs from published template
- **WHEN** an administrator saves a new draft without publishing it
- **THEN** public visitors continue to see the previous published block order and content

### Requirement: Public rendering safely degrades invalid references
The system SHALL omit a block whose referenced asset, video cover, or case is no longer public or within scope, while leaving the rest of the published card usable.

#### Scenario: Referenced case is no longer published
- **WHEN** a case referenced by a published template is unavailable
- **THEN** the case block is hidden and no unauthorized data is returned

### Requirement: Preview and public renderer share a single projection
The system SHALL use the same normalized template projection for the admin mobile preview and the public enterprise card renderer.

#### Scenario: Preview a saved draft
- **WHEN** an administrator saves a valid enterprise template draft
- **THEN** the preview renders the same block types and validation behavior as the public renderer except that it uses the draft projection
