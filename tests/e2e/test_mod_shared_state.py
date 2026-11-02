"""Shared on-disk contract between the v8 mod and the Python hooks (DESIGN §13.1, §4/C1, §12, §11 A3).

- The mod's main-agent state output (fixture `state_main_8`, the exact bytes the mod must write;
  plugins/ace/mod/tests/ace_mod.test.ts asserts the mod writes them) is readable by
  patterns_used_state.load_state / load_* and re-injected by the SessionStart compact hook.
- The mod is registered in plugin.json beside the classic hooks, TypeScript only, no build step.
- The mod's detached learn launcher survives SIGHUP of the session's process group, appends the
  execution metrics row and cleans up trace, .result and lock (fake ace-cli; never the real server).
- Coexistence (ACE_E2E=1): a fresh mod-active marker silences every covered Python hook.
"""
import json
import os
import shutil
import signal
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest

import mod_reference as R

NODE = shutil.which("node")
HERE = Path(__file__).resolve().parent
TSID = "11111111-2222-4333-8444-555555555555"
PRJ, SID = "prj_shared", "sess-shared"


def _mod_state_text():
    return json.loads((R.FIX_JSON / "golden.json").read_text())["state_main_8"].replace(R.TSID_PLACEHOLDER, TSID)


@pytest.fixture
def data_root(tmp_path, monkeypatch):
    root = tmp_path / "ace-plugin-data"  # §16 P5: only an ace* CLAUDE_PLUGIN_DATA is honoured
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(root))
    return root


def _write_mod_state(root):
    sdir = root / "projects" / PRJ / "sessions" / SID
    sdir.mkdir(parents=True)
    (sdir / "patterns-used-main.json").write_text(_mod_state_text())
    return sdir


# ---------- fixtures ----------

def test_committed_fixtures_match_the_generator():
    for path, text in R.generated_files().items():
        assert path.exists(), "missing generated fixture %s (run: python3 tests/e2e/mod_reference.py --write)" % path
        assert path.read_text() == text, "stale fixture %s (run: python3 tests/e2e/mod_reference.py --write)" % path


def test_state_fixture_is_exactly_what_the_python_writer_produces():
    assert json.loads((R.FIX_JSON / "golden.json").read_text())["state_main_8"] == R.expected_main_state(
        (R.FIX_JSON / "search_8.json").read_text())


# ---------- the mod's state output, read by the Python chain ----------

def test_load_state_reads_the_mod_state(data_root):
    import patterns_used_state as pus
    _write_mod_state(data_root)
    st = pus.load_state(SID, None, "Stop", project_id=PRJ)
    want = json.loads(_mod_state_text())
    assert st == want
    assert list(st)[:4] == ["pattern_ids", "retrieval_id", "retrieval_log_ids", "task_session_id"]
    assert st["task_session_id"] == TSID and st["hook_event_name"] == "UserPromptSubmit"
    assert pus.load_task_session_id(SID, None, "Stop", project_id=PRJ) == TSID
    assert pus.load_retrieval_ids(SID, None, "Stop", project_id=PRJ) == want["retrieval_log_ids"]
    assert pus.load_playbook_used(SID, None, "Stop", project_id=PRJ) == want["pattern_ids"]


def test_rendered_context_survives_the_python_reap_into_the_sidecar(data_root):
    import patterns_used_state as pus
    sdir = _write_mod_state(data_root)
    pus.load_playbook_used(SID, None, "Stop", project_id=PRJ)   # Python Stop reaps the main state
    assert pus.load_rendered_context(SID, project_id=PRJ) == json.loads(_mod_state_text())["rendered_context"]
    assert (sdir / "rendered-main.txt").exists()


def _run_compact(root, tmp_path):
    proj = tmp_path / "proj"
    (proj / ".claude").mkdir(parents=True)
    (proj / ".claude" / "settings.json").write_text(json.dumps({"projectId": PRJ, "orgId": "org_shared"}))
    env = dict(os.environ, CLAUDE_PLUGIN_DATA=str(root), CLAUDE_PROJECT_DIR=str(proj))
    event = {"hook_event_name": "SessionStart", "source": "compact", "session_id": SID, "cwd": str(proj)}
    p = subprocess.run([sys.executable, str(R.PLUGIN / "shared-hooks" / "ace_session_start.py"), "--compact"],
                       input=json.dumps(event), capture_output=True, text=True, cwd=str(proj), env=env, timeout=30)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)["hookSpecificOutput"]["additionalContext"]


