"""8.1.4 trace delivery e2e (DESIGN "Trace delivery"): the REAL @ace-sdk/core (the plugin-local pinned one) against
the localhost fake server, both chains:

- python: ace_cli.run_learn (what Stop/SubagentStop/PermissionDenied call), engine/learn.js with the real core;
- mod:    the real detached launcher from mod/lib/trace.ts (node --experimental-strip-types) with engine/learn.js.

Cases: 502 x3 then 200 (the core's own retry absorbs it, nothing queued); 502 x4 then 200 (dead letter -> queued ->
replayed once, same Idempotency-Key on every POST); 400 (dead/, never replayed); server down for a whole session
(the next session's replay delivers); two parallel replays never duplicate; the race (a delayed reader keeps its file);
a Stop trace's body at the server carries result.plugin_version/outcome_rule and no canary secret.
Gated: ACE_E2E=1. Never the real server (GUARD_JS), HOME/CLAUDE_PLUGIN_DATA in tmp.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import engine_harness as E  # noqa: E402

REPO = HERE.parent.parent
SRC = REPO / "plugins" / "ace"
REAL_CORE = SRC / "node_modules" / "@ace-sdk" / "core"
NODE = shutil.which("node")

pytestmark = [
    pytest.mark.skipif(os.environ.get("ACE_E2E") != "1", reason="e2e target tests: set ACE_E2E=1"),
    pytest.mark.skipif(not NODE, reason="node not installed"),
    pytest.mark.skipif(not (REAL_CORE / "package.json").exists(), reason="plugin-local @ace-sdk/core not installed (npm ci in plugins/ace)"),
]
TRACE = {"task": "User request: e2e trace delivery", "trajectory": [{"step": 1, "tool": "Edit", "action": "Edit x.py", "result": "ok"}],
         "result": {"success": True, "failed_steps": 0, "output": "Executed 1 tool calls", "plugin_version": "8.1.4",
                    "outcome_rule": "end-outcome-1"}, "playbook_used": [], "timestamp": "2026-11-08T00:00:00Z", "agent_type": "main"}


@pytest.fixture
def world(tmp_path):
    """A plugin copy whose node_modules holds the real pinned core; plugin data, project, sdk env (fake token)."""
    plugin = tmp_path / "plugin"
    for sub in ("engine", ".claude-plugin", "shared-hooks", "scripts", "mod", "utils"):
        shutil.copytree(str(SRC / sub), str(plugin / sub), ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "tests"))
    (plugin / "node_modules" / "@ace-sdk").mkdir(parents=True)
    os.symlink(str(REAL_CORE), str(plugin / "node_modules" / "@ace-sdk" / "core"))
    pd = tmp_path / "ace-pd"
    proj = tmp_path / "proj"
    (proj / ".claude").mkdir(parents=True)
    pd.mkdir()

    class W:
        root = tmp_path
        servers = []

        def server(self, mode="ok", port=0, **env):
            d = tmp_path / ("srv%d" % len(self.servers))
            d.mkdir()
            s = E.FakeServer(d, mode=mode, port=port, **env)
            self.servers.append(s)
            self.srv = s
            return s

        def env(self, **extra):
            e = E.sdk_env(tmp_path, self.srv, CLAUDE_PLUGIN_DATA=str(pd), CLAUDE_PLUGIN_ROOT=str(plugin),
                          PATH=os.pathsep.join([os.path.dirname(NODE), "/usr/bin", "/bin"]))
            for k in [k for k in e if k.startswith("CLAUDE_") and k not in ("CLAUDE_PLUGIN_DATA", "CLAUDE_PLUGIN_ROOT")]:
                del e[k]
            e.update({k: str(v) for k, v in extra.items()})
            return e

        def traces(self, srv=None):
            reqs = []
            for s in ([srv] if srv else self.servers):
                reqs += [r for r in s.requests() if r["method"] == "POST" and r["path"].startswith("/traces")]
            return reqs

        def qfiles(self):
            q = pd / "trace-queue"
            return sorted(q.glob("*.json")) if q.is_dir() else []

        def rows(self, ev=None):
            f = proj / ".claude" / "data" / "logs" / "ace-relevance.jsonl"
            rs = [json.loads(l) for l in f.read_text().splitlines() if l.strip()] if f.exists() else []
            return [r for r in rs if ev is None or r.get("event") == ev]

        def make_due(self):
            for f in self.qfiles():
                e = json.loads(f.read_text())
                e["next_at"] = 0
                f.write_text(json.dumps(e))

        def replay(self, wait=True):
            p = subprocess.Popen([sys.executable, str(plugin / "shared-hooks" / "utils" / "ace_trace_queue.py"), "--replay",
                                  "--cwd", str(proj)], cwd=str(proj), env=self.env(), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if wait:
                p.wait(timeout=120)
            return p

        def send(self, chain, trace=TRACE):
            return (_send_python if chain == "python" else _send_mod)(self, trace)

    w = W()
    w.plugin, w.pd, w.proj = plugin, pd, proj
    yield w
    for s in w.servers:
        s.stop()


def _send_python(w, trace):
    code = ("import json,sys; sys.path.insert(0, sys.argv[1]); import ace_cli; "
            "out,_ = ace_cli.run_learn(json.loads(sys.argv[2]), org='org_fake', project='prj_fake', hook_event_name='Stop'); "
            "print(json.dumps(out))")
    p = subprocess.run([sys.executable, "-c", code, str(w.plugin / "shared-hooks" / "utils"), json.dumps(trace)],
                       cwd=str(w.proj), env=w.env(), capture_output=True, text=True, timeout=180)
    assert p.returncode == 0, p.stderr


def _launcher_argv(job):
    p = subprocess.run([NODE, "--experimental-strip-types", "--no-warnings", str(HERE / "mod_parity_node.mjs")],
                       input=json.dumps({"fixtures": [], "sids": [], "envs": [], "roots": [], "learnJob": job}),
                       capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr[-2000:]
    return json.loads(p.stdout)["learnArgv"]


def _send_mod(w, trace, wait=True):
    qid = str(uuid.uuid4())
    tmp = w.pd / "tmp"
    tmp.mkdir(mode=0o700, exist_ok=True)
    f = tmp / ("ace-trace-%s.json" % qid)
    f.write_text(json.dumps(trace))
    lock = w.root / ("lock-%s" % qid)
    lock.write_text("")
    log = w.proj / ".claude" / "data" / "logs" / "ace-relevance.jsonl"
    learn = ["node", str(w.plugin / "engine" / "learn.js"), "--transcript", str(f), "--json", "--timeout", "300000",
             "--verbosity", "detailed", "--no-stream", "--idempotency-key", qid, "--org", "org_fake", "--project", "prj_fake"]
    queue = json.dumps({"id": qid, "root": str(w.pd), "utils": str(w.plugin / "shared-hooks" / "utils"), "log": str(log),
                        "cwd": str(w.proj), "on": True, "meta": {"org": "org_fake", "project": "prj_fake", "retrieval_id": None,
                        "applied_log_ids": [], "hook": "Stop", "agent_type": "main", "session_id": "cc-1"}})
    argv = _launcher_argv({"learnArgv": learn, "trace": str(f), "lock": str(lock), "log": str(log),
                           "rowOk": '{"event": "execution", "learning_sent": true}', "rowFail": '{"event": "execution", "learning_sent": false}',
                           "cwd": str(w.proj), "queue": queue})
    subprocess.run(argv, env=w.env(), timeout=30, check=True)
    if wait:
        deadline = time.monotonic() + 150
        while lock.exists() and time.monotonic() < deadline:
            time.sleep(0.2)
        assert not lock.exists(), "the detached learn child did not finish"
    return qid


def _keys(reqs):
    return [r["headers"].get("Idempotency-Key") for r in reqs]


def _ok_posts(srv):
    """POSTs the server stored: every /traces POST in a 200 phase (FAKE_TRACE_502 counts the first ones)."""
    return srv


@pytest.mark.parametrize("chain", ["python", "mod"])
def test_502_three_times_then_200_is_absorbed_by_the_core(world, chain):
    world.server(FAKE_TRACE_502="3")
    world.send(chain)
    t = world.traces()
    assert len(t) == 4 and len(set(_keys(t))) == 1 and _keys(t)[0], "one key on every attempt"
    assert world.qfiles() == [] and not world.rows("learn_requeued")


@pytest.mark.parametrize("chain", ["python", "mod"])
def test_502_four_times_queues_then_the_replay_arrives_exactly_once(world, chain):
    world.server(FAKE_TRACE_502="4")
    world.send(chain)
    files = world.qfiles()
    assert len(files) == 1, world.rows()
    qid = json.loads(files[0].read_text())["id"]
    r = world.rows("learn_requeued")
    assert len(r) == 1 and r[0]["error_class"] == "gateway_5xx" and r[0]["trace_id"] == qid
    world.make_due()
    world.replay()
    t = world.traces()
    assert len(t) == 5, "4 failed attempts + 1 replay"
    assert set(_keys(t)) == {qid}, "the queue id is the Idempotency-Key of the first send and of the replay"
    assert world.qfiles() == [] and len(world.rows("learn_replayed")) == 1
    body = t[-1]["body"]
    assert body["result"]["plugin_version"] and body["result"]["outcome_rule"] == "end-outcome-1"
    world.make_due()
    world.replay()
    assert len(world.traces()) == 5, "nothing sent twice"


@pytest.mark.parametrize("chain", ["python", "mod"])
def test_400_goes_to_dead_and_is_never_replayed(world, chain):
    world.server(mode="400")
    world.send(chain)
    assert world.qfiles() == [] and len(list((world.pd / "trace-queue" / "dead").glob("*.json"))) == 1
    assert world.rows("learn_lost")[0]["error_class"] == "4xx"
    world.replay()
    assert len(world.traces()) == 1


@pytest.mark.parametrize("chain", ["python", "mod"])
def test_server_down_for_a_whole_session_arrives_in_the_next(world, chain):
    s = world.server()
    port = s.url.rsplit(":", 1)[1]
    s.stop()  # the session: the server is down (connection refused, the core's 4 attempts ~30 s)
    world.send(chain)
    assert len(world.qfiles()) == 1, world.rows()
    assert world.rows("learn_requeued")[0]["error_class"] == "network"
    world.server(port=int(port))  # the next session: the server is back
    world.make_due()
    world.replay()
    t = world.traces()
    assert len(t) == 1 and world.qfiles() == [] and world.rows("learn_replayed")


def test_two_parallel_replays_never_duplicate(world):
    """The replay is ONE module for both chains: entries from both, two replayers (two sessions) at once."""
    world.server(FAKE_TRACE_502="8")
    world.send("python")
    world.send("mod")
    assert len(world.qfiles()) == 2
    n_failed = len(world.traces())
    world.make_due()
    ps = [world.replay(wait=False) for _ in range(2)]
    for p in ps:
        p.wait(timeout=120)
    sent = world.traces()[n_failed:]
    assert len(sent) == 2 and len(set(_keys(sent))) == 2, _keys(sent)
    assert world.qfiles() == [] and len(world.rows("learn_replayed")) == 2


def test_the_race_a_delayed_reader_keeps_its_trace(world):
    """The 8.1.3 ENOENT: the mod parent removed the trace when the launcher outlived LAUNCHER_MS while the child was
    about to read it. Now the parent claims by rename; once the child owns the file the claim fails and the reader
    finds its file."""
    world.server()
    bin_dir = world.root / "slowbin"
    bin_dir.mkdir()
    slow = bin_dir / "slow-learn"
    slow.write_text("#!/bin/sh\nsleep 1.5\nf=$(printf '%s\\n' \"$@\" | sed -n '/--transcript/{n;p;}')\ncat \"$f\" > /dev/null || exit 1\necho '{\"success\": true}'\n")
    slow.chmod(0o755)
    qid = str(uuid.uuid4())
    (world.pd / "tmp").mkdir(mode=0o700, exist_ok=True)
    f = world.pd / "tmp" / ("ace-trace-%s.json" % qid)
    f.write_text(json.dumps(TRACE))
    lock = world.root / "lock"
    lock.write_text("")
    log = world.proj / ".claude" / "data" / "logs" / "ace-relevance.jsonl"
    queue = json.dumps({"id": qid, "root": str(world.pd), "utils": str(world.plugin / "shared-hooks" / "utils"), "log": str(log),
                        "cwd": str(world.proj), "on": True, "meta": {"project": "prj_fake", "hook": "Stop", "agent_type": "main"}})
    argv = _launcher_argv({"learnArgv": [str(slow), "--transcript", str(f)], "trace": str(f), "lock": str(lock), "log": str(log),
                           "rowOk": '{"event": "execution", "learning_sent": true}', "rowFail": '{"event": "execution", "learning_sent": false}',
                           "cwd": str(world.proj), "queue": queue})
    subprocess.run(argv, env=world.env(), timeout=30, check=True)
    time.sleep(0.5)  # the parent gives up on the launcher now (old code: rm trace -> ENOENT in the reader)
    claim = subprocess.run(["mv", "-n", str(f), str(f) + ".parent"], capture_output=True)
    assert claim.returncode != 0, "the child already owns the trace"
    deadline = time.monotonic() + 15
    while lock.exists() and time.monotonic() < deadline:
        time.sleep(0.1)
    assert world.rows("execution") == [{"event": "execution", "learning_sent": True}]
    assert world.qfiles() == [] and not list((world.pd / "tmp").iterdir())


def test_stop_trace_at_the_server_has_version_and_rule_and_no_canary(world):
    """A real Stop (ace_after_task.py, inline learn) through the real core: the body the server receives."""
    world.server()
    sys.path.insert(0, str(HERE.parent))
    from test_stop_v8 import _main_transcript, _tool_turn  # noqa: F401
    canary = "ghp_CANARYcanary0123456789"
    sid = "sess-e2e-canary"
    prompt = "publish the release with token %s and password: CANARYyaml please" % canary
    entries = [{"type": "user", "message": {"role": "user", "content": prompt}}] + \
        _tool_turn("toolu_c1", "Bash", {"command": "GITHUB_TOKEN=%s gh release create v1" % canary}, "token %s ok" % canary) + \
        _tool_turn("toolu_c2", "Edit", {"file_path": "src/app.py", "old_string": "a", "new_string": "b"}, "ok")
    tp = world.root / "t.jsonl"
    tp.write_text("\n".join(json.dumps(e) for e in entries) + "\n")
    (world.proj / ".claude" / "settings.json").write_text(json.dumps({"env": {"ACE_PROJECT_ID": "prj_fake", "ACE_ORG_ID": "org_fake"}}))
    sdir = world.pd / "projects" / "prj_fake" / "sessions" / sid
    sdir.mkdir(parents=True)
    (sdir / "patterns-used-main.json").write_text(json.dumps({"pattern_ids": [], "retrieval_id": None, "retrieval_log_ids": {},
                                                              "task_session_id": "tsid-1", "user_prompt": prompt}))
    ev = {"session_id": sid, "transcript_path": str(tp), "cwd": str(world.proj), "hook_event_name": "Stop",
          "stop_hook_active": False, "last_assistant_message": "done with %s" % canary, "background_tasks": []}
    p = subprocess.run([sys.executable, str(world.plugin / "shared-hooks" / "ace_after_task.py")], input=json.dumps(ev),
                       cwd=str(world.proj), env=world.env(ACE_LEARN_INLINE="1", ACE_PROJECT_ID="prj_fake", ACE_ORG_ID="org_fake"),
                       capture_output=True, text=True, timeout=180)
    assert p.returncode == 0, p.stderr
    t = world.traces()
    assert len(t) == 1, world.rows()
    res = t[0]["body"]["result"]
    version = json.loads((SRC / ".claude-plugin" / "plugin.json").read_text())["version"]
    assert res["plugin_version"] == version and re.fullmatch(r"\d+\.\d+\.\d+", version)
    assert res["outcome_rule"] == "end-outcome-1"
    assert "CANARY" not in json.dumps(t[0]["body"])
