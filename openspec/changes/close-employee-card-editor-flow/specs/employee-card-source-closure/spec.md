## ADDED Requirements

### Requirement: Enterprise employee is the employee-card identity source

The system SHALL treat the active same-company enterprise employee as the source for an employee card's name, job title, avatar, and business summary.

#### Scenario: Administrator creates an employee card

- **WHEN** an administrator selects an active enterprise employee and submits a new employee card
- **THEN** the card SHALL bind that employee's user ID and project identity fields from the enterprise employee record
- **AND** the server SHALL reject a missing, foreign, disabled, or duplicate employee binding.

### Requirement: Employee contact exposure is explicit

The system SHALL not publicly expose an employee's mobile number or email unless the employee card has explicitly enabled that field.

#### Scenario: Public visitor reads an employee card

- **WHEN** the card enables only mobile visibility
- **THEN** the public card SHALL return the current mobile contact only
- **AND** it SHALL omit the email contact even when the employee record has an email.

### Requirement: Admin editor guides instead of exposing implementation IDs

The admin UI SHALL present active enterprise employees by human-readable identity and SHALL not ask an administrator to enter a user ID.

#### Scenario: Admin opens the employee-card create flow

- **WHEN** the create drawer opens
- **THEN** it SHALL first provide an employee selector and a default/copy content choice
- **AND** identity fields SHALL be visibly sourced rather than duplicated editable inputs.
