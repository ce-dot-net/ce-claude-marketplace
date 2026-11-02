#!/usr/bin/env python3
"""WP-C (v8.0.0) RED tests — Stop / SubagentStop / accumulator / learn.

Binding spec: DESIGN.md §3 (topology + §3.1 shim contract), §4 (state layout),
§5 C1/C3/C4, §6 "WP-C", §8 addendum (machine-prompt prefixes in is_trivial_task).
Evidence: understand/code-stop-learn-path.md F1-F20, critic-completeness.md
V3/V4/V10/V11, T6/T11/T13/T15/T16/T20/T23.

Hermetic: every subprocess gets an isolated HOME / CLAUDE_PLUGIN_DATA /
XDG_CONFIG_HOME and a fake `ace-cli` first on PATH that logs argv (and the
--transcript trace) to a JSONL file. The real ace-cli is never called.
"""
import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest

from plugin_copy import hermetic_root

REPO = Path(__file__).resolve().parent.parent
PLUGIN = REPO / "plugins" / "ace"
SCRIPTS = PLUGIN / "scripts"
HOOKS = PLUGIN / "shared-hooks"
AFTER_TASK = HOOKS / "ace_after_task.py"
ACCUMULATOR = HOOKS / "ace_tool_accumulator.py"
EVENT_LOGGER = HOOKS / "ace_event_logger.py"

