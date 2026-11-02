#!/usr/bin/env python3
"""WP-A/WP-G: hooks.json reaches the DESIGN §3 v8 topology (round 2: §9 G1/G4/G8, §10 S8, §11 A2).

Doc facts (scratchpad docs/cc_hooks_reference.md): `timeout` is seconds and is NOT
enforced on `async: true` hooks (:414); `statusMessage` = spinner text (:415);
exec form = `args` present, placeholders substituted per element, no shell (:445-470);
`async` is a hook-CONFIG field (:4059); `if` only on tool events (:413).
Critic: T10 (domain-shift double fire), T22 (SessionStart matcher), T25 (unquoted
${CLAUDE_PLUGIN_ROOT} validator warnings, dead hooks), V3 (`{"async": true}` echo).
"""
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
PLUGIN = REPO / "plugins" / "ace"
HOOKS_JSON = PLUGIN / "hooks" / "hooks.json"
ROOT_PREFIX = "${CLAUDE_PLUGIN_ROOT}/scripts/"

# DESIGN §3 table as amended by §9 G1/G4/G8, §10 S8 and §11 A2 (round 2):
# (event, matcher, script, args, async, timeout, statusMessage)
EXPECTED = {
    ("SessionStart", "startup|clear", "ace_install_cli.sh", (), False, 30, "ACE: checking ace-cli…"),  # §16 P9
    ("SessionStart", "startup", "ace_install_cli.sh", ("--update-check",), True, None, None),
    ("SessionStart", "compact", "ace_sessionstart_compact.sh", (), False, 10, None),
    ("UserPromptSubmit", "", "ace_before_task_wrapper.sh", (), False, 30,
     "ACE: searching patterns…"),
    ("PreToolUse", "Agent", "ace_pretooluse_agent_stash.sh", (), False, 5, None),
    ("PostToolBatch", "", "ace_posttooluse_wrapper.sh", ("--batch",), True, None, None),
    ("PostToolUse", "Read|Glob|Grep", "ace_posttooluse_domain_inject.sh", (), False, 20,
     "ACE: domain shift…"),
    ("PostToolUseFailure", "*", "ace_posttoolusefailure_wrapper.sh", (), True, None, None),
    ("SubagentStart", "", "ace_subagent_start_wrapper.sh", (), False, 30,
     "ACE: loading patterns for subagent…"),
    # §13.2 (r3a): Stop/SubagentStop SYNC, timeout 15 — async hooks are killed at `claude -p`
    # teardown before the shim runs (cc_hooks_reference.md:4084-4087; m2 F-V2 0/9 learns).
    ("Stop", "", "ace_stop_wrapper.sh", (), False, 15, None),
    ("SubagentStop", "", "ace_subagent_stop_wrapper.sh", (), False, 15, None),
    ("PermissionDenied", "", "ace_permission_denied_wrapper.sh", (), True, None, None),
    ("SessionEnd", "", "ace_sessionend_wrapper.sh", (), False, None, None),
}


def _flat():
    data = json.loads(HOOKS_JSON.read_text())
    for event, groups in data["hooks"].items():
        for group in groups:
            for hook in group.get("hooks", []):
                yield event, group.get("matcher", ""), hook


def _row(event, matcher, hook):
    cmd = hook.get("command", "")
    script = cmd[len(ROOT_PREFIX):] if cmd.startswith(ROOT_PREFIX) else cmd
    return (event, matcher, script, tuple(hook.get("args") or ()), bool(hook.get("async")),
            hook.get("timeout"), hook.get("statusMessage"))


def test_hooks_json_rows_match_design_table():
    """DESIGN §3: the complete set of (event, matcher, script, args, async, timeout,
    statusMessage) rows — nothing more, nothing less."""
    actual = {_row(*x) for x in _flat()}
    assert actual == EXPECTED, (
        "missing: %s\nunexpected: %s" % (sorted(EXPECTED - actual, key=str),
                                          sorted(actual - EXPECTED, key=str)))


def test_removed_events_absent():
    """DESIGN §3 REMOVED: PreCompact (never block compaction), PermissionRequest (no-op).
    PreToolUse came back in round 2 for the Agent stash only (§9 G1)."""
    hooks = json.loads(HOOKS_JSON.read_text())["hooks"]
    for gone in ("PreCompact", "PermissionRequest"):
        assert gone not in hooks, "%s must be removed from hooks.json (DESIGN §3)" % gone


