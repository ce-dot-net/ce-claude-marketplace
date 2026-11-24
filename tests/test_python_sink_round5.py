"""Round 5, Python side.
C5: ACE_TRACE_SINK=file:<dir> also holds for the Python chain (ace_cli.run_learn / learn_once, the shared bottleneck of
ace_after_task and ace_permission_denied): the body the engine would POST lands in <dir>/ace-trace-<key>.json, 0 subprocess
sends, no queue, invalid = fail closed, one text-free trace_sinked row. The permission-denied trace carries chain='python'.
F9: an existing sink dir keeps its mode; a missing one is created 0700.
Kill switch: the server's full_steps:false (search response) turns the Python chain back to the 8.3.0 text caps, like
ACE_TRACE_FULL_STEPS=0/false/off/no; missing / broken / stale file keeps full steps on; a server true never beats the env."""
import importlib
import json
import os
import stat
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "plugins" / "ace" / "shared-hooks" / "utils"))
sys.path.insert(0, str(REPO / "plugins" / "ace" / "shared-hooks"))

TRACE = {"task": "User request: fix it", "trajectory": [{"step": 1, "action": "a", "result": "r"}, {"step": 2, "action": "b", "result": "r"}],
         "result": {"success": True}, "conversation_id": "conv-1", "chain": "python"}


@pytest.fixture
def cli(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path / "ace-pd"))
    for k in [k for k in os.environ if k.startswith("ACE_")]:
        monkeypatch.delenv(k, raising=False)
    import ace_cli
    import ace_relevance_logger
    ace_relevance_logger._logger = None
    mod = importlib.reload(ace_cli)
    calls = []
    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: calls.append(a) or (_ for _ in ()).throw(AssertionError("spawned")))
    monkeypatch.setattr(mod.subprocess, "Popen", lambda *a, **k: calls.append(a) or (_ for _ in ()).throw(AssertionError("spawned")))
    mod._calls = calls
    return mod


def _rows(tmp_path, ev):
    f = tmp_path / ".claude" / "data" / "logs" / "ace-relevance.jsonl"
    return [r for r in (json.loads(l) for l in f.read_text().splitlines() if l.strip()) if r.get("event") == ev] if f.exists() else []


def test_c5_run_learn_sinks_the_body_and_sends_nothing(cli, tmp_path, monkeypatch):
    sink = tmp_path / "sink"
    monkeypatch.setenv("ACE_TRACE_SINK", "file:%s/" % sink)
    res, _ms = cli.run_learn(dict(TRACE), retrieval_id="rid-1", applied_log_ids=list(range(25)), hook_event_name="Stop")
    assert res is None and cli._calls == []                                  # 0 subprocess sends (no engine, no ace-cli, no replay)
    (f,) = list(sink.iterdir())
    assert f.name.startswith("ace-trace-") and f.name.endswith(".json")
    body = json.loads(f.read_text())
    # the POST body as engine/learn.js builds it: retrieval_id + applied_log_ids (cap 20) merged into the trace
    assert (body["task"], body["retrieval_id"], body["applied_log_ids"], body["chain"]) == ("User request: fix it", "rid-1", list(range(20)), "python")
    assert stat.S_IMODE(f.stat().st_mode) == 0o600 and stat.S_IMODE(sink.stat().st_mode) == 0o700
    (row,) = _rows(tmp_path, "trace_sinked")
    assert row["path"] == str(f) and row["bytes"] == len(f.read_bytes()) and row["steps"] == 2 and row["source"] == "python"
    assert row["error"] is None and "fix it" not in json.dumps(row)
    assert not (tmp_path / "ace-pd" / "trace-queue").exists() or not any((tmp_path / "ace-pd" / "trace-queue").glob("*.json"))


def test_c5_no_applied_ids_is_an_empty_list(cli, tmp_path, monkeypatch):
    monkeypatch.setenv("ACE_TRACE_SINK", "file:%s" % (tmp_path / "s"))
    cli.run_learn(dict(TRACE))
    (f,) = list((tmp_path / "s").iterdir())
    body = json.loads(f.read_text())
    assert body["applied_log_ids"] == [] and "retrieval_id" not in body


@pytest.mark.parametrize("bad", ["http://evil", "file:relative/dir", "file:", "/abs/without/scheme"])
def test_c5_invalid_sink_fails_closed(cli, tmp_path, monkeypatch, bad):
    monkeypatch.setenv("ACE_TRACE_SINK", bad)
    res, _ = cli.run_learn(dict(TRACE))
    assert res is None and cli._calls == []
    (row,) = _rows(tmp_path, "trace_sinked")
    assert (row["error"], row["path"]) == ("invalid_sink", None)


