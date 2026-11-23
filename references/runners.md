# Runners

Pick the section matching the runner. Write only that section's files.

Shared files (all runners):
- `harness/walls.json` is the single source of permissions. Fields read: `allow_write[]`, `deny_write[]`, `allow_read[]`, `deny_read[]`, `allow_bash[]`, `deny_bash[]`, `allow_tools[]`, `ask[]`, `network_allow[]`.
- `harness/checks.sh` exits 0 on pass, nonzero on fail. Prints failing checks to stderr.
- `harness/traces/<run_id>.jsonl` holds one JSON line per event. Add `harness/traces/` and `harness/status.json` to `.gitignore`.
- `harness/status.json` holds `{"run_id","status","ts"}`. `status` is `pass`, `fail`, or `escalate`.
- Trace line shape: exactly templates/trace-event.schema.json: `{"ts"(ISO-8601 UTC string),"run_id","unit","event"(start|tool_call|gate_result|retry|escalate|done|failure),"tool"?,"status"(pass|fail|skip|ok|error),"detail"(max 500 chars)}`. No other keys.
- Every gate failure writes a `gate_result` event with status `fail`, then a `failure` event.
- Pass `RUN_ID`, `UNIT` and `TRACE_FILE=harness/traces/<run_id>.jsonl` as env vars to every `checks.sh` call.
- Never regenerate permissions by hand. Edit `walls.json`, then rerun the generator for the runner.
- Tool-level `walls.json` rules are **not** an OS sandbox against arbitrary code execution (e.g., writable tests executed by an allowed test runner). For write-capable runs, run inside an OS/container sandbox with `harness/checks.sh`, `harness/walls.json`, `harness/hooks/`, `harness/contract.md`, `harness/IMPROVE.md`, and `.claude/` mounted read-only (while keeping `harness/traces/`, `harness/status.json`, `harness/PROGRESS.md`, `harness/HARNESS-LOG.md`, and `harness/PROPOSALS.md` writable) and a restricted network namespace.
- Mark any field you could not confirm as `UNVERIFIED` in `harness/README-unverified.md` (format: `- <runner>: <field> — <status>`). Before first run, confirm every item marked UNVERIFIED against the runner's current docs.

---

## Claude Code

Run id: `session_id` from the hook payload.

### Files to write
1. `.claude/settings.json`
2. `harness/hooks/trace.py`
3. `harness/hooks/gate.py`
4. `harness/hooks/gen_permissions.py`

### 1. `.claude/settings.json`

Copy `templates/hooks/settings.json` to `.claude/settings.json`. It wires `PostToolUse` and `PostToolUseFailure` to `harness/hooks/trace.py` and `Stop` to `harness/hooks/gate.py`.

Confirm before first run (log in `harness/README-unverified.md`):
- UNVERIFIED: `tool_response` key in the PostToolUse payload. `trace.py` must tolerate its absence.
- UNVERIFIED: `$CLAUDE_PROJECT_DIR` expansion in `command`. Fallback: path relative to the repo root.
- UNVERIFIED: `permissions.ask` key.
- UNVERIFIED: Rule syntax `Tool(specifier)`: `Edit(src/**)`, `Bash(npm test:*)`, `WebFetch(domain:example.com)`.

### Permission enforcement from `walls.json`
Copy `templates/hooks/gen_permissions.py` to `harness/hooks/gen_permissions.py`. It reads `harness/walls.json` and rewrites `permissions` in `.claude/settings.json`. Mapping:

| walls.json | settings.json |
|---|---|
| `allow_write[]` | `permissions.allow`: `Edit(<glob>)`, `Write(<glob>)` |
| `deny_write[]` | `permissions.deny`: `Edit(<glob>)`, `Write(<glob>)` |
| `allow_read[]` | `permissions.allow`: `Read(<glob>)` |
| `deny_read[]` | `permissions.deny`: `Read(<glob>)` |
| `allow_bash[]` | `permissions.allow`: `Bash(<cmd>:*)` |
| `deny_bash[]` | `permissions.deny`: `Bash(<cmd>:*)` |
| `allow_tools[]` | `permissions.allow`: `<tool>` |
| `ask[]` | `permissions.ask`: entries as given (`Tool(specifier)` syntax) |
| `network_allow[]` | `permissions.allow`: `WebFetch(domain:<host>)` |

