"""WP-E (v8.0.0) — /ace:ace-doctor and command-markdown hygiene.

DESIGN §6 WP-E: ace-doctor.md gets a CC version check (`claude --version` >= 2.1.300),
a plugin-data layout check (§4), and resolves installPath from installed_plugins.json
instead of `ls -d .../ace/*/ | tail -1` (critic "Coverage gaps": stale cache-dir lookup).
DESIGN §3: PreToolUse / PreCompact / PermissionRequest are removed; PostToolUseFailure added.
DESIGN §0: no /tmp writes.
"""
import re
from pathlib import Path

import pytest

COMMANDS = Path(__file__).resolve().parent.parent / "plugins" / "ace" / "commands"
DOCTOR = COMMANDS / "ace-doctor.md"


def _doc():
    return DOCTOR.read_text(encoding="utf-8")


def test_doctor_checks_claude_code_version_floor_2_1_300():
    """DESIGN §1: WP-E adds a CC-version check to /ace:ace-doctor (floor 2.1.300)."""
    doc = _doc()
    assert "claude --version" in doc
    assert "2.1.300" in doc


def test_doctor_resolves_install_path_from_installed_plugins_json():
    """DESIGN §6 WP-E: installPath from installed_plugins.json (authoritative after a release)."""
    doc = _doc()
    assert "installed_plugins.json" in doc
    assert "installPath" in doc


@pytest.mark.parametrize("cmd", sorted(p.name for p in COMMANDS.glob("*.md")))
def test_command_has_no_tail_1_cache_glob(cmd):
    """Critic coverage gap: `ls -d cache/ace/*/ | tail -1` picks the lexically last dir, not the active one."""
    text = (COMMANDS / cmd).read_text(encoding="utf-8")
    assert not re.search(r"plugins/cache/[^\n]*\|\s*tail -1", text), (
        cmd + " still resolves the plugin root via `ls -d ... | tail -1`"
    )


def test_doctor_checks_plugin_data_layout():
    """DESIGN §4: doctor checks the plugin-data root and its files."""
    doc = _doc()
    assert "CLAUDE_PLUGIN_DATA" in doc
    assert "plugins/data/ace" in doc
    for f in ("python_path", "cli_version.json", "ace-hook-errors.log"):
        assert f in doc, "doctor plugin-data check must mention " + f


V8_HOOK_SCRIPTS = [
    "ace_install_cli.sh",
    "ace_sessionstart_compact.sh",
    "ace_before_task_wrapper.sh",
    "ace_posttooluse_wrapper.sh",
    "ace_posttooluse_domain_inject.sh",
    "ace_posttoolusefailure_wrapper.sh",
    "ace_subagent_start_wrapper.sh",
    "ace_stop_wrapper.sh",
    "ace_subagent_stop_wrapper.sh",
    "ace_permission_denied_wrapper.sh",
    "ace_sessionend_wrapper.sh",
]


def test_doctor_lists_v8_hook_scripts():
    """DESIGN §3 table / C6: doctor's hook check names every v8 shim (fixed names)."""
    doc = _doc()
    missing = [s for s in V8_HOOK_SCRIPTS if s not in doc]
    assert not missing, "ace-doctor.md missing v8 hook scripts: %s" % missing


REMOVED_SCRIPTS = [
    "ace_pretooluse_wrapper.sh",
    "ace_precompact_wrapper.sh",
    "ace_permission_request_wrapper.sh",
    "ace_cwdchanged_wrapper.sh",
    "ace_postcompact_wrapper.sh",
    "ace_after_task_wrapper.sh",
    "ace_monitor_log_reaper.sh",
    "ace_monitor_stale_reaper.sh",
]


@pytest.mark.parametrize("cmd", sorted(p.name for p in COMMANDS.glob("*.md")))
def test_command_does_not_reference_removed_hook_scripts(cmd):
    """DESIGN §3 REMOVED: deleted scripts must not be checked/listed by any command."""
    text = (COMMANDS / cmd).read_text(encoding="utf-8")
    found = [s for s in REMOVED_SCRIPTS if s in text]
    assert not found, cmd + " references removed scripts: %s" % found


def test_doctor_does_not_register_removed_hook_events():
    """DESIGN §3 REMOVED: PreCompact / PermissionRequest are gone. Round 2 (§9 G1) re-adds
    PreToolUse ONLY with matcher `Agent` (prompt stash), so a PreToolUse mapping is allowed
    only on a line that names `Agent`."""
    doc = _doc()
    for ev in ("PreCompact", "PermissionRequest"):
        assert not re.search(r"`?%s`?\s*→" % ev, doc), (
            "ace-doctor.md still maps %s → a wrapper script" % ev
        )
    for line in doc.splitlines():
        if re.search(r"`?PreToolUse`?[^\n]*→", line):
            assert "Agent" in line, "PreToolUse may only be registered for matcher Agent: " + line


def test_doctor_writes_no_tmp_files():
    """DESIGN §0: no writes to /tmp (doctor's curl -o /tmp/ace-doctor-response.json)."""
    assert "/tmp/" not in _doc()