def test_c5_learn_once_never_sends_with_a_sink(cli, tmp_path, monkeypatch):
    monkeypatch.setenv("ACE_TRACE_SINK", "file:%s" % (tmp_path / "s"))
    code, out, keyed = cli.learn_once(dict(TRACE), idempotency_key="k1")
    assert cli._calls == [] and code is None and "sink" in out and keyed is False


def test_c5_queue_replay_is_a_no_op_with_a_sink(monkeypatch, tmp_path):
    import ace_trace_queue
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path / "ace-pd"))
    called = []
    monkeypatch.setattr(ace_trace_queue, "replay", lambda *a, **k: called.append(a) or [])
    monkeypatch.setenv("ACE_TRACE_SINK", "file:%s" % (tmp_path / "s"))
    ace_trace_queue._main(["--replay"])
    assert called == []
    monkeypatch.delenv("ACE_TRACE_SINK")
    ace_trace_queue._main(["--replay"])
    assert len(called) == 1                                                  # control: without a sink the replay runs


def test_f9_existing_sink_dir_keeps_its_mode(cli, tmp_path, monkeypatch):
    sink = tmp_path / "shared"
    sink.mkdir(mode=0o755)
    os.chmod(sink, 0o755)
    monkeypatch.setenv("ACE_TRACE_SINK", "file:%s" % sink)
    cli.run_learn(dict(TRACE))
    assert stat.S_IMODE(sink.stat().st_mode) == 0o755
    (f,) = list(sink.iterdir())
    assert stat.S_IMODE(f.stat().st_mode) == 0o600


def test_c5_without_sink_the_send_runs(cli, tmp_path):
    called = []
    cli._learn = lambda trace, **kw: called.append(kw) or ({"ok": 1}, 1, 0, "", True)
    import ace_trace_queue
    ace_trace_queue.spawn_replay = lambda **k: None
    res, _ = cli.run_learn(dict(TRACE))
    assert res == {"ok": 1} and len(called) == 1 and _rows(tmp_path, "trace_sinked") == []


def test_c5_after_task_with_sink_spawns_no_learn(tmp_path):
    from test_stop_v8 import ORG_ID, PROJECT_ID, WORK, Box
    box = Box(tmp_path)
    sid = "s-sink"
    box.write_state(sid, "main", task_session_id="own", user_prompt="refactor the parser module")
    box.seed_tools(sid, WORK)
    sink = tmp_path / "sink"
    p = box.run_after_task(box.stop_event(sid), ACE_PROJECT_ID=PROJECT_ID, ACE_ORG_ID=ORG_ID, ACE_TRACE_SINK="file:%s" % sink)
    assert p.returncode == 0, p.stderr
    assert box.cli_calls("learn") == []
    (f,) = list(sink.iterdir())
    assert json.loads(f.read_text())["chain"] == "python"
    assert [r["source"] for r in box.relevance_rows("trace_sinked")] == ["python"]


def test_c5_permission_denied_trace_has_chain_python():
    import ace_permission_denied as m
    assert m._build_trace({"session_id": "c", "tool_name": "Bash", "tool_input": {"command": "x"}})["chain"] == "python"


# ---- server kill switch full_steps (Python side) ----

@pytest.fixture
def pdd(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path / "ace-pd"))  # an ace-* dir, else plugin_data_dir falls back to the real one
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ACE_TRACE_FULL_STEPS", raising=False)
    import plugin_data_dir
    import ace_relevance_logger
    ace_relevance_logger._logger = None
    return importlib.reload(plugin_data_dir)


def test_kill_switch_stored_from_a_search_response(pdd):
    assert pdd.stored_full_steps() is True                                  # no file: on
    pdd.store_server_switches({"full_steps": False})
    assert pdd.stored_full_steps() is False
    pdd.store_server_switches({})                                           # missing field keeps the stored value
    assert pdd.stored_full_steps() is False
    pdd.store_server_switches({"full_steps": True})
    assert pdd.stored_full_steps() is True


@pytest.mark.parametrize("bad", ["false", 0, None, "off", [False]])
def test_kill_switch_invalid_value_keeps_it_on_and_logs(pdd, tmp_path, bad):
    pdd.store_server_switches({"full_steps": bad})
    assert pdd.stored_full_steps() is True
    rows = _rows(tmp_path, "full_steps_invalid")
    assert len(rows) == 1 and "value" not in rows[0]