for _p in (HOOKS, HOOKS / "utils", PLUGIN / "utils"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

PROJECT_ID = "prj_wpc_test"
ORG_ID = "org_wpc_test"

FAKE_CLI = r'''#!/usr/bin/env python3
import json, os, sys
argv = sys.argv[1:]
rec = {"argv": argv}
if "--transcript" in argv:
    try:
        with open(argv[argv.index("--transcript") + 1]) as f:
            rec["trace"] = json.load(f)
    except Exception as e:
        rec["trace_error"] = str(e)
chk = os.environ.get("ACE_FAKE_CHECK_PATH")
if chk:
    rec["check_path_exists"] = os.path.exists(chk)
with open(os.environ["ACE_FAKE_CLI_LOG"], "a") as f:
    f.write(json.dumps(rec) + "\n")
if argv[:1] == ["search"]:
    print(json.dumps({"count": 0, "similar_patterns": []}))
elif argv[:1] == ["learn"]:
    print(json.dumps({"learning_statistics": {"patterns_created": 1}}))
else:
    print("{}")
'''

LEGACY_SCHEMA = """
CREATE TABLE IF NOT EXISTS tool_uses (
    id INTEGER PRIMARY KEY, session_id TEXT NOT NULL, tool_name TEXT NOT NULL,
    tool_input TEXT, tool_response TEXT, tool_use_id TEXT, agent_id TEXT,
    start_ms INTEGER, end_ms INTEGER, duration_ms INTEGER, timestamp TEXT,
    UNIQUE(tool_use_id))
"""


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------

class Box:
    """One isolated world: home, plugin data, project dir, fake ace-cli."""

    def __init__(self, tmp_path):
        self.root = tmp_path
        self.home = tmp_path / "home"
        self.pd = tmp_path / "ace-plugin-data"
        self.xdg = tmp_path / "xdg"
        self.project = tmp_path / "project"
        self.elsewhere = tmp_path / "elsewhere"
        self.bin = tmp_path / "bin"
        self.cli_log = tmp_path / "fake-cli.jsonl"
        for d in (self.home, self.pd, self.xdg / "ace", self.project / ".claude",
                  self.elsewhere, self.bin):
            d.mkdir(parents=True, exist_ok=True)
        (self.xdg / "ace" / "config.json").write_text(json.dumps({"apiToken": "x"}))
        (self.project / ".claude" / "settings.json").write_text(
            json.dumps({"orgId": ORG_ID, "projectId": PROJECT_ID}))
        cli = self.bin / "ace-cli"
        cli.write_text(FAKE_CLI.replace("#!/usr/bin/env python3", "#!" + sys.executable, 1))
        cli.chmod(0o755)
        (self.pd / "python_path").write_text(sys.executable + "\n")

    def env(self, **extra):
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(("ACE_", "CLAUDE_"))}
        env.update(
            HOME=str(self.home),
            CLAUDE_PLUGIN_DATA=str(self.pd),
            CLAUDE_PLUGIN_ROOT=str(hermetic_root()),
            XDG_CONFIG_HOME=str(self.xdg),
            PATH=os.pathsep.join([str(self.bin), os.path.dirname(sys.executable),
                                  os.environ.get("PATH", "")]),
            ACE_FAKE_CLI_LOG=str(self.cli_log),
            ACE_DEBUG_HOOKS="0", ACE_LEARN_INLINE="1",
        )
        env.update({k: str(v) for k, v in extra.items()})
        return env

    # -- state -------------------------------------------------------------
    def session_dir(self, sid):
        return self.pd / "projects" / PROJECT_ID / "sessions" / sid

    def write_state(self, sid, agent="main", **state):
        d = self.session_dir(sid)
        d.mkdir(parents=True, exist_ok=True)
        base = {"pattern_ids": [], "retrieval_id": None, "retrieval_log_ids": {},
                "task_session_id": "tsid-" + sid}
        base.update(state)
        f = d / ("patterns-used-%s.json" % agent)
        f.write_text(json.dumps(base))
        return f

    def seed_tools(self, sid, rows, agent_id=None):
        """Seed accumulator rows with the LEGACY schema at the v8 path
        (sessions/<sid>/tools.db) AND at the 7.1.x path so the red run fails
        for the behavior under test, not for a missing seed."""
        paths = [self.session_dir(sid) / "tools.db",
                 self.pd / "projects" / PROJECT_ID / "ace-tools.db"]
        for p in paths:
            p.parent.mkdir(parents=True, exist_ok=True)
            con = sqlite3.connect(str(p))
            con.execute(LEGACY_SCHEMA)
            for i, (name, tin, tresp) in enumerate(rows):
                con.execute(
                    "INSERT OR IGNORE INTO tool_uses (session_id, tool_name, tool_input,"
                    " tool_response, tool_use_id, agent_id, timestamp)"
                    " VALUES (?,?,?,?,?,?,datetime('now'))",
                    (sid, name, json.dumps(tin), json.dumps(tresp),
                     "toolu_%s_%d" % (sid, i), agent_id))
            con.commit()
            con.close()

    # -- running -----------------------------------------------------------
    def run_shim(self, script, event, cwd=None, args=(), **env_extra):
        stdin = event if isinstance(event, str) else json.dumps(event)
        return subprocess.run(
            ["bash", str(SCRIPTS / script)] + list(args),
            input=stdin, capture_output=True, text=True, timeout=60,
            cwd=str(cwd or self.elsewhere), env=self.env(**env_extra))

    def run_after_task(self, event, cwd=None, **env_extra):
        return subprocess.run(
            [sys.executable, str(AFTER_TASK)],
            input=json.dumps(event), capture_output=True, text=True, timeout=60,
            cwd=str(cwd or self.project), env=self.env(**env_extra))

    def cli_calls(self, verb=None):
        if not self.cli_log.exists():
            return []
        recs = [json.loads(l) for l in self.cli_log.read_text().splitlines() if l.strip()]
        return [r for r in recs if verb is None or r["argv"][:1] == [verb]]

    def stop_event(self, sid, **kw):
        ev = {
            "session_id": sid,
            "transcript_path": str(self.root / "no-such-transcript.jsonl"),
            "cwd": str(self.project),
            "permission_mode": "default",
            "hook_event_name": "Stop",
            "stop_hook_active": False,
            "last_assistant_message": "Implemented the change and ran the tests.",
            "background_tasks": [],
        }
        ev.update(kw)
        return ev

    def agent_transcript(self, agent_id):
        p = self.root / "subagents" / ("agent-%s.jsonl" % agent_id)
        p.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            {"type": "user", "message": {"role": "user", "content": "refactor the parser module"}},
            {"type": "assistant", "message": {"role": "assistant", "content": [
                {"type": "tool_use", "id": "toolu_sa_1", "name": "Edit",
                 "input": {"file_path": str(self.project / "parser.py")}}]}},
            {"type": "user", "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "toolu_sa_1", "content": "ok"}]}},
        ]
        p.write_text("\n".join(json.dumps(l) for l in lines) + "\n")
        return p

    def subagent_event(self, sid, agent_id, agent_type="Explore", **kw):
        ev = {
            "session_id": sid,
            "transcript_path": str(self.root / "no-such-transcript.jsonl"),
            "cwd": str(self.project),
            "permission_mode": "default",
            "hook_event_name": "SubagentStop",
            "stop_hook_active": False,
            "agent_id": agent_id,
            "agent_type": agent_type,
            "agent_transcript_path": str(self.agent_transcript(agent_id)),
            "last_assistant_message": "Refactor done.",
            "background_tasks": [],
            "session_crons": [],
        }
        ev.update(kw)
        return ev

    def relevance_rows(self, event_name):
        f = self.project / ".claude" / "data" / "logs" / "ace-relevance.jsonl"
        if not f.exists():
            return []
        rows = []
        for line in f.read_text().splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("event") == event_name:
                rows.append(r)
        return rows


@pytest.fixture
def box(tmp_path):
    return Box(tmp_path)


WORK = [("Edit", {"file_path": "src/app.py", "old_string": "a", "new_string": "b"},
         {"success": True})]


