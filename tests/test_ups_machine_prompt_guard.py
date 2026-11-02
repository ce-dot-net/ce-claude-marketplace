#!/usr/bin/env python3
"""WP-B (v8.0.0) RED tests — UserPromptSubmit hook (shared-hooks/ace_before_task.py).

DESIGN.md §6 "WP-B", §3.1 (shim), §4 (state layout), §5 C1/C2/C3/C5, §8 addendum.
Evidence: critic-completeness.md T1 (97-99.7 % of UPS searches are machine
<task-notification> prompts), T4/T5/V14 (3 ace-cli spawns per UPS: --version,
whoami, search), C8 (patterns_injected logged before render), T17 (no disabled
check in UPS), T20 (observability: hook_ms, log after render).

Hermetic: subprocess.run is replaced by a fake that records every argv and
answers `ace-cli search` with a canned JSON response; the real ace-cli is never
run. Everything is written under tmp_path (CLAUDE_PLUGIN_DATA, HOME, project).
"""
import importlib.util
import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
PLUGIN = REPO / "plugins" / "ace"
SHARED = PLUGIN / "shared-hooks"
UTILS = SHARED / "utils"
for p in (str(SHARED), str(UTILS), str(PLUGIN / "utils")):
    if p not in sys.path:
        sys.path.insert(0, p)

import plugin_data_dir  # noqa: E402
import ace_relevance_logger  # noqa: E402

PROJECT = "prj-wpb-test"
ORG = "org-wpb-test"
CC_SESSION = "cc-sess-wpb-0001"
HUMAN_PROMPT = "refactor the authentication middleware to use JSON web tokens"


def _pid(i):
    return "ctx-%010d-%04x" % (1000000000 + i, i)


def _patterns(n, content_len=60):
    return [
        {
            "id": _pid(i),
            "domain": "python-hooks" if i % 2 else "claude-plugins",
            "section": "strategies",
            "content": ("pattern %d " % i) + "x" * content_len,
            "confidence": 0.8,
            "helpful": 5,
            "harmful": 0,
            "cumulative_v15_reward": 1.0,
            "isAtRisk": False,
            "match_factors": {"bandit_rank": i + 1, "retrieval_log_id": 100 + i},
        }
        for i in range(n)
    ]


def _response(n=3, content_len=60):
    return {"similar_patterns": _patterns(n, content_len), "count": n,
            "retrieval_id": "ret-wpb-001"}


# ── fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def project(tmp_path, monkeypatch):
    """Tmp project with .claude/settings.json; process cwd = project."""
    proj = tmp_path / "proj"
    (proj / ".claude" / "data" / "logs").mkdir(parents=True)
    (proj / ".claude" / "settings.json").write_text(
        json.dumps({"orgId": ORG, "projectId": PROJECT}))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path / "plugin-data"))
    for var in ("ACE_PROJECT_ID", "ACE_ORG_ID", "ACE_MIN_PROMPT_CHARS",
                "ACE_AB_CONTROL_PCT", "ACE_AB_COMPACT_PCT", "CLAUDE_CODE_SESSION_ID"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.chdir(proj)
    # relevance logger is a singleton with a relative log dir; reset it per test
    monkeypatch.setattr(ace_relevance_logger, "_logger", None)
    yield proj
    # the pre-v8 hook writes these; never leave residue in /tmp
    for leftover in ("/tmp/ace-domains-%s.json" % PROJECT, "/tmp/ace-session-%s.txt" % PROJECT):
        Path(leftover).unlink(missing_ok=True)


@pytest.fixture
def fake_cli(monkeypatch):
    """Replace subprocess.run; record ace-cli argv; answer search with JSON."""
    state = {"calls": [], "response": _response()}
    real_run = subprocess.run

    def fake_run(cmd, *a, **kw):
        argv = list(cmd) if isinstance(cmd, (list, tuple)) else [cmd]
        if argv and os.path.basename(str(argv[0])) == "ace-cli":
            state["calls"].append(argv)
            if "search" in argv:
                out = json.dumps(state["response"])
                return subprocess.CompletedProcess(
                    argv, 0, out.encode() if not kw.get("text") else out, b"" if not kw.get("text") else "")
            return subprocess.CompletedProcess(argv, 1, b"" if not kw.get("text") else "",
                                               b"" if not kw.get("text") else "")
        return real_run(cmd, *a, **kw)

    monkeypatch.setattr(subprocess, "run", fake_run)
    state["searches"] = lambda: [c for c in state["calls"] if "search" in c]
    return state


def _load():
    spec = importlib.util.spec_from_file_location("ace_before_task_wpb", SHARED / "ace_before_task.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run(monkeypatch, capsys, prompt, cwd, **extra):
    event = {"session_id": CC_SESSION, "hook_event_name": "UserPromptSubmit",
             "prompt": prompt, "cwd": str(cwd),
             "transcript_path": str(Path(cwd) / "t.jsonl")}
    event.update(extra)
    mod = _load()
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(event)))
    try:
        mod.main()
    except SystemExit:
        pass
    out = capsys.readouterr().out.strip()
    return json.loads(out) if out.startswith("{") else (out or None)