_FILES = {"broken": lambda: "{broken", "no_at": lambda: json.dumps({"on": False}),
          "stale": lambda: json.dumps({"on": False, "at": time.time() - 8 * 86400}), "non_bool": lambda: json.dumps({"on": "no", "at": time.time()})}


@pytest.mark.parametrize("label", sorted(_FILES))
def test_kill_switch_broken_or_stale_file_keeps_it_on(pdd, label):
    text = _FILES[label]()
    pdd.full_steps_file().parent.mkdir(parents=True, exist_ok=True)
    pdd.full_steps_file().write_text(text)
    assert pdd.stored_full_steps() is True


@pytest.mark.parametrize("env,server,want", [(None, None, True), (None, False, False), ("0", True, False), ("OFF", None, False),
                                             ("no", True, False), ("1", False, False), ("yes", True, True)])
def test_kill_switch_env_always_wins_for_off(pdd, monkeypatch, env, server, want):
    import ace_after_task
    if env is not None:
        monkeypatch.setenv("ACE_TRACE_FULL_STEPS", env)
    if server is not None:
        pdd.store_server_switches({"full_steps": server})
    assert ace_after_task.full_steps_on() is want


def _run_box(tmp_path, last, **env):
    from test_stop_v8 import ORG_ID, PROJECT_ID, WORK, Box
    box = Box(tmp_path)
    sid = "s-ks"
    box.write_state(sid, "main", task_session_id="own", user_prompt="refactor " + "p" * 5000)
    box.seed_tools(sid, WORK)
    p = box.run_after_task(box.stop_event(sid, last_assistant_message=last), ACE_PROJECT_ID=PROJECT_ID, ACE_ORG_ID=ORG_ID, **env)
    assert p.returncode == 0, p.stderr
    (learn,) = box.cli_calls("learn")
    return box, learn["trace"]


def test_kill_switch_server_off_brings_back_the_8_3_0_caps(tmp_path):
    pd = tmp_path / "ace-plugin-data"
    pd.mkdir(parents=True, exist_ok=True)
    (pd / "full-steps.json").write_text(json.dumps({"on": False, "at": time.time()}))
    _box, t = _run_box(tmp_path, "s" * 5000)
    assert len(t["task"]) == len("User request: ") + 2000 and len(t["result"]["summary"]) == 2000


def test_kill_switch_env_off_brings_back_the_8_3_0_caps(tmp_path):
    _box, t = _run_box(tmp_path, "s" * 5000, ACE_TRACE_FULL_STEPS="false")
    assert len(t["task"]) == len("User request: ") + 2000 and len(t["result"]["summary"]) == 2000


def test_kill_switch_default_keeps_full_text(tmp_path):
    _box, t = _run_box(tmp_path, "s" * 5000)
    assert len(t["result"]["summary"]) == 5000 and len(t["task"]) > 5000


# ---- F9 on the mod side: SINK_WRITE_SH (plugins/ace/mod/lib/sh.ts) on a real filesystem ----
def _sh(name):
    import re
    src = (REPO / "plugins/ace/mod/lib/sh.ts").read_text()
    block = src.split("export const %s = " % name, 1)[1].split("\n", 1)[0]
    return "".join(re.findall(r"'((?:[^'\\]|\\.)*)'", block))


def test_f9_mod_sink_write_keeps_an_existing_dir_mode_and_creates_a_missing_one_0700(tmp_path):
    import subprocess
    have = tmp_path / "have"
    have.mkdir()
    os.chmod(have, 0o755)
    for d in (have, tmp_path / "new" / "deep"):
        p = subprocess.run(["/bin/sh", "-c", _sh("SINK_WRITE_SH"), "sh", str(d / "ace-trace-k.json")], input="{}", text=True)
        assert p.returncode == 0 and (d / "ace-trace-k.json").read_text() == "{}"
        assert stat.S_IMODE((d / "ace-trace-k.json").stat().st_mode) == 0o600
        assert [x.name for x in d.iterdir()] == ["ace-trace-k.json"]  # atomic: no temp file left
    assert stat.S_IMODE(have.stat().st_mode) == 0o755
    assert stat.S_IMODE((tmp_path / "new" / "deep").stat().st_mode) == 0o700


# ---- F14 (Python): the user prompt is redacted when written to the task state ----
def test_f14_state_user_prompt_is_redacted_on_write(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path / "ace-pd"))
    import patterns_used_state as pus
    importlib.reload(pus)
    key = "AKIA" + "Q" * 16
    pus.append_patterns_used("s1", None, [], project_id="prj_x", user_prompt="deploy with %s now" % key, hook_event_name="UserPromptSubmit", reset=True)
    st = pus.load_state("s1", None, "Stop", project_id="prj_x")
    assert key not in st["user_prompt"] and "[redacted" in st["user_prompt"]


