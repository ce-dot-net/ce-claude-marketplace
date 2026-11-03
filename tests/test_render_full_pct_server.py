#!/usr/bin/env python3
"""Server kill switch for the §31 full split: the search response MAY carry a top-level integer `render_full_pct`
(0-100). Every search persists the latest valid value to <plugin data>/render-full-pct.json ({"pct", "at"}, 0600).
Precedence for the full share: env ACE_RENDER_FULL_PCT if set > server value (file younger than 7 days) > 50.
"""
import hashlib
import json
import os
import stat
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "plugins" / "ace" / "shared-hooks" / "utils"))

import ace_cli  # noqa: E402
import plugin_data_dir  # noqa: E402
from ace_pattern_render import full_pct_source, render_arm, trace_render_variant  # noqa: E402

FULL_SID = next("conv-%d" % i for i in range(1000)
                if int(hashlib.sha256(("render:conv-%d" % i).encode()).hexdigest()[:8], 16) % 100 < 50)


@pytest.fixture
def env(monkeypatch, tmp_path):
    for k in ("ACE_AB_CONTROL_PCT", "ACE_AB_COMPACT_PCT", "ACE_RENDER_FULL_PCT"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(ace_cli.ace_engine, "preflight", lambda: (None, "test"))
    return monkeypatch


def _search(payload):
    r = MagicMock(returncode=0, stdout=json.dumps(payload).encode(), stderr=b"")
    with patch("subprocess.run", return_value=r):
        return ace_cli.run_search("q", hook_event_name="UserPromptSubmit")[0]


def _resp(**extra):
    return dict({"similar_patterns": [], "count": 0}, **extra)


def _file():
    return plugin_data_dir.data_root() / "render-full-pct.json"


def test_default_full_bucket_session_is_full(env):
    assert render_arm(FULL_SID) == "full" and full_pct_source() == (50, "default")


def test_server_0_turns_full_off_from_the_next_arm(env):
    _search(_resp(render_full_pct=0))
    data = json.loads(_file().read_text())
    assert data["pct"] == 0 and abs(data["at"] - time.time()) < 60
    assert stat.S_IMODE(os.stat(_file()).st_mode) == 0o600
    assert render_arm(FULL_SID) == "budget" and full_pct_source() == (0, "server")
    assert trace_render_variant(None, FULL_SID, mod=True) == "budget", "label fallback says budget"


def test_env_overrides_server(env):
    _search(_resp(render_full_pct=0))
    env.setenv("ACE_RENDER_FULL_PCT", "100")
    assert render_arm(FULL_SID) == "full" and full_pct_source() == (100, "env")


def test_stale_file_ignored(env):
    plugin_data_dir.private_write(_file(), json.dumps({"pct": 0, "at": time.time() - 8 * 86400}))
    assert render_arm(FULL_SID) == "full" and full_pct_source() == (50, "default")


@pytest.mark.parametrize("bad", [-1, 101, "0", 12.5, True, None, [0]])
def test_invalid_server_value_ignored(env, bad):
    _search(_resp(render_full_pct=0))
    _search(_resp(render_full_pct=bad))
    assert json.loads(_file().read_text())["pct"] == 0, "invalid value does not overwrite"
    assert full_pct_source() == (0, "server")


def test_invalid_value_alone_writes_nothing(env):
    _search(_resp(render_full_pct="off"))
    assert not _file().exists() and full_pct_source() == (50, "default")


def test_missing_field_keeps_stored_value(env):
    _search(_resp(render_full_pct=0))
    _search(_resp())
    assert full_pct_source() == (0, "server") and render_arm(FULL_SID) == "budget"


@pytest.mark.parametrize("raw", ["not json", '{"pct": 200, "at": 1}', '{"pct": 0}', '[]'])
def test_corrupt_file_ignored(env, raw):
    plugin_data_dir.private_write(_file(), raw)
    assert full_pct_source() == (50, "default")


def test_doctor_readme_changelog_name_the_server_switch():
    ace = REPO / "plugins" / "ace"
    doctor = (ace / "commands" / "ace-doctor.md").read_text()
    assert "full_pct_source" in doctor and "env | server | default" in doctor
    for f in ("README.md", "CHANGELOG.md"):
        assert "`render_full_pct`" in (ace / f).read_text(), f
