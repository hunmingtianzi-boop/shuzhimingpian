# enterprise-card-template-rendering Delta Specification

## MODIFIED Requirements

### Requirement: Published templates extend the original mobile card

The public renderer MUST keep the existing mobile-card shell, fixed directory and fixed sections before and after a template is published.

#### Scenario: Enterprise has a published template

- **WHEN** a visitor opens an enterprise card with a published template
- **THEN** the original seven directory entries remain visible
- **AND** the original overview, introduction, business, cases, resources, FAQ and AI paths remain available
- **AND** valid optional blocks appear in the original content flow using the existing section language.

#### Scenario: Optional block is unavailable

- **WHEN** an optional block has missing or unavailable content
- **THEN** it degrades safely without hiding or breaking any fixed section or bottom action.

### Requirement: Mobile visual language remains continuous

Template blocks MUST inherit the existing public card's typography, spacing, section title, surface, chip and action styles.

#### Scenario: Visitor scrolls from fixed to optional content

- **WHEN** a visitor moves between original and optional sections
- **THEN** the hierarchy and interaction language remain visually continuous
- **AND** there is no second branded header or template-specific navigation shell.
