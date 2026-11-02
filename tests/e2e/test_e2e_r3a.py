"""v8.0.0 round 3a RED (hook-level, ACE_E2E=1) — DESIGN §13.2 Python-chain fixes + §13.1 mod marker.

Every case runs the hooks exactly as hooks.json routes them (ace_e2e_harness.routed_hooks /
exec form) in a sandbox (own HOME, CLAUDE_PLUGIN_DATA, TMPDIR, project with .claude/settings.json)
with an r3a fake ace-cli first on PATH: logs argv + the learn trace, logs a `done` record when a
call finishes, sleeps on `learn` (FAKE_LEARN_SLEEP) and on `--version` (FAKE_VERSION_SLEEP).
Evidence: /tmp/ace-v8-dry/m2-chain-vs-chain/REPORT.md F-V1..F-V4; cc_hooks_reference.md:4084-4087
(`claude -p` kills async hooks at teardown -> Stop/SubagentStop become sync, timeout 15).
"""
import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path

import pytest

import ace_e2e_harness as H

pytestmark = pytest.mark.skipif(os.environ.get("ACE_E2E") != "1", reason="e2e target tests: set ACE_E2E=1")

FIXTURES = Path(__file__).resolve().parent / "fixtures"
STORED_QUERY = "audit the payment webhook retry logic for idempotency bugs"
REMINDER = ("<system-reminder>\nCodebase and user instructions are shown below. Be sure to adhere to "
            "these instructions.\n\nContents of /Users/x/.claude/CLAUDE.md:\n# notes\n</system-reminder>")
TRANSCRIPT_PROMPT = "Read the file notes.md, then use Bash to run: echo sub-done > sub_out.txt"

FAKE_CLI = r'''#!%(python)s
import json, os, sys, time
argv = sys.argv[1:]
log = os.environ["ACE_FAKE_CLI_LOG"]
rec = {"argv": argv, "pid": os.getpid()}
if "--transcript" in argv:
    try:
        with open(argv[argv.index("--transcript") + 1]) as f:
            rec["trace"] = json.load(f)
    except Exception as e:
        rec["trace_error"] = str(e)
with open(log, "a") as f:
    f.write(json.dumps(rec) + "\n")
if "--version" in argv:
    time.sleep(float(os.environ.get("FAKE_VERSION_SLEEP", "0")))
    print("4.2.2")
elif argv[:1] == ["learn"]:
    time.sleep(float(os.environ.get("FAKE_LEARN_SLEEP", "0")))
    print(json.dumps({"learning_statistics": {"patterns_created": 1}}))
elif argv[:1] == ["search"]:
    print(json.dumps({"count": 1, "retrieval_id": "r-e2e", "similar_patterns": [
        {"id": "11111111-2222-4333-8444-555555555555", "content": "auth tip", "domain": "auth",
         "section": "strategies_and_hard_rules", "bandit_rank": 1, "cumulative_v15_reward": 1.0,
         "isAtRisk": False, "retrieval_log_id": 7}]}))
else:
    print("{}")
with open(log, "a") as f:
    f.write(json.dumps({"argv": argv, "pid": os.getpid(), "done": True}) + "\n")
'''


