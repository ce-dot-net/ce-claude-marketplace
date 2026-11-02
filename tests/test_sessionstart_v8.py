#!/usr/bin/env python3
"""WP-A RED: slim SessionStart (`scripts/ace_install_cli.sh`), DESIGN §3 + §4 + §8.

Sync path (matcher startup|clear): `command -v ace-cli`, cache python path + cli
version under CLAUDE_PLUGIN_DATA, NO whoami, NO network. Async path
(`--update-check`, matcher startup): orphan sweep + sqlite rebuild; the daily npm check is gone (§23).
Critic T22 (2.4-2.8 s CPU of --version+whoami+npm per startup, bogus
"Update available v4.2.2 -> v4.1.2"), T17/T21 (/tmp flags), DESIGN §8 (CLAUDE_ENV_FILE
must export the SAME ACE_CLIENT_ID as _ace_env.sh). The first response waits for sync
SessionStart hooks (cc_hooks_reference.md:1248).

Every run uses a fake ace-cli/npm on PATH (tests/wpa_harness.py).
"""
import json
import os
import re
import time
from pathlib import Path

from wpa_harness import Env, parse_stdout, plugin_version

SCRIPT = "ace_install_cli.sh"


def _ev(sid, source="startup"):
    return {"session_id": sid, "hook_event_name": "SessionStart", "source": source,
            "cwd": "", "transcript_path": ""}


def _start(env, sid="s-start", source="startup", args=(), **extra):
    ev = _ev(sid, source)
    ev["cwd"] = str(env.project)
    try:
        r = env.run(SCRIPT, ev, args=args, **extra)
    finally:
        # while RED the v7 script still writes this; never leave litter in /tmp
        tmp_flag = Path("/tmp/ace-disabled-%s.flag" % sid)
        leaked = tmp_flag.exists()
        if leaked:
            tmp_flag.unlink()
    assert r.returncode == 0, r.stderr
    assert not leaked, "SessionStart wrote /tmp/ace-disabled-%s.flag (DESIGN §4: plugin data only)" % sid
    return r


def test_startup_caches_python_path(tmp_path):
    """DESIGN §3.1/§4: SessionStart writes <data>/python_path (an executable python) so
    every shim skips resolving python again."""
    env = Env(tmp_path)
    _start(env)
    p = env.data / "python_path"
    assert p.is_file(), "python_path not written under CLAUDE_PLUGIN_DATA"
    py = p.read_text().strip()
    assert py and os.access(py, os.X_OK), "python_path must name an executable: %r" % py


def test_startup_writes_cli_version_cache(tmp_path):
    """DESIGN §4: <data>/cli_version.json = {path: realpath(ace-cli), mtime, version}."""
    env = Env(tmp_path, cli_version="4.2.2")
    _start(env)
    f = env.data / "cli_version.json"
    assert f.is_file(), "cli_version.json not written"
    data = json.loads(f.read_text())
    assert data.get("version") == "4.2.2"
    assert data.get("path") == os.path.realpath(str(env.cli))
    assert "mtime" in data


def test_startup_reuses_cli_version_cache(tmp_path):
    """Critic T22: `ace-cli --version` costs ~1.2-1.65 s CPU. With an unchanged binary
    (same path + mtime) the second startup must not spawn it again."""
    env = Env(tmp_path)
    _start(env, sid="s1")
    first = len(env.cli_calls("--version"))
    assert first <= 1, "at most one --version probe on a cold cache, got %d" % first
    _start(env, sid="s2")
    assert len(env.cli_calls("--version")) == first, "warm cache must not re-run --version"


def test_startup_never_calls_whoami(tmp_path):
    """DESIGN §3 SessionStart row: NO whoami (critic T22, network + ~1 s CPU)."""
    env = Env(tmp_path)
    _start(env)
    _start(env, sid="s-clear", source="clear")
    assert env.cli_calls("whoami") == [], "SessionStart must not run `ace-cli whoami`"


def test_sync_startup_does_no_network(tmp_path):
    """DESIGN §3: the sync row does no network — npm only runs under --update-check."""
    env = Env(tmp_path)
    _start(env)
    assert env.npm_calls() == [], "sync SessionStart must not call npm: %s" % env.npm_calls()