Rules:
- Evaluation precedence: `deny` -> `ask` -> `allow` (deny wins over ask and allow; ask wins over allow).
- Add `Bash(curl:*)`, `Bash(wget:*)`, `Bash(ssh:*)` to `permissions.deny` whenever the `network_allow` key is present in `walls.json` (including `[]` for deny-all). Never put bare `WebFetch` in `allow_tools` when `network_allow` is set.
- Do not put file-touching tools (`Grep`, `Glob`, `MultiEdit`, `NotebookEdit`) in `allow_tools` unless guarded by a `PreToolUse` path-wall hook; they bypass `Read`/`Edit`/`Write` globs.
- Use `Tool(specifier)` syntax in `ask[]` (e.g., `Bash(git push:*)`, `Edit(harness/checks.sh)`, `Write(harness/checks.sh)`, `Edit(harness/contract.md)`, `Write(harness/contract.md)`). Never put irreversible actions in `allow`.
- Put `harness/walls.json`, `harness/hooks/**`, `harness/IMPROVE.md`, `harness/traces/**`, `harness/status.json`, and `.claude/settings.json` in `deny_write`.
- Put `harness/checks.sh` and `harness/contract.md` edits in `ask`.
- Allow writes to `harness/PROGRESS.md`, `harness/HARNESS-LOG.md`, `harness/PROPOSALS.md`, and `AGENTS.md`.
- Run the generator after every `walls.json` edit.
- OS-level network sandboxing: UNVERIFIED. Do not claim network enforcement beyond the rules above.

### 2. `harness/hooks/trace.py`

Copy `templates/hooks/trace.py` to `harness/hooks/trace.py`. It:
- Registers on `PostToolUse` and `PostToolUseFailure`.
- Anchors `find_root()` to `os.path.realpath(__file__)`, validates `session_id` (`[A-Za-z0-9_-]{1,128}`), sanitizes `UNIT`, redacts secret keys/values + ANSI codes, locks with `fcntl.flock`, and exits 0 always.

### 3. `harness/hooks/gate.py` (Stop hook)

Copy `templates/hooks/gate.py` to `harness/hooks/gate.py`. It:
- Acquires `.gate.lock`, checks `status.json` `run_id` ownership (exiting 0 if already `escalate`), counts top-level `gate_result` fails per `unit` after last `pass` (and consecutive `total_fails`), scrubs env (`SECRET_KEY`, `BASH_FUNC_*`, `BASH_ENV`, `ENV`, `CDPATH`, `PYTHONPATH`), runs `harness/checks.sh`, and writes `status.json` atomically.
- On fail below the cap: blocks stop with `<untrusted_check_output>` delimiters.
- At `retry_cap` from `harness/contract.md`, `total_fails >= cap * 2`, or same failure `detail` twice in a row (normalized for timestamps/durations): writes `escalate` to `harness/status.json`, appends an `escalate` event, appends a single-line summary to `harness/PROGRESS.md`, and exits 0 without blocking.
- `harness/contract.md` must contain a line `retry_cap: <n>`.

### Run command
`claude -p "<task from contract.md>"` with the project as cwd.

---

## Agent SDK

Run id: generate `uuid4()` at process start. Pass it to every hook through closure.

Every SDK name below is UNVERIFIED. Confirm each one in the current Agent SDK reference before first run.

### Files to write
1. `harness/run.py` (Python) or `harness/run.ts` (TypeScript). Match the project language.
2. `harness/sdk_walls.py` or `harness/sdk_walls.ts`: loads `walls.json`, exposes `can_use_tool`.

### Python (`harness/run.py`)

Copy `templates/sdk/run.py` to `harness/run.py`. Confirm the `UNVERIFIED` SDK names (`claude_agent_sdk`, `ClaudeAgentOptions`, `HookMatcher`, `query`, `trace_hook`, `cwd`, `allowed_tools`, `disallowed_tools`) before first run.

### TypeScript (`harness/run.ts`)

TypeScript projects: port `harness/run.py` to `harness/run.ts` with the same hooks, options and loop. Package name `@anthropic-ai/claude-agent-sdk` is UNVERIFIED.

