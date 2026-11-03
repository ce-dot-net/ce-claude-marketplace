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
  next to it (exit 0, no output) so nothing a hook does can reach the registry.
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
_KEEP = ("ACE_E2E", "ACE_PLUGIN_ROOT_UNDER_TEST", "ACE_E2E_CLI", "ACE_PRERELEASE_PREFIX")

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


_OPT_IN = ("real_engine", "live_server")


def pytest_collection_modifyitems(config, items):
    """real_engine (real @ace-sdk/core subprocesses vs the localhost fake server, load-sensitive) and live_server
    (the real ACE server) are out of the default gate: run them with `-m real_engine` / `-m live_server`."""
    if config.getoption("markexpr", ""):
        return
    keep = [i for i in items if not any(i.get_closest_marker(m) for m in _OPT_IN)]
    if len(keep) != len(items):
        config.hook.pytest_deselected(items=[i for i in items if i not in keep])
        items[:] = keep


def pytest_configure(config):
    config.addinivalue_line("markers", "real_engine: real @ace-sdk/core vs the fake server; opt in with -m real_engine")
    config.addinivalue_line("markers", "live_server: talks to the real ACE server; opt in with -m live_server")
    config.addinivalue_line(
        "markers", "real_ace_cli: run without the fake ace-cli on PATH (opt out of the hermetic fake)"
    )
    real_home = os.environ.get("HOME", "")
    root = Path(tempfile.mkdtemp(prefix="ace-tests-"))
    home = root / "home"
    fake_bin = root / "fake-bin"
    for d in (home, fake_bin, root / "ace-plugin-data", root / "xdg-config", root / "xdg-data"):
        d.mkdir(parents=True, exist_ok=True)

    fake = fake_bin / "ace-cli"
    fake.write_text(_FAKE_CLI % {"python": sys.executable, "search": json.dumps(FAKE_SEARCH_OUTPUT)})
    fake.chmod(0o755)
    # npm stub: the only npm a hook may run is `npm rebuild better-sqlite3` (DESIGN §23) -> no network.
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
        "ACE_LEARN_INLINE": "1",  # Stop/SubagentStop learn detaches by default; tests need it synchronous
        "HOME": str(home),
        "CLAUDE_PLUGIN_DATA": str(root / "ace-plugin-data"),
        "XDG_CONFIG_HOME": str(root / "xdg-config"),
        "XDG_DATA_HOME": str(root / "xdg-data"),
        "ACE_FAKE_CLI_LOG": str(root / "fake-ace-cli.log"),
        "PATH": str(fake_bin) + os.pathsep + os.environ.get("PATH", ""),
    })
    from plugin_copy import REPO_PLUGIN, hermetic_root
    if (REPO_PLUGIN / "node_modules").exists() and "CLAUDE_PLUGIN_ROOT" not in os.environ:
        # session-wide too: modules that resolve their root at import time (ace_engine) must not see the real install
        os.environ["CLAUDE_PLUGIN_ROOT"] = str(hermetic_root())
    _state.update(root=root, fake_bin=fake_bin)
    # Guard: no in-process relevance row may target the developer's real <repo>/.claude/data/logs (every row goes
    # through plugin_data_dir.open_project_log); hook subprocesses are kept out by the per-test cwd below.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "ace" / "shared-hooks" / "utils"))
    import plugin_data_dir
    real_log = (Path(__file__).resolve().parent.parent / ".claude" / "data" / "logs" / "ace-relevance.jsonl").resolve()
    orig = plugin_data_dir.open_project_log

    def guarded(path, *a, **kw):
        if Path(path).resolve() == real_log:
            _state.setdefault("real_log_writes", []).append(str(path))
        return orig(path, *a, **kw)
    plugin_data_dir.open_project_log = guarded


def pytest_sessionfinish(session, exitstatus):
    if _state.get("real_log_writes"):
        print("\nFAIL: %d test rows written to the real repo .claude/data/logs/ace-relevance.jsonl" % len(_state["real_log_writes"]))
        session.exitstatus = 1


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
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", tempfile.mkdtemp(prefix="ace-pd-", dir=str(_state["root"] / "ace-plugin-data")))
    from plugin_copy import REPO_PLUGIN, hermetic_root
    if (REPO_PLUGIN / "node_modules").exists() and "CLAUDE_PLUGIN_ROOT" not in os.environ:
        # in-process tests: the hooks' own location must not find a developer's real node_modules
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(hermetic_root()))
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
