#!/usr/bin/env python3
"""Agent SDK harness driver: traces tool calls, enforces walls, and loops up to retry_cap."""
import asyncio
import fcntl
import json
import os
import re
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone

from claude_agent_sdk import ClaudeAgentOptions, HookMatcher, query  # UNVERIFIED names
from sdk_walls import make_can_use_tool  # reads walls.json

RUN_ID = uuid.uuid4().hex
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


def norm_detail(s):
    s = re.sub(r"\b\d+\.\d+s\b", "<TIME>", s)
    return re.sub(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?", "<TS>", s)


UNIT = re.sub(r"[^A-Za-z0-9_.-]", "_", redact(str(os.environ.get("UNIT", "unit"))))[:64] or "unit"
TRACE = f"harness/traces/{RUN_ID}.jsonl"
os.makedirs("harness/traces", exist_ok=True)


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def emit(event, status, detail, tool=None):
    clean = redact(detail)
    s = json.dumps(clean) if isinstance(clean, (dict, list)) else str(clean)
    d_str = s[:500] if event == "tool_call" else s[-500:]
    line = {"ts": now(), "run_id": RUN_ID, "unit": UNIT, "event": event, "status": status, "detail": d_str}
    if tool:
        line["tool"] = tool
    with open(TRACE, "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.write(json.dumps(line) + "\n")


def write_status(final):
    fd, tmp = tempfile.mkstemp(dir="harness", prefix=".status_", suffix=".tmp")
    with os.fdopen(fd, "w") as f:
        json.dump({"run_id": RUN_ID, "status": final, "ts": now()}, f)
    os.replace(tmp, "harness/status.json")


async def trace_hook(input_data, tool_use_id, context):  # UNVERIFIED signature
    resp = input_data.get("tool_response")
    is_error = (
        input_data.get("hook_event_name") == "PostToolUseFailure"
        or bool(input_data.get("error"))
        or (isinstance(resp, dict) and bool(resp.get("is_error")))
    )
    emit("tool_call", "error" if is_error else "ok", redact(input_data.get("tool_input")), input_data.get("tool_name") or "")
    return {}


options = ClaudeAgentOptions(  # UNVERIFIED field names
    can_use_tool=make_can_use_tool(emit),
    cwd=os.getcwd(),  # UNVERIFIED: set to worktree/sandbox
    # allowed_tools=[], disallowed_tools=[],  # UNVERIFIED: populate from walls.json
    hooks={
        "PostToolUse": [HookMatcher(matcher=".*", hooks=[trace_hook])],
        "PostToolUseFailure": [HookMatcher(matcher=".*", hooks=[trace_hook])],
    },
    max_turns=int(os.environ.get("HARNESS_MAX_TURNS", "60")),
)


def run_checks():
    env = {
        k: v
        for k, v in os.environ.items()
        if not SECRET_KEY.search(k)
        and not k.startswith("BASH_FUNC_")
        and k not in ("BASH_ENV", "ENV", "CDPATH", "PYTHONPATH")
    }
    env.update({"RUN_ID": RUN_ID, "UNIT": UNIT, "TRACE_FILE": TRACE})
    r = subprocess.run(["bash", "harness/checks.sh"], capture_output=True, text=True, env=env)
    return r.returncode == 0, redact(r.stdout + r.stderr)


async def main():
    with open("harness/contract.md") as cf:
        contract = cf.read()
    m = re.search(r"(?m)^retry_cap:\s*(\d+)\b", contract)
    cap = max(1, int(m.group(1))) if m else 2
    prompt, last_tail = contract, None
    for attempt in range(1, cap + 1):
        async for _ in query(prompt=prompt, options=options):
            pass
        ok, out = run_checks()
        status = "pass" if ok else "fail"
        emit("gate_result", status, out)
        if ok:
            write_status("pass")
            return
        emit("failure", "fail", out)
        tail = norm_detail(out[-500:])
        if attempt >= cap or (last_tail is not None and last_tail == tail):
            emit("escalate", "fail", out)
            write_status("escalate")
            summary = re.sub(r"\s+", " ", out[-300:]).strip()
            with open("harness/PROGRESS.md", "a") as f:
                f.write(f"\n- escalate {RUN_ID}: {summary}\n")
            sys.exit(1)
        last_tail = tail
        safe_out = out[-1500:].replace("</untrusted_check_output>", "</untrusted_check_output_escaped>")
        prompt = (
            "harness/checks.sh failed. Fix and rerun.\n<untrusted_check_output>\n"
            + safe_out
            + "\n</untrusted_check_output>"
        )


if __name__ == "__main__":
    asyncio.run(main())
