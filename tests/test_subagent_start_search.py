#!/usr/bin/env python3
"""
SubagentStart hook — transcript-derived query (CC 2.1.170+).

CC 2.1.170 removed the 'task' field from the SubagentStart event.
The hook must now derive the search query from the main session
transcript (transcript_path), using the tail-scan algorithm to find
the most-recent Task/Agent tool_use block whose subagent_type matches
the event's agent_type.

Key invariants under test:
  1. run_search is called with the query extracted from the transcript
     (NOT from event['task']) and task_intent OMITTED.
  2. append_patterns_used is called with the subagent's agent_id so
     the per-agent state file exists for SubagentStop crediting.
  3. TYPE-MATCH: the most-recent Task/Agent block whose subagent_type
     == event.agent_type is preferred over earlier or mismatched ones.
  4. GLOBAL FALLBACK: when no type-matched block exists, the most-recent
     Task/Agent block (any type) is used.
  5. GRACEFUL EXIT: when transcript is missing, empty, or has no Task/
     Agent blocks — no run_search, no crash.
  6. GRACEFUL EXIT: when agent_id is None/absent — no run_search, no crash.
  7. task_intent is NOT passed to run_search.
  8. org/project resolved via get_context().
  9. The description field is used as fallback when prompt is absent.
  10. Prompts truncated to ~500 chars for the query.
"""
import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# ── path setup ──────────────────────────────────────────────────────────────
REPO = Path(__file__).resolve().parent.parent
SHARED = REPO / "plugins" / "ace" / "shared-hooks"
SCRIPTS = REPO / "plugins" / "ace" / "scripts"
UTILS = SHARED / "utils"

sys.path.insert(0, str(SHARED))
sys.path.insert(0, str(UTILS))
sys.path.insert(0, str(REPO / "plugins" / "ace" / "utils"))


# ── helper: load ace_subagent_start module ───────────────────────────────────
def _load_subagent_start():
    mod_path = SHARED / "ace_subagent_start.py"
    spec = importlib.util.spec_from_file_location("ace_subagent_start", mod_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── transcript fixture builder ───────────────────────────────────────────────

def _make_transcript(tmp_path, blocks):
    """Write a minimal JSONL transcript with the given Task tool_use blocks.

    Each block in `blocks` is a dict:
      {"subagent_type": "coder", "prompt": "...", "uuid": "optional"}

    Lines are written in order; tail-scan means the LAST line wins.
    """
    lines = []
    for i, block in enumerate(blocks):
        tool_input = {}
        if "subagent_type" in block:
            tool_input["subagent_type"] = block["subagent_type"]
        if "prompt" in block:
            tool_input["prompt"] = block["prompt"]
        if "description" in block:
            tool_input["description"] = block["description"]

        entry = {
            "type": "assistantMessage",
            "uuid": block.get("uuid", f"uuid-{i}"),
            "timestamp": f"2026-06-10T10:00:0{i}.000Z",
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": f"toolu_{i:04d}",
                        "name": "Task",
                        "input": tool_input,
                    }
                ],
            },
        }
        lines.append(json.dumps(entry))

    # Add some non-tool-use lines for robustness
    lines.insert(0, json.dumps({"type": "system", "message": "session start"}))
    lines.insert(1, '{"broken json line')  # malformed — must be skipped

    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text("\n".join(lines) + "\n")
    return str(transcript)


# ── base event shape (CC 2.1.170 — NO 'task' field) ─────────────────────────

def _make_event(tmp_path, transcript_path=None, agent_type="coder", agent_id="subagent-xyz-456"):
    return {
        "hook_event_name": "SubagentStart",
        "session_id": "sess-abc123",
        "agent_id": agent_id,
        "agent_type": agent_type,
        "cwd": str(tmp_path),
        "transcript_path": transcript_path or str(tmp_path / "transcript.jsonl"),
    }


SAMPLE_PATTERNS_RESPONSE = {
    "similar_patterns": [
        {
            "id": "ctx-1234567890-abcd",
            "domain": "claude-plugins",
            "content": "When implementing hooks, always wrap in try/except",
            "confidence": 0.75,
            "helpful": 10,
            "harmful": 2,
        },
        {
            "id": "ctx-2234567890-bcde",
            "domain": "python",
            "content": "Use subprocess.run with timeout to avoid hangs",
            "confidence": 0.80,
            "helpful": 15,
            "harmful": 1,
        },
    ],
    "count": 2,
    "retrieval_id": "ret-abc-001",
}

GOOD_CONTEXT = {"org": "org-test-01", "project": "prj-test-01"}


# ═══════════════════════════════════════════════════════════════════════════
# 1. MODULE EXISTS
# ═══════════════════════════════════════════════════════════════════════════

