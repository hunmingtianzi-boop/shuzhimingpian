# enterprise-card-template-editor Delta Specification

## MODIFIED Requirements

### Requirement: Editor inherits the mobile card product language

The enterprise template editor MUST distinguish immutable mobile-card structure from optional free modules and MUST preview content inside the existing mobile-card shell.

#### Scenario: Administrator opens the editor

- **WHEN** an administrator opens an enterprise template
- **THEN** the interface identifies the fixed navigation and system sections separately from optional modules
- **AND** the preview contains the original top bar, enterprise identity, seven-item directory and bottom actions
- **AND** no independent card theme replaces the product design language.

#### Scenario: Administrator manages a free module

- **WHEN** the administrator adds, selects, reorders, duplicates or removes an optional module
- **THEN** the module changes are reflected in the canvas and preview
- **AND** fixed navigation and system sections remain present and non-removable.

### Requirement: Editor remains responsive and operable

The editor MUST remain keyboard-operable and MUST not overflow horizontally on supported desktop and narrow layouts.

#### Scenario: Narrow viewport

- **WHEN** the editor is viewed at a narrow width
- **THEN** directory, canvas and settings remain reachable through a compact layout
- **AND** primary save/publish actions remain available.
