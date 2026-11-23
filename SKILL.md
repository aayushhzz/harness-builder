---
name: harness-builder
description: Build a self-improving agent harness for any project. Triggers - build agent harness, make agent reliable, self-improving agent, harness for project, add contract and checks to agent, stop agent saying done when not done.
---

## Intake
- Ask the user only for:
  1. Project path.
  2. Task.
  3. Runner: Claude Code | Agent SDK | Managed Agents | other (follow the shared contract in `references/runners.md`).
  4. Risk: read-only | branch writes | prod.
     - For `read-only` tasks, only `.claude/settings.json` (read-only permissions) and `harness/checks.sh` are needed; use the full harness below for `branch writes` and `prod`.
- Infer everything else from the repo (default `<CONTACT>` to the user if none is found; ask for Managed Agents `<model id>` only when using Managed Agents).
- Read package.json, Makefile, pyproject.toml, Cargo.toml, go.mod, CI config.
- Detect test, typecheck, lint, build commands.
- Detect protected paths: migrations, infra, secrets, lockfiles, CI config.

## Triage
- Skip if no failure history exists.
- Classify each failure from transcripts, logs, git history, bug reports.

| Symptom | Class | Fix file |
|---|---|---|
| Wrong task, scope creep | contract | harness/contract.md |
| Breaks project rules | map | AGENTS.md |
| Wrong or misread tool | tool | tool definitions |
| Forgets decisions | state | harness/PROGRESS.md |
| Says done when not | sensor | harness/checks.sh |
| Retries same fix | exit | contract budget and retry cap |
| Touches forbidden files | wall | harness/PROPOSALS.md (human applies to harness/walls.json) |
| Right tools, right info, still fails for a human too | model | no harness change |

- Triage test, in order, per failure:
  1. Could it see the info?
  2. Could it do the action?
  3. Could it tell it was wrong?
- Any "no" = harness bug. Fix the harness, not the prompt.

## Build
Do one step at a time. Verify each before the next. Fill every setup `<PLACEHOLDER>` across all created files before the first run (note: `unit <id>: <summary>` is a runtime commit template; verify no setup placeholders remain before Step 9).

1. Write harness/contract.md from templates/contract.md.
   - Each task-specific done_when item names a test that fails before and passes after.
2. If AGENTS.md exists, strip line 1 (`# AGENTS.md`) from templates/AGENTS.md and append the `## Harness` section (never overwrite it). If it does not exist, create it from templates/AGENTS.md.
   - Link detailed docs next to the code they govern.
   - Keep AGENTS.md under 60 lines (if appending exceeds 60 lines, move detailed existing rules into linked docs).
   - Confirm Stop rules contain every rule under "Write these rules into AGENTS.md".
3. Define tools.
   - One job per tool.
   - Cap output size.
   - Exit nonzero with a message on failure.
   - Write the tool list into the contract.
4. Write harness/PROGRESS.md from templates/PROGRESS.md.
5. Write harness/checks.sh from templates/checks.sh.
   - Fill TEST_CMD, TYPECHECK_CMD, LINT_CMD, BUILD_CMD from detected commands.
   - Run it on the untouched repo. It must run green.
   - If red, stop and ask the user.
6. Write harness/walls.json from templates/walls.json.
   - Fill every key in walls.json.
   - Copy and run the runner scripts from `templates/hooks/` (Claude Code) or `templates/sdk/` (Agent SDK) per `references/runners.md`.
   - Add `harness/traces/` and `harness/status.json` to `.gitignore`, and log any unconfirmed runner fields in `harness/README-unverified.md`.
7. Set retry cap 2 and a time/token budget (default `30` minutes, `100000` tokens) in both `harness/contract.md` and `AGENTS.md`.
8. Run Self-improvement setup below, log any unconfirmed hook/SDK fields in `harness/README-unverified.md`, and confirm every `UNVERIFIED` item before Step 9.
9. Dry run the agent on one trivial unit.
   - Confirm a trace file appears in harness/traces/.
   - Confirm checks.sh ran.
   - Append a fake failure event to a new trace in harness/traces/. Start a run. Confirm the agent follows IMPROVE.md, adds one HARNESS-LOG.md row and leaves checks.sh green. Delete the fake trace, revert any drill harness edit/regression check, remove any drill rows in `HARNESS-LOG.md`/`PROPOSALS.md`, reset `harness/PROGRESS.md` and `harness/status.json`, and revert the trivial unit's code/commit afterwards.

## Self-improvement setup
- harness/traces/
  - One file per run: `<run_id>.jsonl`.
  - One event per line. Match templates/trace-event.schema.json.
- harness/HARNESS-LOG.md
  - One row per harness change. Start from templates/HARNESS-LOG.md.
- harness/IMPROVE.md
  - Copy templates/IMPROVE.md verbatim.
- harness/PROPOSALS.md
  - Start from templates/PROPOSALS.md. Log every proposed walls.json change here.
- Runner hooks. Follow references/runners.md.
  - Hook 1: append a trace event on every tool call.
  - Hook 2: on stop, run harness/checks.sh and write `gate_result` (plus `failure`/`escalate` on fail/cap).

## Write these rules into AGENTS.md
- Do not edit harness/walls.json. Propose changes in harness/PROPOSALS.md.
- Do not edit a gate to pass it.
- Stop at the retry cap or budget. Escalate.
- Irreversible actions require human approval: deploy, delete, migrate, send, publish, force-push.
- Commit after each completed unit. Message: `unit <id>: <summary>`.
- Record every decision, dead end, and blocker in harness/PROGRESS.md.

## Report to user
Send one message containing:
- Files created.
- checks.sh result.
- Dry-run result.
- Unresolved UNVERIFIED items (if any).
- Open questions.
