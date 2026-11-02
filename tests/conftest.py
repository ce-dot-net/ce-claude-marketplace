"""Hermetic test environment for the ACE plugin suite (DESIGN §6 WP-F).

Applied before collection (pytest_configure), so modules that read HOME or
CLAUDE_PLUGIN_DATA at import time already see the sandbox:

- HOME, CLAUDE_PLUGIN_DATA, XDG_CONFIG_HOME, XDG_DATA_HOME -> one per-run temp dir
  (critic T25 / code-tests-release-infra §0.6: tests leaked state into the repo
  and into the developer's real plugin data dir).
- ACE_* and the CC session/project vars are stripped from the environment; a test
  that needs one sets it itself (monkeypatch.setenv / explicit subprocess env).
  ace_context.get_context() falls back to ACE_ORG_ID/ACE_PROJECT_ID
  (ace_context.py:27-29), which CC exports from .claude/settings.json `env`.
- A fake `ace-cli` is prepended to PATH. It appends one JSON line per call
  ({"argv": [...], "stdin": "..."}) to $ACE_FAKE_CLI_LOG and prints
  {"count":0,"similar_patterns":[]} for `search`, {} for `learn` and anything else,
  a version string for `--version`. Never calls the network. An `npm` stub sits
  next to it (exit 0, no output) so update checks stay offline.
  Opt out with @pytest.mark.real_ace_cli (the fake dir is removed from PATH).
- Every test runs with cwd = its own tmp dir, so hooks that resolve
  `.claude/data/logs` relative to cwd never write into the repo checkout.
"""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

_STRIP_EXACT = (
    "CLAUDE_CODE_SESSION_ID",
    "CLAUDE_PROJECT_DIR",
    "CLAUDE_PLUGIN_ROOT",
    "CLAUDE_ENV_FILE",
)

# Test-harness switches, not plugin config: survive the ACE_* strip.
_KEEP = ("ACE_E2E", "ACE_PLUGIN_ROOT_UNDER_TEST")

FAKE_SEARCH_OUTPUT = {"count": 0, "similar_patterns": []}

_FAKE_CLI = r'''#!%(python)s
# Fake ace-cli for the ACE test suite (tests/conftest.py). Logs argv, never touches the network.
import json, os, sys
argv = sys.argv[1:]
stdin = ""
if "--stdin" in argv:
    try:
        stdin = sys.stdin.read()
    except Exception:
        stdin = ""
log = os.environ.get("ACE_FAKE_CLI_LOG")
if log:
    try:
        with open(log, "a") as fh:
            fh.write(json.dumps({"argv": argv, "stdin": stdin[:4000]}) + "\n")
    except OSError:
        pass
if "--version" in argv or (argv and argv[0] == "version"):
    print("4.2.2")
elif argv and argv[0] == "search":
    print(%(search)r)
else:
    print("{}")
'''

_state = {}


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "real_ace_cli: run without the fake ace-cli on PATH (opt out of the hermetic fake)"
    )
    real_home = os.environ.get("HOME", "")
    root = Path(tempfile.mkdtemp(prefix="ace-tests-"))
    home = root / "home"
    fake_bin = root / "fake-bin"
    for d in (home, fake_bin, root / "plugin-data", root / "xdg-config", root / "xdg-data"):
        d.mkdir(parents=True, exist_ok=True)

    fake = fake_bin / "ace-cli"
    fake.write_text(_FAKE_CLI % {"python": sys.executable, "search": json.dumps(FAKE_SEARCH_OUTPUT)})
    fake.chmod(0o755)
    # npm stub: ace_install_cli.sh runs `npm show @ace-sdk/cli version` (update check) -> no network.
    npm = fake_bin / "npm"
    npm.write_text("#!/bin/sh\nexit 0\n")
    npm.chmod(0o755)

    # pyenv shims locate their root via $HOME/.pyenv; keep them working under the fake HOME.
    if real_home and "PYENV_ROOT" not in os.environ and (Path(real_home) / ".pyenv").is_dir():
        os.environ["PYENV_ROOT"] = str(Path(real_home) / ".pyenv")

    for key in list(os.environ):
        if (key.startswith("ACE_") and key not in _KEEP) or key in _STRIP_EXACT:
            del os.environ[key]

    os.environ.update({
        "HOME": str(home),
        "CLAUDE_PLUGIN_DATA": str(root / "plugin-data"),
        "XDG_CONFIG_HOME": str(root / "xdg-config"),
        "XDG_DATA_HOME": str(root / "xdg-data"),
        "ACE_FAKE_CLI_LOG": str(root / "fake-ace-cli.log"),
        "PATH": str(fake_bin) + os.pathsep + os.environ.get("PATH", ""),
    })
    _state.update(root=root, fake_bin=fake_bin)


def pytest_unconfigure(config):
    root = _state.get("root")
    if root:
        shutil.rmtree(str(root), ignore_errors=True)


@pytest.fixture(autouse=True)
def _hermetic_test(request, monkeypatch, tmp_path):
    """Per test: own cwd, own fake-cli log; optional real ace-cli."""
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    monkeypatch.setenv("ACE_FAKE_CLI_LOG", str(tmp_path / "fake-ace-cli.log"))
    # Per-test plugin data (WP-B): the disk search cache / session state must not
    # leak between tests (a cache hit would skip the spawn a later test counts).
    # Kept under the per-run ace-tests-* root so the sandbox guard still holds.
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", tempfile.mkdtemp(prefix="pd-", dir=str(_state["root"] / "plugin-data")))
    if request.node.get_closest_marker("real_ace_cli"):
        fake = str(_state["fake_bin"])
        monkeypatch.setenv(
            "PATH", os.pathsep.join(p for p in os.environ["PATH"].split(os.pathsep) if p != fake)
        )
    yield


@pytest.fixture
def fake_cli_calls():
    """Return a callable that reads the fake ace-cli invocations of the current test."""
    def _read():
        log = Path(os.environ["ACE_FAKE_CLI_LOG"])
        if not log.exists():
            return []
        return [json.loads(l) for l in log.read_text().splitlines() if l.strip()]
    return _read
