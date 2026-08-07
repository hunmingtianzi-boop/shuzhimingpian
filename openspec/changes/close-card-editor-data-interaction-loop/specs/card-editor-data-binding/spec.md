## ADDED Requirements

### Requirement: Card blocks bind canonical company data
The system SHALL resolve identity, business, case and FAQ content from canonical company-scoped sources and MUST NOT require duplicate protected content in template blocks.

#### Scenario: Resolving employee identity
- **WHEN** an employee card is previewed or published
- **THEN** its name, company, job information and avatar come from the linked active enterprise employee.

#### Scenario: Updating an employee avatar from card work
- **WHEN** an authorized editor replaces the employee avatar from the card flow
- **THEN** the linked enterprise-employee profile is updated and every associated card resolves the new avatar.

### Requirement: FAQ blocks use published knowledge
The system SHALL support `all_published` and `selected` FAQ modes using canonical knowledge-document identifiers.

#### Scenario: Automatic FAQ mode
- **WHEN** a FAQ block uses `all_published`
- **THEN** preview and public rendering show the company's current published, public FAQ documents and never read block body text.

#### Scenario: Selected FAQ mode
- **WHEN** an editor selects and orders FAQ documents
- **THEN** the saved block preserves those document IDs in order and the renderer revalidates company, type, status, version and visibility before display.

#### Scenario: FAQ becomes unavailable
- **WHEN** a selected FAQ is unpublished, made internal or removed
- **THEN** it disappears without exposing stale text and the rest of the page remains usable.