### Permission enforcement from `walls.json`
`can_use_tool(tool_name, tool_input, context)` returns allow or deny. Return shape is UNVERIFIED. Evaluation order for every tool: `deny` -> `ask` -> `allow` (deny is default; allow only on a match). Normalize all file paths via `os.path.realpath`, verify `os.path.commonpath([real_root, real_p]) == real_root`, convert to `os.path.relpath(real_p, real_root).lower()` on case-insensitive filesystems (macOS APFS / Windows — note `os.path.normcase` is a no-op on macOS POSIX), and match recursive `**` globs (not `PurePosixPath.match`).
1. File-writing tools (`Edit`, `Write`, `MultiEdit`, `NotebookEdit`): normalize path (`file_path` or `notebook_path`); check `deny_write`, `ask` (matching `Edit(<glob>)`/`Write(<glob>)` rules for `MultiEdit`/`NotebookEdit` too; deny in headless mode), then `allow_write`.
2. File-reading/search tools (`Read`, `Grep`, `Glob`): normalize path (defaulting missing `path` to `.`); check `deny_read`, `ask`, then `allow_read`.
3. Tool is `Bash`: reject commands containing shell metacharacters (`;`, `&`, `&&`, `||`, `|`, `$`, `` ` ``, `<`, `>`, `(`, `)`, `{`, `}`, `*`, `?`, `~`, newlines) and validate parsed argv (guarding flag wrappers like `git -c` / `--config-env` and `env`/path-qualified binaries). Check `deny_bash`, then `ask` (`Bash(<cmd>:*)`, prompt human or deny in headless mode), then `allow_bash`. Block network tools (`curl`, `wget`, `ssh`, etc.) whenever `network_allow` is present (`[]` = deny-all) and enforce `network_allow` at the OS/container layer.
4. Tool is `WebFetch` / `WebSearch`: check `ask`, then for `WebFetch` parse `urllib.parse.urlparse(url).hostname` and allow only if exact-matched in `network_allow` (block `WebSearch` when `network_allow` is `[]`).
5. Any other non-file tool: check `deny`, `ask`, then allow only if listed in `allow_tools` (never include file-touching tools in Rule 5).
6. Every deny returns a message naming the rule that fired and calls `emit("tool_call", "error", f"denied_by:{rule}", tool_name)`.

Rules:
- Deny is the default. Allow only on a match.
- Enforce only in `can_use_tool`. Never enforce through prompt text.
- Put `harness/run.py`, `harness/sdk_walls.py`, `harness/run.ts`, `harness/sdk_walls.ts`, `harness/walls.json`, `harness/IMPROVE.md`, `harness/traces/**`, and `harness/status.json` in `deny_write`.
- Put `harness/checks.sh` and `harness/contract.md` in `ask`; allow writes to `harness/PROGRESS.md`, `harness/HARNESS-LOG.md`, `harness/PROPOSALS.md`, and `AGENTS.md`.
- Set `cwd` to an isolated worktree or sandbox (`UNVERIFIED: SDK option name cwd`), and set static `allowed_tools` / `disallowed_tools` (`UNVERIFIED: option names`).

### Trace and stop
- Trace: `PostToolUse` and `PostToolUseFailure` hooks append one redacted line per tool call, as shown above.
- Stop:
  1. After the stream ends, run `harness/checks.sh` in the driver with `RUN_ID`, `UNIT`, and `TRACE_FILE` set.
  2. On fail below the retry cap, start a new `query` with the failure tail as the prompt.
  3. At the cap, or on the same failure tail twice, write status `escalate`, append an `escalate` event, append to `harness/PROGRESS.md`, exit nonzero.

---

## Managed Agents

Run id: `session.id` returned at session creation.

Every field name, endpoint and method below is UNVERIFIED. Confirm each one in the current Managed Agents reference before first run.

### Files to write
1. `harness/ma/agent.json`
2. `harness/ma/environment.json`
3. `harness/ma/local_tools.json`
4. `harness/ma/run.py`

### `harness/ma/agent.json`

```json
{
  "name": "<project>-harness-agent",
  "model": "<model id>",
  "system": "<contents of harness/contract.md + pointer to AGENTS.md>",
  "tools": [],
  "mcp_servers": [],
  "skills": []
}
```

- `tools`: list only tools the contract needs. Narrow list. Generate from `walls.json`: omit any tool with no allow rule.
- Add each local tool from `local_tools.json` here.
- Coarse tool allowlisting lives in `agent.json` (`UNVERIFIED`: key names and values); path- and command-scoped `walls.json` rules (`deny` -> `ask` -> `allow`) are enforced in `harness/ma/run.py` local tool handlers.

### `harness/ma/environment.json`

```json
{
  "name": "<project>-env",
  "networking": { "type": "limited", "allowed_hosts": [] }
}
```

- Fill `allowed_hosts` from `walls.json` `network_allow`. Never use unrestricted networking.
- UNVERIFIED: `networking`, `type`, `allowed_hosts` names and the `limited` value.
- Credentials: store in a vault. Never put secrets in `agent.json`, `environment.json`, or the repo.
- File-path walls (`allow_write`, `deny_write`, `allow_read`, `deny_read`): enforce inside local tools, not in the environment. Mount only the paths the contract needs. Put `harness/ma/**`, `harness/walls.json`, `harness/IMPROVE.md`, `harness/traces/**`, and `harness/status.json` in `deny_write`; put `harness/checks.sh` and `harness/contract.md` in `ask`; allow writes to `harness/PROGRESS.md`, `harness/HARNESS-LOG.md`, `harness/PROPOSALS.md`, and `AGENTS.md`.

### `harness/ma/local_tools.json`

```json
[
  {
    "name": "run_checks",
    "description": "Run harness/checks.sh. Returns exit code and failing output. Call before declaring done.",
    "input_schema": { "type": "object", "properties": {}, "required": [] }
  },
  {
    "name": "write_progress",
    "description": "Append a line to harness/PROGRESS.md.",
    "input_schema": {
      "type": "object",
      "properties": { "line": { "type": "string" } },
      "required": ["line"]
    }
  }
]
```

- Add one local tool per project command the agent needs (test, lint, typecheck, build). Each tool does one job. Each fails loudly with the exit code and the output tail.
- UNVERIFIED: the `input_schema` key and the tool-definition shape.

### `harness/ma/run.py`

Loop logic (write with the current Managed Agents client; names UNVERIFIED):
1. Create the agent from `agent.json`. Create the environment from `environment.json`.
2. Create a session. `run_id = session.id`. Create `harness/traces/<run_id>.jsonl`.
3. Send the contract as the first user message.
4. Stream events. For every event, append one schema-conformant trace line. Map stream events to schema event names: tool call to `tool_call`, session start to `start`, terminal state to `done`.
5. On a local tool call event:
   - Look up the tool name in `local_tools.json`. Unknown name: return an error result. Do not run it.
   - `run_checks`: run `bash harness/checks.sh` with `RUN_ID`, `UNIT` (default `"unit"`), and `TRACE_FILE` set, scrubbing secret env vars (`SECRET_KEY`, `BASH_ENV`, `ENV`, `CDPATH`). Return exit code and the last 2000 chars of redacted output.
   - Any file-reading, file-writing, or command tool: check args against `walls.json` first (`deny` -> `ask` -> `allow`). On `ask`, prompt the human operator (or deny in headless mode); on `deny`, return an error result naming the rule.
   - Send the result back to the session.
   - Append a trace line for the result.
6. On session state `idle` (agent claims done): run `harness/checks.sh` locally.
   - Run it with `RUN_ID`, `UNIT` (default `"unit"`), and `TRACE_FILE` set, scrubbing secret env vars.
   - Append `gate_result` with `status` and redacted output tail. On fail, also append a `failure` event.
   - Write `harness/status.json` atomically.
   - Pass: delete the session if retention requires it. Exit 0.
   - Fail below the retry cap: send the failure tail wrapped in `<untrusted_check_output>` as a new user message. Continue streaming.
   - At the cap, or the same failure tail twice: write `status: escalate`, append an `escalate` event, append single-line summary to `harness/PROGRESS.md`, exit nonzero.
7. On state `terminated`: append an `escalate` event. Exit nonzero.
8. On Ctrl-C or error: do not leave the session running. Interrupt or delete it. UNVERIFIED: method names.

### Run command
`python3 harness/ma/run.py` with the project as cwd.

Rules:
- Checks run locally as a tool, never inside the agent's own claim of success.
- Trace comes from the event stream. Do not add a separate hook.
