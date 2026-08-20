## ADDED Requirements

### Requirement: Platform releases and company installations are separate states
The system SHALL allow only platform-available plugin releases to be enabled by a company and SHALL preserve company-specific status, grants and optimistic version independently from the platform release record.

#### Scenario: Enable an unavailable plugin release
- **WHEN** a company attempts to enable a plugin version that is not available in the platform registry
- **THEN** the operation is rejected and the company installation remains unchanged

### Requirement: Publication pins an exact enabled plugin version
The system SHALL publish only plugin blocks whose exact versions are available, enabled for the company and covered by the company's capability grants, and SHALL preserve the previous public snapshot on failure.

#### Scenario: Revoke a required grant before publish
- **WHEN** an administrator publishes a draft after a required plugin capability grant has been revoked
- **THEN** publication fails with an actionable readiness issue and the previous snapshot remains public

#### Scenario: Publish while a compatible newer release exists
- **WHEN** a draft references version 1.0.0 and version 1.1.0 is also available
- **THEN** publication continues to pin 1.0.0 until an administrator explicitly upgrades the draft

### Requirement: Enterprise disablement does not silently rewrite published cards
The system SHALL prevent a company-disabled plugin from being added to new drafts or newly published, while leaving an already published fixed-version snapshot unchanged unless an explicit public-removal policy is invoked.

#### Scenario: Disable a plugin used by the current public snapshot
- **WHEN** a company disables that plugin
- **THEN** the existing public snapshot remains deterministic, new publication is blocked until resolved, and the disablement is audited

### Requirement: Platform emergency kill switch safely degrades public output
The system SHALL allow a platform operator to immediately suspend a faulty plugin release, omit affected optional blocks from public Render Plans, preserve a safe identity fallback, and restore service without rewriting card snapshots.

#### Scenario: Kill the FAQ plugin release
- **WHEN** the platform suspends the FAQ release used by a published card
- **THEN** the FAQ block is omitted, remaining blocks and directory remain usable, and health/audit records identify the degraded plugin

### Requirement: Referenced plugin releases remain recoverable
The system SHALL prevent deletion of a plugin release while any draft or published snapshot references it and SHALL support disablement or compatibility implementations instead.

#### Scenario: Delete a referenced release
- **WHEN** an operator attempts to delete a plugin version referenced by a published snapshot
- **THEN** deletion is rejected and the snapshot remains renderable or safely degradable