# ---------------------------------------------------------------------------
# 1. Shims (DESIGN §3.1; code-stop F13, critic T6/T13)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("script,entry", [
    ("ace_stop_wrapper.sh", "ace_after_task.py"),
    ("ace_subagent_stop_wrapper.sh", "ace_after_task.py"),
    ("ace_posttooluse_wrapper.sh", "ace_tool_accumulator.py"),
])
def test_wrapper_is_thin_shim(script, entry):
    """DESIGN §3.1: wrappers become thin shims that exec ONE python entry with
    stdin untouched — no jq, no cat, no mktemp, no `&` backgrounding, no
    ~/.claude/logs files, no argv-passed tool payloads, no `{"async": true}`
    stdout echo (critic V3: not an output field), no --chat transcript copy."""
    src = (SCRIPTS / script).read_text()
    code = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))
    assert "exec " in code and entry in code, "shim must exec %s" % entry
    for banned in ("jq", "mktemp", ".claude/logs", "cat ", "cat)", "iconv",
                   '"async"', "--tool-input", "--tool-response", "ace-chat-",
                   "ace-spawn-log", "LEARN_LOCK", "ACE_REVIEW"):
        assert banned not in code, "%s still contains %r" % (script, banned)
    assert not any(l.rstrip().endswith("&") for l in code.splitlines()), \
        "%s still backgrounds a process with &" % script
    assert len([l for l in code.splitlines() if l.strip()]) <= 12, \
        "%s is not a thin shim" % script


# ---------------------------------------------------------------------------
# 2. Stop runs learning in the (async) hook process itself
# ---------------------------------------------------------------------------

def test_stop_learns_in_hook_process_without_home_logs(box):
    """DESIGN §3 Stop row + §6 WP-C: CC `async: true` replaces the hand-rolled
    `&` subshell; learning finishes before the hook process exits; nothing is
    written to ~/.claude/logs (critic V4/T11: 84,634 leaked ace-background-*
    files). Shim runs from an unrelated cwd (no `cd` in shims)."""
    sid = "sess-sync-learn"
    box.seed_tools(sid, WORK)
    box.write_state(sid, user_prompt="implement the retry policy for the uploader")
    proc = box.run_shim("ace_stop_wrapper.sh", box.stop_event(sid))
    assert proc.returncode == 0, proc.stderr
    assert not (box.home / ".claude" / "logs").exists(), \
        "Stop must not create ~/.claude/logs (ace-background-* leak)"
    learns = box.cli_calls("learn")
    assert len(learns) == 1, "learn must complete inside the hook process: %r" % learns
    out = proc.stdout.strip()
    if out:
        json.loads(out)  # async hook: stdout empty or exactly one JSON object


def test_ace_review_without_time_phrase_still_learns(box):
    """critic T15 / code-stop F2: `ACE_REVIEW: 80` without a time-saved phrase
    made `set -eo pipefail` + grep abort the Stop hook before learning. The
    parse moves to Python (DESIGN §6 WP-C); learning must still happen and the
    review file the statusline reads must still be written."""
    sid = "sess-review"
    box.seed_tools(sid, WORK)
    box.write_state(sid, user_prompt="fix the flaky upload test")
    ev = box.stop_event(sid, last_assistant_message="All green. ACE_REVIEW: 80")
    proc = box.run_shim("ace_stop_wrapper.sh", ev)
    assert proc.returncode == 0, proc.stderr
    assert len(box.cli_calls("learn")) == 1, "ACE_REVIEW message must not abort learning"
    review = box.project / ".claude" / "data" / "logs" / "ace-review-result.json"
    assert review.exists(), "review file must be written into the hook cwd project"
    assert json.loads(review.read_text())["quality_pct"] == 80


@pytest.mark.parametrize("hook", ["Stop", "SubagentStop"])
def test_stop_hook_active_skips_before_any_work(box, hook):
    """DESIGN §3 SubagentStop row + §6 WP-C: `stop_hook_active` handling moves
    from bash into Python — early exit, no learn, no state reaping."""
    sid = "sess-active-" + hook
    box.seed_tools(sid, WORK)
    if hook == "Stop":
        state = box.write_state(sid, user_prompt="implement the retry policy")
        ev = box.stop_event(sid, stop_hook_active=True)
    else:
        state = box.write_state(sid, agent="agent-a1", user_prompt="refactor parser")
        ev = box.subagent_event(sid, "agent-a1", stop_hook_active=True)
    proc = box.run_after_task(ev, ACE_PROJECT_ID=PROJECT_ID, ACE_ORG_ID=ORG_ID)
    assert proc.returncode == 0, proc.stderr
    assert box.cli_calls() == [], "stop_hook_active must exit before any ace-cli call"
    assert state.exists(), "stop_hook_active must not reap the state file"


