# harness-builder

An agent skill and hardened template kit for building reliable, self-improving agent harnesses across **Claude Code**, **Claude Agent SDK**, and **Managed Agents**.

Instead of relying on prompt-only reminders, `harness-builder` scaffolds deterministic gates (`checks.sh`), redacted JSONL tracing (`trace.py`), retry-cap & escalation enforcement (`gate.py` / `run.py`), permission walls (`walls.json` -> `gen_permissions.py`), and a structured failure-triage loop (`IMPROVE.md`).

## Layout

```text
harness-builder/
├── SKILL.md                       # Step-by-step skill workflow (Intake -> Triage -> Build -> Dry Run)
├── references/
│   └── runners.md                 # Claude Code, Agent SDK, and Managed Agents wiring & rules
├── templates/
│   ├── AGENTS.md                  # Concise (<60 lines) agent map & stop rules
│   ├── contract.md                # Task scope, test-backed done_when, retry_cap, and budgets
│   ├── checks.sh                  # Portable bash + python3 gate runner with secret scrubbing
│   ├── walls.json                 # Single source of truth for read/write/bash/network permissions
│   ├── trace-event.schema.json    # JSON Schema (Draft 2020-12) for harness/traces/*.jsonl
│   ├── PROGRESS.md                # Cross-unit state & dead-end log
│   ├── IMPROVE.md                 # Post-failure triage & regression-check loop
│   ├── HARNESS-LOG.md             # Append-only log of harness changes
│   ├── PROPOSALS.md               # Agent-proposed walls.json changes for human approval
│   ├── hooks/                     # Executable Claude Code hooks & settings template
│   │   ├── settings.json
│   │   ├── trace.py
│   │   ├── gate.py
│   │   └── gen_permissions.py
│   └── sdk/
│       └── run.py                 # Agent SDK driver with retry loop & escalation
└── tests/
    └── test_harness.py            # Automated stdlib unittest suite
```

## Installation

Clone into your agent skills directory (e.g. `~/.claude/skills/harness-builder` or your project's `.claude/skills/harness-builder`):

```bash
git clone https://github.com/aayushhzz/harness-builder.git ~/.claude/skills/harness-builder
```

## Verification

Run the test suite locally (requires Python 3.9+ and `bash`):

```bash
python3 -m unittest discover -s tests -v
```

## License

[MIT](LICENSE)
