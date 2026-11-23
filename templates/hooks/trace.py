#!/usr/bin/env python3
"""Claude Code PostToolUse / PostToolUseFailure hook: appends redacted tool_call events."""
import fcntl
import json
import os
import re
import sys
from datetime import datetime, timezone

SECRET_KEY = re.compile(
    r"(?i)(token|key|secret|pass|auth|cookie|cred|bearer|dsn|jwt|(?:^|_)pat(?:_|$)|webhook|database_url|connection_string|npm_rc)"
)
SECRET_VAL = re.compile(
    r"(?is)(Bearer\s+\S+|Basic\s+[A-Za-z0-9+/=_-]{4,}|sk-[A-Za-z0-9_-]{8,}|gh[opsuhr]_[A-Za-z0-9_]{16,}|github_pat_[A-Za-z0-9_-]{16,}|x(?:ox[baprs]|app)-[A-Za-z0-9_-]{10,}|AIza[0-9A-Za-z_-]{20,}|A[SK]IA[0-9A-Z]{16}|https://hooks\.slack\.com/services/\S+|eyJ[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{3,}\.[A-Za-z0-9_-]*|-----BEGIN [A-Z0-9 ]*PRIVATE KEY[A-Z0-9 ]*-----.*?-----END [A-Z0-9 ]*PRIVATE KEY[A-Z0-9 ]*-----|://[^/\s]+@|-u[^\s\"']+:\S+|(?:-u|--user|--password|--passphrase)(?:=|\s+)(?:\"[^\"]*\"|'[^']*'|\S+)|\"(?:api_?key|access_token|client_secret|apiSecret|token|secret|password|database_url|slack_webhook)\"\s*:\s*\"(?:\\.|[^\"])*\"|\b[A-Za-z0-9_]*(?:KEY|SECRET|TOKEN|PASSWORD|PAT|WEBHOOK|DATABASE_URL|CONNECTION_STRING|NPM_RC|PASS|DSN)\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s\n]+))"
)


def redact(val):
    if isinstance(val, dict):
        return {k: ("[REDACTED]" if SECRET_KEY.search(str(k)) else redact(v)) for k, v in val.items()}
    if isinstance(val, list):
        return [redact(v) for v in val]
    if isinstance(val, str):
        s = re.sub(r"\x1b\[[0-9;?]*[ -/]*[@-~]", "", val)
        return SECRET_VAL.sub("[REDACTED]", s)
    return val


def find_root():
    # Anchor to the repo containing harness/hooks/trace.py (never trust unvalidated cwd or symlinks).
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))


def main():
    try:
        d = json.load(sys.stdin)
    except Exception:
        sys.exit(0)
    if not isinstance(d, dict):
        sys.exit(0)

    raw_id = d.get("session_id")
    run_id = raw_id if isinstance(raw_id, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", raw_id) else "unknown"
    root = find_root()
    os.makedirs(os.path.join(root, "harness", "traces"), exist_ok=True)
    resp = d.get("tool_response")
    is_error = (
        d.get("hook_event_name") == "PostToolUseFailure"
        or bool(d.get("error"))
        or (isinstance(resp, dict) and bool(resp.get("is_error")))
    )
    unit = re.sub(r"[^A-Za-z0-9_.-]", "_", redact(str(os.environ.get("UNIT", "unit"))))[:64] or "unit"
    inp = redact(d.get("tool_input"))
    line = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "run_id": run_id,
        "unit": unit,
        "event": "tool_call",
        "tool": d.get("tool_name") or "",
        "status": "error" if is_error else "ok",
        "detail": json.dumps(inp)[:500],
    }
    with open(os.path.join(root, "harness", "traces", f"{run_id}.jsonl"), "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.write(json.dumps(line) + "\n")


if __name__ == "__main__":
    main()