def test_subagent_stop_empty_agent_type_exits_before_work(box):
    """critic T23 / code-stop F19 / hooks doc (SubagentStop input): CC-internal
    agents (prompt suggestions, /btw) fire SubagentStop with agent_type == "".
    Python must exit before transcript/state/db work and before any CLI call."""
    sid = "sess-btw"
    state = box.write_state(sid, agent="agent-btw", user_prompt="side question")
    ev = box.subagent_event(sid, "agent-btw", agent_type="")
    proc = box.run_after_task(ev, ACE_PROJECT_ID=PROJECT_ID, ACE_ORG_ID=ORG_ID)
    assert proc.returncode == 0, proc.stderr
    assert box.cli_calls() == [], "empty agent_type must not reach ace-cli"
    assert state.exists(), "empty agent_type must exit before touching state"


def test_subagent_stop_writes_no_spawn_log_and_no_event_log(box):
    """code-stop F6/F11, critic T23: the parent_agent_id spawn-log read (10 MB
    file, constant "main") is removed and the ungated SubagentStop event logger
    is gone. Learning still happens for a real subagent via
    agent_transcript_path."""
    assert "ace-spawn-log" not in AFTER_TASK.read_text(), \
        "ace_after_task.py must not read ace-spawn-log.jsonl any more"
    sid = "sess-sub"
    aid = "a1b2c3d4"
    box.write_state(sid, agent=aid, user_prompt="refactor the parser module")
    proc = box.run_shim("ace_subagent_stop_wrapper.sh", box.subagent_event(sid, aid))
    assert proc.returncode == 0, proc.stderr
    logs = box.project / ".claude" / "data" / "logs"
    assert not (logs / "ace-spawn-log.jsonl").exists()
    assert not (logs / "ace-subagentstop.jsonl").exists()
    assert not (box.home / ".claude" / "logs").exists()
    assert len(box.cli_calls("learn")) == 1


def test_after_task_uses_hook_cwd_not_process_cwd(box):
    """DESIGN §3.1: shims do not `cd`; Python must resolve project context
    (.claude/settings.json) from the hook JSON `cwd`."""
    sid = "sess-cwd"
    box.seed_tools(sid, WORK)
    box.write_state(sid, user_prompt="implement the retry policy for the uploader")
    proc = box.run_after_task(box.stop_event(sid), cwd=box.elsewhere)
    assert proc.returncode == 0, proc.stderr
    assert len(box.cli_calls("learn")) == 1, \
        "project context must come from event cwd, not the process cwd"


# ---------------------------------------------------------------------------
# 3. User prompt: state first (C1), bounded transcript tail second (F1/V10)
# ---------------------------------------------------------------------------

def test_user_prompt_comes_from_state(box):
    """DESIGN §5 C1 + §6 WP-C, code-stop F1: the trace task uses the
    `user_prompt` UPS stored in the session state — no transcript read."""
    sid = "sess-prompt"
    box.seed_tools(sid, WORK)
    box.write_state(sid, user_prompt="implement the frobnicator cache eviction")
    proc = box.run_after_task(box.stop_event(sid),
                              ACE_PROJECT_ID=PROJECT_ID, ACE_ORG_ID=ORG_ID)
    assert proc.returncode == 0, proc.stderr
    learns = box.cli_calls("learn")
    assert len(learns) == 1, proc.stdout
    assert "implement the frobnicator cache eviction" in learns[0]["trace"]["task"]


def test_user_prompt_fallback_reads_only_transcript_tail(tmp_path):
    """critic V10 / code-stop F1: the fallback is a bounded reverse read of the
    last 2 MB of the transcript, never a full parse (1.3 GB RSS on 684 MB).
    A prompt that sits more than 2 MB before EOF must NOT be found; one in the
    tail must be."""
    import ace_after_task as at

    filler = json.dumps({"type": "assistant", "message": {
        "role": "assistant", "content": [{"type": "text", "text": "x" * 4000}]}})
    head_prompt = json.dumps({"type": "user", "message": {
        "role": "user", "content": "ancient prompt far before the tail window"}})
    tail_prompt = json.dumps({"type": "user", "message": {
        "role": "user", "content": "recent prompt inside the tail window"}})
    n_fill = (3 * 1024 * 1024) // len(filler) + 1  # ~3 MB

    far = tmp_path / "far.jsonl"
    far.write_text(head_prompt + "\n" + "\n".join([filler] * n_fill) + "\n")
    assert at.get_user_prompt_from_transcript(str(far)) == "No user prompt found", \
        "fallback must not scan beyond the last 2 MB"

    near = tmp_path / "near.jsonl"
    near.write_text("\n".join([filler] * n_fill) + "\n" + tail_prompt + "\n")
    assert at.get_user_prompt_from_transcript(str(near)) == \
        "recent prompt inside the tail window"


