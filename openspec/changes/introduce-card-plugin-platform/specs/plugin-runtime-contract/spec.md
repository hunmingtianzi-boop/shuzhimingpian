## ADDED Requirements

### Requirement: Plugins have a canonical versioned manifest
The system SHALL identify each built-in plugin by a canonical namespaced ID and semantic version, declare a compatible host API range, permissions and contributed surfaces, and reject invalid, duplicate or incompatible registrations before serving affected traffic.

#### Scenario: Two implementations claim the same contribution
- **WHEN** startup or build discovery finds the same plugin ID, version and contribution ID more than once
- **THEN** validation fails with a deterministic conflict and the ambiguous contribution is not served

#### Scenario: A plugin requires an unsupported host API
- **WHEN** a plugin manifest does not include the current host API version in its compatibility range
- **THEN** the plugin release is unavailable and cannot be enabled or published

### Requirement: Required runtime surfaces remain contract-compatible
The system SHALL verify that every card-block contribution has the required public renderer, admin editor metadata and server validator/resolver for the same plugin identity and serialized contract.

#### Scenario: The API implementation is missing
- **WHEN** a built-in card-block plugin is present in the frontend registry but absent from the API registry
- **THEN** build or startup validation fails before a page using that plugin can be published

### Requirement: Plugins use scoped host capabilities
The system SHALL expose host operations to a plugin only through declared, granted and tenant/company-scoped capability handles, and SHALL reject undeclared or ungranted calls.

#### Scenario: A plugin calls an undeclared catalogue capability
- **WHEN** the plugin attempts to read catalogue data without declaring and receiving `catalog.published.read`
- **THEN** the host denies the call, returns no catalogue data and records the denied capability attempt

### Requirement: Runtime plugin code is platform-delivered in phase one
The system SHALL load only built-in plugin code delivered with the current platform release and SHALL NOT download or execute enterprise-supplied frontend or backend code.

#### Scenario: Enterprise configuration contains a remote module URL
- **WHEN** an enterprise attempts to configure a plugin implementation using a remote script or package URL
- **THEN** the configuration is rejected and no remote code is fetched or executed
