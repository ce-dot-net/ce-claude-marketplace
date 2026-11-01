#!/usr/bin/env python3
"""WP-D (v8) — compact re-inject replaces the PreCompact → /tmp → SessionStart
handoff.

v7 (removed): PreCompact (`ace_precompact_wrapper.sh`) blocked compaction while a
learn lock existed (`decision: block` + exit 2, even on auto/recovery compaction
→ "the current request fails", cc_hooks_reference.md PreCompact section), ran
`ace-cli cache recall` keyed by CC session_id while pins are keyed by
task_session_id (0 of 5 hits), and handed patterns through
`/tmp/ace-patterns-precompact-<sid>.json` (critic T13, T21, V8).

v8 (DESIGN §3 row "SessionStart compact", §5 C1, §6 WP-D):
SessionStart `matcher: compact` → `scripts/ace_sessionstart_compact.sh` (thin
shim) → `shared-hooks/ace_session_start.py --compact`, which reads the MAIN
agent's state `rendered_context` (the exact additionalContext UPS emitted,
C1) for this `session_id` and emits it as SessionStart additionalContext
(≤ 10,000 chars, CC hook output cap). No ace-cli call, no /tmp, never blocks.
CC doc facts: SessionStart input `source == "compact"` (cc_hooks_reference.md:1256-1262),
output `hookSpecificOutput.additionalContext` (:1295-1312).
"""
import json
import uuid

import pytest

from wpd_harness import HookEnv, SCRIPTS, SHARED, shim_violations

SHIM = "ace_sessionstart_compact.sh"
SID = "sess-wpd-compact"
RENDERED = ('<ace-patterns shown="2" of="9">\n{"similar_patterns": [{"id": '
            '"ctx-1111111111-aaaa", "content": "quote \\" back\\\\slash é"}]}\n</ace-patterns>')


@pytest.fixture
def env(tmp_path):
    return HookEnv(tmp_path, project_id="prj-wpd-cmp-%s" % uuid.uuid4().hex[:8])


def _event(env, source="compact", session_id=SID):
    return {
        "session_id": session_id,
        "transcript_path": str(env.tmp / "t.jsonl"),
        "cwd": str(env.proj),
        "hook_event_name": "SessionStart",
        "source": source,
        "model": "claude-opus-5",
    }


def _run(env, event=None, raw=None):
    return env.run(SHIM, event, args=(), raw_stdin=raw)


def test_session_start_module_exists():
    """C6/WP-D: new shared-hooks/ace_session_start.py (with --compact)."""
    assert (SHARED / "ace_session_start.py").exists()


def test_compact_shim_is_thin():
    """DESIGN §3.1/§3: ace_sessionstart_compact.sh is a thin shim that execs
    ace_session_start.py (passing --compact), no jq/cat/cd."""
    assert shim_violations(SCRIPTS / SHIM, "ace_session_start.py") == []
    assert "--compact" in (SCRIPTS / SHIM).read_text()


def test_precompact_wrapper_deleted():
    """DESIGN §3 REMOVED: PreCompact (never block compaction; critic T13/V8)."""
    assert not (SCRIPTS / "ace_precompact_wrapper.sh").exists()


def test_compact_reinjects_rendered_context_from_main_state(env):
    """C1/WP-D: additionalContext == the main state's rendered_context, verbatim."""
    env.write_state(SID, None, rendered_context=RENDERED, task_session_id="tsid-x")
    proc = _run(env, _event(env))
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["hookSpecificOutput"]["additionalContext"] == RENDERED


def test_compact_output_is_sessionstart_hook_specific_json(env):
    """Doc :1295-1312: hookSpecificOutput.hookEventName must be SessionStart;
    stdout holds only that JSON object."""
    env.write_state(SID, None, rendered_context=RENDERED)
    proc = _run(env, _event(env))
    out = json.loads(proc.stdout)
    assert out["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert "decision" not in out and "continue" not in out


def test_compact_no_state_no_output(env):
    """WP-D: nothing saved for this session → rc 0, empty stdout."""
    proc = _run(env, _event(env))
    assert proc.returncode == 0 and proc.stdout.strip() == ""


def test_compact_state_without_rendered_context_no_output(env):
    """WP-D: state exists (e.g. control cohort / machine prompt) but carries no
    rendered_context → nothing to re-inject."""
    env.write_state(SID, None, pattern_ids=["ctx-1111111111-aaaa"], task_session_id="t")
    proc = _run(env, _event(env))
    assert proc.returncode == 0 and proc.stdout.strip() == ""


def test_compact_caps_additional_context_at_10000_chars(env):
    """CC caps hook additionalContext at 10,000 chars (over → ephemeral file +
    2 KB preview, v7.1.11 finding); a state written by an older/other writer
    must not push the re-inject over the cap."""
    env.write_state(SID, None, rendered_context="P" * 15000)
    proc = _run(env, _event(env))
    ctx = json.loads(proc.stdout)["hookSpecificOutput"]["additionalContext"]
    assert 0 < len(ctx) <= 10000


def test_compact_makes_no_cli_calls(env):
    """Critic T13: no `ace-cli cache recall` (keyed wrong, 0/5 hits) and no
    search — compaction re-inject is local state only."""
    env.write_state(SID, None, rendered_context=RENDERED)
    _run(env, _event(env))
    assert env.cli_calls() == []


def test_compact_ignores_subagent_state(env):
    """WP-D: only the MAIN agent's state (patterns-used-main.json) is re-injected
    into the main conversation, never a subagent's."""
    env.write_state(SID, "agent-sub-9", rendered_context="<ace-patterns-subagent/>")
    proc = _run(env, _event(env))
    assert proc.returncode == 0 and proc.stdout.strip() == ""


def test_compact_uses_only_this_sessions_state(env):
    """§4, critic T21: state is per CC session_id — another session of the same
    project must not get this session's patterns (v7 /tmp/ace-session-<project>
    clobbered across concurrent sessions)."""
    env.write_state("sess-other", None, rendered_context=RENDERED)
    proc = _run(env, _event(env, session_id=SID))
    assert proc.returncode == 0 and proc.stdout.strip() == ""


@pytest.mark.parametrize("source", ["startup", "resume", "clear"])
def test_compact_mode_ignores_non_compact_source(env, source):
    """WP-D: --compact only acts on source == "compact" (doc :1260)."""
    env.write_state(SID, None, rendered_context=RENDERED)
    proc = _run(env, _event(env, source=source))
    assert proc.returncode == 0 and proc.stdout.strip() == ""


def test_compact_disabled_flag_no_output(env):
    """§4: session disabled flag under plugin data suppresses the re-inject."""
    env.write_state(SID, None, rendered_context=RENDERED)
    env.disable(SID)
    proc = _run(env, _event(env))
    assert proc.returncode == 0 and proc.stdout.strip() == ""


@pytest.mark.parametrize("raw", ["", "not json", "{}"])
def test_compact_bad_stdin_exits_zero_silently(env, raw):
    """WP-D: never fail SessionStart — rc 0, empty stdout."""
    proc = _run(env, raw=raw)
    assert proc.returncode == 0 and proc.stdout.strip() == ""