def _relevance(proj):
    log = Path(proj) / ".claude" / "data" / "logs" / "ace-relevance.jsonl"
    if not log.exists():
        return []
    return [json.loads(l) for l in log.read_text().splitlines() if l.strip()]


def _additional_context(out):
    if isinstance(out, dict):
        return (out.get("hookSpecificOutput") or {}).get("additionalContext")
    return None


def _main_state(proj=None):
    sf = plugin_data_dir.session_dir(PROJECT, CC_SESSION, create=False) / "patterns-used-main.json"
    return json.loads(sf.read_text()) if sf.exists() else None


# ── (1) machine-prompt guard ────────────────────────────────────────────────

MACHINE_PROMPTS = [
    "<task-notification>\n<task-id>abc</task-id>\n<status>completed</status>\n</task-notification>",
    "<agent-message from=\"coder\">done with the refactor of the hooks</agent-message>",
    "<cross-session-message from=\"s2\">please review the diff now</cross-session-message>",
    "[SYSTEM NOTIFICATION] background task finished with exit code 0",
    "<local-command-stdout>Compacted conversation history</local-command-stdout>",
    "<command-name>/model</command-name>\n<command-message>model</command-message>",
    "<bash-input>git status --short</bash-input>",
    "<bash-stdout>On branch main, nothing to commit</bash-stdout>",
    "<bash-stderr>fatal: not a git repository at all</bash-stderr>",
]


@pytest.mark.parametrize("prompt", MACHINE_PROMPTS, ids=lambda p: p[:16])
def test_machine_prompt_prefix_skips_search_and_injection(project, fake_cli, monkeypatch, capsys, prompt):
    """DESIGN §6 WP-B (1), critic T1: a prompt whose stripped text starts with a
    machine prefix spawns NO ace-cli search and injects no additionalContext."""
    out = _run(monkeypatch, capsys, "  \n" + prompt, project)
    assert fake_cli["searches"]() == [], "machine prompt must not spawn ace-cli search"
    assert _additional_context(out) is None


def test_system_reminder_only_prompt_skips_search(project, fake_cli, monkeypatch, capsys):
    """DESIGN §6 WP-B (1): a prompt that is only a <system-reminder>…</system-reminder>
    block is a machine prompt (no search, no injection)."""
    prompt = "<system-reminder>\nTodo list changed; continue with the current task please.\n</system-reminder>\n"
    out = _run(monkeypatch, capsys, prompt, project)
    assert fake_cli["searches"]() == []
    assert _additional_context(out) is None


def test_machine_prompt_logs_search_skipped_with_reason(project, fake_cli, monkeypatch, capsys):
    """DESIGN §6 WP-B (1), critic T20: a skipped machine prompt logs one
    `search_skipped` relevance event with a non-empty `reason`."""
    _run(monkeypatch, capsys, MACHINE_PROMPTS[0], project)
    skipped = [e for e in _relevance(project) if e.get("event") == "search_skipped"]
    assert len(skipped) == 1, _relevance(project)
    assert skipped[0].get("reason")
    assert skipped[0].get("hook") == "UserPromptSubmit"
    assert not [e for e in _relevance(project) if e.get("event") == "search"]


def test_ace_slash_command_skip_kept(project, fake_cli, monkeypatch, capsys):
    """DESIGN §6 WP-B (1): the existing /ace- and /ace: skip stays (regression guard)."""
    for prompt in ("/ace-status please show everything", "/ace:ace-search hooks and stuff"):
        _run(monkeypatch, capsys, prompt, project)
    assert fake_cli["searches"]() == []


