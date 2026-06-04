#!/usr/bin/env python3
"""
Tests for the single-source-of-truth patterns-used state module:
    plugins/ace/shared-hooks/utils/patterns_used_state.py

The fix closes a tracking gap: subagents search (PreToolUse domain-shift) but
their recalls were never written. PER-AGENT-PURE attribution (authoritative):
the CLIENT owns trajectory/session/agent attribution; EACH agent (main + each
subagent) manages its OWN trajectory/traces independently. The server only
learns from the ExecutionTrace the client POSTs. Therefore playbook_used MUST
be per-agent — NEVER merge one agent's recalls into another agent's trace.

Reader semantics:
  - terminal main Stop  -> read ONLY -{session}-main.json (force 'main',
    ignore any agent_id CC stamps on Stop), reap it, LEAVE sibling -{uuid}.
  - SubagentStop        -> read ONLY this subagent's own -{uuid}.json, reap it,
    LEAVE -main and other siblings.
No glob, no cross-agent union.

INVARIANTS exercised here:
  1. STRICT SUPERSET (regression guard): terminal Stop with only -main.json
     present returns EXACTLY today's IDs.  [GREEN now + after fix]
  2. NO STEAL: SubagentStop must not read/unlink -main.json. [GREEN now + after]
  3. FORCED-MAIN: terminal Stop with own agent_id=UUID (own file absent) but
     -main.json present must still return the main IDs via forced 'main'.
  4. NO-MERGE: terminal Stop reads ONLY -main and LEAVES sibling -{uuid} on disk
     (a subagent's file is NOT consumed by the main Stop). [RED until fix]
  5. SubagentStop reads ONLY its own suffix (leaves -main).
  6. Writers keep the RELATIVE path scheme (state_file_path).
  7. Corrupt-file self-heal: the file actually read is corrupt -> returns [] and
     unlinks (single-file self-heal), for both terminal Stop and SubagentStop.

All tests pass an explicit tmp state_dir -> the real .claude/data/logs is never
touched. Pattern IDs are REAL-shaped so is_valid_pattern_id() passes.
"""
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SHARED_UTILS = REPO_ROOT / "plugins" / "ace" / "shared-hooks" / "utils"
sys.path.insert(0, str(SHARED_UTILS))

import patterns_used_state as pus  # noqa: E402

# Real-shaped IDs (ctx-<digits>-<hex> and a UUID) — all pass is_valid_pattern_id.
PID_A = "ctx-4338628010-5127"
PID_B = "ctx-6257961166-f081"
PID_C = "ctx-1234567890-abcd"
PID_UUID = "0b9f1abd-c2d1-551e-a147-0b9548f5c5bd"
INVALID = "not-a-valid-id"  # no ctx- prefix, not a UUID -> filtered out

SESSION = "sess-aaaa-1111"
SUBAGENT_UUID = "11111111-2222-3333-4444-555555555555"


def _path(state_dir, session, suffix):
    return Path(state_dir) / f"ace-patterns-used-{session}-{suffix}.json"


# --------------------------------------------------------------------------
# (a) append writes + dedupes + filters invalid IDs
# --------------------------------------------------------------------------
def test_append_writes_dedupes_and_filters(tmp_path):
    out1 = pus.append_patterns_used(SESSION, None, [PID_A, INVALID, PID_B], state_dir=str(tmp_path))
    assert out1 == [PID_A, PID_B], "invalid IDs filtered, valid order preserved"

    # second append with overlap -> dedupe, append new
    out2 = pus.append_patterns_used(SESSION, None, [PID_A, PID_C], state_dir=str(tmp_path))
    assert out2 == [PID_A, PID_B, PID_C], "dedupe existing, append new"

    sf = _path(tmp_path, SESSION, "main")
    assert sf.exists()
    assert json.loads(sf.read_text()) == [PID_A, PID_B, PID_C]


def test_append_noops_without_session_or_valid_ids(tmp_path):
    assert pus.append_patterns_used("", None, [PID_A], state_dir=str(tmp_path)) == []
    assert pus.append_patterns_used(SESSION, None, [INVALID], state_dir=str(tmp_path)) == []
    # nothing written
    assert not _path(tmp_path, SESSION, "main").exists()