MACHINE_PROMPTS = [
    "<task-notification>\n<task-id>abc</task-id><status>completed</status></task-notification>",
    "<agent-message from=\"worker-1\">done with the refactor</agent-message>",
    "<cross-session-message from=\"other\">ping about the deployment</cross-session-message>",
    "[SYSTEM NOTIFICATION] background job finished with status 0",
    "<local-command-stdout>(no content)</local-command-stdout>",
    "<command-name>/model</command-name> switch the model to something else",
    "<bash-input>npm run build --production</bash-input>",
    "<bash-stdout>compiled 42 modules successfully</bash-stdout>",
    "<bash-stderr>warning: deprecated dependency detected</bash-stderr>",
    "<system-reminder>The user opened a file in the IDE.</system-reminder>",
    "\n  <task-notification><task-id>x</task-id></task-notification>",
]


@pytest.mark.parametrize("prompt", MACHINE_PROMPTS)
def test_machine_prompts_are_trivial(prompt):
    """DESIGN §8 addendum (WP-C): is_trivial_task applies WP-B's machine-prompt
    prefix list so Stop/SubagentStop exit before transcript/db work on
    notification turns (critic / docs-subagents §5.1)."""
    import ace_after_task as at
    assert at.is_trivial_task(prompt) is True


# ---------------------------------------------------------------------------
# 4. Crash fixes (critic T16, code-stop F4/F5)
# ---------------------------------------------------------------------------

def test_array_tool_response_is_summarized():
    """critic T16 / code-stop F4: MCP tools return content ARRAYS; the
    dict-only summarizer raised AttributeError and lost the whole learn."""
    import ace_after_task as at
    resp = [{"type": "text", "text": "issue ENG-12: login broken"}]
    out = at.summarize_tool_response("mcp__linear__get_issue", resp)
    assert isinstance(out, str) and len(out) <= 103


def test_detect_commits_handles_accumulator_rows():
    """critic T16 / code-stop F5: detect_commits_in_session unpacked 4-tuples
    but accumulator rows are 8-tuples since v6.5.0 -> ValueError on every call,
    session_commits never reached the server (git_utils.py:278)."""
    from utils.git_utils import detect_commits_in_session
    row = ("Bash", json.dumps({"command": "git commit -m 'fix'"}),
           json.dumps({"stdout": "[main abc1234] fix"}), "toolu_1", None, 1, 2, 1)
    assert detect_commits_in_session([row]) == ["abc1234"]


# ---------------------------------------------------------------------------
# 5. Errors + telemetry + lock
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("script", [
    "ace_stop_wrapper.sh", "ace_subagent_stop_wrapper.sh", "ace_posttooluse_wrapper.sh",
])
def test_hook_errors_go_to_plugin_data_error_log(box, script):
    """DESIGN §4 + §6 WP-C: errors go to <plugin-data>/logs/ace-hook-errors.log
    only; exit 0; nothing under ~/.claude/logs; nothing on stdout that CC would
    reject as invalid JSON."""
    proc = box.run_shim(script, "this is {not json")
    assert proc.returncode == 0, proc.stderr
    err_log = box.pd / "logs" / "ace-hook-errors.log"
    assert err_log.exists() and err_log.stat().st_size > 0, \
        "malformed hook input must be logged to the plugin-data error log"
    assert not (box.home / ".claude" / "logs").exists()
    out = proc.stdout.strip()
    if out:
        json.loads(out)


@pytest.mark.parametrize("pre_lock_age", [None, 30])
def test_stop_telemetry_reports_real_learn_lock(box, pre_lock_age):
    """critic T20 / DESIGN §6 WP-C: hook_stop_telemetry hard-coded
    learn_lock_present=True, age 0. Python now reports whether a learn lock
    for this agent already existed when the hook started (and its real age),
    plus the background_tasks count from the event."""
    sid = "sess-telemetry-%s" % pre_lock_age
    box.seed_tools(sid, WORK)
    box.write_state(sid, user_prompt="implement the retry policy for the uploader")
    if pre_lock_age is not None:
        lock = box.session_dir(sid) / "learn-inflight-main.lock"
        lock.touch()
        old = time.time() - pre_lock_age
        os.utime(str(lock), (old, old))
    ev = box.stop_event(sid, background_tasks=[{"id": "t1"}, {"id": "t2"}])
    proc = box.run_after_task(ev, ACE_PROJECT_ID=PROJECT_ID, ACE_ORG_ID=ORG_ID)
    assert proc.returncode == 0, proc.stderr
    rows = [r for r in box.relevance_rows("hook_stop_telemetry") if r.get("session_id") == sid]
    assert len(rows) == 1, "after_task must emit exactly one hook_stop_telemetry row"
    row = rows[0]
    assert row["hook_type"] == "Stop"
    assert row["background_tasks_count"] == 2
    if pre_lock_age is None:
        assert row["learn_lock_present"] is False
    else:
        assert row["learn_lock_present"] is True
        assert row["learn_lock_age_seconds"] >= pre_lock_age - 5