def test_machine_marker_mid_prompt_still_searches(project, fake_cli, monkeypatch, capsys):
    """DESIGN §6 WP-B (1): the guard is prefix-only — a human prompt that merely
    mentions <task-notification> later on is still searched (regression guard)."""
    _run(monkeypatch, capsys, "explain why the <task-notification> prompts were searched", project)
    assert len(fake_cli["searches"]()) == 1


def test_short_prompt_below_min_chars_skips_search(project, fake_cli, monkeypatch, capsys):
    """DESIGN §6 WP-B (1): prompts with < 12 visible chars (default) are skipped
    and logged as search_skipped."""
    out = _run(monkeypatch, capsys, "  ok go  ", project)
    assert fake_cli["searches"]() == []
    assert _additional_context(out) is None
    assert [e for e in _relevance(project) if e.get("event") == "search_skipped"]


def test_min_prompt_chars_env_override(project, fake_cli, monkeypatch, capsys):
    """DESIGN §6 WP-B (1): ACE_MIN_PROMPT_CHARS overrides the 12-char minimum."""
    monkeypatch.setenv("ACE_MIN_PROMPT_CHARS", "40")
    _run(monkeypatch, capsys, "fix the flaky hook test now", project)  # 27 chars
    assert fake_cli["searches"]() == [], "27 visible chars < ACE_MIN_PROMPT_CHARS=40"


# ── (2) single spawn ────────────────────────────────────────────────────────

def test_human_prompt_single_ace_cli_spawn_with_pin_session(project, fake_cli, monkeypatch, capsys):
    """DESIGN §6 WP-B (2), §5 C2, critic T5/V14: a human prompt costs exactly ONE
    ace-cli spawn (search --stdin --json --pin-session <task_session_id>) — no
    `--version` probe, no `whoami` pre-check on the success path."""
    out = _run(monkeypatch, capsys, HUMAN_PROMPT, project)
    assert len(fake_cli["calls"]) == 1, fake_cli["calls"]
    argv = fake_cli["calls"][0]
    assert "search" in argv and "--pin-session" in argv
    tsid = argv[argv.index("--pin-session") + 1]
    assert tsid and tsid != CC_SESSION
    assert _additional_context(out)


# ── (3) no UPS disk cache (F-080: every turn searches with --pin-session) ───

def test_repeated_prompt_searches_again_with_pin_session(project, fake_cli, monkeypatch, capsys):
    """A repeated short follow-up must NOT be served from a cache: the cache hit carried no
    retrieval_id / applied_log_ids and never pinned the new tsid, losing F-080 credit."""
    _run(monkeypatch, capsys, HUMAN_PROMPT, project)
    first_tsid = _main_state()["task_session_id"]
    out = _run(monkeypatch, capsys, HUMAN_PROMPT, project)
    assert len(fake_cli["calls"]) == 2
    argv = fake_cli["calls"][1]
    assert argv[argv.index("--pin-session") + 1] == _main_state()["task_session_id"] != first_tsid
    st = _main_state()
    assert st["retrieval_id"] == "ret-wpb-001" and st["retrieval_log_ids"]
    assert _additional_context(out)


def test_new_task_resets_stale_state_from_interrupted_turn(project, fake_cli, monkeypatch, capsys):
    """Stop does not run on interrupt: the next UPS must not merge the old ids/retrieval_id."""
    _run(monkeypatch, capsys, HUMAN_PROMPT, project)
    sf = plugin_data_dir.session_dir(PROJECT, CC_SESSION, create=False) / "patterns-used-main.json"
    st = json.loads(sf.read_text())
    st["pattern_ids"].append("ctx-1111111111-aaaa")
    st["retrieval_id"] = "RID_OLD"
    st["retrieval_log_ids"]["ctx-1111111111-aaaa"] = 99
    sf.write_text(json.dumps(st))
    fake_cli["response"] = {"error": "timeout", "message": "slow"}
    _run(monkeypatch, capsys, HUMAN_PROMPT + " second", project)
    new = _main_state()
    assert "ctx-1111111111-aaaa" not in new["pattern_ids"] and not new.get("retrieval_id")


