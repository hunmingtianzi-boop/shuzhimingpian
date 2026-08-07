## ADDED Requirements

### Requirement: Configuration is chosen before card creation
The system SHALL let an authorized editor choose a company default, an existing-card baseline or customize-before-create before persisting a new enterprise or employee card.

#### Scenario: Create with default configuration
- **WHEN** the editor chooses the matching company default
- **THEN** the new draft card is created with that layout without requiring repetitive editing.

#### Scenario: Customize before create
- **WHEN** the editor chooses customization
- **THEN** the composer opens with an in-memory baseline and the card is not persisted until the editor saves creation.

### Requirement: Employee cards require an enterprise employee
The system SHALL require one active company employee for every employee card and SHALL project identity from that relationship.

#### Scenario: Attempt unbound employee card creation
- **WHEN** no eligible employee is selected
- **THEN** creation remains unavailable with a clear field error.