def test_f14_redact_is_idempotent_on_the_shared_fixture():
    import ace_after_task as a
    from test_secret_filter_py import NORMAL, SECRETS
    for text in [t for _, t, _ in SECRETS] + NORMAL:
        once = a.redact(text)
        assert a.redact(once) == once


def test_kill_switch_engine_passes_full_steps_through(tmp_path, monkeypatch):
    """engine/search.js captures full_steps from the raw /patterns/search body (like feedback_downvote / client_policy)."""
    import subprocess
    import engine_harness as E
    if E.node_bin() is None:
        pytest.skip("node not installed")
    monkeypatch.setenv("ACE_FAKE_CORE_MODE", "raw_old")
    monkeypatch.setenv("ACE_FAKE_CORE_LOG", str(tmp_path / "core.log"))
    bin_dir = E.make_prefix(tmp_path)
    p = subprocess.run([E.node_bin(), str(E.ENGINE / "search.js")], input=json.dumps({"query": "q", "org": "o", "project": "p"}),
                       capture_output=True, text=True, timeout=60, env=dict(os.environ, PATH=E.path_with(bin_dir)))
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout.strip().splitlines()[-1])["full_steps"] is False


# ---- round 6 blocker 1: the permission-denied trace sends nothing of the call or of the deny text ----
@pytest.mark.parametrize("cmd", ["API_KEY=sk_CANARY77 ./deploy --prod", "SECRET=CANARY77 curl x", "curl -H 'Authorization: Bearer CANARY77' x"])
def test_r6_denied_bash_fingerprint_and_reason_carry_no_canary(cmd):
    import ace_permission_denied as m
    t = m._build_trace({"session_id": "c", "tool_name": "Bash", "tool_input": {"command": cmd},
                        "reason": "hook said no: %s REASONZ9" % cmd})
    s = json.dumps(t)
    assert "CANARY77" not in s and "REASONZ9" not in s and "hook said" not in s
    assert t["trajectory"][0]["result"] == "denied" and t["result"]["output"] == "denied"


def test_r6_denied_bash_keeps_a_visible_family():
    import ace_permission_denied as m
    fp = lambda c: m._build_trace({"session_id": "c", "tool_name": "Bash", "tool_input": {"command": c}})["trajectory"][0]["action"]
    assert fp("git push --force origin main") == "Attempt Bash (verb='git push')"
    assert fp("API_KEY=x9 ./deploy --prod") == "Attempt Bash (verb='unknown')"   # an env prefix swallows the line: nothing shown


# ---- round 6 item 6: the queue replay respects the opt-out / kill switch; the SessionStart sweep queues nothing with a sink ----
def _replay_send(monkeypatch, tmp_path):
    import ace_trace_queue, ace_cli
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path / "ace-pd"))  # plugin_data_dir honours only an ace-* dir
    got, sent = [], []
    monkeypatch.setattr(ace_trace_queue, "replay", lambda qdir, send, *a, **k: got.append(send) or [])
    monkeypatch.setattr(ace_cli, "learn_once", lambda trace, **k: sent.append(trace) or (0, "", True))
    ace_trace_queue._main(["--replay"])
    entry = {"trace": {"task": "t", "trajectory": [{"step": 1, "action": "a", "result": "r", "tool_input": {"command": "x"}, "tool_response": "y"}]},
             "meta": {}, "key": "k"}
    got[0](entry)
    return sent[0]


def test_r6_replay_strips_full_fields_when_full_steps_are_off(monkeypatch, tmp_path):
    monkeypatch.setenv("ACE_TRACE_FULL_STEPS", "off")
    st = _replay_send(monkeypatch, tmp_path)["trajectory"][0]
    assert "tool_input" not in st and "tool_response" not in st and st["action"] == "a"


def test_r6_replay_keeps_full_fields_by_default(monkeypatch, tmp_path):
    monkeypatch.delenv("ACE_TRACE_FULL_STEPS", raising=False)
    assert "tool_input" in _replay_send(monkeypatch, tmp_path)["trajectory"][0]


def test_r6_replay_strips_on_the_server_kill_switch(monkeypatch, tmp_path):
    monkeypatch.delenv("ACE_TRACE_FULL_STEPS", raising=False)
    (tmp_path / "ace-pd").mkdir()
    (tmp_path / "ace-pd" / "full-steps.json").write_text(json.dumps({"on": False, "at": time.time()}))
    assert "tool_input" not in _replay_send(monkeypatch, tmp_path)["trajectory"][0]


