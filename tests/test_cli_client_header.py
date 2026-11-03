#!/usr/bin/env python3
"""ace-cli >= 4.3.0 sends X-ACE-Client from ACE_CLIENT_ID (default 'cli'). The plugin's CLI path
(ace_cli._env, ACE_ENGINE=cli) must export it so the server reads the plugin, not the bare CLI.
Real pinned CLI (plugins/ace/node_modules) against the hermetic engine_fake_server.py (logs headers)."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import engine_harness as E

REPO_PLUGIN = Path(__file__).resolve().parent.parent / "plugins" / "ace"
CLI_JS = REPO_PLUGIN / "node_modules" / "@ace-sdk" / "cli" / "dist" / "cli.js"

pytestmark = pytest.mark.skipif(not (CLI_JS.is_file() and E.node_bin()),
                                reason="pinned CLI not installed: npm ci --ignore-scripts in plugins/ace")

DRIVER = r"""
import json, sys
sys.path.insert(0, sys.argv[1])
import ace_cli
res, _ = ace_cli.run_search("hook json", org="org_fake", project="prj_fake", top_k=5)
print(json.dumps({"retrieval_id": (res or {}).get("retrieval_id")}))
ace_cli.run_learn({"task": "t", "trajectory": [], "result": {"success": True, "output": "ok"}, "playbook_used": []},
                  retrieval_id="ret-fake-1", applied_log_ids=[7], org="org_fake", project="prj_fake", timeout=60)
"""


def test_cli_path_sends_the_plugin_client_header(tmp_path):
    srv = E.FakeServer(tmp_path)
    try:
        env = E.sdk_env(tmp_path, srv, ACE_ENGINE="cli", CLAUDE_PROJECT_DIR=str(tmp_path / "proj"),
                        CLAUDE_PLUGIN_DATA=str(tmp_path / "data"))
        env.pop("CLAUDE_PLUGIN_ROOT", None)
        cache = tmp_path / "home" / ".ace-cache"
        cache.mkdir(parents=True, exist_ok=True)
        (cache / "cli-version-check.json").write_text(json.dumps(  # keep the CLI's npm check offline
            {"lastCheck": 32503680000000, "latestVersion": "0.0.0", "timestamp": 32503680000000}))
        r = subprocess.run([sys.executable, "-c", DRIVER, str(REPO_PLUGIN / "shared-hooks" / "utils")],
                           capture_output=True, text=True, env=env, timeout=120, cwd=str(tmp_path))
        assert r.returncode == 0, r.stderr
        assert json.loads(r.stdout.splitlines()[-1])["retrieval_id"] == "ret-fake-1", r.stdout
        reqs = srv.requests()
    finally:
        srv.stop()
    want = "claude-code-plugin/" + E.plugin_version()
    hits = [q for q in reqs if q["path"].startswith(("/patterns/search", "/traces"))]
    assert {q["path"].split("?")[0].split("/")[1] for q in hits} >= {"patterns", "traces"}, [q["path"] for q in reqs]
    for q in hits:
        assert q["headers"].get("X-ACE-Client") == want, q
