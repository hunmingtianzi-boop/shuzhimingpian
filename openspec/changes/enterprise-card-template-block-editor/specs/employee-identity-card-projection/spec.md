## ADDED Requirements

### Requirement: Employee card identity is projected from the bound member
The system SHALL derive an employee card's display name, contact details, job title and portrait from its active owner membership and user identity rather than accepting a second editable identity copy on the card.

#### Scenario: Update an employee title
- **WHEN** a company administrator changes an employee's membership profile title
- **THEN** that employee's card projection reflects the updated title without a separate card identity edit

### Requirement: Employee card retains only card-specific expression
The system SHALL project personal business summary from the bound membership while permitting employee-card editing of AI assistant text and recommendation content, and SHALL prevent card edits from overwriting member identity fields.

#### Scenario: Edit employee card assistant text
- **WHEN** an administrator updates an employee card's assistant welcome message
- **THEN** the message changes while the employee identity remains sourced from the membership projection

### Requirement: Employee card owner remains company-scoped and active
The system SHALL reject creation, update or publication of an employee card whose owner is not an active member of the current company.

#### Scenario: Owner membership becomes inactive
- **WHEN** a bound employee membership is disabled
- **THEN** publishing the employee card is rejected and public identity data is not newly exposed