def test_r6_sweep_queues_nothing_with_a_sink(monkeypatch, tmp_path):
    import ace_trace_queue
    tmp = tmp_path / "tmp"
    tmp.mkdir()
    f = tmp / "ace-trace-x.json"
    f.write_text("{}")
    os.utime(f, (1, 1))
    monkeypatch.setenv("ACE_TRACE_SINK", "file:%s" % (tmp_path / "s"))
    assert ace_trace_queue.sweep_orphans(tmp_path) == [] and f.exists() and not (tmp_path / "trace-queue").exists()
    monkeypatch.delenv("ACE_TRACE_SINK")
    assert ace_trace_queue.sweep_orphans(tmp_path) != []   # control: without a sink the orphan is handled


def test_r6_mod_sink_write_uses_mktemp_not_a_predictable_name():
    sh = _sh("SINK_WRITE_SH")
    assert "mktemp" in sh and "$$" not in sh


def test_r6_python_sink_creates_missing_parents_0700(cli, tmp_path, monkeypatch):
    sink = tmp_path / "a" / "b" / "c"
    monkeypatch.setenv("ACE_TRACE_SINK", "file:%s" % sink)
    cli.run_learn(dict(TRACE))
    for d in (tmp_path / "a", tmp_path / "a" / "b", sink):
        assert stat.S_IMODE(d.stat().st_mode) == 0o700, d


# ---- round 6 additions: feedback_upvote reaches the switch store; the permission-denied trace has no `domains` ----
def test_r6_engine_passes_feedback_upvote_through(tmp_path, monkeypatch):
    import subprocess
    import engine_harness as E
    if E.node_bin() is None:
        pytest.skip("node not installed")
    monkeypatch.setenv("ACE_FAKE_CORE_MODE", "raw_old")
    monkeypatch.setenv("ACE_FAKE_CORE_LOG", str(tmp_path / "core.log"))
    bin_dir = E.make_prefix(tmp_path)
    p = subprocess.run([E.node_bin(), str(E.ENGINE / "search.js")], input=json.dumps({"query": "q", "org": "o", "project": "p"}),
                       capture_output=True, text=True, timeout=60, env=dict(os.environ, PATH=E.path_with(bin_dir)))
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout.strip().splitlines()[-1])["feedback_upvote"] is True


def test_r6_python_stores_feedback_upvote(pdd):
    pdd.store_server_switches({"feedback_upvote": True})
    assert json.loads(pdd.feedback_upvote_file().read_text())["on"] is True
    pdd.store_server_switches({"feedback_upvote": "yes"})               # non-bool: the stored value stays
    assert json.loads(pdd.feedback_upvote_file().read_text())["on"] is True


def test_r6_permission_denied_trace_has_no_domains():
    import ace_permission_denied as m
    assert "domains" not in m._build_trace({"session_id": "c", "tool_name": "Bash", "tool_input": {"command": "ls"}})


# ---- round 8 W1 (acceptance): under the opt-out a REPLAYED trace is byte-identical to what the live path sends for the same task ----
import shutil


def _replay_off(monkeypatch, tmp_path, trace, meta=None):
    import ace_trace_queue, ace_cli
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path / "ace-pd"))
    monkeypatch.setenv("ACE_TRACE_FULL_STEPS", "0")
    got, sent = [], []
    monkeypatch.setattr(ace_trace_queue, "replay", lambda qdir, send, *a, **k: got.append(send) or [])
    monkeypatch.setattr(ace_cli, "learn_once", lambda trace, **k: sent.append(trace) or (0, "", True))
    ace_trace_queue._main(["--replay"])
    got[0]({"trace": json.loads(json.dumps(trace)), "meta": meta or {}, "key": "k"})
    return sent[0]


_BUILD_TS = """import { buildTrace, toolRec } from '%s'
import { pyDumps } from '%s'
const big = (c: string) => c.repeat(10000)
const recs = () => [toolRec('Edit', { file_path: '/p/a.py', old_string: 'a', new_string: big('n') }, { filePath: '/p/a.py' }, false, undefined, 0, 1),
  ...Array.from({ length: 60 }, (_, i) => toolRec('Bash', { command: 'echo ' + i }, { stdout: 'x'.repeat(300), stderr: '', interrupted: false }, false, undefined, i + 1, i + 2))]
const a = (full: boolean) => buildTrace({ userPrompt: big('t'), answer: big('s'), playbookUsed: [], agentType: '%s', appliedLogIds: [], nowIso: 'T', effort: 'normal',
  tools: recs(), fullSteps: full, legacySummaryCap: %d } as any).trace
console.log(JSON.stringify({ full: pyDumps(a(true)), off: pyDumps(a(false)) }))
"""