@pytest.mark.parametrize("hook", ["Stop", "SubagentStop"])
def test_learn_lock_is_per_agent_in_plugin_data(box, hook):
    """code-stop F9 / DESIGN §4 learn-inflight-<agent>.lock: the lock is per
    agent under the session dir (not /tmp per session, which the first
    finishing sibling deleted), held while ace-cli learn runs, removed after."""
    sid = "sess-lock-" + hook
    if hook == "Stop":
        box.seed_tools(sid, WORK)
        box.write_state(sid, user_prompt="implement the retry policy for the uploader")
        ev, agent = box.stop_event(sid), "main"
    else:
        agent = "e5f6a7b8"
        box.write_state(sid, agent=agent, user_prompt="refactor the parser module")
        ev = box.subagent_event(sid, agent)
    lock = box.session_dir(sid) / ("learn-inflight-%s.lock" % agent)
    proc = box.run_after_task(ev, ACE_PROJECT_ID=PROJECT_ID, ACE_ORG_ID=ORG_ID,
                              ACE_FAKE_CHECK_PATH=lock)
    assert proc.returncode == 0, proc.stderr
    learns = box.cli_calls("learn")
    assert len(learns) == 1, proc.stdout
    assert learns[0].get("check_path_exists") is True, \
        "the per-agent learn lock must exist while ace-cli learn runs"
    assert not lock.exists(), "the learn lock must be removed after learning"


def test_eval_request_written_by_python_when_patterns_were_injected(box):
    """DESIGN §6 WP-C (all bash logic moves to Python): the Stop wrapper's
    METRICS block (full re-parse of ace-relevance.jsonl, code-stop F15) is
    replaced by Python writing .claude/data/logs/ace-eval-request.json (read by
    UPS ace_before_task.py) from what it already knows (playbook_used)."""
    sid = "sess-eval"
    box.seed_tools(sid, WORK)
    box.write_state(sid, user_prompt="implement the retry policy for the uploader",
                    pattern_ids=["ctx-abc123", "ctx-def456"])
    proc = box.run_after_task(box.stop_event(sid),
                              ACE_PROJECT_ID=PROJECT_ID, ACE_ORG_ID=ORG_ID)
    assert proc.returncode == 0, proc.stderr
    req = box.project / ".claude" / "data" / "logs" / "ace-eval-request.json"
    assert req.exists(), "after_task must write the eval request when patterns were used"
    data = json.loads(req.read_text())
    assert data["patterns_injected"] >= 1
    assert data["timestamp"].endswith("Z")


def test_eval_request_carries_the_task_eval_stats(box):
    """Item 1: avg_relevance / domains come from the task's search (state eval_stats), not a hardcoded 0."""
    sid = "sess-eval-stats"
    box.seed_tools(sid, WORK)
    box.write_state(sid, user_prompt="implement the retry policy for the uploader",
                    pattern_ids=["ctx-abc123", "ctx-def456"], eval_stats={"avg_relevance": 80, "domains": 2})
    proc = box.run_after_task(box.stop_event(sid), ACE_PROJECT_ID=PROJECT_ID, ACE_ORG_ID=ORG_ID)
    assert proc.returncode == 0, proc.stderr
    data = json.loads((box.project / ".claude" / "data" / "logs" / "ace-eval-request.json").read_text())
    assert (data["avg_relevance"], data["domains"]) == (80, 2)


def _main_transcript(box, entries):
    p = box.root / "main-transcript.jsonl"
    p.write_text("\n".join(json.dumps(e) for e in entries) + "\n")
    return str(p)


def _tool_turn(tuid, name, inp, result="ok"):
    return [{"type": "assistant", "message": {"role": "assistant", "content": [
                {"type": "tool_use", "id": tuid, "name": name, "input": inp}]}},
            {"type": "user", "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": tuid, "content": result}]}}]


