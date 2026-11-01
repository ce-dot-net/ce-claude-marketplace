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
    """DESIGN §3 REMOVED: PreToolUse / PreCompact / PermissionRequest are no longer registered."""
    doc = _doc()
    for ev in ("PreToolUse", "PreCompact", "PermissionRequest"):
        assert not re.search(r"`?%s`?\s*→" % ev, doc), (
            "ace-doctor.md still maps %s → a wrapper script" % ev
        )


def test_doctor_writes_no_tmp_files():
    """DESIGN §0: no writes to /tmp (doctor's curl -o /tmp/ace-doctor-response.json)."""
    assert "/tmp/" not in _doc()
