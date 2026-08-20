## ADDED Requirements

### Requirement: Plugin blocks separate host fields from plugin configuration
The system SHALL store common page composition fields independently from plugin-owned configuration and SHALL validate each configuration using the exact referenced plugin contribution and version.

#### Scenario: Save a valid FAQ plugin block
- **WHEN** an administrator saves an FAQ block using an available plugin version and valid FAQ configuration
- **THEN** the draft preserves the common ordering fields, exact plugin reference and normalized FAQ configuration

#### Scenario: Submit configuration for a different contribution
- **WHEN** a block references the action contribution but contains an FAQ-only configuration
- **THEN** the server rejects the draft without changing the previous document

### Requirement: Public rendering uses a server-authorized Render Plan
The system SHALL resolve published plugin blocks under the current tenant/company scope and return only public presentation data and allowed host actions to the public renderer.

#### Scenario: FAQ selects another company's knowledge document
- **WHEN** a published or draft FAQ configuration references a knowledge document outside the current company
- **THEN** publication is rejected or the invalid legacy reference is omitted without exposing the foreign document

### Requirement: Identity is a required system contribution
The system SHALL require exactly one visible identity contribution in every card page and SHALL prevent enterprise users from deleting, hiding or disabling it.

#### Scenario: Disable the identity plugin
- **WHEN** an enterprise administrator attempts to disable the system identity contribution
- **THEN** the operation is rejected and existing card identity rendering remains available

### Requirement: FAQ and action collection prove independent plugin behavior
The system SHALL provide FAQ and action collection as separately registered built-in plugins with their own configuration, validation, editor and public rendering contributions.

#### Scenario: Disable FAQ but keep actions
- **WHEN** an enterprise disables FAQ while the action plugin remains enabled
- **THEN** new drafts cannot add FAQ, existing publication policy is applied, and valid action blocks remain editable and usable

#### Scenario: Configure an unsafe action
- **WHEN** an action plugin configuration contains an unsafe URL, path traversal or malformed phone target
- **THEN** the server rejects the configuration and the target is never emitted to the public Render Plan

### Requirement: Legacy blocks have a deterministic compatibility projection
The system SHALL read version-one identity, FAQ, action collection and other legacy blocks through stable built-in plugin mappings without rewriting existing published snapshots.

#### Scenario: Read an existing published card
- **WHEN** a public card still contains a version-one page document
- **THEN** the compatibility adapter produces a stable ordered Render Plan with equivalent visible content and actions
