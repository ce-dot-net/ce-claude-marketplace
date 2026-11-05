"""Guards for the hermetic test environment (tests/conftest.py, DESIGN §6 WP-F,
code-tests-release-infra §0.6: tests leaked state into the repo and read the
developer's ACE_ORG_ID/ACE_PROJECT_ID)."""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def test_home_and_plugin_data_are_sandboxed():
    """HOME / CLAUDE_PLUGIN_DATA / XDG_* never point at the developer's real dirs."""
    for key in ("HOME", "CLAUDE_PLUGIN_DATA", "XDG_CONFIG_HOME", "XDG_DATA_HOME"):
        assert "ace-tests-" in os.environ[key], (key, os.environ[key])


def test_ace_and_session_env_is_stripped():
    """ACE_ORG_ID/ACE_PROJECT_ID (exported by CC from .claude/settings.json) must not leak in."""
    leaked = [k for k in os.environ if k.startswith("ACE_") and k not in
              ("ACE_FAKE_CLI_LOG", "ACE_E2E", "ACE_PLUGIN_ROOT_UNDER_TEST", "ACE_LEARN_INLINE", "ACE_AUTO_INSTALL")]
    leaked += [k for k in ("CLAUDE_CODE_SESSION_ID", "CLAUDE_PROJECT_DIR") if k in os.environ]
    assert leaked == []
    from plugin_copy import hermetic_root  # only the copy conftest sets when node_modules exists, never CC's own root
    assert os.environ.get("CLAUDE_PLUGIN_ROOT") in (None, str(hermetic_root()))


def test_cwd_is_not_the_checkout():
    """Hooks resolve .claude/data/logs relative to cwd; tests must not write into the repo."""
    assert REPO not in Path.cwd().resolve().parents and Path.cwd().resolve() != REPO


def test_fake_ace_cli_logs_argv_and_returns_empty_search(fake_cli_calls):
    """The fake ace-cli is first on PATH, logs argv+stdin, answers search/learn offline."""
    assert "ace-tests-" in shutil.which("ace-cli")
    out = subprocess.run(["ace-cli", "search", "--stdin", "--json"], input="hello",
                         capture_output=True, text=True, check=True).stdout
    assert out.strip() == '{"count": 0, "similar_patterns": []}'
    learn = subprocess.run(["ace-cli", "learn", "--json"], capture_output=True, text=True, check=True).stdout
    assert learn.strip() == "{}"
    assert fake_cli_calls() == [
        {"argv": ["search", "--stdin", "--json"], "stdin": "hello"},
        {"argv": ["learn", "--json"], "stdin": ""},
    ]


@pytest.mark.real_ace_cli
def test_real_ace_cli_marker_removes_the_fake():
    """Opt-out marker: the fake dir is gone from PATH."""
    found = shutil.which("ace-cli")
    assert found is None or "ace-tests-" not in found