class World:
    """One sandboxed CC session (same layout as ace_e2e_harness.run_fixture)."""

    def __init__(self):
        self.root = Path(tempfile.mkdtemp(prefix="ace-e2e-r3a-"))
        self.home, self.data, self.tmpdir, self.proj, self.bin = (
            self.root / d for d in ("home", "ace-plugin-data", "tmp", "proj", "bin"))
        for d in (self.home, self.data, self.tmpdir, self.proj / ".claude", self.proj / "src" / "auth",
                  self.bin, self.root / "xdg-config" / "ace", self.root / "xdg-data"):
            d.mkdir(parents=True)
        tok = uuid.uuid4().hex[:10]
        self.project_id, self.session_id, self.agent_id = "prj_r3a" + tok, "r3a" + tok + "-session", "a" + tok + "c0ffee"
        self.prompt_id = str(uuid.uuid4())
        (self.proj / ".claude" / "settings.json").write_text(
            json.dumps({"projectId": self.project_id, "orgId": "org_r3a"}))
        (self.proj / "src" / "auth" / "login.py").write_text("def login(): pass\n")
        (self.root / "xdg-config" / "ace" / "config.json").write_text(json.dumps({"apiToken": "e2e"}))
        (self.data / "python_path").write_text(sys.executable + "\n")
        cli = self.bin / "ace-cli"
        cli.write_text(FAKE_CLI % {"python": sys.executable})
        cli.chmod(0o755)
        self.cli_log = self.root / "fake-ace-cli.log"
        self.transcript = self.root / "transcript.jsonl"
        self._write(self.transcript, [
            {"type": "user", "message": {"role": "user", "content": "Refactor the auth login flow"}},
            {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "Done."}]}}])
        self.agent_transcript = self.root / "subagents" / ("agent-%s.jsonl" % self.agent_id)
        self.agent_transcript.parent.mkdir()
        self._write(self.agent_transcript, self.subagent_entries())
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(("ACE_", "CLAUDE_"))}
        self.env.update({
            "HOME": str(self.home), "CLAUDE_PLUGIN_DATA": str(self.data), "CLAUDE_PLUGIN_ROOT": str(H.plugin_root()),
            "CLAUDE_PROJECT_DIR": str(self.proj), "XDG_CONFIG_HOME": str(self.root / "xdg-config"),
            "XDG_DATA_HOME": str(self.root / "xdg-data"), "TMPDIR": str(self.tmpdir),
            "ACE_FAKE_CLI_LOG": str(self.cli_log), "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
            "PATH": os.pathsep.join([str(self.bin), os.path.dirname(sys.executable), os.environ.get("PATH", "")]),
            "ACE_LEARN_INLINE": "1",
        })
        self.hooks_json = json.loads((H.plugin_root() / "hooks" / "hooks.json").read_text())

    @staticmethod
    def _write(path, entries):
        path.write_text("\n".join(json.dumps(e) for e in entries) + "\n")

    @staticmethod
    def subagent_entries():
        """Real 2.1.316 subagent transcript shape (m2 runs/S4-v8-1/.../agent-*.jsonl): the prompt,
        then an api-request-blob USER entry starting with the <system-reminder> CLAUDE.md block."""
        return [
            {"type": "user", "message": {"role": "user", "content": TRANSCRIPT_PROMPT}},
            {"type": "api-request-blob", "message": {"role": "user", "content": [
                {"type": "text", "text": REMINDER}, {"type": "text", "text": TRANSCRIPT_PROMPT}]}},
            {"type": "assistant", "message": {"role": "assistant", "content": [
                {"type": "tool_use", "id": "toolu_r3a_sub1", "name": "Bash",
                 "input": {"command": "echo sub-done > sub_out.txt"}}]}},
            {"type": "user", "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "toolu_r3a_sub1",
                 "content": "(Bash completed with no output)", "is_error": False}]}},
        ]

    # ── state ──────────────────────────────────────────────────────────────
    @property
    def session_dir(self):
        return self.data / "projects" / self.project_id / "sessions" / self.session_id

    def marker(self, age_s):
        p = self.session_dir / "mod-active"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("")
        t = time.time() - age_s
        os.utime(str(p), (t, t))
        return p

    def stash_agent_prompt(self, prompt=STORED_QUERY, subagent_type="general-purpose"):
        d = self.session_dir / "agent-prompts"
        d.mkdir(parents=True, exist_ok=True)
        (d / ("%s-%s.json" % (self.prompt_id, subagent_type))).write_text(json.dumps(
            {"prompt": prompt, "subagent_type": subagent_type, "description": "audit"}))

    def write_domains(self):
        f = self.data / "projects" / self.project_id / "domains.json"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({"auth": 5}))

    def tool_rows(self):
        import sqlite3
        db = self.session_dir / "tools.db"
        if not db.exists():
            return []
        con = sqlite3.connect(str(db))
        try:
            return con.execute("SELECT tool_name, tool_use_id, success FROM tool_uses").fetchall()
        except sqlite3.Error:
            return []
        finally:
            con.close()

    def cli_calls(self, verb=None, done=None):
        if not self.cli_log.exists():
            return []
        recs = [json.loads(l) for l in self.cli_log.read_text().splitlines() if l.strip()]
        return [r for r in recs if (verb is None or r["argv"][:1] == [verb] or verb in r["argv"])
                and bool(r.get("done")) == bool(done)]

    # ── events ─────────────────────────────────────────────────────────────
    def event(self, name, **over):
        """A fixture from tests/e2e/fixtures with this world's ids substituted."""
        text = (FIXTURES / (name + ".json")).read_text()
        for k, v in (("__SESSION__", self.session_id), ("__TRANSCRIPT__", str(self.transcript)),
                     ("__CWD__", str(self.proj)), ("__AGENT_TRANSCRIPT__", str(self.agent_transcript)),
                     ("__AGENT__", self.agent_id)):
            text = text.replace(k, v)
        ev = json.loads(text)
        ev.update(over)
        return ev

    def agent_pretooluse(self, prompt=STORED_QUERY, subagent_type="general-purpose"):
        return {"session_id": self.session_id, "transcript_path": str(self.transcript), "cwd": str(self.proj),
                "permission_mode": "default", "hook_event_name": "PreToolUse", "prompt_id": self.prompt_id,
                "tool_name": "Agent", "tool_use_id": "toolu_r3a_agent",
                "tool_input": {"prompt": prompt, "description": "audit", "subagent_type": subagent_type}}

    def argv_of(self, hook):
        root = str(H.plugin_root())
        sub = lambda s: s.replace("${CLAUDE_PLUGIN_ROOT}", root).replace(
            "${CLAUDE_PLUGIN_DATA}", str(self.data)).replace("${CLAUDE_PROJECT_DIR}", str(self.proj))
        if hook.get("args") is not None:
            return [sub(hook["command"])] + [sub(a) for a in hook["args"]]
        return ["sh", "-c", sub(hook["command"])]

    def hooks_for(self, ev):
        hooks = H.routed_hooks(self.hooks_json, ev["hook_event_name"], ev)
        assert hooks, "hooks.json routes nothing for %s" % ev["hook_event_name"]
        return hooks

    def run(self, ev, **env):
        """Run every routed hook for `ev`; returns [(hook, rc, stdout, stderr, wall_s)]."""
        e = dict(self.env)
        e.update({k: str(v) for k, v in env.items()})
        for k in [k for k, v in env.items() if v is None]:
            e.pop(k, None)
        out = []
        for hook in self.hooks_for(ev):
            rc, so, se, wall, _bg = H._run_hook(self.argv_of(hook), json.dumps(ev), str(self.proj), e)
            out.append((hook, rc, so, se, wall))
        return out