def test_stop_adds_tool_calls_the_async_batch_hook_has_not_written_yet(box):
    """Item 8: PostToolBatch is async (no ordering vs Stop), so the last batch can be missing from
    the db at Stop. Stop fills the gap from the main transcript tail (calls after the last user
    prompt): the learn gate and the trajectory see the Bash call; db rows are not duplicated."""
    sid = "sess-race"
    box.seed_tools(sid, [("Read", {"file_path": "src/app.py"}, {"content": "x"})])  # toolu_sess-race_0
    entries = [{"type": "user", "message": {"role": "user", "content": "old task text here please"}}] + \
        _tool_turn("toolu_old", "Write", {"file_path": "old.py"}) + \
        [{"type": "user", "message": {"role": "user", "content": "implement the retry policy for the uploader"}}] + \
        _tool_turn("toolu_sess-race_0", "Read", {"file_path": "src/app.py"}) + \
        _tool_turn("toolu_late", "Bash", {"command": "pytest -q"}, "3 passed")
    box.write_state(sid, user_prompt="implement the retry policy for the uploader")
    proc = box.run_after_task(box.stop_event(sid, transcript_path=_main_transcript(box, entries)),
                              ACE_PROJECT_ID=PROJECT_ID, ACE_ORG_ID=ORG_ID, ACE_LEARN_INLINE="1")
    assert proc.returncode == 0, proc.stderr
    learns = box.cli_calls("learn")
    assert len(learns) == 1, "the Bash call from the transcript makes the task substantial"
    tools = [st.get("action") for st in learns[0]["trace"]["trajectory"]]
    assert tools == ["Read app.py", "Ran: pytest -q"], tools  # db row once, the late Bash added, the older task's Write not


def test_stop_without_a_transcript_keeps_the_db_rows_only(box):
    sid = "sess-race-none"
    box.seed_tools(sid, [("Read", {"file_path": "src/app.py"}, {"content": "x"})])
    box.write_state(sid, user_prompt="implement the retry policy for the uploader")
    proc = box.run_after_task(box.stop_event(sid), ACE_PROJECT_ID=PROJECT_ID, ACE_ORG_ID=ORG_ID, ACE_LEARN_INLINE="1")
    assert proc.returncode == 0, proc.stderr
    assert box.cli_calls("learn") == []


def test_dead_event_logger_is_gone():
    """final review: ace_event_logger.py had no caller and wrote through symlinks; it is deleted."""
    assert not EVENT_LOGGER.exists()


def test_posttooluse_shim_records_event_from_stdin_silently(box):
    """critic V3/T6, DESIGN §3 PostToolUse `--log` row: the accumulator reads
    the event from stdin (not argv), prints nothing (no `{"async": true}`),
    makes zero ace-cli calls, tolerates array-shaped MCP tool_response, and
    stores rows in <plugin-data>/projects/<pid>/sessions/<sid>/tools.db
    (DESIGN §4) — never .claude/data/logs/ace-tools.db in the project."""
    sid = "sess-ptu"
    ev = {
        "session_id": sid, "transcript_path": "/x.jsonl", "cwd": str(box.project),
        "permission_mode": "default", "hook_event_name": "PostToolUse",
        "tool_name": "mcp__linear__get_issue", "tool_input": {"id": "ENG-1"},
        "tool_response": [{"type": "text", "text": "issue body"}],
        "tool_use_id": "toolu_ptu_1", "duration_ms": 12,
    }
    proc = box.run_shim("ace_posttooluse_wrapper.sh", ev, args=["--log"])
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "", "accumulator must print nothing"
    assert box.cli_calls() == []
    assert not (box.project / ".claude" / "data" / "logs" / "ace-tools.db").exists()
    db = box.session_dir(sid) / "tools.db"
    assert db.exists(), "tools.db must live in the plugin-data session dir"
    con = sqlite3.connect(str(db))
    names = [r[0] for r in con.execute(
        "SELECT tool_name FROM tool_uses WHERE session_id=?", (sid,))]
    con.close()
    assert names == ["mcp__linear__get_issue"]


def test_accumulator_sqlite_wal_and_busy_timeout(tmp_path):
    """DESIGN §6 WP-C: sqlite WAL + timeout=5 (concurrent PostToolUse writers
    and the Stop reader no longer fail with 'database is locked')."""
    import ace_tool_accumulator as acc
    con = acc.init_db(tmp_path / "tools.db")
    try:
        assert con.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert con.execute("PRAGMA busy_timeout").fetchone()[0] >= 5000
    finally:
        con.close()


def test_accumulator_versioned_migration(tmp_path, monkeypatch):
    """DESIGN §6 WP-C, critic T6: one versioned migration (PRAGMA user_version)
    instead of 4 failing `ALTER TABLE` statements on every tool call. A legacy
    db is migrated once (gains the C4 columns); a current db runs no ALTER."""
    import ace_tool_accumulator as acc
    db = tmp_path / "tools.db"
    con = sqlite3.connect(str(db))
    con.execute("CREATE TABLE tool_uses (id INTEGER PRIMARY KEY, session_id TEXT NOT NULL,"
                " tool_name TEXT NOT NULL, tool_input TEXT, tool_response TEXT,"
                " tool_use_id TEXT, timestamp TEXT, UNIQUE(tool_use_id))")
    con.commit()
    con.close()

    acc.init_db(db).close()
    con = sqlite3.connect(str(db))
    cols = {r[1] for r in con.execute("PRAGMA table_info(tool_uses)")}
    version = con.execute("PRAGMA user_version").fetchone()[0]
    con.close()
    assert {"agent_id", "start_ms", "end_ms", "duration_ms",
            "success", "error_first_line"} <= cols
    assert version >= 1

    statements = []
    real_connect = sqlite3.connect

    def tracing_connect(*a, **kw):
        c = real_connect(*a, **kw)
        c.set_trace_callback(statements.append)
        return c

    monkeypatch.setattr(acc.sqlite3, "connect", tracing_connect)
    acc.init_db(db).close()
    assert not [s for s in statements if "ALTER TABLE" in s.upper()], statements