def test_pretooluse_only_agent_never_task():
    """§9 G1 / p4.a: `Task` is a live alias of `Agent` -> declaring both double-fires."""
    hooks = json.loads(HOOKS_JSON.read_text())["hooks"]
    matchers = [g.get("matcher") for g in hooks.get("PreToolUse", [])]
    assert matchers == ["Agent"], matchers


def test_no_per_tool_posttooluse_accumulator():
    """§9 G4: PostToolBatch (one event per batch, no matcher support, doc :311/:2351)
    replaces the PostToolUse `*` accumulator; only the sync domain-shift stays on PostToolUse."""
    hooks = json.loads(HOOKS_JSON.read_text())["hooks"]
    assert [g.get("matcher") for g in hooks["PostToolUse"]] == ["Read|Glob|Grep"]
    assert all("matcher" not in g for g in hooks["PostToolBatch"]), \
        "PostToolBatch has no matcher support (doc :311); omit the key"


def test_every_hook_uses_exec_form():
    """DESIGN §3 / critic T25: exec form (cc_hooks_reference.md:445-470) — `command` is
    exactly the shim path, `args` is a list; no shell tokenizing of an unquoted
    ${CLAUDE_PLUGIN_ROOT} (the 12 validator warnings)."""
    bad = []
    for event, matcher, hook in _flat():
        cmd = hook.get("command", "")
        if not (cmd.startswith(ROOT_PREFIX) and " " not in cmd and isinstance(hook.get("args"), list)):
            bad.append((event, matcher, cmd, hook.get("args")))
    assert not bad, "hooks not in exec form: %s" % bad


def test_async_hooks_carry_no_timeout():
    """cc_hooks_reference.md:414 — timeout is not enforced on async command hooks; a value
    there would only mislead. DESIGN §3 table shows '—' for every async row."""
    bad = [(e, m, h.get("command")) for e, m, h in _flat() if h.get("async") and "timeout" in h]
    assert not bad, "async hooks must not set timeout: %s" % bad


def test_no_if_field():
    """DESIGN §3: remove the `if: Read(*)` — the domain-shift row uses the
    Read|Glob|Grep matcher instead."""
    bad = [(e, m, h.get("command")) for e, m, h in _flat() if "if" in h]
    assert not bad, "no hook may use `if`: %s" % bad


def test_stop_hooks_drop_log_chat_notify_flags():
    """DESIGN §6 WP-C: --log/--chat/--notify logic moves to Python, `--chat` transcript
    copy dropped — hooks.json passes no flags to Stop/SubagentStop."""
    for e, m, h in _flat():
        if e in ("Stop", "SubagentStop"):
            flags = h.get("command", "").split()[1:] + list(h.get("args") or [])
            assert not flags, "%s must pass no flags, got %s" % (e, flags)


def test_every_referenced_script_exists_and_is_executable():
    """C6: hooks.json names are fixed; every shim must exist + be executable
    (ace_posttoolusefailure_wrapper.sh comes from WP-C, ace_sessionstart_compact.sh shim
    from WP-D)."""
    missing = []
    for e, m, h in _flat():
        cmd = h.get("command", "")
        p = PLUGIN / "scripts" / cmd[len(ROOT_PREFIX):] if cmd.startswith(ROOT_PREFIX) else None
        if p is None or not p.is_file() or not os.access(p, os.X_OK):
            missing.append((e, cmd))
    assert not missing, "missing/non-executable shims: %s" % missing


@pytest.mark.skipif(shutil.which("claude") is None, reason="claude CLI not installed")
def test_claude_plugin_validate_strict_passes():
    """DESIGN §3: `claude plugin validate plugins/ace --strict` passes with 0 hook warnings."""
    r = subprocess.run(["claude", "plugin", "validate", str(PLUGIN), "--strict"],
                       capture_output=True, text=True, timeout=120)
    out = r.stdout + r.stderr
    hook_warnings = [l for l in out.splitlines() if re.search(r"\bhooks\.[A-Z]", l)]
    assert not hook_warnings, "hook validator warnings:\n" + "\n".join(hook_warnings)
    assert r.returncode == 0, out[-3000:]


def test_batch_mode_is_silent_rc0_noop():
    """WP-G->WP-H gate: PostToolBatch row points at `--batch`; until WP-H it must not fail."""
    ev = {"hook_event_name": "PostToolBatch", "session_id": "s", "tool_calls": []}
    p = subprocess.run([str(PLUGIN / "scripts" / "ace_posttooluse_wrapper.sh"), "--batch"],
                       input=json.dumps(ev), capture_output=True, text=True, timeout=30)
    assert p.returncode == 0 and p.stdout == "" and p.stderr == "", (p.returncode, p.stderr)
