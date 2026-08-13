## Requirements

### Requirement: Shared import workbench

The enterprise workspace SHALL expose one dedicated import workbench and SHALL link to it from enterprise profile, products, cases and FAQ without duplicating import implementations.

### Requirement: Human-readable import tasks

Every import batch SHALL have a company-scoped sequence number and editable display name. Ordinary UI SHALL hide the UUID.

### Requirement: Progressive candidate review

The workbench SHALL display candidate navigation separately from a single selected candidate editor and evidence. Bulk acceptance SHALL require an explicit summary confirmation and SHALL NOT silently accept medium/low-confidence candidates.

### Requirement: Website-visible states

Processing, review, partial failure, failure and completion SHALL remain discoverable from the workbench history.