def test_record_tool_c4_api(tmp_path, monkeypatch):
    """DESIGN §5 C4: record_tool(session_id, agent_id, tool_name,
    tool_input_summary, tool_response_summary, success, error_first_line);
    a failed row surfaces its error in the learn trajectory built by
    ace_after_task."""
    import ace_tool_accumulator as acc
    import ace_after_task as at
    project = tmp_path / "project"
    (project / ".claude").mkdir(parents=True)
    (project / ".claude" / "settings.json").write_text(
        json.dumps({"orgId": ORG_ID, "projectId": PROJECT_ID}))
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path / "ace-pd"))
    monkeypatch.chdir(project)
    sid = "sess-c4"
    assert acc.record_tool(sid, None, "Edit", json.dumps({"file_path": "a/b.py"}),
                           json.dumps({"success": True}), True, None)
    assert acc.record_tool(session_id=sid, agent_id=None, tool_name="Bash",
                           tool_input_summary=json.dumps({"command": "npm test"}),
                           tool_response_summary="", success=False,
                           error_first_line="Exit code 1")
    assert (tmp_path / "ace-pd" / "projects" / PROJECT_ID / "sessions" / sid / "tools.db").exists()
    trajectory, tools = at.build_trajectory_from_accumulated_tools(sid, str(project))
    assert [s["tool"] for s in trajectory] == ["Edit", "Bash"]
    assert trajectory[0]["action"] == "Edited b.py"
    assert "Exit code 1" in trajectory[1]["result"]


# ---------------------------------------------------------------------------
# 7. Round 2 (WP-H): P-12 relevance rows via the logger, UTC timestamps
# ---------------------------------------------------------------------------

def test_after_task_writes_no_relevance_rows_by_hand():
    """DESIGN §10 P-12: keymap / degenerate / playbook_load rows go through
    ace_relevance_logger (one writer: rotation + UTC), never a hand-rolled open()."""
    src = AFTER_TASK.read_text()
    code = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))
    assert "ace-relevance.jsonl" not in code, \
        "ace_after_task.py still appends to ace-relevance.jsonl directly"


def test_after_task_relevance_rows_go_through_logger(box, monkeypatch, capsys):
    """P-12 behavioral: every row ace_after_task emits passes ACERelevanceLogger._write_log."""
    import io
    import ace_after_task as at
    import ace_relevance_logger as rl
    sid = "sess-p12"
    agent = "p12agent"
    box.seed_tools(sid, WORK, agent_id=agent)
    box.write_state(sid, agent=agent, user_prompt="refactor the parser module")
    for k, v in box.env(ACE_PROJECT_ID=PROJECT_ID, ACE_ORG_ID=ORG_ID).items():
        monkeypatch.setenv(k, v)
    monkeypatch.chdir(box.project)
    monkeypatch.setattr(rl, "_logger", None)
    routed = []
    real = rl.ACERelevanceLogger._write_log

    def spy(self, entry):
        routed.append(entry.get("event"))
        return real(self, entry)

    monkeypatch.setattr(rl.ACERelevanceLogger, "_write_log", spy)
    monkeypatch.setattr(at, "run_learn", lambda *a, **kw: ({}, 1))
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(box.subagent_event(sid, agent))))
    with pytest.raises(SystemExit):
        at.main()
    written = [json.loads(l).get("event") for l in
               (box.project / ".claude" / "data" / "logs" / "ace-relevance.jsonl").read_text().splitlines()]
    for ev in ("subagent_stop_keymap", "playbook_load"):
        assert ev in written, written
        assert ev in routed, "%s row bypassed the relevance logger" % ev


def test_learn_trace_timestamp_is_utc(box):
    """DESIGN §10 accepted loss: 'trace timestamps now UTC' (was naive local isoformat)."""
    sid = "sess-utc"
    box.seed_tools(sid, WORK)
    box.write_state(sid, user_prompt="implement the utc trace timestamp")
    p = box.run_after_task(box.stop_event(sid), ACE_PROJECT_ID=PROJECT_ID, ACE_ORG_ID=ORG_ID)
    assert p.returncode == 0, p.stderr
    ts = box.cli_calls("learn")[0]["trace"]["timestamp"]
    assert ts.endswith("Z") or ts.endswith("+00:00"), ts
