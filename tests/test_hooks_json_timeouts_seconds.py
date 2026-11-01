#!/usr/bin/env python3
"""v8 Foundation: hooks.json `timeout` values are SECONDS, not milliseconds.

CC hooks reference (scratchpad docs/cc_hooks_reference.md:414): "`timeout` |
Seconds before canceling ... Defaults: 600 for `command`". The v7 file carried
millisecond-looking values (5000, 15000, 130000) which CC reads as 83 min, 4 h,
36 h -- i.e. effectively no timeout. DESIGN §6 Foundation fixes the values.
"""
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOOKS_JSON = REPO / "plugins" / "ace" / "hooks" / "hooks.json"


def _iter_hooks():
    data = json.loads(HOOKS_JSON.read_text())
    for event, entries in data.get("hooks", {}).items():
        for entry in entries:
            for hook in entry.get("hooks", []):
                yield event, hook


def _script(hook):
    cmd = hook.get("command", "")
    return cmd.split("/")[-1].split()[0] if cmd else ""


def test_every_timeout_is_int_seconds_le_600():
    """Guard (permanent): any timeout must be an int number of seconds <= 600."""
    offenders = []
    for event, hook in _iter_hooks():
        if "timeout" not in hook:
            continue
        t = hook["timeout"]
        if not isinstance(t, int) or isinstance(t, bool) or t <= 0 or t > 600:
            offenders.append((event, _script(hook), t))
    assert not offenders, f"timeouts must be int seconds in (0, 600]: {offenders}"


# DESIGN §6 Foundation per-event values (WP-A later reshapes hooks.json per §3
# and owns tests/test_hooks_json_v8.py; it may retire this table then).
EXPECTED = {
    ("UserPromptSubmit", "ace_before_task_wrapper.sh"): 20,
    ("SubagentStart", "ace_subagent_start_wrapper.sh"): 20,
    ("Stop", "ace_stop_wrapper.sh"): 130,
    ("SubagentStop", "ace_subagent_stop_wrapper.sh"): 130,
    ("PostToolUse", "ace_posttooluse_wrapper.sh"): 30,
    ("PostToolUse", "ace_posttooluse_domain_inject.sh"): 15,
    ("SessionStart", "ace_install_cli.sh"): 20,
    ("SessionEnd", "ace_sessionend_wrapper.sh"): 5,
    ("SessionStart", "ace_sessionstart_compact.sh"): 10,
    ("PermissionRequest", "ace_permission_request_wrapper.sh"): 10,
    ("PermissionDenied", "ace_permission_denied_wrapper.sh"): 10,
}


def test_foundation_per_event_timeouts():
    actual = {(event, _script(hook)): hook.get("timeout") for event, hook in _iter_hooks()}
    mismatches = {k: (actual.get(k), v) for k, v in EXPECTED.items() if actual.get(k) != v}
    assert not mismatches, f"(event, script): (actual, expected) -> {mismatches}"
