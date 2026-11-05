#!/usr/bin/env python3
"""8.1.1: the pinned plugin-local ace-cli is installed in the BACKGROUND at SessionStart.

Unit tests for the decision logic (needs-install, opt-out, throttle, lock, safety) plus an e2e in a throwaway
plugin copy with a FAKE `npm`/`node` on PATH that records every call (no network, no real npm).
"""
import hashlib
import json
import os
import shutil
import stat
import sys
import time
from pathlib import Path

import pytest

from plugin_copy import REPO_PLUGIN
from wpa_harness import Env, parse_stdout

UTILS = str(REPO_PLUGIN / "shared-hooks" / "utils")
PIN = json.loads((REPO_PLUGIN / "package.json").read_text())["dependencies"]["@ace-sdk/cli"]

_FAKE_NPM = r"""#!/bin/sh
printf '%s|%s|%s|%s\n' "$PWD" "$*" "${npm_config_replace_registry_host:-}" "${npm_config_ignore_scripts:-}" >> "$FAKE_NPM_LOG"
[ -n "$FAKE_NPM_SLEEP" ] && sleep "$FAKE_NPM_SLEEP"
[ -n "$FAKE_NPM_FAIL" ] && { echo "npm ERR! network" >&2; exit 1; }
if [ "$1" = ci ]; then
  V=$(sed -n 's/.*"@ace-sdk\/cli": *"\([^"]*\)".*/\1/p' package.json)
  mkdir -p node_modules/@ace-sdk/cli/dist
  printf '{"version":"%s"}' "$V" > node_modules/@ace-sdk/cli/package.json
  echo "// fake" > node_modules/@ace-sdk/cli/dist/cli.js
fi
exit 0
"""


@pytest.fixture
def box(tmp_path, monkeypatch):
    """A throwaway plugin copy (no node_modules), a fake bin dir, its own plugin data."""
    root = tmp_path / "cache" / "ace" / "8.1.1"
    shutil.copytree(str(REPO_PLUGIN), str(root), ignore=shutil.ignore_patterns("node_modules", "__pycache__", ".pytest_cache"))
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    for name, body in (("npm", _FAKE_NPM), ("node", "#!/bin/sh\nexit 0\n")):
        (bin_ / name).write_text(body)
        (bin_ / name).chmod(0o755)
    log = tmp_path / "npm.log"
    log.touch()
    data = tmp_path / "ace-plugin-data"
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(root))
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(data))
    monkeypatch.setenv("PATH", "%s:/usr/bin:/bin" % bin_)
    monkeypatch.setenv("FAKE_NPM_LOG", str(log))
    monkeypatch.setenv("ACE_AUTO_INSTALL", "1")
    monkeypatch.delenv("CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC", raising=False)
    monkeypatch.syspath_prepend(UTILS)
    import ace_cli_installer as inst
    return type("Box", (), {"root": root, "bin": bin_, "log": log, "data": data, "inst": inst,
                            "calls": lambda self: [l for l in log.read_text().splitlines() if l]})()


def _sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


# ---- decision logic ----

def test_needs_install_when_missing(box):
    assert box.inst.decide()[0] == "start"


def test_ok_when_pinned_cli_present(box):
    d = box.root / "node_modules" / "@ace-sdk" / "cli"
    (d / "dist").mkdir(parents=True)
    (d / "dist" / "cli.js").write_text("")
    (d / "package.json").write_text(json.dumps({"version": PIN}))
    assert box.inst.decide()[0] == "ok"


def test_wrong_version_needs_install(box):
    d = box.root / "node_modules" / "@ace-sdk" / "cli"
    (d / "dist").mkdir(parents=True)
    (d / "dist" / "cli.js").write_text("")
    (d / "package.json").write_text(json.dumps({"version": "0.0.1"}))
    assert box.inst.decide()[0] == "start"


def test_opt_out_never_spawns(box, monkeypatch):
    monkeypatch.setenv("ACE_AUTO_INSTALL", "0")
    assert box.inst.decide()[0] == "off"
    assert box.inst.ensure()["state"] == "off"
    assert box.inst.decide(auto=False)[0] == "start"  # the manual path ignores the opt-out