def test_multiple_leading_reminder_blocks_are_machine(project, fake_cli, monkeypatch, capsys):
    p = "<system-reminder>x</system-reminder><system-reminder>y</system-reminder>"
    _run(monkeypatch, capsys, p, project)
    assert fake_cli["searches"]() == []


# ── (4) domains.json, state C1 keys, relevance log after render ─────────────

def test_domains_json_written_under_plugin_data_not_tmp(project, fake_cli, monkeypatch, capsys):
    """DESIGN §6 WP-B (4), §4, C3: search-result domains go to
    <plugin-data>/projects/<project>/domains.json — never /tmp/ace-domains-*."""
    tmp_file = Path("/tmp/ace-domains-%s.json" % PROJECT)
    tmp_file.unlink(missing_ok=True)
    _run(monkeypatch, capsys, HUMAN_PROMPT, project)
    df = plugin_data_dir.domains_file(PROJECT)
    assert df.exists(), "domains.json missing under plugin data"
    domains = json.loads(df.read_text())
    assert "python-hooks" in domains and "claude-plugins" in domains
    assert not tmp_file.exists()


def test_no_tmp_session_file_written(project, fake_cli, monkeypatch, capsys):
    """DESIGN §0/§4 (no /tmp writes), §3 (PreCompact recall removed): UPS no longer
    writes /tmp/ace-session-<project>.txt."""
    tmp_file = Path("/tmp/ace-session-%s.txt" % PROJECT)
    tmp_file.unlink(missing_ok=True)
    _run(monkeypatch, capsys, HUMAN_PROMPT, project)
    assert not tmp_file.exists()


def test_state_has_user_prompt_rendered_context_and_event(project, fake_cli, monkeypatch, capsys):
    """DESIGN §6 WP-B (4), C1: the main state file carries user_prompt (≤ 4,000),
    rendered_context == the exact additionalContext emitted, and hook_event_name."""
    long_prompt = HUMAN_PROMPT + " " + "y" * 5000
    out = _run(monkeypatch, capsys, long_prompt, project)
    state = _main_state()
    assert state, "main state file not written"
    assert state.get("user_prompt") == long_prompt[:4000]
    assert state.get("rendered_context") == _additional_context(out)
    assert state.get("hook_event_name") == "UserPromptSubmit"


def test_relevance_log_counts_real_injected_after_render(project, fake_cli, monkeypatch, capsys):
    """DESIGN §6 WP-B (4), C5, critic C8: the search event is logged AFTER render;
    patterns_injected = ids actually rendered (budget-trimmed), not the returned count."""
    fake_cli["response"] = _response(n=40, content_len=600)  # far above the 9,500 budget
    out = _run(monkeypatch, capsys, HUMAN_PROMPT, project)
    ctx = _additional_context(out) or ""
    injected_ids = [_pid(i) for i in range(40) if _pid(i) in ctx]
    searches = [e for e in _relevance(project) if e.get("event") == "search"]
    assert len(searches) == 1
    assert searches[0]["patterns_returned"] == 40
    assert 0 < searches[0]["patterns_injected"] < 40
    assert searches[0]["patterns_injected"] == len(injected_ids)


def test_relevance_log_has_hook_ms(project, fake_cli, monkeypatch, capsys):
    """DESIGN §6 WP-B (4), C5, critic T20: the search event carries an int hook_ms."""
    _run(monkeypatch, capsys, HUMAN_PROMPT, project)
    searches = [e for e in _relevance(project) if e.get("event") == "search"]
    assert searches and isinstance(searches[-1].get("hook_ms"), int)
    assert searches[-1]["hook_ms"] >= 0


# ── (5) disabled flag ───────────────────────────────────────────────────────

def test_disabled_flag_skips_search(project, fake_cli, monkeypatch, capsys):
    """DESIGN §6 WP-B (5), §4, critic T17: a disabled.flag in this session's
    plugin-data dir stops the UPS search (UPS had no check at all)."""
    flag = plugin_data_dir.disabled_flag(PROJECT, CC_SESSION)
    flag.write_text("cli outdated")
    out = _run(monkeypatch, capsys, HUMAN_PROMPT, project)
    assert fake_cli["calls"] == []
    assert _additional_context(out) is None


