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


# The Foundation per-event table was retired by WP-A: tests/test_hooks_json_v8.py pins
# the full DESIGN §3 rows (incl. timeouts); this file keeps only the permanent guard.


def test_every_sync_hook_declares_timeout_except_sessionend():
    """DESIGN §11 A2: sync hooks carry an explicit seconds budget (CC default 600 would let a
    hung search block the turn for 10 min); SessionEnd carries none (doc :3578-3586 hard 1.5 s)."""
    missing, extra = [], []
    for event, hook in _iter_hooks():
        if hook.get("async"):
            continue
        if event == "SessionEnd":
            if "timeout" in hook:
                extra.append(_script(hook))
        elif "timeout" not in hook:
            missing.append((event, _script(hook)))
    assert not missing and not extra, (missing, extra)