@pytest.mark.parametrize("agent,cap", [("main", 2000), ("Explore", 4000)], ids=["main", "subagent_handback"])
def test_r8_w1_mod_trace_replay_off_vs_live_off(monkeypatch, tmp_path, agent, cap):
    bun = shutil.which("bun")
    if not bun:
        pytest.skip("bun not installed")
    lib = REPO / "plugins/ace/mod/lib"
    f = tmp_path / "build.ts"
    f.write_text(_BUILD_TS % (lib / "trace.ts", lib / "pyjson.ts", agent, cap))
    import subprocess
    p = subprocess.run([bun, str(f)], capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    out = json.loads(p.stdout)
    full, off = json.loads(out["full"]), json.loads(out["off"])
    assert len(full["task"]) > 10000 and "tool_input" in full["trajectory"][0]   # the live-on trace really is full
    replayed = _replay_off(monkeypatch, tmp_path, full)
    if agent == "main":
        assert json.dumps(replayed) == json.dumps(off)
    else:  # round 9 N1, deliberate: a handback report goes out with 2000 on replay (live 4000); everything else identical
        assert (len(off["result"]["summary"]), len(replayed["result"]["summary"])) == (4000, 2000)
        off["result"]["summary"] = off["result"]["summary"][:2000]
        assert json.dumps(replayed) == json.dumps(off)


def test_r8_w1_python_trace_replay_off_is_byte_identical_to_live_off(monkeypatch, tmp_path):
    from test_stop_v8 import ORG_ID, PROJECT_ID, WORK, Box

    def build(sub, **env):
        box = Box(tmp_path / sub)
        sid = "s-w1"
        box.write_state(sid, "main", task_session_id="own", user_prompt="t" * 10000)
        box.seed_tools(sid, WORK + [("Bash", {"command": "echo %d" % i}, {"stdout": "ok", "stderr": ""}) for i in range(60)])
        p = box.run_after_task(box.stop_event(sid, last_assistant_message="s" * 10000), ACE_PROJECT_ID=PROJECT_ID, ACE_ORG_ID=ORG_ID, **env)
        assert p.returncode == 0, p.stderr
        (learn,) = box.cli_calls("learn")
        t = learn["trace"]
        t.pop("timestamp")  # the build time differs between the two runs, nothing else may
        return t
    full, off = build("on"), build("off", ACE_TRACE_FULL_STEPS="0")
    assert len(full["task"]) > 10000
    replayed = _replay_off(monkeypatch, tmp_path, full)
    assert json.dumps(replayed) == json.dumps(off)


def test_r8_w1_replay_on_keeps_the_trace_untouched(monkeypatch, tmp_path):
    import ace_trace_queue, ace_cli
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path / "ace-pd"))
    monkeypatch.delenv("ACE_TRACE_FULL_STEPS", raising=False)
    got, sent = [], []
    monkeypatch.setattr(ace_trace_queue, "replay", lambda qdir, send, *a, **k: got.append(send) or [])
    monkeypatch.setattr(ace_cli, "learn_once", lambda trace, **k: sent.append(trace) or (0, "", True))
    ace_trace_queue._main(["--replay"])
    t = {"task": "User request: " + "t" * 10000, "result": {"summary": "s" * 10000}, "trajectory": [{"step": 1, "tool_input": {"c": 1}}]}
    got[0]({"trace": json.loads(json.dumps(t)), "meta": {}, "key": "k"})
    assert json.dumps(sent[0]) == json.dumps(t)


def test_r9_n1_no_new_meta_field_reaches_the_queue():
    turn = (REPO / "plugins/ace/mod/handlers/turn.ts").read_text()
    cli = (REPO / "plugins/ace/shared-hooks/utils/ace_cli.py").read_text()
    after = (REPO / "plugins/ace/shared-hooks/ace_after_task.py").read_text()
    assert "summary_cap" not in turn + cli + after


# ---- round 8 L2: the update watchdog for real: timeout recognised and the child killed, one text-free row, the lock released ----
def _watchdog():
    bun = shutil.which("bun")
    if not bun:
        pytest.skip("bun not installed")
    import subprocess
    p = subprocess.run([bun, "-e", "import { UPDATE_WATCHDOG } from '%s'; console.log(JSON.stringify(UPDATE_WATCHDOG))" % (REPO / "plugins/ace/mod/lib/update.ts")],
                       capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)


