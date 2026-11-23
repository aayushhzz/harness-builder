#!/usr/bin/env python3
"""Generate .claude/settings.json permissions from harness/walls.json."""
import json
import os
import sys
import tempfile


def dedupe(items):
    seen = set()
    out = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def generate_permissions(walls):
    allow, deny, ask = [], [], []

    for g in walls.get("allow_write", []):
        allow.extend([f"Edit({g})", f"Write({g})"])
    for g in walls.get("deny_write", []):
        deny.extend([f"Edit({g})", f"Write({g})"])

    for g in walls.get("allow_read", []):
        allow.append(f"Read({g})")
    for g in walls.get("deny_read", []):
        deny.append(f"Read({g})")

    for cmd in walls.get("allow_bash", []):
        allow.append(f"Bash({cmd}:*)")
    for cmd in walls.get("deny_bash", []):
        deny.append(f"Bash({cmd}:*)")

    has_network = "network_allow" in walls
    for tool in walls.get("allow_tools", []):
        if has_network and tool == "WebFetch":
            raise ValueError("allow_tools must not include bare 'WebFetch' when network_allow is set")
        allow.append(tool)

    ask.extend(walls.get("ask", []))

    if has_network:
        deny.extend(["Bash(curl:*)", "Bash(wget:*)", "Bash(ssh:*)"])
        for host in walls.get("network_allow", []):
            allow.append(f"WebFetch(domain:{host})")

    deny_list = dedupe(deny)
    deny_set = set(deny_list)
    ask_list = [x for x in dedupe(ask) if x not in deny_set]
    blocked = deny_set | set(ask_list)
    allow_list = [x for x in dedupe(allow) if x not in blocked]

    return {"allow": allow_list, "deny": deny_list, "ask": ask_list}


def main():
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
    walls_path = os.path.join(root, "harness", "walls.json")
    settings_path = os.path.join(root, ".claude", "settings.json")

    with open(walls_path) as f:
        walls = json.load(f)

    if os.path.exists(settings_path):
        with open(settings_path) as f:
            settings = json.load(f)
    else:
        os.makedirs(os.path.dirname(settings_path), exist_ok=True)
        settings = {}

    settings["permissions"] = generate_permissions(walls)

    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(settings_path), prefix=".settings_", suffix=".tmp")
    with os.fdopen(fd, "w") as f:
        json.dump(settings, f, indent=2)
        f.write("\n")
    os.replace(tmp, settings_path)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"gen_permissions error: {exc}", file=sys.stderr)
        sys.exit(1)