def test_missing_cli_writes_no_disabled_flag(tmp_path):
    """DESIGN §23: never write disabled.flag for a missing CLI; ACE activates once one appears."""
    env = Env(tmp_path, with_cli=False)
    sid = "s-nocli-%d" % os.getpid()
    out = parse_stdout(_start(env, sid=sid).stdout)
    assert out and "/ace:ace-install-cli" in out.get("systemMessage", "")
    assert not env.disabled_flag(sid).exists()
    assert not Path("/tmp/ace-disabled-%s.flag" % sid).exists(), "must not write /tmp flag"


def test_outdated_cli_writes_no_disabled_flag(tmp_path):
    """DESIGN §23: a global below the package.json pin is resolution step 3 (none), not a disable."""
    env = Env(tmp_path, cli_version="4.0.0")
    sid = "s-old-%d" % os.getpid()
    out = parse_stdout(_start(env, sid=sid).stdout)
    assert out and "/ace:ace-install-cli" in out.get("systemMessage", "")
    assert not env.disabled_flag(sid).exists()
    assert not Path("/tmp/ace-disabled-%s.flag" % sid).exists()


def test_healthy_startup_clears_stale_disabled_flag(tmp_path):
    """A healthy startup re-enables ACE: an old §4 disabled.flag for this session is removed."""
    env = Env(tmp_path)
    flag = env.disabled_flag("s-heal")
    flag.parent.mkdir(parents=True)
    flag.write_text("CLI not installed")
    _start(env, sid="s-heal")
    assert not flag.exists(), "stale disabled.flag must be removed on healthy startup"


def test_stdout_is_one_json_object_with_multiple_warnings(tmp_path):
    """cc_hooks_reference.md (JSON output): stdout must be ONE JSON object. v7 printed one
    object per warning (two deprecated-config warnings -> invalid JSON, CC drops it)."""
    env = Env(tmp_path)
    (env.home / ".ace").mkdir()
    (env.home / ".ace" / "config.json").write_text('{"apiToken": "x"}')
    (env.home / ".config" / "ace").mkdir(parents=True)
    (env.home / ".config" / "ace" / "config.json").write_text('{"apiToken": "y"}')
    r = _start(env)
    out = parse_stdout(r.stdout)  # raises on concatenated objects
    assert out is None or isinstance(out, dict)


def test_env_file_exports_same_client_id_as_ace_env(tmp_path):
    """DESIGN §8: CLAUDE_ENV_FILE must export ACE_CLIENT_ID=claude-code-plugin/<version>
    (same as _ace_env.sh), not `claude-code`. Plain assignment (doc :1360-1388 PowerShell
    rule)."""
    env = Env(tmp_path)
    env_file = tmp_path / "claude-env.sh"
    env_file.touch()
    _start(env, CLAUDE_ENV_FILE=env_file)
    want = "claude-code-plugin/%s" % plugin_version()
    lines = [l for l in env_file.read_text().splitlines() if "ACE_CLIENT_ID" in l]
    assert lines, "no ACE_CLIENT_ID export written"
    assert re.fullmatch(r"""export ACE_CLIENT_ID=(["']?)%s\1""" % re.escape(want), lines[-1]), lines


def test_async_row_never_checks_npm_for_a_new_cli(tmp_path):
    """DESIGN §23: the plugin update check is removed: a plugin version runs the CLI it was tested with."""
    env = Env(tmp_path, cli_version="4.2.2")
    r = _start(env, args=("--update-check",), FAKE_NPM_LATEST="9.9.9")
    assert r.stdout.strip() == "", "async row prints nothing (doc :4093)"
    assert [c for c in env.npm_calls() if c.split()[:1] in (["show"], ["view"], ["install"])] == []
    assert "Update available" not in _start(env, sid="u-sync").stdout


def test_sync_startup_is_fast_with_warm_cache(tmp_path):
    """Critic T22: startup blocked 2.4-2.8 s CPU. With a warm cache and a fake CLI the
    slim hook must finish well under 1.5 s."""
    env = Env(tmp_path)
    _start(env, sid="w1")
    t0 = time.monotonic()
    _start(env, sid="w2")
    assert time.monotonic() - t0 < 1.5
