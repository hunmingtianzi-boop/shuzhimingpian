## ADDED Requirements

### Requirement: Platform defines stable commercial features and plan defaults
The system SHALL expose stable feature identifiers and starter, professional and enterprise plan defaults without embedding customer-specific prices in feature authorization logic.

#### Scenario: Resolve a professional plan
- **WHEN** an enterprise is assigned the professional plan without overrides
- **THEN** all starter and professional features are enabled and enterprise-only features are disabled

### Requirement: Platform operators control company plan and feature overrides
The system SHALL allow only platform administrators to change a company's plan, billing cycle, optional contract price, overrideable feature states and quota overrides using optimistic company version checks.

#### Scenario: Close one feature for an enterprise customer
- **WHEN** a platform administrator disables an otherwise included feature for one company
- **THEN** the effective entitlement is disabled only for that company and the change is audited

#### Scenario: Submit a stale entitlement update
- **WHEN** a platform administrator saves against an outdated company version
- **THEN** the update is rejected with a version conflict and no entitlement is changed

### Requirement: Plans define effective commercial quotas
The system SHALL expose stable quota identifiers with per-plan defaults and company-level overrides, where an absent override follows the plan, a non-negative integer is a custom limit and `null` means unlimited.

#### Scenario: Give one contracted company more AI capacity
- **WHEN** a platform administrator changes `ai.conversations.monthly` from the professional-plan default to a larger custom value
- **THEN** the enterprise entitlement read model returns the custom effective value without changing other professional-plan customers

#### Scenario: Return a quota to its plan default
- **WHEN** a platform administrator removes a company's quota override
- **THEN** the effective quota is recalculated from the currently selected plan

#### Scenario: Submit an unknown quota
- **WHEN** an entitlement update contains a quota identifier outside the platform catalog
- **THEN** the server rejects the update without persisting partial entitlement changes

### Requirement: Required kernel capabilities cannot be disabled
The system SHALL keep required identity and card-kernel capabilities enabled regardless of plan or company override.

#### Scenario: Override the required card core to false
- **WHEN** an update attempts to disable the required card core feature
- **THEN** the update is rejected and public identity rendering remains available

### Requirement: Effective entitlements govern UI and server operations
The system SHALL use the same effective feature state for enterprise navigation, direct-route access, public-card capabilities and protected API operations, with server authorization as the final authority.

#### Scenario: Call a disabled feature directly
- **WHEN** a user calls a protected endpoint for a feature hidden from the enterprise navigation
- **THEN** the server returns `FEATURE_NOT_ENTITLED` without performing the business operation

#### Scenario: Disable public AI while an old conversation exists
- **WHEN** AI conversations are disabled after a visitor already created a conversation
- **THEN** the public card reports AI unavailable and new messages on the old conversation are rejected

### Requirement: Commercial entitlement dominates plugin installation
The system SHALL require both an enabled commercial feature and a valid company plugin installation before an optional plugin can be enabled or newly published.

#### Scenario: Enable FAQ plugin on a starter plan
- **WHEN** the company lacks `card.blocks.faq` but attempts to enable the FAQ plugin
- **THEN** the operation is rejected with `FEATURE_NOT_ENTITLED` even if all plugin permissions were granted

### Requirement: Legacy and new enterprises have explicit compatibility behavior
The system SHALL preserve all existing capabilities for companies without commercial settings and SHALL assign an explicit default plan to newly created companies.

#### Scenario: Deploy entitlements to an existing enterprise
- **WHEN** an existing company has no commercial entitlement settings
- **THEN** it resolves to the compatibility enterprise plan with unlimited compatibility quotas without silently disabling live functions

#### Scenario: Create a new enterprise
- **WHEN** a platform administrator creates a new company
- **THEN** the company stores an explicit starter plan that can later be upgraded or overridden
