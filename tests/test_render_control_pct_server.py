#!/usr/bin/env python3
"""Server-supplied A/B CONTROL share: the search response MAY carry a top-level integer `render_control_pct` (0-100).
Every search persists the latest valid value to <plugin data>/render-control-pct.json ({"pct", "at"}, 0600), its OWN file.
Precedence: env ACE_AB_CONTROL_PCT if set > server value (file younger than 7 days) > 0 (control off).
Hash unchanged: bucket = sha256("render:" + conversation_id)[:8] % 100; buckets 0..pct-1 = control, before compact/full.
Traces carry render_variant 'control' and render_control_pct (the share applied, 0 when off).
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
from ace_pattern_render import render_arm, render_cohort, render_control_pct, trace_render_variant  # noqa: E402

VECTORS = json.loads((REPO / "plugins" / "ace" / "tests-fixtures" / "control-pct" / "vectors.json").read_text())


def _bucket(sid):
    return int(hashlib.sha256(("render:" + sid).encode()).hexdigest()[:8], 16) % 100


def _sid(pred):
    return next("cc-%d" % i for i in range(10000) if pred(_bucket("cc-%d" % i)))


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
    return plugin_data_dir.data_root() / "render-control-pct.json"


def test_default_is_off(env):
    assert render_control_pct() == 0
    assert all(render_arm("cc-%d" % i) != "control" for i in range(200))


def test_server_value_applies_and_is_stored_0600_in_its_own_file(env):
    _search(_resp(render_control_pct=30))
    data = json.loads(_file().read_text())
    assert data["pct"] == 30 and abs(data["at"] - time.time()) < 60
    assert stat.S_IMODE(os.stat(_file()).st_mode) == 0o600
    assert not plugin_data_dir.render_full_pct_file().exists(), "render-full-pct.json untouched"
    assert render_control_pct() == 30
    assert render_arm(_sid(lambda b: b < 30)) == "control"
    assert render_arm(_sid(lambda b: b >= 30)) != "control"


def test_bucket_boundary_at_pct(env):
    _search(_resp(render_control_pct=40))
    assert render_arm(_sid(lambda b: b == 39)) == "control"
    assert render_arm(_sid(lambda b: b == 40)) != "control"
    assert render_cohort(_sid(lambda b: b < 40)) == "control"


def test_env_overrides_server(env):
    _search(_resp(render_control_pct=100))
    env.setenv("ACE_AB_CONTROL_PCT", "0")
    assert render_control_pct() == 0 and render_arm(_sid(lambda b: b < 50)) != "control"
    _file().unlink()
    _search(_resp(render_control_pct=0))
    env.setenv("ACE_AB_CONTROL_PCT", "100")
    assert render_control_pct() == 100 and render_arm(_sid(lambda b: b > 90)) == "control"


def test_stale_file_ignored(env):
    plugin_data_dir.private_write(_file(), json.dumps({"pct": 100, "at": time.time() - 8 * 86400}))
    assert render_control_pct() == 0
    plugin_data_dir.private_write(_file(), json.dumps({"pct": 100, "at": time.time() - 6 * 86400}))
    assert render_control_pct() == 100


@pytest.mark.parametrize("bad", [-1, 101, "10", 12.5, True, None, [10]])
def test_invalid_server_value_ignored(env, bad):
    _search(_resp(render_control_pct=10))
    _search(_resp(render_control_pct=bad))
    assert json.loads(_file().read_text())["pct"] == 10, "invalid value does not overwrite"


def test_invalid_value_alone_writes_nothing(env):
    _search(_resp(render_control_pct="off"))
    assert not _file().exists() and render_control_pct() == 0


def test_missing_field_keeps_stored_value(env):
    _search(_resp(render_control_pct=25))
    _search(_resp())
    assert render_control_pct() == 25


@pytest.mark.parametrize("raw", ["not json", '{"pct": 200, "at": 1}', '{"pct": 5}', '[]', '{"pct": true, "at": 9999999999}'])
def test_corrupt_file_ignored(env, raw):
    plugin_data_dir.private_write(_file(), raw)
    assert render_control_pct() == 0


def test_control_plus_compact_over_100_means_both_0(env):
    _search(_resp(render_control_pct=60))
    env.setenv("ACE_AB_COMPACT_PCT", "50")
    assert render_control_pct() == 0
    assert all(render_arm("cc-%d" % i) in ("full", "budget") for i in range(100))


def test_full_share_is_capped_to_the_rest(env):
    _search(_resp(render_control_pct=80))
    env.setenv("ACE_RENDER_FULL_PCT", "100")
    arms = {render_arm("cc-%d" % i) for i in range(300)}
    assert arms == {"control", "full"}
    assert render_arm(_sid(lambda b: b >= 80)) == "full" and render_arm(_sid(lambda b: b < 80)) == "control"


def test_no_conversation_id_is_never_control(env):
    _search(_resp(render_control_pct=100))
    assert render_arm(None) == "budget" and render_arm("") == "budget"


def test_trace_label_control(env):
    _search(_resp(render_control_pct=100))
    assert trace_render_variant("control", None) == "control"
    assert trace_render_variant(None, "cc-1") == "control", "no stored label: the conversation arm"
    assert trace_render_variant("compact", None) is None, "compact stays no server label"


# ---------- parity vectors shared with the mod (tests-fixtures/control-pct/vectors.json) ----------
def test_vectors_200_ids_every_config(env):
    assert len(VECTORS["ids"]) == 200
    for cfg in VECTORS["configs"]:
        raw = cfg.get("raw", cfg)
        env.setenv("ACE_AB_COMPACT_PCT", str(raw["comp"]))
        env.setenv("ACE_RENDER_FULL_PCT", str(raw["full"]))
        env.delenv("ACE_AB_CONTROL_PCT", raising=False)
        _file().parent.mkdir(parents=True, exist_ok=True)
        plugin_data_dir.private_write(_file(), json.dumps({"pct": raw["ctrl"], "at": time.time()}))  # the share comes from the server
        assert [render_arm(i) for i in VECTORS["ids"]] == cfg["arms"], cfg["ctrl"]
        env.setenv("ACE_AB_CONTROL_PCT", str(raw["ctrl"]))  # and from env: same arms
        plugin_data_dir.private_write(_file(), json.dumps({"pct": 0, "at": time.time()}))
        assert [render_arm(i) for i in VECTORS["ids"]] == cfg["arms"], cfg["ctrl"]
