# AGENTS.md

## Harness

### Start here
1. Read `harness/contract.md` and `harness/PROGRESS.md`.
2. At run start, read `harness/IMPROVE.md` and follow it if any trace in `harness/traces/` has a `failure` or `escalate` event.
3. Work only inside the contract scope.

### Layout
- Architecture: <ARCHITECTURE_DOC> | Rules: <RULES_DOC> | Testing: <TESTING_DOC>
- Harness: `harness/contract.md`, `harness/PROGRESS.md`, `harness/checks.sh`, `harness/walls.json`, `harness/IMPROVE.md`, `harness/traces/`, `harness/HARNESS-LOG.md`, `harness/PROPOSALS.md`

### Never touch
- <NEVER_TOUCH_PATHS>
- `harness/walls.json`, `harness/hooks/**`, `.claude/settings.json`, `harness/IMPROVE.md`, `harness/traces/**`, `harness/status.json`
- `harness/checks.sh` gate lines (add only; never edit or delete)
- `harness/HARNESS-LOG.md` rows (append only)

### Commands
- Run all gates: `<CHECKS_COMMAND>` (after every finished unit; commit after every green unit)

### Stop rules
- Do not edit `harness/walls.json`. Propose changes in `harness/PROPOSALS.md`.
- Do not edit a gate to pass it.
- Stop at the retry cap (2 per unit) or budget (<BUDGET_MINUTES> minutes or <BUDGET_TOKENS> tokens), or on the same error twice. Write state to `harness/PROGRESS.md`, notify <CONTACT>, and stop (runner hooks emit `escalate`).
- Irreversible actions require human approval: deploy, delete, migrate, send, publish, force-push.
- Commit after each completed unit. Message: `unit <id>: <summary>`.
- Record every decision, dead end, and blocker in `harness/PROGRESS.md`.
- Never declare done unless every `done_when` item is checked and `harness/checks.sh` is green.