def test_managed_no_traffic_falls_back(box, monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC", "1")
    assert box.inst.decide()[0] == "unavailable"


def test_no_npm_falls_back(box, monkeypatch):
    (box.bin / "npm").unlink()
    monkeypatch.setenv("PATH", str(box.bin))
    s, why = box.inst.decide()
    assert s == "unavailable" and "npm" in why


def test_read_only_plugin_dir_falls_back(box):
    box.root.chmod(0o555)
    try:
        if os.access(str(box.root), os.W_OK):
            pytest.skip("running as a user that ignores directory modes")
        assert box.inst.decide()[0] == "unavailable"
    finally:
        box.root.chmod(0o755)


def test_node_modules_symlink_outside_refused(box, tmp_path):
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    (box.root / "node_modules").symlink_to(outside)
    assert box.inst.decide(auto=False)[0] == "unavailable"
    assert box.inst.run(auto=False)["state"] == "unavailable"
    assert box.calls() == [] and list(outside.iterdir()) == []


def test_node_modules_symlink_inside_allowed(box):
    (box.root / "real_nm").mkdir()
    (box.root / "node_modules").symlink_to(box.root / "real_nm")
    assert box.inst.decide()[0] == "start"


def test_non_https_lock_refused(box):
    lk = box.root / "package-lock.json"
    j = json.loads(lk.read_text())
    j["packages"]["node_modules/evil"] = {"version": "1.0.0", "resolved": "http://evil.example/evil.tgz"}
    lk.write_text(json.dumps(j))
    assert box.inst.run(auto=False)["state"] == "unavailable" and box.calls() == []


# ---- the run ----

def test_run_commands_cwd_registry_and_lock_untouched(box):
    lock, pkg = _sha(box.root / "package-lock.json"), _sha(box.root / "package.json")
    r = box.inst.run(auto=True)
    assert r["state"] == "ok", r
    c = [l.split("|") for l in box.calls()]
    assert [x[1] for x in c] == ["ci --ignore-scripts --no-audit --no-fund", "rebuild better-sqlite3"]
    assert all(os.path.realpath(x[0]) == os.path.realpath(str(box.root)) for x in c)  # the plugin dir, never the project
    assert all(x[2] == "never" for x in c)  # registry = the lockfile's resolved URLs
    assert (c[0][3], c[1][3]) == ("true", "false")  # ci without scripts; the rebuild needs them
    assert not any(x[1].startswith("install") for x in c)
    assert (_sha(box.root / "package-lock.json"), _sha(box.root / "package.json")) == (lock, pkg)
    assert box.inst.decide()[0] == "ok"
    line = [l for l in (box.data / "logs" / "ace-hook-errors.log").read_text().splitlines() if "cli_auto_install" in l]
    assert len(line) == 1 and " ok " in line[0]


def test_failure_is_throttled_per_version_per_hour(box, monkeypatch):
    monkeypatch.setenv("FAKE_NPM_FAIL", "1")
    t0 = time.time()
    assert box.inst.run(auto=True)["state"] == "failed"
    n = len(box.calls())
    s, why = box.inst.decide(True, now=t0 + 60)
    assert s == "failed" and "network" in why
    assert box.inst.ensure(now=t0 + 60)["state"] == "failed" and len(box.calls()) == n  # no retry storm
    assert box.inst.decide(True, now=t0 + 3601)[0] == "start"  # an hour later
    assert box.inst.decide(auto=False, now=t0 + 60)[0] == "start"  # [Erneut versuchen] / the command: not throttled
    # another plugin version (cache dir name) is not throttled by this one's failure
    other = box.root.parent / "8.1.2"
    box.root.rename(other)
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(other))
    assert box.inst.decide(True, now=t0 + 60)[0] == "start"


def test_failure_leaves_no_lock_and_manual_retry_runs(box, monkeypatch):
    monkeypatch.setenv("FAKE_NPM_FAIL", "1")
    box.inst.run(auto=True)
    assert not box.inst.lock_held()
    monkeypatch.delenv("FAKE_NPM_FAIL")
    assert box.inst.run(auto=False)["state"] == "ok"


def test_live_lock_blocks_second_installer(box):
    box.inst._pdd().cli_install_lock().write_text(json.dumps({"pid": os.getpid(), "at": time.time()}))
    assert box.inst.decide()[0] == "running"
    assert box.inst.run(auto=False)["state"] == "running" and box.calls() == []
    assert box.inst.ensure()["state"] == "running"


def test_stale_lock_is_taken_over(box):
    lk = box.inst._pdd().cli_install_lock()
    lk.write_text(json.dumps({"pid": os.getpid(), "at": time.time() - 5000}))  # live pid, but hung for too long
    assert box.inst.decide()[0] == "start"
    lk.write_text(json.dumps({"pid": 2 ** 22 + 12345, "at": time.time()}))  # dead pid
    assert box.inst.run(auto=True)["state"] == "ok"
    assert not lk.exists()


def test_cli_resolves_per_call_no_restart(box):
    """The shims resolve the CLI on every call: the same process sees the new CLI right after the install."""
    import ace_cli
    assert ace_cli.cli_source() is None
    assert box.inst.run(auto=True)["state"] == "ok"
    assert ace_cli.cli_source() == "plugin-local"