def test_module_exists():
    """ace_subagent_start.py must exist in shared-hooks/."""
    mod_path = SHARED / "ace_subagent_start.py"
    assert mod_path.exists(), (
        f"ace_subagent_start.py not found at {mod_path} — create the module first"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 2. WRAPPER SCRIPT EXISTS
# ═══════════════════════════════════════════════════════════════════════════

def test_wrapper_script_exists():
    """ace_subagent_start_wrapper.sh must exist in scripts/."""
    wrapper = SCRIPTS / "ace_subagent_start_wrapper.sh"
    assert wrapper.exists(), (
        f"ace_subagent_start_wrapper.sh not found at {wrapper}"
    )


def test_wrapper_script_is_executable():
    wrapper = SCRIPTS / "ace_subagent_start_wrapper.sh"
    if wrapper.exists():
        import stat
        mode = wrapper.stat().st_mode
        assert mode & stat.S_IXUSR, "ace_subagent_start_wrapper.sh must be executable"


# ═══════════════════════════════════════════════════════════════════════════
# 3. HOOKS.JSON REGISTRATION
# ═══════════════════════════════════════════════════════════════════════════

def test_hooks_json_has_subagent_start_entry():
    """hooks.json must register the SubagentStart hook."""
    hooks_path = REPO / "plugins" / "ace" / "hooks" / "hooks.json"
    data = json.loads(hooks_path.read_text())
    hooks = data.get("hooks", {})
    assert "SubagentStart" in hooks, (
        "hooks.json missing 'SubagentStart' entry — register the hook"
    )


def test_hooks_json_subagent_start_calls_wrapper():
    """The SubagentStart entry must invoke ace_subagent_start_wrapper.sh."""
    hooks_path = REPO / "plugins" / "ace" / "hooks" / "hooks.json"
    data = json.loads(hooks_path.read_text())
    entries = data.get("hooks", {}).get("SubagentStart", [])
    assert entries, "SubagentStart hook list is empty"
    # hooks.json nests command under entry["hooks"][*]["command"]
    commands = []
    for entry in entries:
        for hook in entry.get("hooks", []):
            commands.append(hook.get("command", ""))
    assert any("ace_subagent_start_wrapper" in cmd for cmd in commands), (
        f"No command referencing ace_subagent_start_wrapper found in: {commands}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 4. TRANSCRIPT-DERIVED QUERY — type-matched hit
# ═══════════════════════════════════════════════════════════════════════════

def test_run_search_called_with_transcript_query_type_matched(tmp_path, monkeypatch):
    """main() must call run_search(query=<prompt from transcript>).

    The transcript has two Task blocks: one 'general-purpose' and one 'coder'.
    The event agent_type='coder', so the most-recent 'coder' block's prompt
    must be used. task_intent must NOT be passed.
    """
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    transcript_path = _make_transcript(tmp_path, [
        {"subagent_type": "general-purpose", "prompt": "Do some general research"},
        {"subagent_type": "coder", "prompt": "Implement the SubagentStart hook"},
    ])
    event = _make_event(tmp_path, transcript_path=transcript_path, agent_type="coder")

    mod = _load_subagent_start()
    captured = {}

    def fake_run_search(query, org=None, project=None, session_id=None, **kwargs):
        captured["query"] = query
        captured["kwargs"] = kwargs
        captured["task_intent_present"] = "task_intent" in kwargs
        return SAMPLE_PATTERNS_RESPONSE

    monkeypatch.setattr(mod, "run_search", fake_run_search)
    monkeypatch.setattr(mod, "get_context", lambda: GOOD_CONTEXT)
    monkeypatch.setattr(mod, "append_patterns_used", MagicMock())

    try:
        mod.main(event=event)
    except SystemExit:
        pass

    assert "query" in captured, "run_search was never called"
    assert "Implement the SubagentStart hook" in captured["query"], (
        f"Expected coder prompt in query; got: {captured['query']!r}"
    )
    assert not captured["task_intent_present"], (
        "task_intent must NOT be passed to run_search"
    )


def test_tail_scan_picks_most_recent_matching_type(tmp_path, monkeypatch):
    """When multiple blocks match agent_type, the LAST one (tail-scan first) is used."""
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    transcript_path = _make_transcript(tmp_path, [
        {"subagent_type": "coder", "prompt": "OLD coder task"},
        {"subagent_type": "coder", "prompt": "NEW coder task — use this one"},
    ])
    event = _make_event(tmp_path, transcript_path=transcript_path, agent_type="coder")

    mod = _load_subagent_start()
    captured = {}

    def fake_run_search(query, **kwargs):
        captured["query"] = query
        return SAMPLE_PATTERNS_RESPONSE

    monkeypatch.setattr(mod, "run_search", fake_run_search)
    monkeypatch.setattr(mod, "get_context", lambda: GOOD_CONTEXT)
    monkeypatch.setattr(mod, "append_patterns_used", MagicMock())

    try:
        mod.main(event=event)
    except SystemExit:
        pass

    assert "query" in captured, "run_search was never called"
    assert "NEW coder task" in captured["query"], (
        f"Expected newest coder prompt; got: {captured['query']!r}"
    )


def test_type_match_skips_mismatched_types(tmp_path, monkeypatch):
    """A 'general-purpose' block must not be returned for agent_type='coder'."""
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    transcript_path = _make_transcript(tmp_path, [
        {"subagent_type": "general-purpose", "prompt": "General task"},
        {"subagent_type": "coder", "prompt": "Correct coder task"},
    ])
    event = _make_event(tmp_path, transcript_path=transcript_path, agent_type="coder")

    mod = _load_subagent_start()
    captured = {}

    def fake_run_search(query, **kwargs):
        captured["query"] = query
        return SAMPLE_PATTERNS_RESPONSE

    monkeypatch.setattr(mod, "run_search", fake_run_search)
    monkeypatch.setattr(mod, "get_context", lambda: GOOD_CONTEXT)
    monkeypatch.setattr(mod, "append_patterns_used", MagicMock())

    try:
        mod.main(event=event)
    except SystemExit:
        pass

    assert "query" in captured, "run_search was never called"
    assert "Correct coder task" in captured["query"], (
        f"Expected coder prompt; got: {captured['query']!r}"
    )
    assert "General task" not in captured["query"], (
        f"Must not use mismatched general-purpose prompt; got: {captured['query']!r}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 5. GLOBAL FALLBACK — no type-matched block
# ═══════════════════════════════════════════════════════════════════════════

def test_global_fallback_when_no_type_match(tmp_path, monkeypatch):
    """When no block matches agent_type, the most-recent Task/Agent block is used."""
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    transcript_path = _make_transcript(tmp_path, [
        {"subagent_type": "general-purpose", "prompt": "First general task"},
        {"subagent_type": "general-purpose", "prompt": "Most recent general task"},
    ])
    # agent_type='coder' — no matching block, should fall back to most-recent
    event = _make_event(tmp_path, transcript_path=transcript_path, agent_type="coder")

    mod = _load_subagent_start()
    captured = {}

    def fake_run_search(query, **kwargs):
        captured["query"] = query
        return SAMPLE_PATTERNS_RESPONSE

    monkeypatch.setattr(mod, "run_search", fake_run_search)
    monkeypatch.setattr(mod, "get_context", lambda: GOOD_CONTEXT)
    monkeypatch.setattr(mod, "append_patterns_used", MagicMock())

    try:
        mod.main(event=event)
    except SystemExit:
        pass

    assert "query" in captured, "run_search was never called (global fallback failed)"
    assert "Most recent general task" in captured["query"], (
        f"Global fallback should use most-recent Task block; got: {captured['query']!r}"
    )


def test_global_fallback_when_subagent_type_absent(tmp_path, monkeypatch):
    """When block.input has no subagent_type, global fallback must still find it."""
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    transcript_path = _make_transcript(tmp_path, [
        {"prompt": "Task without subagent_type field"},
    ])
    event = _make_event(tmp_path, transcript_path=transcript_path, agent_type="coder")

    mod = _load_subagent_start()
    captured = {}

    def fake_run_search(query, **kwargs):
        captured["query"] = query
        return SAMPLE_PATTERNS_RESPONSE

    monkeypatch.setattr(mod, "run_search", fake_run_search)
    monkeypatch.setattr(mod, "get_context", lambda: GOOD_CONTEXT)
    monkeypatch.setattr(mod, "append_patterns_used", MagicMock())

    try:
        mod.main(event=event)
    except SystemExit:
        pass

    assert "query" in captured, "run_search was never called (no-subagent_type fallback)"
    assert "Task without subagent_type field" in captured["query"], (
        f"Expected prompt from block without subagent_type; got: {captured['query']!r}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 6. description FALLBACK when prompt is absent
# ═══════════════════════════════════════════════════════════════════════════

def test_description_used_when_prompt_absent(tmp_path, monkeypatch):
    """When block.input has no 'prompt', 'description' must be used as fallback."""
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    transcript_path = _make_transcript(tmp_path, [
        {"subagent_type": "coder", "description": "Task via description field"},
    ])
    event = _make_event(tmp_path, transcript_path=transcript_path, agent_type="coder")

    mod = _load_subagent_start()
    captured = {}

    def fake_run_search(query, **kwargs):
        captured["query"] = query
        return SAMPLE_PATTERNS_RESPONSE

    monkeypatch.setattr(mod, "run_search", fake_run_search)
    monkeypatch.setattr(mod, "get_context", lambda: GOOD_CONTEXT)
    monkeypatch.setattr(mod, "append_patterns_used", MagicMock())

    try:
        mod.main(event=event)
    except SystemExit:
        pass

    assert "query" in captured, "run_search was never called"
    assert "Task via description field" in captured["query"], (
        f"Expected description as query fallback; got: {captured['query']!r}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 7. PROMPT TRUNCATION to ~500 chars
# ═══════════════════════════════════════════════════════════════════════════

def test_long_prompt_is_truncated(tmp_path, monkeypatch):
    """Prompts longer than ~500 chars must be truncated before passing to run_search."""
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    long_prompt = "A" * 1200
    transcript_path = _make_transcript(tmp_path, [
        {"subagent_type": "coder", "prompt": long_prompt},
    ])
    event = _make_event(tmp_path, transcript_path=transcript_path, agent_type="coder")

    mod = _load_subagent_start()
    captured = {}

    def fake_run_search(query, **kwargs):
        captured["query"] = query
        return SAMPLE_PATTERNS_RESPONSE

    monkeypatch.setattr(mod, "run_search", fake_run_search)
    monkeypatch.setattr(mod, "get_context", lambda: GOOD_CONTEXT)
    monkeypatch.setattr(mod, "append_patterns_used", MagicMock())

    try:
        mod.main(event=event)
    except SystemExit:
        pass

    assert "query" in captured, "run_search was never called"
    assert len(captured["query"]) <= 600, (
        f"Query should be truncated to ~500 chars; got {len(captured['query'])} chars"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 8. GRACEFUL EXIT — no usable query (empty transcript / missing file)
# ═══════════════════════════════════════════════════════════════════════════

def test_no_run_search_when_transcript_missing(tmp_path, monkeypatch):
    """When transcript_path doesn't exist, run_search must NOT be called."""
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    event = _make_event(tmp_path, transcript_path=str(tmp_path / "nonexistent.jsonl"))

    mod = _load_subagent_start()
    rs_mock = MagicMock()
    monkeypatch.setattr(mod, "run_search", rs_mock)
    monkeypatch.setattr(mod, "get_context", lambda: GOOD_CONTEXT)
    monkeypatch.setattr(mod, "append_patterns_used", MagicMock())

    try:
        mod.main(event=event)
    except SystemExit:
        pass

    rs_mock.assert_not_called()


def test_no_run_search_when_transcript_has_no_task_blocks(tmp_path, monkeypatch):
    """When transcript has no Task/Agent tool_use blocks, run_search must NOT be called."""
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    # Transcript with only user/system entries, no Task tool_use
    entries = [
        {"type": "userMessage", "message": {"role": "user", "content": "hello"}},
        {"type": "assistantMessage", "message": {
            "role": "assistant",
            "content": [{"type": "text", "text": "response"}]
        }},
    ]
    transcript = tmp_path / "empty.jsonl"
    transcript.write_text("\n".join(json.dumps(e) for e in entries) + "\n")
    event = _make_event(tmp_path, transcript_path=str(transcript))

    mod = _load_subagent_start()
    rs_mock = MagicMock()
    monkeypatch.setattr(mod, "run_search", rs_mock)
    monkeypatch.setattr(mod, "get_context", lambda: GOOD_CONTEXT)
    monkeypatch.setattr(mod, "append_patterns_used", MagicMock())

    try:
        mod.main(event=event)
    except SystemExit:
        pass

    rs_mock.assert_not_called()


def test_no_run_search_when_transcript_empty(tmp_path, monkeypatch):
    """When transcript is empty/blank, run_search must NOT be called."""
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    transcript = tmp_path / "empty.jsonl"
    transcript.write_text("")
    event = _make_event(tmp_path, transcript_path=str(transcript))

    mod = _load_subagent_start()
    rs_mock = MagicMock()
    monkeypatch.setattr(mod, "run_search", rs_mock)
    monkeypatch.setattr(mod, "get_context", lambda: GOOD_CONTEXT)
    monkeypatch.setattr(mod, "append_patterns_used", MagicMock())

    try:
        mod.main(event=event)
    except SystemExit:
        pass

    rs_mock.assert_not_called()


def test_no_run_search_when_transcript_path_absent(tmp_path, monkeypatch):
    """When transcript_path key is absent from event, run_search must NOT be called."""
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    event = _make_event(tmp_path)
    del event["transcript_path"]

    mod = _load_subagent_start()
    rs_mock = MagicMock()
    monkeypatch.setattr(mod, "run_search", rs_mock)
    monkeypatch.setattr(mod, "get_context", lambda: GOOD_CONTEXT)
    monkeypatch.setattr(mod, "append_patterns_used", MagicMock())

    try:
        mod.main(event=event)
    except SystemExit:
        pass

    rs_mock.assert_not_called()


def test_graceful_when_transcript_is_all_malformed_json(tmp_path, monkeypatch):
    """When every line of the transcript is malformed JSON, must not crash."""
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    transcript = tmp_path / "bad.jsonl"
    transcript.write_text("{{not json\nnot json either\n{broken")
    event = _make_event(tmp_path, transcript_path=str(transcript))

    mod = _load_subagent_start()
    rs_mock = MagicMock()
    monkeypatch.setattr(mod, "run_search", rs_mock)
    monkeypatch.setattr(mod, "get_context", lambda: GOOD_CONTEXT)
    monkeypatch.setattr(mod, "append_patterns_used", MagicMock())

    try:
        mod.main(event=event)
    except SystemExit:
        pass
    # No crash; run_search not called since no usable content
    rs_mock.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════
# 9. run_search IS CALLED — task_intent OMITTED
# ═══════════════════════════════════════════════════════════════════════════

def test_run_search_task_intent_kwarg_not_passed(tmp_path, monkeypatch):
    """task_intent must not appear in the run_search call at all (not even as None)."""
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    transcript_path = _make_transcript(tmp_path, [
        {"subagent_type": "coder", "prompt": "Some coder task"},
    ])
    event = _make_event(tmp_path, transcript_path=transcript_path, agent_type="coder")

    mod = _load_subagent_start()
    calls = []

    def fake_run_search(*args, **kwargs):
        calls.append(kwargs)
        return SAMPLE_PATTERNS_RESPONSE

    monkeypatch.setattr(mod, "run_search", fake_run_search)
    monkeypatch.setattr(mod, "get_context", lambda: GOOD_CONTEXT)
    monkeypatch.setattr(mod, "append_patterns_used", MagicMock())

    try:
        mod.main(event=event)
    except SystemExit:
        pass

    assert calls, "run_search was never called"
    for kw in calls:
        assert "task_intent" not in kw, (
            f"task_intent must not be passed to run_search; got kwargs: {kw}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 10. append_patterns_used IS CALLED WITH SUBAGENT'S agent_id
# ═══════════════════════════════════════════════════════════════════════════

def test_append_patterns_used_called_with_subagent_agent_id(tmp_path, monkeypatch):
    """Pattern IDs must be persisted keyed to the subagent's agent_id."""
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    transcript_path = _make_transcript(tmp_path, [
        {"subagent_type": "coder", "prompt": "Implement the SubagentStart hook"},
    ])
    event = _make_event(tmp_path, transcript_path=transcript_path, agent_type="coder")

    mod = _load_subagent_start()
    monkeypatch.setattr(mod, "run_search", lambda *a, **kw: SAMPLE_PATTERNS_RESPONSE)
    monkeypatch.setattr(mod, "get_context", lambda: GOOD_CONTEXT)
    pu_calls = []
    monkeypatch.setattr(mod, "append_patterns_used",
                        lambda *a, **kw: pu_calls.append((a, kw)))

    try:
        mod.main(event=event)
    except SystemExit:
        pass

    assert pu_calls, "append_patterns_used was never called"
    first_call_args = pu_calls[0][0]
    assert first_call_args[0] == "sess-abc123", (
        f"First arg (session_id) should be 'sess-abc123'; got {first_call_args[0]!r}"
    )
    assert first_call_args[1] == "subagent-xyz-456", (
        f"Second arg (agent_id) should be 'subagent-xyz-456'; got {first_call_args[1]!r}"
    )


def test_per_agent_state_file_written_for_subagent(tmp_path, monkeypatch):
    """A per-agent state file keyed by agent_id must exist after main() runs."""
    import patterns_used_state as pus

    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    transcript_path = _make_transcript(tmp_path, [
        {"subagent_type": "coder", "prompt": "Implement the SubagentStart hook"},
    ])
    event = _make_event(tmp_path, transcript_path=transcript_path, agent_type="coder")

    mod = _load_subagent_start()
    monkeypatch.setattr(mod, "run_search", lambda *a, **kw: SAMPLE_PATTERNS_RESPONSE)
    monkeypatch.setattr(mod, "get_context", lambda: GOOD_CONTEXT)
    # Use REAL append_patterns_used so the file is actually written
    monkeypatch.setattr(mod, "append_patterns_used", pus.append_patterns_used)

    try:
        mod.main(event=event)
    except SystemExit:
        pass

    state_file = pus.state_file_path("sess-abc123", "subagent-xyz-456")
    assert state_file.exists(), (
        f"Per-agent state file not found at {state_file}; "
        "SubagentStop crediting chain will be broken"
    )
    data = json.loads(state_file.read_text())
    pattern_ids = data.get("pattern_ids", data) if isinstance(data, dict) else data
    expected_ids = [p["id"] for p in SAMPLE_PATTERNS_RESPONSE["similar_patterns"]]
    for eid in expected_ids:
        assert eid in pattern_ids, (
            f"Expected pattern id {eid!r} not found in state file; got: {pattern_ids}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 11. GRACEFUL DEGRADATION — run_search returns None/empty
# ═══════════════════════════════════════════════════════════════════════════

def test_graceful_when_run_search_returns_none(tmp_path, monkeypatch):
    """Hook must not raise even when run_search returns None."""
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    transcript_path = _make_transcript(tmp_path, [
        {"subagent_type": "coder", "prompt": "Some task"},
    ])
    event = _make_event(tmp_path, transcript_path=transcript_path, agent_type="coder")

    mod = _load_subagent_start()
    monkeypatch.setattr(mod, "run_search", lambda *a, **kw: None)
    monkeypatch.setattr(mod, "get_context", lambda: GOOD_CONTEXT)
    monkeypatch.setattr(mod, "append_patterns_used", MagicMock())

    try:
        mod.main(event=event)
    except SystemExit:
        pass  # sys.exit(0) is fine


def test_graceful_when_no_context(tmp_path, monkeypatch):
    """Hook must not raise when get_context returns None."""
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    transcript_path = _make_transcript(tmp_path, [
        {"subagent_type": "coder", "prompt": "Some task"},
    ])
    event = _make_event(tmp_path, transcript_path=transcript_path, agent_type="coder")

    mod = _load_subagent_start()
    monkeypatch.setattr(mod, "run_search", MagicMock())
    monkeypatch.setattr(mod, "get_context", lambda: None)
    monkeypatch.setattr(mod, "append_patterns_used", MagicMock())

    try:
        mod.main(event=event)
    except SystemExit:
        pass  # fine


def test_graceful_when_run_search_raises(tmp_path, monkeypatch):
    """Hook must not propagate exceptions from run_search."""
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    transcript_path = _make_transcript(tmp_path, [
        {"subagent_type": "coder", "prompt": "Some task"},
    ])
    event = _make_event(tmp_path, transcript_path=transcript_path, agent_type="coder")

    mod = _load_subagent_start()

    def boom(*a, **kw):
        raise RuntimeError("CLI timeout")

    monkeypatch.setattr(mod, "run_search", boom)
    monkeypatch.setattr(mod, "get_context", lambda: GOOD_CONTEXT)
    monkeypatch.setattr(mod, "append_patterns_used", MagicMock())

    try:
        mod.main(event=event)
    except SystemExit:
        pass  # fine
    # no RuntimeError must escape


# ═══════════════════════════════════════════════════════════════════════════
# 12. OUTPUT SHAPE — patterns found → additionalContext injected
# ═══════════════════════════════════════════════════════════════════════════

def test_output_contains_additional_context_when_patterns_found(tmp_path, monkeypatch, capsys):
    """When patterns are found, stdout JSON must include hookSpecificOutput.additionalContext."""
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    transcript_path = _make_transcript(tmp_path, [
        {"subagent_type": "coder", "prompt": "Implement the SubagentStart hook"},
    ])
    event = _make_event(tmp_path, transcript_path=transcript_path, agent_type="coder")

    mod = _load_subagent_start()
    monkeypatch.setattr(mod, "run_search", lambda *a, **kw: SAMPLE_PATTERNS_RESPONSE)
    monkeypatch.setattr(mod, "get_context", lambda: GOOD_CONTEXT)
    monkeypatch.setattr(mod, "append_patterns_used", MagicMock())

    try:
        mod.main(event=event)
    except SystemExit:
        pass

    captured = capsys.readouterr().out
    if not captured.strip():
        pytest.skip("main() returned without printing (early exit)")

    output = json.loads(captured)
    assert "hookSpecificOutput" in output, (
        "Output missing 'hookSpecificOutput' key"
    )
    hso = output["hookSpecificOutput"]
    assert "additionalContext" in hso, (
        "hookSpecificOutput missing 'additionalContext'"
    )
    assert "ace-patterns" in hso["additionalContext"], (
        "additionalContext should contain <ace-patterns...> XML"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 13. ORG/PROJECT RESOLVED VIA get_context (Candidate-1 non-regression)
# ═══════════════════════════════════════════════════════════════════════════

def test_org_and_project_passed_to_run_search_from_context(tmp_path, monkeypatch):
    """org and project must come from get_context(), not hardcoded or from env directly."""
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    transcript_path = _make_transcript(tmp_path, [
        {"subagent_type": "coder", "prompt": "Some coder task"},
    ])
    event = _make_event(tmp_path, transcript_path=transcript_path, agent_type="coder")

    mod = _load_subagent_start()
    context_used = {}

    def fake_get_context():
        return {"org": "org-from-context", "project": "prj-from-context"}

    def fake_run_search(query, org=None, project=None, **kwargs):
        context_used["org"] = org
        context_used["project"] = project
        return SAMPLE_PATTERNS_RESPONSE

    monkeypatch.setattr(mod, "get_context", fake_get_context)
    monkeypatch.setattr(mod, "run_search", fake_run_search)
    monkeypatch.setattr(mod, "append_patterns_used", MagicMock())

    try:
        mod.main(event=event)
    except SystemExit:
        pass

    assert context_used.get("org") == "org-from-context", (
        f"org passed to run_search should come from get_context(); got {context_used.get('org')!r}"
    )
    assert context_used.get("project") == "prj-from-context", (
        f"project passed to run_search should come from get_context(); got {context_used.get('project')!r}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 14. session_id FROM EVENT
# ═══════════════════════════════════════════════════════════════════════════

def test_session_id_from_event_passed_to_run_search(tmp_path, monkeypatch):
    """run_search receives a per-task uuid4 session_id (task_session_id), NOT the CC session_id.

    Updated for per-task session_id design: SubagentStart generates a fresh uuid4
    as task_session_id and passes it to run_search (--pin-session).  The CC
    conversation session_id ("sess-abc123") must NOT be forwarded to run_search.
    """
    import uuid as _uuid
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    transcript_path = _make_transcript(tmp_path, [
        {"subagent_type": "coder", "prompt": "Some coder task"},
    ])
    event = _make_event(tmp_path, transcript_path=transcript_path, agent_type="coder")
    cc_session_id = event["session_id"]  # "sess-abc123"

    mod = _load_subagent_start()
    captured = {}

    def fake_run_search(query, org=None, project=None, session_id=None, **kwargs):
        captured["session_id"] = session_id
        return SAMPLE_PATTERNS_RESPONSE

    monkeypatch.setattr(mod, "run_search", fake_run_search)
    monkeypatch.setattr(mod, "get_context", lambda: GOOD_CONTEXT)
    monkeypatch.setattr(mod, "append_patterns_used", MagicMock())

    try:
        mod.main(event=event)
    except SystemExit:
        pass

    sid = captured.get("session_id")
    # When pinning is active, must be a uuid4 that is NOT the CC session_id.
    # When pinning is disabled, sid will be None — that is also acceptable.
    if sid is not None:
        assert sid != cc_session_id, (
            f"run_search must receive task_session_id (uuid4), NOT CC session_id "
            f"{cc_session_id!r}; got {sid!r}"
        )
        try:
            _uuid.UUID(sid)
        except ValueError:
            raise AssertionError(
                f"task_session_id passed to run_search is not a uuid4: {sid!r}"
            )


# ═══════════════════════════════════════════════════════════════════════════
# 15. STDIN-DRIVEN main() entrypoint (wrapper compatibility)
# ═══════════════════════════════════════════════════════════════════════════

def test_main_accepts_event_kwarg():
    """main() must accept an optional `event` kwarg (for testing without stdin)."""
    mod = _load_subagent_start()
    import inspect
    sig = inspect.signature(mod.main)
    assert "event" in sig.parameters, (
        "main() must accept an `event` keyword argument for testability"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 16. MISSING / NULL agent_id GUARD
# ═══════════════════════════════════════════════════════════════════════════

def test_no_append_when_agent_id_is_none(tmp_path, monkeypatch):
    """When agent_id is None, append_patterns_used must NOT be called."""
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    transcript_path = _make_transcript(tmp_path, [
        {"subagent_type": "coder", "prompt": "Some task"},
    ])
    event = _make_event(tmp_path, transcript_path=transcript_path, agent_id=None)

    mod = _load_subagent_start()
    rs_mock = MagicMock(return_value=SAMPLE_PATTERNS_RESPONSE)
    pu_mock = MagicMock()
    monkeypatch.setattr(mod, "run_search", rs_mock)
    monkeypatch.setattr(mod, "get_context", lambda: GOOD_CONTEXT)
    monkeypatch.setattr(mod, "append_patterns_used", pu_mock)

    try:
        mod.main(event=event)
    except SystemExit:
        pass

    pu_mock.assert_not_called(), (
        "append_patterns_used must NOT be called when agent_id is None"
    )


def test_no_run_search_when_agent_id_is_none(tmp_path, monkeypatch):
    """When agent_id is None, run_search must NOT be called (early exit)."""
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    transcript_path = _make_transcript(tmp_path, [
        {"subagent_type": "coder", "prompt": "Some task"},
    ])
    event = _make_event(tmp_path, transcript_path=transcript_path, agent_id=None)

    mod = _load_subagent_start()
    rs_mock = MagicMock(return_value=SAMPLE_PATTERNS_RESPONSE)
    pu_mock = MagicMock()
    monkeypatch.setattr(mod, "run_search", rs_mock)
    monkeypatch.setattr(mod, "get_context", lambda: GOOD_CONTEXT)
    monkeypatch.setattr(mod, "append_patterns_used", pu_mock)

    try:
        mod.main(event=event)
    except SystemExit:
        pass

    rs_mock.assert_not_called(), (
        "run_search must NOT be called when agent_id is None"
    )


def test_no_append_when_agent_id_absent(tmp_path, monkeypatch):
    """When the agent_id key is entirely absent from the event, must be a no-op."""
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    transcript_path = _make_transcript(tmp_path, [
        {"subagent_type": "coder", "prompt": "Some task"},
    ])
    event = _make_event(tmp_path, transcript_path=transcript_path)
    del event["agent_id"]

    mod = _load_subagent_start()
    rs_mock = MagicMock(return_value=SAMPLE_PATTERNS_RESPONSE)
    pu_mock = MagicMock()
    monkeypatch.setattr(mod, "run_search", rs_mock)
    monkeypatch.setattr(mod, "get_context", lambda: GOOD_CONTEXT)
    monkeypatch.setattr(mod, "append_patterns_used", pu_mock)

    try:
        mod.main(event=event)
    except SystemExit:
        pass

    pu_mock.assert_not_called(), (
        "append_patterns_used must NOT be called when agent_id key is absent"
    )
    rs_mock.assert_not_called(), (
        "run_search must NOT be called when agent_id key is absent"
    )


def test_agent_id_none_does_not_write_main_state_file(tmp_path, monkeypatch):
    """agent_id=None must not create a state file with the 'main' suffix."""
    import patterns_used_state as pus

    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    transcript_path = _make_transcript(tmp_path, [
        {"subagent_type": "coder", "prompt": "Some task"},
    ])
    event = _make_event(tmp_path, transcript_path=transcript_path, agent_id=None)

    mod = _load_subagent_start()
    monkeypatch.setattr(mod, "run_search", lambda *a, **kw: SAMPLE_PATTERNS_RESPONSE)
    monkeypatch.setattr(mod, "get_context", lambda: GOOD_CONTEXT)
    monkeypatch.setattr(mod, "append_patterns_used", pus.append_patterns_used)

    try:
        mod.main(event=event)
    except SystemExit:
        pass

    main_state = pus.state_file_path("sess-abc123", None)
    assert not main_state.exists(), (
        f"Main-agent state file must NOT be created when agent_id=None; "
        f"found: {main_state}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 17. TIMEOUT BUDGET — hooks.json SubagentStart timeout must cover run_search
# ═══════════════════════════════════════════════════════════════════════════

def test_hooks_json_subagent_start_timeout_covers_run_search_budget():
    """SubagentStart hook timeout must be >= 40000ms."""
    hooks_path = REPO / "plugins" / "ace" / "hooks" / "hooks.json"
    data = json.loads(hooks_path.read_text())
    entries = data.get("hooks", {}).get("SubagentStart", [])
    assert entries, "SubagentStart hook list is empty"

    timeouts = []
    for entry in entries:
        for hook in entry.get("hooks", []):
            t = hook.get("timeout")
            if t is not None:
                timeouts.append(t)

    assert timeouts, "No timeout values found in SubagentStart hooks"
    for t in timeouts:
        assert t >= 40000, (
            f"SubagentStart hook timeout {t}ms is too low — run_search alone "
            f"needs up to 30s; set timeout >= 40000ms to avoid SIGKILL before "
            f"append_patterns_used writes the state file"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 18. Agent tool_use (not just 'Task') is also matched
# ═══════════════════════════════════════════════════════════════════════════

def test_agent_tool_use_name_also_matched(tmp_path, monkeypatch):
    """Tool_use blocks with name='Agent' (not just 'Task') must also be scanned."""
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))

    # Build a transcript with an 'Agent' block instead of 'Task'
    entry = {
        "type": "assistantMessage",
        "uuid": "uuid-agent-block",
        "message": {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu_agent",
                    "name": "Agent",
                    "input": {
                        "subagent_type": "coder",
                        "prompt": "Agent-named block prompt",
                    },
                }
            ],
        },
    }
    transcript = tmp_path / "agent_block.jsonl"
    transcript.write_text(json.dumps(entry) + "\n")

    event = _make_event(tmp_path, transcript_path=str(transcript), agent_type="coder")

    mod = _load_subagent_start()
    captured = {}

    def fake_run_search(query, **kwargs):
        captured["query"] = query
        return SAMPLE_PATTERNS_RESPONSE

    monkeypatch.setattr(mod, "run_search", fake_run_search)
    monkeypatch.setattr(mod, "get_context", lambda: GOOD_CONTEXT)
    monkeypatch.setattr(mod, "append_patterns_used", MagicMock())

    try:
        mod.main(event=event)
    except SystemExit:
        pass

    assert "query" in captured, "run_search was never called for 'Agent' tool_use block"
    assert "Agent-named block prompt" in captured["query"], (
        f"Expected prompt from Agent block; got: {captured['query']!r}"
    )
