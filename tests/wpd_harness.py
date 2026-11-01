"""Shared subprocess harness for the WP-D hook tests (SubagentStart, domain shift,
SessionStart compact). Not a test module.

Runs a hook SHIM (plugins/ace/scripts/*.sh) the way Claude Code does: event JSON
on stdin, process cwd NOT the project (v8 shims never `cd`; DESIGN §3.1 — Python
must use the hook `cwd` field), a fake `ace-cli` first on PATH that logs argv +
stdin, and HOME / CLAUDE_PLUGIN_DATA pointed into tmp so nothing leaks.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PLUGIN_ROOT = REPO / "plugins" / "ace"
SCRIPTS = PLUGIN_ROOT / "scripts"
SHARED = PLUGIN_ROOT / "shared-hooks"
UTILS = SHARED / "utils"

for _p in (str(SHARED), str(UTILS), str(PLUGIN_ROOT / "utils")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

_FAKE_CLI = r'''#!/usr/bin/env python3
import json, os, sys
data = ""
try:
    if not sys.stdin.isatty():
        data = sys.stdin.read()
except Exception:
    pass
log = os.environ.get("ACE_FAKE_CLI_LOG")
if log:
    with open(log, "a") as f:
        f.write(json.dumps({"argv": sys.argv[1:], "stdin": data}) + "\n")
if os.environ.get("ACE_FAKE_CLI_EXIT"):
    sys.stderr.write("fake failure\n")
    sys.exit(int(os.environ["ACE_FAKE_CLI_EXIT"]))
if sys.argv[1:2] == ["search"]:
    resp = os.environ.get("ACE_FAKE_CLI_RESPONSE")
    sys.stdout.write(open(resp).read() if resp else '{"count":0,"similar_patterns":[]}')
elif sys.argv[1:2] == ["--version"]:
    sys.stdout.write("4.2.2\n")
else:
    sys.stdout.write("{}")
'''


class HookEnv:
    """tmp layout: home/, pd/ (CLAUDE_PLUGIN_DATA), proj/ (hook cwd), elsewhere/
    (process cwd), bin/ace-cli (fake)."""

    def __init__(self, tmp_path, project_id="prj-wpd-test", org_id="org-wpd-test"):
        self.tmp = Path(tmp_path)
        self.project_id = project_id
        self.home = self.tmp / "home"
        self.pd = self.tmp / "pd"
        self.proj = self.tmp / "proj"
        self.elsewhere = self.tmp / "elsewhere"
        self.bin = self.tmp / "bin"
        for d in (self.home, self.pd, self.proj / ".claude", self.elsewhere, self.bin):
            d.mkdir(parents=True, exist_ok=True)
        (self.proj / ".claude" / "settings.json").write_text(
            json.dumps({"projectId": project_id, "orgId": org_id}))
        cli = self.bin / "ace-cli"
        cli.write_text(_FAKE_CLI)
        cli.chmod(0o755)
        self.cli_log = self.tmp / "cli_calls.jsonl"
        self.response_file = self.tmp / "search_response.json"

    def set_search_response(self, obj):
        self.response_file.write_text(json.dumps(obj))

    def env(self, extra=None):
        path = os.pathsep.join([str(self.bin), os.path.dirname(sys.executable),
                                "/usr/bin", "/bin", "/usr/local/bin", "/opt/homebrew/bin"])
        e = {
            "PATH": path,
            "HOME": str(self.home),
            "CLAUDE_PLUGIN_DATA": str(self.pd),
            "CLAUDE_PLUGIN_ROOT": str(PLUGIN_ROOT),
            "ACE_FAKE_CLI_LOG": str(self.cli_log),
            "LANG": "en_US.UTF-8",
        }
        if self.response_file.exists():
            e["ACE_FAKE_CLI_RESPONSE"] = str(self.response_file)
        if extra:
            e.update(extra)
        return e

    def run(self, script, event, args=(), extra_env=None, raw_stdin=None, timeout=60):
        stdin = raw_stdin if raw_stdin is not None else json.dumps(event)
        proc = subprocess.run(
            ["bash", str(SCRIPTS / script)] + list(args),
            input=stdin, capture_output=True, text=True, timeout=timeout,
            cwd=str(self.elsewhere), env=self.env(extra_env),
        )
        return proc

    def cli_calls(self):
        if not self.cli_log.exists():
            return []
        return [json.loads(l) for l in self.cli_log.read_text().splitlines() if l.strip()]

    # ── v8 state layout (DESIGN §4) ──────────────────────────────────────────
    def session_dir(self, session_id):
        return self.pd / "projects" / self.project_id / "sessions" / session_id

    def domains_json(self):
        return self.pd / "projects" / self.project_id / "domains.json"

    def write_domains(self, domains):
        p = self.domains_json()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(domains))

    def state_file(self, session_id, agent_id=None):
        return self.session_dir(session_id) / ("patterns-used-%s.json" % (agent_id or "main"))

    def write_state(self, session_id, agent_id=None, **fields):
        p = self.state_file(session_id, agent_id)
        p.parent.mkdir(parents=True, exist_ok=True)
        base = {"pattern_ids": [], "retrieval_id": None, "retrieval_log_ids": {}}
        base.update(fields)
        p.write_text(json.dumps(base))
        return p

    def read_state(self, session_id, agent_id=None):
        p = self.state_file(session_id, agent_id)
        return json.loads(p.read_text()) if p.exists() else None

    def disable(self, session_id):
        d = self.session_dir(session_id)
        d.mkdir(parents=True, exist_ok=True)
        (d / "disabled.flag").write_text("disabled by test")

    def relevance_rows(self):
        p = self.proj / ".claude" / "data" / "logs" / "ace-relevance.jsonl"
        if not p.exists():
            return []
        rows = []
        for l in p.read_text().splitlines():
            try:
                rows.append(json.loads(l))
            except ValueError:
                pass
        return rows


def flag_value(argv, flag):
    """Value following `flag` in an argv list, or None."""
    if flag in argv:
        i = argv.index(flag)
        if i + 1 < len(argv):
            return argv[i + 1]
    return None


def shim_violations(script_path, entry):
    """DESIGN §3.1 thin-shim contract: no jq / cat / cd, exec the python entry."""
    text = Path(script_path).read_text()
    code = "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("#"))
    problems = []
    import re
    if re.search(r"\bjq\b", code):
        problems.append("uses jq")
    if re.search(r"(^|[;&|(\s])cat(\s|$|\))", code):
        problems.append("uses cat")
    # the §3.1 ROOT fallback `$(cd "$(dirname ...)/.." && pwd)` is the one allowed cd
    non_root = "\n".join(l for l in code.splitlines() if not l.lstrip().startswith("ROOT="))
    if re.search(r"(^|[;&|(\s])cd\s", non_root):
        problems.append("uses cd")
    if not re.search(r"exec\s+\"?\$PY\"?\s+\"?\$ROOT/shared-hooks/%s" % re.escape(entry), code):
        problems.append("does not `exec \"$PY\" \"$ROOT/shared-hooks/%s\"`" % entry)
    if "python_path" not in code:
        problems.append("does not read the cached python_path (DESIGN §3.1)")
    return problems