def test_state_file_path_relative_scheme(tmp_path):
    # agent_id None -> 'main'
    p_main = pus.state_file_path(SESSION, None, state_dir=str(tmp_path))
    assert p_main.name == f"ace-patterns-used-{SESSION}-main.json"
    # agent_id UUID -> uuid suffix
    p_sub = pus.state_file_path(SESSION, SUBAGENT_UUID, state_dir=str(tmp_path))
    assert p_sub.name == f"ace-patterns-used-{SESSION}-{SUBAGENT_UUID}.json"
    # default (no state_dir) anchors to the RELATIVE default dir, NOT $CLAUDE_PROJECT_DIR
    p_default = pus.state_file_path(SESSION, None)
    assert str(p_default).startswith(pus.STATE_DIR_DEFAULT)
    assert pus.STATE_DIR_DEFAULT == ".claude/data/logs"


# --------------------------------------------------------------------------
# (b) REGRESSION GUARD — terminal Stop with only -main.json returns those IDs
#     and reaps the file. MUST be GREEN now and after the fix.
# --------------------------------------------------------------------------
def test_terminal_stop_main_only_returns_main_ids(tmp_path):
    pus.append_patterns_used(SESSION, None, [PID_A, PID_B], state_dir=str(tmp_path))
    main_file = _path(tmp_path, SESSION, "main")
    assert main_file.exists()

    out = pus.load_playbook_used(
        SESSION, None, hook_event_name="Stop", state_dir=str(tmp_path)
    )
    assert out == [PID_A, PID_B], "strict superset: same IDs as today"
    assert not main_file.exists(), "one-time use: main file reaped"


# --------------------------------------------------------------------------
# (c) FORCED-MAIN — terminal Stop, own agent_id is a UUID (own file absent) but
#     -main.json exists -> must still return the main IDs because terminal Stop
#     forces the 'main' suffix and ignores any agent_id CC stamps on Stop.
# --------------------------------------------------------------------------
def test_terminal_stop_uuid_agent_returns_main_ids(tmp_path):
    # main file written by the UserPromptSubmit handler (agent_id None)
    pus.append_patterns_used(SESSION, None, [PID_A, PID_B], state_dir=str(tmp_path))
    main_file = _path(tmp_path, SESSION, "main")
    assert main_file.exists()
    # own file for the terminal Stop's UUID agent_id does NOT exist
    own_file = _path(tmp_path, SESSION, SUBAGENT_UUID)
    assert not own_file.exists()

    out = pus.load_playbook_used(
        SESSION, SUBAGENT_UUID, hook_event_name="Stop", state_dir=str(tmp_path)
    )
    assert out == [PID_A, PID_B], "terminal Stop forces 'main' despite UUID own agent_id"
    assert not main_file.exists(), "main file reaped by the terminal Stop"


# --------------------------------------------------------------------------
# (d) NO-MERGE — -main.json + -{uuid}.json both present, terminal Stop reads
#     ONLY -main, returns ONLY main IDs, reaps -main, and LEAVES the sibling
#     -{uuid}.json on disk (a subagent's file is NOT consumed by the main Stop).
#     RED until the fix (glob-union steals + reaps the sibling).
# --------------------------------------------------------------------------
def test_terminal_stop_reads_main_only_and_leaves_siblings(tmp_path):
    pus.append_patterns_used(SESSION, None, [PID_A, PID_B], state_dir=str(tmp_path))
    pus.append_patterns_used(SESSION, SUBAGENT_UUID, [PID_B, PID_C, PID_UUID], state_dir=str(tmp_path))
    main_file = _path(tmp_path, SESSION, "main")
    sub_file = _path(tmp_path, SESSION, SUBAGENT_UUID)
    assert main_file.exists() and sub_file.exists()

    out = pus.load_playbook_used(
        SESSION, None, hook_event_name="Stop", state_dir=str(tmp_path)
    )
    assert out == [PID_A, PID_B], "per-agent-pure: terminal Stop returns ONLY main IDs"
    assert not main_file.exists(), "main file reaped"
    assert sub_file.exists() is True, "NO-MERGE: sibling -{uuid} left on disk"
    assert json.loads(sub_file.read_text()) == [PID_B, PID_C, PID_UUID], \
        "sibling content intact"


