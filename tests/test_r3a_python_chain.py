#!/usr/bin/env python3
"""v8.0.0 round 3a RED — DESIGN §13.2 Python-chain fixes + §13.1 mod-active marker helper.

Evidence: /tmp/ace-v8-dry/m2-chain-vs-chain/REPORT.md (F-V1 version probe, F-V3 SubagentStop
trivial skip, F-V4 Write recorded "Failed"), m3-ace-cli-usage-deepdive (stream learn exits 0 on
server 401/500; ace-cli hard-codes X-ACE-Client: cli). Hook-level variants live in
tests/e2e/test_e2e_r3a.py (ACE_E2E=1).
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from test_stop_v8 import Box, PROJECT_ID, ORG_ID  # noqa: F401

REPO = Path(__file__).resolve().parent.parent
PLUGIN = REPO / "plugins" / "ace"
HOOKS = PLUGIN / "shared-hooks"
for _p in (HOOKS, HOOKS / "utils", PLUGIN / "utils"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

@pytest.fixture
def box(tmp_path):
    return Box(tmp_path)


REMINDER = ("<system-reminder>\nCodebase and user instructions are shown below. Be sure to adhere "
            "to these instructions.\n\nContents of /Users/x/.claude/CLAUDE.md:\n# notes\n</system-reminder>")
REAL_PROMPT = "Read the file ace-cli/notes.md, then use Bash to run: echo sub-done > sub_out.txt"


# ── §13.2 run_learn --no-stream (m3: stream mode exits 0 on server 401/500) ────────────────

def test_run_learn_passes_no_stream(fake_cli_calls):
    """`ace-cli learn --help` (4.2.2): `--no-stream  Disable SSE streaming (use sync POST)`.
    run_learn must pass it so a server 401/500 becomes a non-zero exit that reaches the error log."""
    import ace_cli
    ace_cli.run_learn({"task": "t", "trajectory": []}, org="org_x", project="prj_x")
    learns = [c["argv"] for c in fake_cli_calls() if c["argv"][:1] == ["learn"]]
    assert len(learns) == 1, learns
    assert "--no-stream" in learns[0], learns[0]
    # P-18 single source of truth stays: --timeout 300000 with run_learn(timeout=300)
    assert learns[0][learns[0].index("--timeout") + 1] == "300000"


def test_run_learn_skips_instead_of_writing_the_trace_to_system_tmp(fake_cli_calls, monkeypatch):
    """final review: no private plugin-data tmp -> no learn; the trace (it holds the prompt) never hits /tmp."""
    import ace_cli
    import plugin_data_dir
    import tempfile as _tf
    monkeypatch.setattr(plugin_data_dir, "private_dir", lambda p: (_ for _ in ()).throw(OSError("ro")))
    made = []
    real = _tf.mkstemp
    monkeypatch.setattr(_tf, "mkstemp", lambda *a, **k: made.append(k) or real(*a, **k))
    out, _ms = ace_cli.run_learn({"task": "secret prompt", "trajectory": []}, org="o", project="p")
    assert out is None and made == []
    assert [c for c in fake_cli_calls() if c["argv"][:1] == ["learn"]] == []


def test_ensure_authenticated_is_deleted():
    """§13.2: delete dead `ensure_authenticated` (no hook or command calls it)."""
    import ace_cli
    assert not hasattr(ace_cli, "ensure_authenticated")
    hits = [str(p.relative_to(REPO)) for d in ("shared-hooks", "commands", "scripts", "utils")
            for p in (PLUGIN / d).rglob("*") if p.is_file() and p.suffix in (".py", ".sh", ".md")
            and "ensure_authenticated" in p.read_text(errors="replace")]
    assert hits == [], hits


# ── §13.2 Write/Edit success detection (m2 F-V4: every successful Write traced as "Failed") ──

@pytest.mark.parametrize("tool,resp", [
    # PostToolUse structured Output objects (cc_hooks_reference.md PostToolBatch note: Write ->
    # {filePath, type: "create"}); no `success` key, no exit code.
    ("Write", {"type": "create", "filePath": "/p/hello_ace.py", "content": "print('hi')\n",
               "structuredPatch": []}),
    ("Write", {"type": "update", "filePath": "/p/hello_ace.py", "content": "x\n",
               "structuredPatch": [{"oldStart": 1, "lines": ["-a", "+x"]}]}),
    ("Edit", {"filePath": "/p/a.py", "oldString": "a", "newString": "b", "originalFile": "a\n",
              "structuredPatch": [{"oldStart": 1, "lines": ["-a", "+b"]}], "userModified": False}),
    # PostToolBatch serialized tool_result strings (what the accumulator stores since §9 G4)
    ("Write", "File created successfully at: /p/hello_ace.py"),
    ("Edit", "The file /p/a.py has been updated. Here's the result of running `cat -n` ..."),
    # per-agent transcript tool_result (parse_agent_transcript -> {'content': ...})
    ("Write", {"content": "File created successfully at: /p/hello_ace.py"}),
    ("Edit", {"content": "The file /p/a.py has been updated."}),
])
def test_write_edit_success_detection(tool, resp):
    from ace_after_task import summarize_tool_response
    assert summarize_tool_response(tool, resp) == "Success"


@pytest.mark.parametrize("tool,resp", [
    ("Write", {"error": "EACCES: permission denied"}),
    ("Edit", {"content": "<tool_use_error>String to replace not found in file.</tool_use_error>",
              "error": "<tool_use_error>String to replace not found in file.</tool_use_error>"}),
])
def test_write_edit_errors_are_not_success(tool, resp):
    from ace_after_task import summarize_tool_response
    assert summarize_tool_response(tool, resp) != "Success"


def test_posttoolbatch_write_edit_traced_as_success(box):
    """End to end through the real accumulator shim (--batch) and Stop: the learned trajectory
    records Write/Edit as Success (3/3 'Failed' in m2)."""
    sid = "s-r3a-write"
    calls = [
        {"tool_name": "Write", "tool_input": {"file_path": str(box.project / "hello_ace.py"),
                                              "content": "print('hi')"},
         "tool_use_id": "toolu_w1", "tool_response": "File created successfully at: %s/hello_ace.py" % box.project},
        {"tool_name": "Edit", "tool_input": {"file_path": str(box.project / "hello_ace.py"),
                                             "old_string": "hi", "new_string": "hi-from-ace"},
         "tool_use_id": "toolu_e1", "tool_response": "The file %s/hello_ace.py has been updated." % box.project},
    ]
    ev = {"session_id": sid, "transcript_path": str(box.root / "t.jsonl"), "cwd": str(box.project),
          "permission_mode": "default", "hook_event_name": "PostToolBatch", "tool_calls": calls}
    p = box.run_shim("ace_posttooluse_wrapper.sh", ev, args=["--batch"])
    assert p.returncode == 0, p.stderr
    box.write_state(sid, user_prompt="create hello_ace.py that prints hi-from-ace and run it")
    p = box.run_after_task(box.stop_event(sid))
    assert p.returncode == 0, p.stderr
    learns = box.cli_calls("learn")
    assert len(learns) == 1, learns
    steps = {s["tool"]: s["result"] for s in learns[0]["trace"]["trajectory"]}
    assert steps == {"Write": "Success", "Edit": "Success"}, steps


# ── §13.2 SubagentStop trivial-skip (m2 F-V3: <system-reminder> taken as the task) ─────────

def _write_transcript(path, entries):
    path.write_text("\n".join(json.dumps(e) for e in entries) + "\n")
    return path


def _subagent_entries(prompt=REAL_PROMPT):
    """Shape of the real 2.1.316 subagent transcript (m2 runs/S4-v8-1/.../agent-*.jsonl):
    the prompt entry, then an `api-request-blob` user entry whose content starts with the
    injected <system-reminder> CLAUDE.md blocks, then tool use."""
    return [
        {"type": "user", "message": {"role": "user", "content": prompt}},
        {"type": "api-request-blob", "message": {"role": "user", "content": [
            {"type": "text", "text": REMINDER},
            {"type": "text", "text": "<system-reminder>\nClaude Code attached this context.\n</system-reminder>"},
            {"type": "text", "text": prompt}]}},
        {"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": "toolu_sr_1", "name": "Bash",
             "input": {"command": "echo sub-done > sub_out.txt"}}]}},
        {"type": "user", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "toolu_sr_1", "content": "(Bash completed with no output)",
             "is_error": False}]}},
    ]


def test_transcript_fallback_skips_system_reminder_blocks(tmp_path):
    from ace_after_task import get_user_prompt_from_transcript
    t = _write_transcript(tmp_path / "agent-x.jsonl", _subagent_entries())
    got = get_user_prompt_from_transcript(str(t))
    assert "<system-reminder>" not in got, got[:200]
    assert got.strip() == REAL_PROMPT


def test_transcript_fallback_reminder_only_entry_is_skipped(tmp_path):
    """A user entry made only of <system-reminder> blocks is not a prompt: take the real one."""
    from ace_after_task import get_user_prompt_from_transcript
    t = _write_transcript(tmp_path / "agent-y.jsonl", [
        {"type": "user", "message": {"role": "user", "content": REAL_PROMPT}},
        {"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": REMINDER}]}},
    ])
    assert get_user_prompt_from_transcript(str(t)).strip() == REAL_PROMPT


def test_subagent_stop_uses_stored_subagentstart_query_first(box):
    """§13.2: task text for subagents = SubagentStart's stored query (state `user_prompt`) FIRST;
    the transcript is only the fallback."""
    sid, agent = "s-r3a-sub", "a1b2c3d4e5f6a7b8c"
    stored = "audit the payment webhook retry logic for idempotency bugs"
    box.write_state(sid, agent=agent, user_prompt=stored, query_source="stash", task_session_id="sub-tsid-1")
    ev = box.subagent_event(sid, agent, agent_type="general-purpose")  # writes the default transcript
    _write_transcript(Path(ev["agent_transcript_path"]), _subagent_entries())  # replace with the real shape
    p = box.run_after_task(ev)
    assert p.returncode == 0, p.stderr
    learns = box.cli_calls("learn")
    assert len(learns) == 1, "subagent learn skipped (trivial?) — stderr: %s" % p.stderr[-400:]
    assert learns[0]["trace"]["task"] == "User request: " + stored


# ── §13.2 SessionStart: a timed-out version probe never disables ACE (m2 F-V1) ────────────

def test_version_probe_timeout_does_not_disable(tmp_path, monkeypatch):
    import ace_install_cli as m
    import plugin_data_dir
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path / "ace-pd"))
    cli = tmp_path / "ace-cli"
    cli.write_text("#!/bin/sh\nsleep 20\n")
    cli.chmod(0o755)

    def hang(*a, **k):
        raise subprocess.TimeoutExpired(a[0] if a else "ace-cli", k.get("timeout", 15))
    monkeypatch.setattr(m.subprocess, "run", hang)
    msgs = m.startup({}, "sid-r3a", "prj_r3a", str(cli))
    assert not plugin_data_dir.disabled_flag("prj_r3a", "sid-r3a").exists(), \
        "a timed-out/unknown version must never write disabled.flag"
    assert not any("Outdated" in x or "DISABLED" in x for x in msgs), msgs
    logged = "".join(p.read_text(errors="replace") for p in (tmp_path / "ace-pd").rglob("*") if p.is_file())
    assert "version_unknown" in logged, "unknown version must be logged as version_unknown"


# ── §13.1 mod-active marker helpers ─────────────────────────────────────────────────────

def test_mod_active_marker_path(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path / "ace-pd"))
    import plugin_data_dir as pdd
    p = pdd.mod_active_marker("prj_m", "sid_m")
    assert p == tmp_path / "ace-pd" / "projects" / "prj_m" / "sessions" / "sid_m" / "mod-active"


def test_is_mod_active_fresh_stale_absent(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path / "ace-pd"))
    import plugin_data_dir as pdd
    assert pdd.is_mod_active("prj_m", "sid_m") is False
    assert not (tmp_path / "ace-pd" / "projects").exists(), "is_mod_active must never create dirs"
    p = tmp_path / "ace-pd" / "projects" / "prj_m" / "sessions" / "sid_m" / "mod-active"
    p.parent.mkdir(parents=True)
    p.write_text("")
    assert pdd.is_mod_active("prj_m", "sid_m") is True
    old = time.time() - 3 * 60
    os.utime(str(p), (old, old))
    assert pdd.is_mod_active("prj_m", "sid_m") is False, "after-tool window: older than 120 s is stale"
    young = time.time() - 90
    os.utime(str(p), (young, young))
    assert pdd.is_mod_active("prj_m", "sid_m") is True
    assert pdd.is_mod_active("prj_m", "sid_m", pdd.MOD_HANDOFF_S) is False, "handoff window: the mod wrote right before"


def test_a_crashed_mod_releases_the_python_chain_within_seconds(tmp_path, monkeypatch):
    """Claude Code unloads all user mods after 3 worker crashes. The marker of the dead mod must not keep the
    Python chain quiet for 10 minutes: a live mod rewrites it right before every handoff hook, so 30 s = dead."""
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path / "ace-pd"))
    import plugin_data_dir as pdd
    sdir = tmp_path / "ace-pd" / "projects" / "prj_m" / "sessions" / "sid_m"
    sdir.mkdir(parents=True)
    for n in ("mod-active", "mod-classic"):
        (sdir / n).write_text("")
        t = time.time() - 30
        os.utime(str(sdir / n), (t, t))
    assert pdd.is_mod_active("prj_m", "sid_m", pdd.MOD_HANDOFF_S) is False   # UPS / SubagentStart / Agent stash search
    assert pdd.mod_owns_learn("prj_m", "sid_m", pdd.MOD_HANDOFF_S) is False  # Stop / SubagentStop learn


def test_is_mod_active_sanitizes_ids(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path / "ace-pd"))
    import plugin_data_dir as pdd
    assert "projects" in str(pdd.mod_active_marker("../../etc", "../x").resolve().relative_to(tmp_path / "ace-pd"))


# ── §13.2 ACE_CLIENT_ID truth (ace-cli 4.3.0 honours it; tests/test_cli_client_header.py proves it) ──

def test_docs_state_ace_cli_sends_the_plugin_client_id():
    """ace-cli >= 4.3.0 sends X-ACE-Client from ACE_CLIENT_ID (older: hard-coded `cli`).
    CHANGELOG 8.0.0 and ADR-001 must say so (info for the server/SDK teams)."""
    changelog = (PLUGIN / "CHANGELOG.md").read_text()
    v8 = changelog.split("## [8.0.0]", 1)[1].split("\n## [", 1)[0]
    adr = (PLUGIN / "docs" / "technical" / "ADR-001-language.md").read_text()
    for name, text in (("CHANGELOG 8.0.0", v8), ("ADR-001", adr)):
        assert "4.3.0" in text and "claude-code-plugin/<version>" in text, name
        assert "ACE_CLIENT_ID" in text, name


def test_mod_owns_learn_needs_a_fresh_classic_marker(tmp_path, monkeypatch):
    """Seats where the managed-settings guard filters the mod's classic.* hooks: the mod is active
    (mod-active) but its Stop/SubagentStop hooks never run, so the Python Stop must keep the learn."""
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path / "ace-pd"))
    import plugin_data_dir as pdd
    sdir = tmp_path / "ace-pd" / "projects" / "prj_m" / "sessions" / "sid_m"
    sdir.mkdir(parents=True)
    (sdir / "mod-active").write_text("")
    assert pdd.is_mod_active("prj_m", "sid_m") is True
    assert pdd.mod_owns_learn("prj_m", "sid_m") is False, "no classic marker: the Python Stop learns"
    (sdir / "mod-classic").write_text("")
    assert pdd.mod_owns_learn("prj_m", "sid_m") is True
    old = time.time() - 11 * 60
    os.utime(str(sdir / "mod-classic"), (old, old))
    assert pdd.mod_owns_learn("prj_m", "sid_m") is False