@pytest.mark.parametrize("cmd,want", [(["/bin/sh", "-c", "sleep 30"], "timeout"), (["/bin/sh", "-c", "exit 0"], "ok"), (["/bin/sh", "-c", "exit 3"], "failed")])
def test_r8_l2_watchdog(tmp_path, cmd, want):
    import subprocess
    log, lock = tmp_path / "logs" / "ace-relevance.jsonl", tmp_path / "auto-update.lock"
    log.parent.mkdir()
    lock.mkdir()
    (lock / "owner").write_text("N1")
    t0 = time.time()
    p = subprocess.run([sys.executable, "-I", "-c", _watchdog(), "/usr/bin:/bin", str(log), json.dumps({"event": "auto_update_result", "target": "8.2.0"}),
                        str(lock), "N1", "1"] + cmd, capture_output=True, text=True, timeout=30)
    assert p.returncode == 0 and time.time() - t0 < 15                      # a timeout kills the child: no 30 s wait
    (row,) = [json.loads(l) for l in log.read_text().splitlines()]
    assert row["result"] == want and row["event"] == "auto_update_result" and isinstance(row["ms"], int) and row["target"] == "8.2.0"
    assert set(row) <= {"event", "target", "result", "exit_code", "ms", "timestamp"}       # text-free: no output of the command
    assert not lock.exists()


def test_r8_l2_watchdog_keeps_a_lock_it_does_not_own(tmp_path):
    import subprocess
    log, lock = tmp_path / "ace-relevance.jsonl", tmp_path / "auto-update.lock"
    lock.mkdir()
    (lock / "owner").write_text("OTHER")
    subprocess.run([sys.executable, "-I", "-c", _watchdog(), "/usr/bin:/bin", str(log), "{}", str(lock), "N1", "5", "/bin/sh", "-c", "exit 0"], timeout=30)
    assert (lock / "owner").read_text() == "OTHER"


# ---- round 8 I3: the hard trace cap is clamped below the queue's MAX_FILE (a queued trace must never be too_large) ----
def test_r8_i3_python_hard_cap_clamped(monkeypatch):
    import trace_truncate, ace_trace_queue
    monkeypatch.setenv("ACE_TRACE_HARD_CAP_BYTES", str(20 * 1024 * 1024))
    assert trace_truncate.hard_cap_bytes() == trace_truncate.TRACE_HARD_CAP_MAX < ace_trace_queue.MAX_FILE
    assert ace_trace_queue.MAX_FILE - trace_truncate.TRACE_HARD_CAP_MAX >= 128 * 1024   # room for the queue entry around the trace
    monkeypatch.setenv("ACE_TRACE_HARD_CAP_BYTES", "600")
    assert trace_truncate.hard_cap_bytes() == 600


def test_r8_i3_mod_hard_cap_clamped_to_the_same_value():
    import trace_truncate
    ts = (REPO / "plugins/ace/mod/lib/trace.ts").read_text()
    assert "export const TRACE_HARD_CAP_MAX = 5 * 1024 * 1024 - 256 * 1024" in ts
    assert trace_truncate.TRACE_HARD_CAP_MAX == 5 * 1024 * 1024 - 256 * 1024


def test_r9_n1_meta_with_an_unknown_key_is_still_invalid():
    import ace_trace_queue as q
    base = {"org": "o", "project": "p", "retrieval_id": None, "applied_log_ids": [], "hook": "Stop", "agent_type": "main"}
    assert q._valid_meta(base) and not q._valid_meta(dict(base, summary_cap=2000))