def test_sessionstart_compact_reinjects_the_mod_rendered_context(data_root, tmp_path):
    _write_mod_state(data_root)
    rc = json.loads(_mod_state_text())["rendered_context"]
    assert _run_compact(data_root, tmp_path) == rc
    assert len(rc) <= R.STATE_RENDER_CAP and rc.endswith("</ace-patterns>")


def test_sessionstart_compact_reinjects_the_mod_sidecar_after_its_learn(data_root, tmp_path):
    """The mod reaps patterns-used-main.json at turn.complete and keeps rendered-main.txt (ace_mod.test.ts)."""
    sdir = data_root / "projects" / PRJ / "sessions" / SID
    sdir.mkdir(parents=True)
    rc = json.loads(_mod_state_text())["rendered_context"]
    (sdir / "rendered-main.txt").write_text(rc)
    assert _run_compact(data_root, tmp_path) == rc


# ---------- registration ----------

def test_mod_is_registered_in_plugin_json_beside_the_classic_hooks():
    manifest = json.loads((R.PLUGIN / ".claude-plugin" / "plugin.json").read_text())
    hooks = manifest.get("hooks")
    hooks = hooks if isinstance(hooks, list) else [hooks]
    assert "./mod/hooks.json" in hooks
    assert "./hooks/hooks.json" not in hooks  # loaded by convention; listing it again is a duplicate
    assert json.loads((R.MOD / "hooks.json").read_text()) == {"modules": ["./register.ts"]}
    assert (R.PLUGIN / "hooks" / "hooks.json").exists()
    assert (R.MOD / "register.ts").exists() and (R.MOD / "core.ts").exists()


def test_mod_is_typescript_without_build_step_or_dependencies():
    src = [p for p in R.MOD.rglob("*") if p.is_file() and "fixtures" not in p.parts]
    assert not [p for p in src if p.name in ("package.json", "package-lock.json", "tsconfig.json") or "node_modules" in p.parts]
    assert {p.suffix for p in src} <= {".ts", ".json", ".md"}
    for p in src:
        if p.suffix == ".ts":
            text = p.read_text()
            assert "import(" not in text, "%s: a module holding import() does not load" % p
            assert "CLAUDE_PLUGIN_DATA" not in text or p.parent.name == "tests", "%s: derive the data dir from $.plugin.root (F1)" % p


# ---------- detached learn launcher (SIGHUP-safe, metrics row, cleanup) ----------

FAKE_LEARN = """#!/bin/sh
# fake ace-cli: never the network. Sleeps, records argv, exits $FAKE_LEARN_RC.
sleep 2
printf '%s\\n' "$*" > "$FAKE_LEARN_MARKER"
echo '{"ok": true}'
exit "${FAKE_LEARN_RC:-0}"
"""


