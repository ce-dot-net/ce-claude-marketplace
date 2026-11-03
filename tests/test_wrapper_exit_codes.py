#!/usr/bin/env python3
"""v8 shim contract (DESIGN §3.1) + DESIGN §3 deletions, WP-A.

Rewritten from the v5.5 test: the wrapper list named scripts DESIGN deletes
(ace_after_task_wrapper.sh, ace_precompact_wrapper.sh) and required an ERR trap,
which a §3.1 thin shim no longer has (Python catches everything).
Shim contract checks cover only the WP-A-owned shims; WP-B/C/D own theirs.
"""
import re
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parent.parent / "plugins" / "ace"
SCRIPTS = PLUGIN / "scripts"

WPA_SHIMS = ["ace_install_cli.sh", "ace_sessionend_wrapper.sh", "ace_permission_denied_wrapper.sh"]

# DESIGN §3 REMOVED + dead config (critic T25). PreToolUse/PreCompact wrappers are WP-D's
# deletions and are asserted in its tests.
DELETED = [
    "scripts/ace_permission_request_wrapper.sh",
    "shared-hooks/ace_permission_request.py",
    "scripts/ace_cwdchanged_wrapper.sh",
    "scripts/ace_postcompact_wrapper.sh",
    "scripts/ace_after_task_wrapper.sh",
    "scripts/ace_monitor_log_reaper.sh",
    "scripts/ace_monitor_stale_reaper.sh",
    ".claude-plugin/settings.json",
    ".mcp.template.json",
    "plugin.local.json",
]


def _code_lines(path):
    return [l.strip() for l in path.read_text().splitlines()
            if l.strip() and not l.strip().startswith("#")]


def test_no_exit_1_in_any_script():
    """Hooks never block: exit 1 is a non-blocking error in CC but ACE always exits 0."""
    bad = ["%s: %s" % (p.name, l) for p in sorted(SCRIPTS.glob("ace_*.sh"))  # hook shims, not command helpers
           for l in _code_lines(p) if re.search(r"\bexit\s+1\b", l)]
    assert not bad, "\n".join(bad)


@pytest.mark.parametrize("name", DELETED)
def test_dead_file_deleted(name):
    """DESIGN §3 REMOVED / critic T25: dead hooks, scripts and config are gone."""
    assert not (PLUGIN / name).exists(), "%s must be deleted (DESIGN §3)" % name


@pytest.mark.parametrize("name", WPA_SHIMS)
def test_wpa_shim_execs_python_with_cached_path(name):
    """§3.1: read <data>/python_path, fall back to `command -v python3`, `exec` the hook."""
    src = (SCRIPTS / name).read_text()
    assert "python_path" in src, "%s must read the cached python_path" % name
    assert re.search(r'^exec "\$PY" ', src, re.M), "%s must exec the python hook" % name


@pytest.mark.parametrize("name", WPA_SHIMS)
def test_wpa_shim_has_no_jq_cat_tmp_or_cd(name):
    """§0/§3.1: never handle JSON in bash (no jq), stdin untouched (no cat), no /tmp state,
    no `cd` except inside the ROOT fallback."""
    bad = []
    for l in _code_lines(SCRIPTS / name):
        if re.search(r"\bjq\b|\bcat\b|/tmp\b", l):
            bad.append(l)
        if re.search(r"(^|[;&|]\s*)cd\s", l) and not l.startswith("ROOT="):
            bad.append(l)
    assert not bad, "%s violates the shim contract:\n%s" % (name, "\n".join(bad))


@pytest.mark.parametrize("name", WPA_SHIMS)
def test_wpa_shim_is_thin(name):
    """§3.1 shim is ~6 code lines; logic lives in Python."""
    n = len(_code_lines(SCRIPTS / name))
    assert n <= 10, "%s has %d code lines; a thin shim has <= 10" % (name, n)