# ---- round 9 N1 proof: an entry written by THIS code survives the 8.3.0 queue code (an older session shares the data dir) ----
def test_r9_n1_entries_of_this_version_pass_the_8_3_0_queue(tmp_path, monkeypatch):
    import importlib.util
    # Round 10 / M4: the 8.3.0 module is a checked-in fixture (git show 70c1624:plugins/ace/shared-hooks/utils/ace_trace_queue.py):
    # a shallow CI checkout has no 70c1624
    spec = importlib.util.spec_from_file_location("ace_trace_queue_830", REPO / "tests" / "fixtures" / "ace_trace_queue_830.py")
    old = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(old)
    import ace_trace_queue as new
    qdir = tmp_path / "ace-pd" / "trace-queue"  # plugin_data_dir honours only an ace-* CLAUDE_PLUGIN_DATA
    trace = {"task": "User request: x", "trajectory": [{"step": 1, "tool_input": {"c": 1}, "tool_response": "y"}], "chain": "mod",
             "result": {"success": False}, "fork_of": {"parent_retrieval_id": "r"}, "feedback": {"kind": "upvote", "applied_log_ids": [1]}}
    import importlib
    metas = [{"org": "o", "project": "p", "retrieval_id": "r", "applied_log_ids": [1], "hook": "Stop", "agent_type": "main", "session_id": "s"},
             {"org": "o", "project": "p", "retrieval_id": None, "applied_log_ids": [], "hook": "PermissionDenied", "agent_type": "permission_gate"}]
    # the mod's meta shape (handlers/turn.ts queue meta), settled directly
    rows = list(new.settle(str(qdir), "%032x" % 1, trace, metas[0], None, "ECONNREFUSED", keyed=False))
    assert [r["event"] for r in rows] == ["learn_requeued"], rows
    # the Python chain's real producer: ace_cli.run_learn with a send that never reached the server (the permission-denied path)
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path / "ace-pd"))
    monkeypatch.chdir(tmp_path)
    import ace_cli, ace_relevance_logger
    ace_relevance_logger._logger = None
    importlib.reload(ace_cli)
    monkeypatch.setattr(ace_cli, "_learn", lambda trace, **k: (None, 1, None, "connect ECONNREFUSED 127.0.0.1", False))
    ace_cli.run_learn(dict(trace, agent_type="permission_gate"), org="o", project="p", hook_event_name="PermissionDenied")
    entries = sorted(qdir.glob("*.json"))
    assert len(entries) == 2
    # negative control: one unknown meta key and 8.3.0 refuses the entry
    bad = dict(metas[1], summary_cap=None)
    assert not old._valid_meta(bad)
    key = old.load_key(str(qdir))
    for f in entries:
        e, why = old._load(str(f), f.name, key)
        assert e is not None and why is None, (f.name, why)
        assert old._valid_entry(e)
    old._prune(str(qdir), time.time(), key)
    assert len(list(qdir.glob("*.json"))) == 2
    assert not (qdir / "dead").exists() or not list((qdir / "dead").iterdir())


# ---- round 9 N3: on a timeout the watchdog ends the update's whole process group (grandchildren too, nothing else) ----
def test_r9_n3_watchdog_timeout_kills_grandchildren(tmp_path):
    import subprocess, signal
    log, lock, pidf = tmp_path / "ace-relevance.jsonl", tmp_path / "auto-update.lock", tmp_path / "gc.pid"
    lock.mkdir()
    (lock / "owner").write_text("N1")
    p = subprocess.run([sys.executable, "-I", "-c", _watchdog(), "/usr/bin:/bin", str(log), "{}", str(lock), "N1", "1",
                        "/bin/sh", "-c", "sleep 60 & echo $! > %s; wait" % pidf], timeout=30)
    gc = int(pidf.read_text())
    time.sleep(0.3)
    try:
        os.kill(gc, 0)
        alive = True
    except ProcessLookupError:
        alive = False
    if alive:
        os.kill(gc, signal.SIGKILL)
    assert not alive and json.loads(log.read_text())["result"] == "timeout"



def test_round10_m4_the_8_3_0_fixture_is_the_released_module():
    import hashlib
    src = (REPO / "tests" / "fixtures" / "ace_trace_queue_830.py").read_bytes()
    assert b'_META = {"org": 128, "project": 128, "retrieval_id": 128, "hook": 64, "agent_type": 128, "session_id": 512}' in src
    assert b"summary_cap" not in src and b"strip_full_steps" not in src


# ---- Round 10 / L1: with a sink the detached path writes no signed learn-job file (another session without a sink could send it) ----
def test_round10_l1_sink_writes_no_learn_job_file(tmp_path):
    from test_stop_v8 import ORG_ID, PROJECT_ID, WORK, Box
    box = Box(tmp_path)
    sid = "s-l1"
    box.write_state(sid, "main", task_session_id="own", user_prompt="refactor the parser module")
    box.seed_tools(sid, WORK)
    sink = tmp_path / "sink"
    p = box.run_after_task(box.stop_event(sid), ACE_PROJECT_ID=PROJECT_ID, ACE_ORG_ID=ORG_ID, ACE_TRACE_SINK="file:%s" % sink, ACE_LEARN_INLINE="")
    assert p.returncode == 0, p.stderr
    assert list(box.pd.rglob("learn-job-*.json")) == []
    assert len(list(sink.iterdir())) == 1 and box.cli_calls("learn") == []
