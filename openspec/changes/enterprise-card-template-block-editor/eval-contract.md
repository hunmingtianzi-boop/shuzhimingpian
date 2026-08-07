# Eval Contract

## Hard Gates

| Gate | Evidence |
| --- | --- |
| Member identity is not duplicated by employee-card writes | focused API/service tests |
| Enterprise template draft and public snapshot differ until publish | focused API/public-store tests |
| All block resources are company-scoped and type-valid | schema/store negative tests |
| Existing cards are migration-compatible | migration/backfill test |
| Editor has keyboard-accessible reorder and publishes only valid templates | component tests + browser smoke |
| Public mobile renderer matches published block order | card-web tests + 390px browser evidence |

## Commands

- `corepack pnpm api:test -- -k "template or member or card"`
- `corepack pnpm admin:test -- --runInBand` (or the repository's focused Vitest equivalent)
- `corepack pnpm web:test`
- `corepack pnpm contracts:sync && corepack pnpm contracts:validate`
- focused Playwright runtime smoke after a current-code runtime is available.

## Stop Rule

Do not claim completion if any existing public card, RLS scope, published snapshot, or identity-projection gate lacks current direct evidence.