# ── shim-free cwd: context comes from the hook JSON `cwd` ───────────────────

def test_context_resolved_from_event_cwd(project, fake_cli, monkeypatch, capsys, tmp_path):
    """DESIGN §3.1 (no `cd` in shims; Python uses `cwd` from the hook JSON): with the
    process cwd elsewhere, the project context comes from <event.cwd>/.claude/settings.json."""
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    _run(monkeypatch, capsys, HUMAN_PROMPT, project)
    assert len(fake_cli["searches"]()) == 1, "context must be read from event cwd"


# ── §8 addendum: sessionTitle ───────────────────────────────────────────────

def test_session_title_not_emitted_when_custom_title_present(project, fake_cli, monkeypatch, capsys):
    """DESIGN §8 (hooks doc ~1265/~1496): when the input has `session_title`
    (custom title via /rename or --name), UPS must not emit sessionTitle."""
    out = _run(monkeypatch, capsys, HUMAN_PROMPT, project, session_title="my-custom-title")
    assert _additional_context(out), "patterns must still be injected"
    assert "sessionTitle" not in out["hookSpecificOutput"]


def test_session_title_emitted_without_custom_title(project, fake_cli, monkeypatch, capsys):
    """DESIGN §8: without `session_title` the ACE sessionTitle is still emitted (regression guard)."""
    out = _run(monkeypatch, capsys, HUMAN_PROMPT, project)
    assert out["hookSpecificOutput"].get("sessionTitle")


# ── §3.1 shim contract for ace_before_task_wrapper.sh ───────────────────────

def test_before_task_wrapper_is_thin_shim():
    """DESIGN §3.1, §6 WP-B: ace_before_task_wrapper.sh is a thin shim — no jq,
    no cat, no cd; reads the cached python_path; execs ace_before_task.py."""
    src = (PLUGIN / "scripts" / "ace_before_task_wrapper.sh").read_text()
    code = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))
    assert "jq" not in code
    assert "$(cat" not in code and "cat " not in code
    assert "cd " not in code.replace("$(cd \"$(dirname", "")  # ROOT fallback only
    assert "python_path" in code
    assert "exec " in code and "ace_before_task.py" in code


# ── review fixes (WP-B fix round) ───────────────────────────────────────────

def test_reminder_prefix_on_human_prompt_still_searches(project, fake_cli, monkeypatch, capsys):
    prompt = "<system-reminder>The user opened foo.py in the IDE.</system-reminder> " + HUMAN_PROMPT
    out = _run(monkeypatch, capsys, prompt, project)
    assert len(fake_cli["searches"]()) == 1
    assert _additional_context(out)


def test_relevance_log_keeps_avg_confidence_and_top_patterns(project, fake_cli, monkeypatch, capsys):
    _run(monkeypatch, capsys, HUMAN_PROMPT, project)
    e = [x for x in _relevance(project) if x.get("event") == "search"][0]
    assert e["avg_confidence"] > 0
    assert e["top_patterns"] and e["top_patterns"][0]["id"].startswith("ctx-")
    assert e["patterns_injected"] == 3


def test_failed_search_state_keeps_user_prompt_and_event(project, fake_cli, monkeypatch, capsys):
    fake_cli["response"] = {"error": "timeout", "message": "slow"}
    _run(monkeypatch, capsys, HUMAN_PROMPT, project)
    st = _main_state()
    assert st["user_prompt"] == HUMAN_PROMPT and st["hook_event_name"] == "UserPromptSubmit"


def test_control_arm_clears_stale_rendered_context(project, fake_cli, monkeypatch, capsys):
    _run(monkeypatch, capsys, HUMAN_PROMPT, project)  # budget arm leaves rendered_context
    assert _main_state()["rendered_context"]
    monkeypatch.setenv("ACE_AB_CONTROL_PCT", "100")
    _run(monkeypatch, capsys, HUMAN_PROMPT + " again please", project)
    assert not _main_state().get("rendered_context")


def test_no_project_context_message_is_json(project, fake_cli, monkeypatch, capsys):
    (project / ".claude" / "settings.json").write_text("{}")
    out = _run(monkeypatch, capsys, HUMAN_PROMPT, project)
    assert out is None  # silent exit: /ace:ace-doctor reports a missing project context