@pytest.fixture
def w():
    world = World()
    yield world
    import shutil
    shutil.rmtree(str(world.root), ignore_errors=True)


def _wait(pred, secs):
    end = time.monotonic() + secs
    while time.monotonic() < end:
        if pred():
            return True
        time.sleep(0.05)
    return pred()


def _seed_work(w):
    """Substantial work in the accumulator via the real PostToolBatch hook (Write + Bash)."""
    for _h, rc, _o, se, _t in w.run(w.event("PostToolBatch")):
        assert rc == 0, se


# ── §13.2 hooks.json: Stop / SubagentStop sync, timeout 15 ───────────────────────────────

@pytest.mark.parametrize("event", ["Stop", "SubagentStop"])
def test_stop_hooks_are_sync_timeout_15(event):
    hooks = json.loads((H.plugin_root() / "hooks" / "hooks.json").read_text())["hooks"][event]
    (h,) = [h for g in hooks for h in g["hooks"]]
    assert not h.get("async"), "%s must be sync (async hooks die at claude -p teardown, doc :4084-4087)" % event
    assert h.get("timeout") == 15, h


# ── §13.2 sync Stop: < 0.5 s, silent, learn survives the killed parent ───────────────────

@pytest.mark.parametrize("sig", ["SIGKILL", "SIGHUP"])
def test_sync_stop_fast_silent_and_detached_learn_survives_killed_parent(w, sig):
    _seed_work(w)
    ev = w.event("Stop")
    (hook,) = w.hooks_for(ev)
    env = dict(w.env)
    env.pop("ACE_LEARN_INLINE", None)  # production path: detached learn
    env["FAKE_LEARN_SLEEP"] = "2"
    result = w.root / "parent-result.json"
    # The "claude -p" parent: runs the sync hook, records it, then SIGKILLs its whole process group
    # (teardown). Only a properly detached (new session) learner survives.
    runner = (
        "import json, os, signal, subprocess, sys, time\n"
        "signal.signal(signal.SIGHUP, signal.SIG_DFL)\n"  # nohup'd pytest hands down SIG_IGN: not a product bug
        "argv, raw, cwd, out = json.loads(sys.argv[1]), sys.argv[2], sys.argv[3], sys.argv[4]\n"
        "t0 = time.monotonic()\n"
        "p = subprocess.run(argv, input=raw, capture_output=True, text=True, cwd=cwd, timeout=15)\n"
        "open(out, 'w').write(json.dumps({'rc': p.returncode, 'stdout': p.stdout, 'stderr': p.stderr,"
        " 'wall': time.monotonic() - t0}))\n"
        "os.killpg(0, signal.%s)\n" % sig)
    parent = subprocess.Popen([sys.executable, "-c", runner, json.dumps(w.argv_of(hook)), json.dumps(ev),
                               str(w.proj), str(result)], env=env, start_new_session=True,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    parent.wait(timeout=30)
    assert parent.returncode == -getattr(signal, sig), "parent did not reach its teardown kill"
    r = json.loads(result.read_text())
    assert r["rc"] == 0, r["stderr"][-500:]
    assert r["stdout"] == "", "sync Stop must print nothing: %r" % r["stdout"][:300]
    budget = float(os.environ.get("ACE_E2E_STOP_BUDGET_S", "2.0"))  # the point: not the 2 s learn; CI runners are slow
    assert r["wall"] < budget, "sync Stop must return before the learn finishes (%.1f s): %.2f s" % (budget, r["wall"])
    assert _wait(lambda: w.cli_calls("learn", done=True), 6), \
        "detached learn did not complete after the parent was killed; calls=%s" % w.cli_calls()
    assert _wait(lambda: not list(w.session_dir.glob("learn-inflight-*.lock")), 3), "learn lock not released"


# ── §13.2 learn argv carries --no-stream ─────────────────────────────────────────────────

def test_stop_learn_argv_has_no_stream(w):
    _seed_work(w)
    for _h, rc, _o, se, _t in w.run(w.event("Stop")):
        assert rc == 0, se
    learns = w.cli_calls("learn")
    assert len(learns) == 1, w.cli_calls()
    assert "--no-stream" in learns[0]["argv"], learns[0]["argv"]


# ── §13.2 SubagentStop: <system-reminder> first user entry -> stored SubagentStart query ───

def test_subagent_stop_learns_with_stored_subagentstart_query(w):
    """m2 F-V3 (0/3 subagent learns): the subagent transcript's user entry is the injected
    <system-reminder> CLAUDE.md block -> trivial skip. Real chain: PreToolUse Agent stash ->
    SubagentStart (stores the query) -> SubagentStop learns with THAT query."""
    for ev in (w.agent_pretooluse(),
               w.event("SubagentStart", prompt_id=w.prompt_id, agent_type="general-purpose")):
        for _h, rc, _o, se, _t in w.run(ev):
            assert rc == 0, se
    stop = w.event("SubagentStop", prompt_id=w.prompt_id, agent_type="general-purpose")
    for _h, rc, so, se, _t in w.run(stop):
        assert rc == 0, se
        assert so == ""
    learns = w.cli_calls("learn")
    assert len(learns) == 1, "subagent learn skipped; calls=%s" % w.cli_calls()
    assert learns[0]["trace"]["task"] == "User request: " + STORED_QUERY


# ── §13.2 PostToolBatch Write/Edit recorded as success ───────────────────────────────────

def test_posttoolbatch_write_edit_recorded_success(w):
    calls = [
        {"tool_name": "Write", "tool_input": {"file_path": str(w.proj / "hello_ace.py"), "content": "x"},
         "tool_use_id": "toolu_r3a_w", "tool_response": "File created successfully at: %s/hello_ace.py" % w.proj},
        {"tool_name": "Edit", "tool_input": {"file_path": str(w.proj / "hello_ace.py"),
                                             "old_string": "x", "new_string": "y"},
         "tool_use_id": "toolu_r3a_e", "tool_response": [{"type": "text",
                                                          "text": "The file %s/hello_ace.py has been updated." % w.proj}]},
    ]
    for _h, rc, so, se, _t in w.run(w.event("PostToolBatch", tool_calls=calls)):
        assert rc == 0 and so == "", se
    assert sorted(w.tool_rows()) == [("Edit", "toolu_r3a_e", 1), ("Write", "toolu_r3a_w", 1)]
    for _h, rc, _o, se, _t in w.run(w.event("Stop")):
        assert rc == 0, se
    (learn,) = w.cli_calls("learn")
    steps = {s["tool"]: s["result"] for s in learn["trace"]["trajectory"]}
    assert steps == {"Write": "Success", "Edit": "Success"}, steps


# ── §13.2 SessionStart: hanging `ace-cli --version` never disables ACE ───────────────────

def test_sessionstart_hanging_version_probe_does_not_disable(w):
    """m2 F-V1: cold probe > 15 s -> v0.0.0 -> disabled.flag + 'Outdated CLI' -> session without ACE."""
    ev = w.event("SessionStart_startup")
    runs = w.run(ev, FAKE_VERSION_SLEEP=20)
    for h, rc, so, se, wall in runs:
        assert rc == 0, se
        assert wall < (h.get("timeout") or 30) - 2, "hook must finish inside its own timeout: %.1f s" % wall
        assert "Outdated" not in so and "DISABLED" not in so, so
    assert list(w.data.rglob("disabled.flag")) == [], "an unknown version must never write disabled.flag"
    logged = "".join(p.read_text(errors="replace") for p in w.data.rglob("*")
                     if p.is_file() and p.suffix in (".log", ".jsonl", ".json", ""))
    logged += "".join(p.read_text(errors="replace") for p in (w.proj / ".claude").rglob("*.jsonl"))
    assert "version_unknown" in logged, "unknown version must be logged as version_unknown"


# ── §13.1 coexistence: fresh mod-active marker -> covered hooks exit silent, no spawn ─────

def _covered_case(w, name):
    """(event, prepare) for each Python hook the mod covers. `prepare` makes the hook have real
    work to do (so a no-op proves the marker check, not a missing input)."""
    if name == "UserPromptSubmit":
        return w.event("UserPromptSubmit_human", prompt_id=w.prompt_id), lambda: None
    if name == "PreToolUse_Agent":
        return w.agent_pretooluse(), lambda: None
    if name == "SubagentStart":
        return (w.event("SubagentStart", prompt_id=w.prompt_id, agent_type="general-purpose"),
                w.stash_agent_prompt)
    if name == "DomainShift":
        return w.event("PostToolUse_Read"), w.write_domains
    if name == "PostToolBatch":
        return w.event("PostToolBatch"), lambda: None
    if name == "PostToolUseFailure":
        return w.event("PostToolUseFailure_Bash"), lambda: None
    if name == "Stop":
        return w.event("Stop"), lambda: _seed_work(w)
    if name == "SubagentStop":  # plain prompt transcript: learns today, independent of the F-V3 fix
        return w.event("SubagentStop"), lambda: w._write(w.agent_transcript, [
            {"type": "user", "message": {"role": "user", "content": "Refactor the auth login flow"}}]
            + w.subagent_entries()[2:])
    raise KeyError(name)


COVERED = ["UserPromptSubmit", "PreToolUse_Agent", "SubagentStart", "DomainShift", "PostToolBatch",
           "PostToolUseFailure", "Stop", "SubagentStop"]


def _side_effects(w):
    stash = sorted(p.name for p in (w.session_dir / "agent-prompts").glob("*")) \
        if (w.session_dir / "agent-prompts").is_dir() else []
    return {"cli": len(w.cli_calls()), "rows": len(w.tool_rows()), "stash": stash,
            "state": sorted(p.name for p in w.session_dir.glob("patterns-used-*.json"))}


@pytest.mark.parametrize("name", COVERED)
def test_fresh_mod_marker_covered_hook_is_silent_noop(w, name):
    ev, prepare = _covered_case(w, name)
    prepare()
    w.marker(age_s=30)
    before = _side_effects(w)
    for h, rc, so, se, _t in w.run(ev):
        assert rc == 0, se
        assert so == "", "%s must print nothing while the mod is active: %r" % (name, so[:300])
    after = _side_effects(w)
    assert after["cli"] == before["cli"], "%s spawned ace-cli while the mod is active: %s" % (name, w.cli_calls())
    assert after == before, "%s did work while the mod is active: %s -> %s" % (name, before, after)


@pytest.mark.parametrize("name", COVERED)
def test_stale_mod_marker_covered_hook_runs_normally(w, name):
    ev, prepare = _covered_case(w, name)
    prepare()
    w.marker(age_s=11 * 60)
    before = _side_effects(w)
    for h, rc, so, se, _t in w.run(ev):
        assert rc == 0, se
    after = _side_effects(w)
    assert after != before, "%s did nothing with a stale (> 10 min) marker: %s" % (name, after)


# ── §13.2 domain-shift parallel double-inject (fixed in 1eb0d7e; m2 S3 scenario) ──────────

def test_parallel_reads_same_domain_inject_once(w):
    """m2 S3: two Reads in one API message -> two concurrent PostToolUse hooks; exactly one may
    search + inject for the domain."""
    w.write_domains()
    evs = [w.event("PostToolUse_Read", tool_use_id="toolu_par_%d" % i,
                   tool_input={"file_path": str(w.proj / "src" / "auth" / ("f%d.py" % i))}) for i in (1, 2)]
    results = [None, None]

    def go(i):
        results[i] = w.run(evs[i])
    ts = [threading.Thread(target=go, args=(i,)) for i in (0, 1)]
    for t in ts:
        t.start()
    for t in ts:
        t.join(60)
    outs = [so for r in results for (_h, rc, so, _se, _t) in r if so.strip()]
    assert len(w.cli_calls("search")) == 1, w.cli_calls()
    assert len(outs) == 1, outs


# ── review fix: parallel same-type siblings must not learn with a sibling's guessed query ──

def test_sibling_fanout_uses_own_transcript_not_parent_scan_guess(w):
    a = "Agent A: audit src/auth/login.py for SQL injection"
    b = "Agent B: write release notes for the billing module"
    w._write(w.transcript, [
        {"type": "user", "message": {"role": "user", "content": "Refactor the auth login flow"}},
        {"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": "t1", "name": "Agent", "input": {"subagent_type": "general-purpose", "prompt": a}},
            {"type": "tool_use", "id": "t2", "name": "Agent", "input": {"subagent_type": "general-purpose", "prompt": b}}]}}])
    ents = w.subagent_entries()
    ents[0]["message"]["content"] = b
    ents[1]["message"]["content"][1]["text"] = b
    w._write(w.agent_transcript, ents)
    for p in (a, b):  # same prompt_id + type -> stash tombstoned ambiguous
        for _h, rc, _o, se, _t in w.run(w.agent_pretooluse(prompt=p)):
            assert rc == 0, se
    for ev in ("SubagentStart", "SubagentStop"):
        for _h, rc, _o, se, _t in w.run(w.event(ev, prompt_id=w.prompt_id, agent_type="general-purpose")):
            assert rc == 0, se
    assert w.cli_calls("learn")[0]["trace"]["task"] == "User request: " + b