# ---------------------------------------------------------------------------
# WP-I (round 2): DESIGN §11 A5 sessions.db health, §10 S10 downloads, §9 G1/G4 topology
# ---------------------------------------------------------------------------
import json  # noqa: E402
import os  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
from datetime import datetime, timedelta, timezone  # noqa: E402

A5_MARKER = "# ace-doctor: sessions-db-health"
MB = 1024 * 1024


def _a5_block():
    doc = _doc()
    i = doc.find(A5_MARKER)
    assert i >= 0, "ace-doctor.md has no embedded python block starting with %r (DESIGN §11 A5)" % A5_MARKER
    out = []
    for line in doc[doc.rfind("\n", 0, i) + 1:].splitlines():
        if line.strip() in ("PY", "```"):
            break
        out.append(line)
    return "\n".join(out) + "\n"


def _iso(dt):
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _run_a5(tmp_path, db_bytes, locked_age_hours):
    home = tmp_path / "home"
    proj = tmp_path / "proj"
    (home / ".ace-cache").mkdir(parents=True)
    logs = proj / ".claude" / "data" / "logs"
    logs.mkdir(parents=True)
    with open(home / ".ace-cache" / "sessions.db", "wb") as fh:
        fh.truncate(db_bytes)  # sparse
    rows = [
        {"timestamp": _iso(datetime.now(timezone.utc)), "event": "search", "patterns_injected": 3},
        {"timestamp": _iso(datetime.now(timezone.utc) - timedelta(hours=locked_age_hours)),
         "event": "error", "location": "ace_cli_nonzero_exit",
         "stderr_sample": "SqliteError: database is locked"},
    ]
    (logs / "ace-relevance.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    script = tmp_path / "a5.py"
    script.write_text(_a5_block(), encoding="utf-8")
    r = subprocess.run([sys.executable, str(script)], cwd=str(proj),
                       env=dict(os.environ, HOME=str(home)), capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    return r.stdout


def _warns(out):
    return [l for l in out.splitlines() if l.startswith("WARN:")]


def test_a5_flags_big_sessions_db_and_recent_lock(tmp_path):
    out = _run_a5(tmp_path, 101 * MB, locked_age_hours=1)
    warns = _warns(out)
    assert any("sessions.db" in w and "100 MB" in w for w in warns), out
    assert any("database is locked" in w for w in warns), out
    # remediation: stop ace-cli processes, delete sessions.db{,-wal,-shm} (24 h-TTL local cache)
    for token in ("ace-cli", "sessions.db-wal", "sessions.db-shm", "/ace:ace-cleanup --legacy"):
        assert token in out, "A5 remediation must mention " + token


def test_a5_quiet_when_small_db_and_old_lock(tmp_path):
    out = _run_a5(tmp_path, 1 * MB, locked_age_hours=30)
    assert _warns(out) == [], out


def test_a5_block_is_stdlib_python39():
    src = _a5_block()
    compile(src, "a5.py", "exec")
    if os.path.exists("/usr/bin/python3"):
        r = subprocess.run(["/usr/bin/python3", "-c", "import sys;compile(sys.stdin.read(),'b','exec')"],
                           input=src, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr


def test_doctor_allows_python3_for_embedded_block():
    fm = _doc().split("\n---", 1)[0]
    assert "Bash(python3:*)" in fm


@pytest.mark.parametrize("cmd", sorted(p.name for p in COMMANDS.glob("*.md")))
def test_no_command_downloads_or_writes_under_tmp(cmd):
    """DESIGN §10 S10 (regression; already true at 997c0de): downloads go under <root>/tmp, never /tmp/."""
    assert "/tmp/" not in (COMMANDS / cmd).read_text(encoding="utf-8")


def test_doctor_describes_round2_topology():
    """DESIGN §9 G1/G4: doctor's hook check names PostToolBatch and the PreToolUse `Agent` prompt stash."""
    doc = _doc()
    assert "PostToolBatch" in doc
    assert re.search(r"PreToolUse[^\n]*Agent", doc)


def test_a5_counts_pin_failed_and_backoff_rows(tmp_path):
    home = tmp_path / "home"; proj = tmp_path / "proj"
    (home / ".ace-cache").mkdir(parents=True)
    logs = proj / ".claude" / "data" / "logs"; logs.mkdir(parents=True)
    ts = _iso(datetime.now(timezone.utc))
    (logs / "ace-relevance.jsonl").write_text(json.dumps({"timestamp": ts, "event": "search", "pin_failed": True}) + "\n")
    (logs / "ace-relevance.jsonl.1").write_text(json.dumps({"timestamp": ts, "event": "search", "pin_skipped": "backoff"}) + "\n")
    script = tmp_path / "a5.py"; script.write_text(_a5_block(), encoding="utf-8")
    r = subprocess.run([sys.executable, str(script)], cwd=str(proj), env=dict(os.environ, HOME=str(home)),
                       capture_output=True, text=True, timeout=30)
    assert "2 lock incident" in r.stdout, r.stdout