# --------------------------------------------------------------------------
# (e) NO STEAL — SubagentStop reads/reaps ONLY its own file; -main.json
#     untouched and only the subagent's own IDs returned. Should be GREEN.
# --------------------------------------------------------------------------
def test_subagent_stop_does_not_steal_main(tmp_path):
    pus.append_patterns_used(SESSION, None, [PID_A, PID_B], state_dir=str(tmp_path))
    pus.append_patterns_used(SESSION, SUBAGENT_UUID, [PID_C, PID_UUID], state_dir=str(tmp_path))
    main_file = _path(tmp_path, SESSION, "main")
    sub_file = _path(tmp_path, SESSION, SUBAGENT_UUID)

    out = pus.load_playbook_used(
        SESSION, SUBAGENT_UUID, hook_event_name="SubagentStop", state_dir=str(tmp_path)
    )
    assert out == [PID_C, PID_UUID], "SubagentStop returns only its own IDs"
    assert sub_file.exists() is False, "subagent's own file reaped"
    assert main_file.exists() is True, "NO STEAL: -main.json untouched"
    assert json.loads(main_file.read_text()) == [PID_A, PID_B], "main file content intact"


# --------------------------------------------------------------------------
# (e2) SUBAGENT READS OWN SUFFIX — -main + -{uuid} present; SubagentStop with
#      agent_id=uuid returns ONLY the uuid IDs, reaps ONLY -{uuid}, leaves -main.
# --------------------------------------------------------------------------
def test_subagent_stop_reads_own_suffix(tmp_path):
    pus.append_patterns_used(SESSION, None, [PID_A, PID_B], state_dir=str(tmp_path))
    pus.append_patterns_used(SESSION, SUBAGENT_UUID, [PID_C, PID_UUID], state_dir=str(tmp_path))
    main_file = _path(tmp_path, SESSION, "main")
    sub_file = _path(tmp_path, SESSION, SUBAGENT_UUID)
    assert main_file.exists() and sub_file.exists()

    out = pus.load_playbook_used(
        SESSION, SUBAGENT_UUID, hook_event_name="SubagentStop", state_dir=str(tmp_path)
    )
    assert out == [PID_C, PID_UUID], "SubagentStop returns ONLY its own suffix IDs"
    assert not sub_file.exists(), "own -{uuid} reaped"
    assert main_file.exists() is True, "-main left untouched"
    assert json.loads(main_file.read_text()) == [PID_A, PID_B], "main content intact"


# --------------------------------------------------------------------------
# (f) CORRUPT RESILIENCE (single-file self-heal) — the file the reader actually
#     reads is corrupt -> returns [] and unlinks (self-heal); on_error fires.
#     Terminal Stop reads ONLY -main, so the -main file itself must be corrupt.
# --------------------------------------------------------------------------
def test_terminal_stop_corrupt_main_self_heals(tmp_path):
    main_file = _path(tmp_path, SESSION, "main")
    main_file.parent.mkdir(parents=True, exist_ok=True)
    main_file.write_text("{ this is not valid json ]")

    errors = []

    def _on_error(f, e):
        errors.append((str(f), str(e)))

    out = pus.load_playbook_used(
        SESSION, None, hook_event_name="Stop", state_dir=str(tmp_path), on_error=_on_error
    )
    assert out == [], "corrupt main file -> empty result"
    assert not main_file.exists(), "corrupt main file self-healed (unlinked)"
    assert errors, "on_error callback invoked for the corrupt main file"


# --------------------------------------------------------------------------
# (f2) CORRUPT RESILIENCE — SubagentStop variant: the subagent's OWN file is
#      corrupt -> returns [] and unlinks its own file; -main is left untouched.
# --------------------------------------------------------------------------
def test_subagent_stop_corrupt_own_self_heals(tmp_path):
    pus.append_patterns_used(SESSION, None, [PID_A, PID_B], state_dir=str(tmp_path))
    main_file = _path(tmp_path, SESSION, "main")
    sub_file = _path(tmp_path, SESSION, SUBAGENT_UUID)
    sub_file.write_text("{ this is not valid json ]")

    errors = []

    def _on_error(f, e):
        errors.append((str(f), str(e)))

    out = pus.load_playbook_used(
        SESSION, SUBAGENT_UUID, hook_event_name="SubagentStop",
        state_dir=str(tmp_path), on_error=_on_error,
    )
    assert out == [], "corrupt own file -> empty result"
    assert not sub_file.exists(), "corrupt own file self-healed (unlinked)"
    assert main_file.exists() is True, "NO STEAL: -main untouched by corrupt SubagentStop"
    assert json.loads(main_file.read_text()) == [PID_A, PID_B], "main content intact"
    assert errors, "on_error callback invoked for the corrupt own file"
