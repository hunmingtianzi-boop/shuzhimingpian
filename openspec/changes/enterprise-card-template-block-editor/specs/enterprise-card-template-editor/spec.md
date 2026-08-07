## ADDED Requirements

### Requirement: Enterprise template draft is a controlled document
The system SHALL allow a company administrator to create and update an enterprise-card template draft containing only supported, versioned content-block types.

#### Scenario: Add and reorder a supported block
- **WHEN** a company administrator adds an image gallery and moves it before a case collection
- **THEN** the draft persists stable block identifiers, explicit order, visibility and type-valid payloads

#### Scenario: Reject unsupported block payload
- **WHEN** a client submits an unknown block type or invalid payload
- **THEN** the system rejects the request without altering the draft

### Requirement: Enterprise card basic settings are complete before publish
The system SHALL require a company name, brand identity, business positioning and a valid contact route before publishing an enterprise template.

#### Scenario: Publish with missing required information
- **WHEN** an administrator tries to publish a template missing a required setting
- **THEN** the response identifies each missing setting and no public snapshot is changed

### Requirement: Publishing produces an isolated public snapshot
The system SHALL publish a validated immutable template snapshot using optimistic card version control.

#### Scenario: Publish a valid current draft
- **WHEN** an administrator publishes a valid draft with the current card version
- **THEN** the public snapshot is updated and subsequent public reads use that snapshot

#### Scenario: Publish a stale draft
- **WHEN** an administrator publishes using a stale card version
- **THEN** the system returns a conflict and preserves both the newer draft and public snapshot

### Requirement: Template media is constrained and company-scoped
The system SHALL accept images only through the existing company-scoped asset service, accept videos only as approved HTTPS links with a cover asset, and resolve case references only within the same company.

#### Scenario: Add a cross-company case reference
- **WHEN** an administrator submits a case identifier outside the current company
- **THEN** the system rejects the block and does not expose the foreign case
