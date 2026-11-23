#!/usr/bin/env python3
"""Claude Code Stop hook: runs harness/checks.sh, tracks retry_cap, and escalates."""
import fcntl
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

SECRET_KEY = re.compile(
    r"(?i)(token|key|secret|pass|auth|cookie|cred|bearer|dsn|jwt|(?:^|_)pat(?:_|$)|webhook|database_url|connection_string|npm_rc)"
)
SECRET_VAL = re.compile(
    r"(?is)(Bearer\s+\S+|Basic\s+[A-Za-z0-9+/=_-]{4,}|sk-[A-Za-z0-9_-]{8,}|gh[opsuhr]_[A-Za-z0-9_]{16,}|github_pat_[A-Za-z0-9_-]{16,}|x(?:ox[baprs]|app)-[A-Za-z0-9_-]{10,}|AIza[0-9A-Za-z_-]{20,}|A[SK]IA[0-9A-Z]{16}|https://hooks\.slack\.com/services/\S+|eyJ[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{3,}\.[A-Za-z0-9_-]*|-----BEGIN [A-Z0-9 ]*PRIVATE KEY[A-Z0-9 ]*-----.*?-----END [A-Z0-9 ]*PRIVATE KEY[A-Z0-9 ]*-----|://[^/\s]+@|-u[^\s\"']+:\S+|(?:-u|--user|--password|--passphrase)(?:=|\s+)(?:\"[^\"]*\"|'[^']*'|\S+)|\"(?:api_?key|access_token|client_secret|apiSecret|token|secret|password|database_url|slack_webhook)\"\s*:\s*\"(?:\\.|[^\"])*\"|\b[A-Za-z0-9_]*(?:KEY|SECRET|TOKEN|PASSWORD|PAT|WEBHOOK|DATABASE_URL|CONNECTION_STRING|NPM_RC|PASS|DSN)\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s\n]+))"
)


def scrub(s):
    s = re.sub(r"\x1b\[[0-9;?]*[ -/]*[@-~]", "", s)
    s = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", " ", s)
    return SECRET_VAL.sub("[REDACTED]", s)


def norm_detail(s):
    s = re.sub(r"\b\d+\.\d+s\b", "<TIME>", s)
    return re.sub(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?", "<TS>", s)


def find_root():
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))


def main():
    try:
        d = json.load(sys.stdin)
    except Exception:
        d = {}
    if not isinstance(d, dict):
        d = {}

    root = find_root()
    raw_id = d.get("session_id")
    run_id = raw_id if isinstance(raw_id, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", raw_id) else "unknown"
    unit = re.sub(r"[^A-Za-z0-9_.-]", "_", scrub(str(os.environ.get("UNIT", "unit"))))[:64] or "unit"
    traces_dir = os.path.join(root, "harness", "traces")
    os.makedirs(traces_dir, exist_ok=True)
    trace = os.path.join(traces_dir, f"{run_id}.jsonl")
    status_path = os.path.join(root, "harness", "status.json")
    now = lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def emit(event, status, detail):
        with open(trace, "a") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            f.write(
                json.dumps(
                    {
                        "ts": now(),
                        "run_id": run_id,
                        "unit": unit,
                        "event": event,
                        "status": status,
                        "detail": scrub(detail)[-500:],
                    }
                )
                + "\n"
            )

    def write_status(final):
        fd, tmp = tempfile.mkstemp(dir=os.path.join(root, "harness"), prefix=".status_", suffix=".tmp")
        with os.fdopen(fd, "w") as f:
            json.dump({"run_id": run_id, "status": final, "ts": now()}, f)
        os.replace(tmp, status_path)

    cap = 2
    contract_path = os.path.join(root, "harness", "contract.md")
    if os.path.exists(contract_path):
        with open(contract_path) as cf:
            m = re.search(r"(?m)^retry_cap:\s*(\d+)\b", cf.read())
        if m:
            cap = max(1, int(m.group(1)))

    with open(os.path.join(traces_dir, ".gate.lock"), "a+") as lockf:
        fcntl.flock(lockf, fcntl.LOCK_EX)
        cur_status = None
        if os.path.exists(status_path):
            try:
                with open(status_path) as sf:
                    sdata = json.load(sf)
                if isinstance(sdata, dict) and sdata.get("run_id") == run_id:
                    cur_status = sdata.get("status")
            except Exception:
                pass
        if cur_status == "escalate":
            sys.exit(0)

        prior, total_fails, last_fail_detail = 0, 0, None
        if os.path.exists(trace):
            with open(trace) as tf:
                for line in tf:
                    try:
                        ev = json.loads(line)
                    except ValueError:
                        continue
                    if ev.get("event") == "gate_result" and not ev.get("tool"):
                        if ev.get("status") == "pass":
                            total_fails = 0
                        elif ev.get("status") == "fail":
                            total_fails += 1
                        if ev.get("unit") == unit:
                            if ev.get("status") == "pass":
                                prior, last_fail_detail = 0, None
                            elif ev.get("status") == "fail":
                                prior += 1
                                last_fail_detail = ev.get("detail")

        clean_env = {
            k: v
            for k, v in os.environ.items()
            if not SECRET_KEY.search(k)
            and not k.startswith("BASH_FUNC_")
            and k not in ("BASH_ENV", "ENV", "CDPATH", "PYTHONPATH")
        }
        clean_env.update({"RUN_ID": run_id, "UNIT": unit, "TRACE_FILE": trace})
        r = subprocess.run(
            ["bash", os.path.join(root, "harness", "checks.sh")],
            cwd=root,
            capture_output=True,
            text=True,
            env=clean_env,
        )
        out = scrub(r.stdout + r.stderr)
        status = "pass" if r.returncode == 0 else "fail"
        emit("gate_result", status, out)
        final = status
        if status == "fail":
            emit("failure", "fail", out)
            same_twice = last_fail_detail is not None and norm_detail(last_fail_detail) == norm_detail(out[-500:])
            if prior + 1 >= cap or total_fails + 1 >= cap * 2 or same_twice:
                final = "escalate"
                emit("escalate", "fail", out)
                summary = re.sub(r"\s+", " ", out[-300:]).strip()
                with open(os.path.join(root, "harness", "PROGRESS.md"), "a") as f:
                    f.write(f"\n- escalate {run_id}: {summary}\n")
        write_status(final)
        if final == "fail":
            safe_out = out[-1500:].replace("</untrusted_check_output>", "</untrusted_check_output_escaped>")
            print(
                json.dumps(
                    {
                        "decision": "block",
                        "reason": "harness/checks.sh failed. Fix and rerun.\n<untrusted_check_output>\n"
                        + safe_out
                        + "\n</untrusted_check_output>",
                    }
                )
            )


if __name__ == "__main__":
    main()