# ---- e2e: SessionStart in a throwaway copy, fake npm, background child ----

def _wait(pred, s=15):
    t0 = time.time()
    while time.time() - t0 < s:
        if pred():
            return True
        time.sleep(0.1)
    return False


@pytest.fixture
def e2e(tmp_path, box):
    env = Env(tmp_path / "e", with_cli=False)
    for n in ("npm", "node"):
        (env.bin / n).write_text((box.bin / n).read_text())
        (env.bin / n).chmod(0o755)
    env.npm_log = box.log
    return env, box


def _start(env, box, sid="s1", **extra):
    ev = {"session_id": sid, "hook_event_name": "SessionStart", "source": "startup", "cwd": str(env.project), "transcript_path": ""}
    kw = dict(CLAUDE_PLUGIN_ROOT=str(box.root), ACE_AUTO_INSTALL="1", FAKE_NPM_LOG=str(box.log))
    kw.update(extra)
    t0 = time.time()
    r = env.run("ace_install_cli.sh", ev, **kw)
    assert r.returncode == 0, r.stderr
    return r, time.time() - t0


def test_e2e_background_install_quiet_on_success(e2e):
    env, box = e2e
    r, dt = _start(env, box, FAKE_NPM_SLEEP="2")
    assert parse_stdout(r.stdout) is None, r.stdout  # no message while it runs, none after
    assert dt < 1.9, "SessionStart must not wait for npm (took %.1fs)" % dt
    assert _wait(lambda: (env.data / "cli-install.json").exists())
    assert json.loads((env.data / "cli-install.json").read_text())["ok"] is True
    assert [l.split("|")[1] for l in box.calls()][0].startswith("ci --ignore-scripts")
    n = len(box.calls())
    r2, _ = _start(env, box, sid="s2")
    assert parse_stdout(r2.stdout) is None and len(box.calls()) == n  # installed: nothing more to do


def test_e2e_failure_message_once_then_throttled(e2e):
    env, box = e2e
    r, _ = _start(env, box, FAKE_NPM_FAIL="1")
    assert parse_stdout(r.stdout) is None  # still running / starting: quiet
    assert _wait(lambda: (env.data / "cli-install.json").exists())
    n = len(box.calls())
    r2, _ = _start(env, box, sid="s2", FAKE_NPM_FAIL="1")
    msg = parse_stdout(r2.stdout)["systemMessage"]
    assert "automatic install failed" in msg and "/ace:ace-install-cli" in msg
    time.sleep(0.5)
    assert len(box.calls()) == n  # no retry within the hour


def test_e2e_opt_out_keeps_old_behavior(e2e):
    env, box = e2e
    r, _ = _start(env, box, ACE_AUTO_INSTALL="0")
    assert "Run /ace:ace-install-cli" in parse_stdout(r.stdout)["systemMessage"]
    time.sleep(0.5)
    assert box.calls() == []


def test_e2e_no_npm_falls_back_to_message(e2e):
    env, box = e2e
    (env.bin / "npm").unlink()
    r, _ = _start(env, box)
    assert "Run /ace:ace-install-cli" in parse_stdout(r.stdout)["systemMessage"]


# ---- the Python chain's ▼ line stays quiet while the install runs ----

def _notice(box, tmp_path, state):
    import ace_project_context as apc
    env = {"ACE_ORG_ID": "org_t", "ACE_PROJECT_ID": "prj_t"}
    p = apc._state_path("s1", "prj_t")
    apc._save(p, {"state": state, "shown": False, "adopted": None, "adopt_shown": False})
    line = apc.session_notice("s1", str(tmp_path), env=env, spawn_verify=False)
    return apc, line, apc._load(p)


def test_notice_quiet_while_installing(box, tmp_path):
    box.inst._pdd().cli_install_lock().write_text(json.dumps({"pid": os.getpid(), "at": time.time()}))
    apc, line, st = _notice(box, tmp_path, "cli_missing")
    assert line is None and st["state"] == "cli_missing" and not st["shown"]


def test_notice_shows_cli_missing_when_no_install_runs(box, tmp_path):
    apc, line, st = _notice(box, tmp_path, "cli_missing")
    assert line == apc.LINES["cli_missing"] and st["shown"]


def test_notice_drops_stale_cli_missing_once_the_cli_arrived(box, tmp_path):
    assert box.inst.run(auto=True)["state"] == "ok"
    apc, line, st = _notice(box, tmp_path, "cli_missing")
    assert line is None and st["state"] is None
