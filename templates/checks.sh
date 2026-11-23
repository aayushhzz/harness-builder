#!/usr/bin/env bash
set -uo pipefail
unset BASH_ENV ENV CDPATH PYTHONPATH
# Gates use bash + python3 for safe JSONL trace serialization. Adjust PATH if your tools live elsewhere.
export PATH="$PATH:/opt/homebrew/bin:/usr/local/bin"

TEST_CMD=""
TYPECHECK_CMD=""
LINT_CMD=""
BUILD_CMD=""

RUN_ID="${RUN_ID:-local}"
UNIT="${UNIT:-unit}"
FAILED=0

scrub() {
  python3 - "$1" <<'PY'
import re, sys
SECRET_VAL = re.compile(
    r"(?is)(Bearer\s+\S+|Basic\s+[A-Za-z0-9+/=_-]{4,}|sk-[A-Za-z0-9_-]{8,}|gh[opsuhr]_[A-Za-z0-9_]{16,}|github_pat_[A-Za-z0-9_-]{16,}|x(?:ox[baprs]|app)-[A-Za-z0-9_-]{10,}|AIza[0-9A-Za-z_-]{20,}|A[SK]IA[0-9A-Z]{16}|https://hooks\.slack\.com/services/\S+|eyJ[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{3,}\.[A-Za-z0-9_-]*|-----BEGIN [A-Z0-9 ]*PRIVATE KEY[A-Z0-9 ]*-----.*?-----END [A-Z0-9 ]*PRIVATE KEY[A-Z0-9 ]*-----|://[^/\s]+@|-u[^\s\"']+:\S+|(?:-u|--user|--password|--passphrase)(?:=|\s+)(?:\"[^\"]*\"|'[^']*'|\S+)|\"(?:api_?key|access_token|client_secret|apiSecret|token|secret|password|database_url|slack_webhook)\"\s*:\s*\"(?:\\.|[^\"])*\"|\b[A-Za-z0-9_]*(?:KEY|SECRET|TOKEN|PASSWORD|PAT|WEBHOOK|DATABASE_URL|CONNECTION_STRING|NPM_RC|PASS|DSN)\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s\n]+))"
)
s = re.sub(r"\x1b\[[0-9;?]*[ -/]*[@-~]", "", sys.argv[1])
s = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", " ", s)
print(SECRET_VAL.sub("[REDACTED]", s).replace("\r", "").replace("\t", " "), end="")
PY
}

trace() { # name status detail
  [ -n "${TRACE_FILE:-}" ] || return 0
  python3 - "$TRACE_FILE" "$RUN_ID" "$UNIT" "$1" "$2" "$3" <<'PY'
import fcntl, json, os, re, sys
from datetime import datetime, timezone

SECRET_VAL = re.compile(
    r"(?is)(Bearer\s+\S+|Basic\s+[A-Za-z0-9+/=_-]{4,}|sk-[A-Za-z0-9_-]{8,}|gh[opsuhr]_[A-Za-z0-9_]{16,}|github_pat_[A-Za-z0-9_-]{16,}|x(?:ox[baprs]|app)-[A-Za-z0-9_-]{10,}|AIza[0-9A-Za-z_-]{20,}|A[SK]IA[0-9A-Z]{16}|https://hooks\.slack\.com/services/\S+|eyJ[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{3,}\.[A-Za-z0-9_-]*|-----BEGIN [A-Z0-9 ]*PRIVATE KEY[A-Z0-9 ]*-----.*?-----END [A-Z0-9 ]*PRIVATE KEY[A-Z0-9 ]*-----|://[^/\s]+@|-u[^\s\"']+:\S+|(?:-u|--user|--password|--passphrase)(?:=|\s+)(?:\"[^\"]*\"|'[^']*'|\S+)|\"(?:api_?key|access_token|client_secret|apiSecret|token|secret|password|database_url|slack_webhook)\"\s*:\s*\"(?:\\.|[^\"])*\"|\b[A-Za-z0-9_]*(?:KEY|SECRET|TOKEN|PASSWORD|PAT|WEBHOOK|DATABASE_URL|CONNECTION_STRING|NPM_RC|PASS|DSN)\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s\n]+))"
)

def scrub_text(s):
    s = re.sub(r"\x1b\[[0-9;?]*[ -/]*[@-~]", "", s)
    s = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", " ", s)
    return SECRET_VAL.sub("[REDACTED]", s).replace("\r", "").replace("\t", " ")

path, run_id, unit, tool, status, detail = sys.argv[1:7]
real_p = os.path.realpath(path)
if not real_p.endswith(".jsonl") or (os.path.basename(os.path.dirname(real_p)) != "traces" and not real_p.startswith(("/tmp/", "/private/tmp/"))):
    sys.exit(0)
line = {
    "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "run_id": scrub_text(run_id)[:128],
    "unit": scrub_text(unit)[:64],
    "event": "gate_result",
    "tool": tool,
    "status": status,
    "detail": scrub_text(detail)[-500:],
}
with open(real_p, "a") as f:
    fcntl.flock(f, fcntl.LOCK_EX)
    f.write(json.dumps(line) + "\n")
PY
}

gate() { # name command
  local name="$1" cmd="$2" out clean
  if [ -z "$cmd" ]; then
    echo "GATE $name: SKIP"
    trace "$name" skip "no command set"
    return 0
  fi
  echo "GATE $name: RUN"
  if out=$(bash -o pipefail -c "$cmd" 2>&1); then
    clean=$(scrub "$out")
    trace "$name" pass "$(printf '%s' "$clean" | tail -n 5)"
  else
    clean=$(scrub "$out")
    echo "GATE FAILED: $name" >&2
    printf '%s\n' "$clean" | tail -n 40 >&2
    trace "$name" fail "$(printf '%s' "$clean" | tail -n 10)"
    FAILED=1
  fi
}

gate test "$TEST_CMD"
gate typecheck "$TYPECHECK_CMD"
gate lint "$LINT_CMD"
gate build "$BUILD_CMD"

if [ "$FAILED" -ne 0 ]; then exit 1; fi
echo "GATE PASS"
