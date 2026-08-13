## Requirements

### Requirement: Shared content references

Cards SHALL reference published products, cases and FAQ by identity while keeping layout, order and visibility as card-owned configuration.

### Requirement: Impact confirmation

Before publishing or rolling back shared content, the service SHALL return affected cards and require confirmation against the current affected-set digest.

### Requirement: Version history and rollback

Published shared content SHALL retain immutable revisions. Rollback SHALL create a new publication event from a selected prior revision and SHALL update every referencing public card atomically.