def _launcher_argv(job):
    p = subprocess.run([NODE, "--experimental-strip-types", "--no-warnings", str(HERE / "mod_parity_node.mjs")],
                       input=json.dumps({"fixtures": [], "sids": [], "envs": [], "roots": [], "learnJob": job}),
                       capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, "mod core.ts did not run:\n" + p.stderr[-2000:]
    return json.loads(p.stdout)["learnArgv"]


@pytest.mark.skipif(not NODE, reason="node not installed")
@pytest.mark.parametrize("rc,sent", [(0, True), (1, False)])
def test_detached_learn_survives_sighup_and_cleans_up(tmp_path, rc, sent):
    fake_dir = tmp_path / "bin"
    fake_dir.mkdir()
    fake = fake_dir / "ace-cli"
    fake.write_text(FAKE_LEARN)
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    sdir = tmp_path / "data" / "projects" / PRJ / "sessions" / SID
    (tmp_path / "data" / "tmp").mkdir(parents=True)
    sdir.mkdir(parents=True)
    trace = tmp_path / "data" / "tmp" / "ace-trace-x.json"
    trace.write_text('{"task": "User request: x"}')
    lock = sdir / "learn-inflight-main.lock"
    lock.write_text("")
    log = tmp_path / "proj" / ".claude" / "data" / "logs" / "ace-relevance.jsonl"
    row_ok = json.dumps({"event": "execution", "hook": "Stop", "learning_sent": True})
    row_fail = json.dumps({"event": "execution", "hook": "Stop", "learning_sent": False})
    learn = ["ace-cli", "learn", "--transcript", str(trace), "--json", "--no-stream", "--timeout", "300000",
             "--verbosity", "detailed", "--retrieval-id", "rid-1", "--applied-log-ids", "1,2"]
    argv = _launcher_argv({"learnArgv": learn, "trace": str(trace), "lock": str(lock), "log": str(log),
                           "rowOk": row_ok, "rowFail": row_fail})
    assert isinstance(argv, list) and argv and argv[0] != "ace-cli"
    marker = tmp_path / "learn-ran"
    env = dict(os.environ, PATH=str(fake_dir) + os.pathsep + os.environ.get("PATH", ""),
               FAKE_LEARN_MARKER=str(marker), FAKE_LEARN_RC=str(rc))

    # The session: its own process group, as `claude -p` is; the launcher must return at once.
    t0 = time.monotonic()
    sess = subprocess.Popen(argv, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, start_new_session=True)
    sess.wait(timeout=5)
    assert time.monotonic() - t0 < 1.0, "the launcher blocked on the learn"
    for sig in (signal.SIGHUP, signal.SIGKILL):  # teardown of the whole session group
        try:
            os.killpg(sess.pid, sig)
        except OSError:
            pass

    deadline = time.monotonic() + 8
    while time.monotonic() < deadline and (lock.exists() or not log.exists()):
        time.sleep(0.1)
    assert marker.exists(), "learn was killed with the session"
    assert "--no-stream" in marker.read_text() and "--applied-log-ids 1,2" in marker.read_text()
    assert log.read_text() == (row_ok if sent else row_fail) + "\n"
    assert not lock.exists() and not trace.exists() and not Path(str(trace) + ".result").exists()


# ---------- coexistence: the Python hooks step aside while the mod is active ----------

COVERED = ["UserPromptSubmit_human", "SubagentStart", "PostToolUse_Read", "PostToolBatch",
           "PostToolUseFailure_Bash", "Stop", "SubagentStop"]


def _marker(age_s):
    def prepare(data, project_id, session_id):
        m = data / "projects" / project_id / "sessions" / session_id / "mod-active"
        m.parent.mkdir(parents=True, exist_ok=True)
        m.write_text("")
        t = time.time() - age_s
        os.utime(str(m), (t, t))
    return prepare


def _artifacts(r):
    """State/log files a hook wrote (the marker and the harness's own python_path excluded)."""
    sb = r["sandbox"]
    found = [p for p in (sb / "plugin-data").rglob("*") if p.is_file() and p.name not in ("mod-active", "python_path")]
    found += [p for p in (sb / "proj" / ".claude" / "data").rglob("*") if p.is_file()] \
        if (sb / "proj" / ".claude" / "data").exists() else []
    return sorted(str(p.relative_to(sb)) for p in found)


@pytest.mark.skipif(os.environ.get("ACE_E2E") != "1", reason="e2e target tests: set ACE_E2E=1")
@pytest.mark.parametrize("name", COVERED)
def test_fresh_mod_marker_silences_covered_python_hooks(name):
    import ace_e2e_harness as H
    r = H.run_fixture(name, prepare=_marker(60))
    try:
        assert r["cli_calls"] == [], "mod active: the Python hook must not spawn ace-cli"
        assert all(run["stdout"].strip() == "" for run in r["runs"]), "mod active: no output"
        assert _artifacts(r) == [], "mod active: the Python hook must not write state or log rows"
    finally:
        shutil.rmtree(str(r["sandbox"]), ignore_errors=True)


@pytest.mark.skipif(os.environ.get("ACE_E2E") != "1", reason="e2e target tests: set ACE_E2E=1")
def test_stale_mod_marker_leaves_python_hooks_working():
    import ace_e2e_harness as H
    r = H.run_fixture("UserPromptSubmit_human", prepare=_marker(11 * 60))
    try:
        assert [c["argv"][:1] for c in r["cli_calls"]] == [["search"]]
    finally:
        shutil.rmtree(str(r["sandbox"]), ignore_errors=True)
