"""Shared harness for the WP-A v8 tests (SessionStart / SessionEnd / PermissionDenied shims).

Runs a real shim under scripts/ as CC would: stdin = hook JSON, env carries
CLAUDE_PLUGIN_ROOT / CLAUDE_PLUGIN_DATA, PATH holds a FAKE ace-cli + npm that log
their argv (never the real CLI, never the network). HOME, plugin data and the
project live in pytest tmp dirs. Not a test module (no test_ prefix).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from plugin_copy import hermetic_root

REPO = Path(__file__).resolve().parent.parent
PLUGIN = REPO / "plugins" / "ace"
SCRIPTS = PLUGIN / "scripts"
PROJECT_ID = "prj_wpa_test"
ORG_ID = "org_wpa_test"

_FAKE_CLI = r"""#!/bin/sh
# fake ace-cli: log "<ACE_CLIENT_ID>|<argv>" and answer like the real one
printf '%s|%s\n' "${ACE_CLIENT_ID:-}" "$*" >> "$FAKE_CLI_LOG"
case "$1" in
  --version) echo "${FAKE_CLI_VERSION:-4.2.2}" ;;
  whoami) echo '{"authenticated": true}' ;;
  learn) cat > /dev/null; echo '{}' ;;
  search) cat > /dev/null; echo '{"count":0,"similar_patterns":[]}' ;;
  *) echo '{}' ;;
esac
exit 0
"""

_FAKE_NPM = r"""#!/bin/sh
printf '%s\n' "$*" >> "$FAKE_NPM_LOG"
case "$1" in
  show|view) echo "${FAKE_NPM_LATEST:-4.2.2}" ;;
  root) echo "$FAKE_NPM_ROOT" ;;
esac
exit 0
"""


def plugin_version() -> str:
    return json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text())["version"]


class Env:
    """One hermetic hook environment rooted in a pytest tmp_path."""

    def __init__(self, tmp_path: Path, with_cli: bool = True, cli_version: str = "4.2.2"):
        self.tmp = tmp_path
        self.home = tmp_path / "home"
        self.data = tmp_path / "ace-plugin-data"
        self.project = tmp_path / "project"
        self.bin = tmp_path / "bin"
        self.cli_log = tmp_path / "fake-cli.log"
        self.npm_log = tmp_path / "fake-npm.log"
        for d in (self.home, self.data, self.project / ".claude", self.bin):
            d.mkdir(parents=True, exist_ok=True)
        (self.project / ".claude" / "settings.json").write_text(
            json.dumps({"projectId": PROJECT_ID, "orgId": ORG_ID}))
        self.cli_log.touch()
        self.npm_log.touch()
        # python3 on PATH = the interpreter running the tests; no jq/ace-cli/npm leak in
        (self.bin / "python3").symlink_to(sys.executable)
        self._write(self.bin / "npm", _FAKE_NPM)
        self.cli = self.bin / "ace-cli"
        if with_cli:
            self._write(self.cli, _FAKE_CLI)
        self.extra_env = {"FAKE_CLI_VERSION": cli_version}

    @staticmethod
    def _write(path: Path, body: str) -> None:
        path.write_text(body)
        path.chmod(0o755)

    def env(self, **extra) -> dict:
        drop = ("ACE_ORG_ID", "ACE_PROJECT_ID", "ACE_CLIENT_ID", "ACE_PLUGIN_VERSION",
                "CLAUDE_ENV_FILE", "CLAUDE_CODE_SESSION_ID", "CLAUDE_PROJECT_DIR",
                "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC", "ACE_DEBUG_HOOKS")
        e = {k: v for k, v in os.environ.items() if k not in drop}
        e.update({
            "HOME": str(self.home),
            "CLAUDE_PLUGIN_ROOT": str(hermetic_root()),
            "CLAUDE_PLUGIN_DATA": str(self.data),
            "PATH": "%s:/usr/bin:/bin" % self.bin,
            "FAKE_CLI_LOG": str(self.cli_log),
            "FAKE_NPM_LOG": str(self.npm_log),
            "FAKE_NPM_ROOT": str(self.tmp / "npm-root"),
        })
        e.update(self.extra_env)
        e.update({k: str(v) for k, v in extra.items()})
        return e

    def run(self, script: str, event: dict, args=(), cwd: Path = None, timeout: int = 30, **extra):
        return subprocess.run(
            [str(SCRIPTS / script)] + list(args),
            input=json.dumps(event), capture_output=True, text=True,
            cwd=str(cwd or self.project), env=self.env(**extra), timeout=timeout)

    def cli_calls(self, verb: str = None) -> list:
        """[(client_id, argv_str)] logged by the fake ace-cli, optionally filtered by argv[0]."""
        out = []
        for line in self.cli_log.read_text().splitlines():
            cid, _, argv = line.partition("|")
            if verb is None or argv.split(" ")[0] == verb:
                out.append((cid, argv))
        return out

    def npm_calls(self) -> list:
        return [l for l in self.npm_log.read_text().splitlines() if l.strip()]

    # DESIGN §4 paths (independent re-statement, so the test does not trust the impl)
    def session_dir(self, session_id: str) -> Path:
        return self.data / "projects" / PROJECT_ID / "sessions" / session_id

    def disabled_flag(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "disabled.flag"


def parse_stdout(stdout: str):
    """Hook stdout must be empty or exactly ONE JSON object (cc_hooks_reference: JSON alone on stdout)."""
    s = stdout.strip()
    if not s:
        return None
    return json.loads(s)  # raises on two concatenated objects
