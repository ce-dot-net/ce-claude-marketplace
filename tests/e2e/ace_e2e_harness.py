"""Hook-level e2e runner (DESIGN §6 WP-F; code-tests-release-infra §6/§7).

Feeds one realistic stdin JSON per event (tests/e2e/fixtures, shapes from the saved
CC hooks reference) through the commands that hooks.json of the plugin under test
routes that event to, exactly as Claude Code would: matcher rules per
cc_hooks_reference.md:277-283, `if` per :413, exec form (`args`) vs shell form per
:449-455, placeholders + exported CLAUDE_PROJECT_DIR/CLAUDE_PLUGIN_ROOT/
CLAUDE_PLUGIN_DATA per :480.

Every run is sandboxed: own HOME, CLAUDE_PLUGIN_DATA, TMPDIR, project dir with
.claude/settings.json {projectId, orgId}, and the fake ace-cli from tests/conftest.py
logging to a per-run ACE_FAKE_CLI_LOG. Nothing touches the network or the real ace-cli.
"""
import glob
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures"

# Allowed stdout JSON (cc_hooks_reference.md:1062-1068 universal fields; per-event
# decision fields: UPS :1524-1530, SessionStart :1299-1305, PostToolUse :2224-2231,
# PostToolUseFailure :2336-2338, SubagentStart :2570-2572, Stop/SubagentStop :2618,
# PermissionDenied :2439-2446, SessionEnd :3578 discards everything).
UNIVERSAL_KEYS = {"continue", "stopReason", "suppressOutput", "systemMessage", "terminalSequence"}
TOP_LEVEL_DECISION_EVENTS = {"UserPromptSubmit", "PostToolUse", "Stop", "SubagentStop"}
HOOK_SPECIFIC_KEYS = {
    "SessionStart": {"additionalContext", "initialUserMessage", "sessionTitle", "watchPaths", "reloadSkills"},
    "UserPromptSubmit": {"additionalContext", "sessionTitle", "suppressOriginalPrompt"},
    "PostToolUse": {"additionalContext", "classifierContext", "updatedToolOutput", "updatedMCPToolOutput"},
    "PostToolUseFailure": {"additionalContext"},
    "SubagentStart": {"additionalContext"},
    "SubagentStop": {"additionalContext"},
    "Stop": {"additionalContext"},
    "PermissionDenied": {"retry"},
    "SessionEnd": set(),
}
CONTEXT_CAP = 10000  # cc_hooks_reference.md:1050
# per hook with the fake CLI (DESIGN §6 WP-F); override on slow shared CI runners.
WALL_BUDGET_S = float(os.environ.get("ACE_E2E_WALL_BUDGET_S", "1.5"))

# Which field each event's matcher filters on (cc_hooks_reference.md:291-311).
MATCHER_FIELD = {
    "PostToolUse": "tool_name", "PostToolUseFailure": "tool_name", "PermissionDenied": "tool_name",
    "PreToolUse": "tool_name", "PermissionRequest": "tool_name",
    "SessionStart": "source", "SessionEnd": "reason",
    "SubagentStart": "agent_type", "SubagentStop": "agent_type",
    "PreCompact": "trigger",
}
TOOL_EVENTS = {"PreToolUse", "PostToolUse", "PostToolUseFailure", "PermissionRequest", "PermissionDenied"}


def plugin_root():
    return Path(os.environ.get("ACE_PLUGIN_ROOT_UNDER_TEST") or (REPO / "plugins" / "ace")).resolve()


def fixture_names():
    return sorted(p.stem for p in FIXTURES.glob("*.json"))


def matcher_matches(matcher, value):
    """cc_hooks_reference.md:277-283."""
    if matcher in (None, "", "*"):
        return True
    value = value or ""
    if re.fullmatch(r"[A-Za-z0-9_\- ,|]+", matcher):
        return value in [m.strip() for m in re.split(r"[|,]", matcher)]
    return re.search(matcher, value) is not None


def if_matches(rule, event_name, event):
    """Minimal `if` support (cc_hooks_reference.md:413): `Tool(...)` on tool events only."""
    if not rule or event_name not in TOOL_EVENTS:
        return True
    m = re.match(r"^([A-Za-z0-9_]+)\(", rule)
    return bool(m) and m.group(1) == event.get("tool_name")


def routed_hooks(hooks_json, event_name, event):
    out = []
    for group in hooks_json.get("hooks", {}).get(event_name, []):
        if not matcher_matches(group.get("matcher"), event.get(MATCHER_FIELD.get(event_name, ""), "")):
            continue
        for h in group.get("hooks", []):
            if h.get("type") == "command" and if_matches(h.get("if"), event_name, event):
                out.append(h)
    return out


def script_names(hook):
    """Basenames of the plugin scripts a hook entry runs."""
    text = " ".join([hook.get("command", "")] + list(hook.get("args") or []))
    return sorted(set(re.findall(r"([A-Za-z0-9_.-]+\.(?:sh|py))", text)))


_UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def _tmp_snapshot(token):
    # All /tmp/ace* entries (catches hashed/agent-keyed/ace_raw_* names, not just tokened ones);
    # run_fixture() diffs before/after and keeps only entries that are new AND touched during the
    # run, so files from concurrent real CC sessions that already existed are not false positives.
    # Real CC sessions on this machine (e.g. an installed v7 plugin) keep writing
    # /tmp/ace-*-<session-uuid>.* during the run; the fixture's ids are never UUIDs,
    # so a full UUID in a name not carrying our token marks a foreign file: skip it
    # (and never delete it).
    return {os.path.realpath(p) for p in glob.glob("/tmp/ace*")
            if token in p or not _UUID_RE.search(os.path.basename(p))}


def _mtime(p):
    try:
        return os.lstat(p).st_mtime
    except OSError:
        return 0


def _group_alive(pgid):
    try:
        os.killpg(pgid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def _run_hook(argv, raw, cwd, env):
    """Run one hook in its own process group; wait (bounded) for anything it left
    running in the background, then kill it. Returns (rc, out, err, wall_s, left_bg)."""
    t0 = time.monotonic()
    p = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True, cwd=cwd, env=env, start_new_session=True)
    try:
        out, err = p.communicate(raw, timeout=60)
        rc = p.returncode
    except subprocess.TimeoutExpired:
        p.kill()
        out, err = p.communicate()
        rc = "timeout"
    wall = time.monotonic() - t0
    left_bg = _group_alive(p.pid)
    deadline = time.monotonic() + 15
    while _group_alive(p.pid) and time.monotonic() < deadline:
        time.sleep(0.1)
    if _group_alive(p.pid):
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except OSError:
            pass
    return rc, out, err, wall, left_bg


def _remove(path):
    try:
        shutil.rmtree(path) if os.path.isdir(path) else os.unlink(path)
    except OSError:
        pass


def run_fixture(name):
    """Run every hook hooks.json routes this fixture's event to; return a result dict."""
    root = plugin_root()
    token = "e2e" + uuid.uuid4().hex[:12]
    sandbox = Path(tempfile.mkdtemp(prefix="ace-e2e-"))
    home, data, tmpdir, proj = (sandbox / d for d in ("home", "plugin-data", "tmp", "proj"))
    for d in (home, data, tmpdir, proj / ".claude", proj / "src" / "auth"):
        d.mkdir(parents=True)
    project_id, session_id, agent_id = "prj_" + token, token + "-session", "agent-" + token
    (proj / ".claude" / "settings.json").write_text(json.dumps({"projectId": project_id, "orgId": "org_" + token}))
    (proj / "src" / "auth" / "login.py").write_text("def login(): pass\n")
    (data / "python_path").write_text(sys.executable + "\n")  # what SessionStart caches (DESIGN §3.1)
    transcript = sandbox / "transcript.jsonl"
    transcript.write_text(
        json.dumps({"type": "user", "message": {"role": "user", "content": "Refactor the auth login flow"}}) + "\n"
        + json.dumps({"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": "toolu_e2e1", "name": "Edit",
             "input": {"file_path": str(proj / "src" / "auth" / "login.py")}}]}}) + "\n"
        + json.dumps({"type": "user", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "toolu_e2e1", "content": "ok"}]}}) + "\n"
        + json.dumps({"type": "assistant", "message": {"role": "assistant",
                      "content": [{"type": "text", "text": "Done."}]}}) + "\n")
    agent_transcript = sandbox / "subagents" / ("agent-%s.jsonl" % agent_id)
    agent_transcript.parent.mkdir()
    agent_transcript.write_text(transcript.read_text())

    def load(fixture):
        text = (FIXTURES / (fixture + ".json")).read_text()
        for k, v in (("__SESSION__", session_id), ("__TRANSCRIPT__", str(transcript)), ("__CWD__", str(proj)),
                     ("__AGENT_TRANSCRIPT__", str(agent_transcript)), ("__AGENT__", agent_id)):
            text = text.replace(k, v)
        return text

    raw = load(name)
    event = json.loads(raw)
    event_name = event["hook_event_name"]

    # Global ACE config: ace_stop_wrapper.sh:57-62 exits 0 silently when
    # ${XDG_CONFIG_HOME:-$HOME/.config}/ace/config.json is missing, which would make the Stop /
    # SubagentStop checks pass without ever reaching learn. XDG dirs are per run, not shared.
    xdg_config, xdg_data = sandbox / "xdg-config", sandbox / "xdg-data"
    (xdg_config / "ace").mkdir(parents=True)
    xdg_data.mkdir()
    (xdg_config / "ace" / "config.json").write_text(json.dumps({"serverUrl": "http://127.0.0.1:9", "apiToken": "e2e"}))

    cli_log = sandbox / "fake-ace-cli.log"
    env = dict(os.environ)
    env.update({
        "HOME": str(home), "CLAUDE_PLUGIN_DATA": str(data), "CLAUDE_PLUGIN_ROOT": str(root),
        "CLAUDE_PROJECT_DIR": str(proj), "XDG_CONFIG_HOME": str(xdg_config), "XDG_DATA_HOME": str(xdg_data),
        "TMPDIR": str(tmpdir), "ACE_FAKE_CLI_LOG": str(cli_log),
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
    })
    hooks_json = json.loads((root / "hooks" / "hooks.json").read_text())
    before = _tmp_snapshot(token)
    started = time.time() - 1
    runs = []
    sub = lambda s: s.replace("${CLAUDE_PLUGIN_ROOT}", str(root)).replace(
        "${CLAUDE_PLUGIN_DATA}", str(data)).replace("${CLAUDE_PROJECT_DIR}", str(proj))

    def argv_of(hook):
        if hook.get("args") is not None:
            return [sub(hook["command"])] + [sub(a) for a in hook["args"]]  # exec form
        return ["sh", "-c", sub(hook["command"])]  # shell form: sh -c on macOS/Linux (:455)

    if event_name in ("Stop", "SubagentStop"):
        # Stop/SubagentStop learn only after substantial work (Edit/Write/Bash) was accumulated by
        # PostToolUse; without it the hook exits early and never reaches `learn`. Seed through the
        # real accumulator hook so this stays independent of where the plugin keeps its db.
        seed_raw = load("PostToolBatch")
        seed = json.loads(seed_raw)
        # Seed through the real hooks.json PostToolBatch accumulator row (§9 G4).
        for seeder in routed_hooks(hooks_json, "PostToolBatch", seed):
            _run_hook(argv_of(seeder), seed_raw, str(proj), env)

    for hook in routed_hooks(hooks_json, event_name, event):
        rc, out, err, wall, left_bg = _run_hook(argv_of(hook), raw, str(proj), env)
        runs.append({"hook": hook, "scripts": script_names(hook), "rc": rc, "stdout": out, "stderr": err,
                     "wall_s": wall, "left_background_process": left_bg})

    calls = []
    if cli_log.exists():
        calls = [json.loads(l) for l in cli_log.read_text().splitlines() if l.strip()]
    claude_logs = home / ".claude" / "logs"
    new_tmp = sorted(p for p in _tmp_snapshot(token) - before if _mtime(p) >= started)
    for leftover in new_tmp:  # record, then clean up: the pre-v8 hooks still write /tmp
        _remove(leftover)
    return {
        "name": name, "event": event, "event_name": event_name, "runs": runs, "cli_calls": calls,
        "new_tmp": new_tmp,
        "home_claude_logs": sorted(str(p) for p in claude_logs.glob("ace*")) if claude_logs.exists() else [],
        "tmpdir_leftovers": sorted(str(p) for p in tmpdir.rglob("*")),
        "sandbox": sandbox,
    }


def output_problems(event_name, stdout):
    """[] when stdout is empty or one JSON object whose fields the event accepts."""
    text = stdout.strip()
    if not text:
        return []
    try:
        obj = json.loads(text)
    except ValueError as e:
        return ["stdout is not a single JSON object: %s: %r" % (e, text[:300])]
    if not isinstance(obj, dict):
        return ["stdout JSON is not an object: %r" % text[:300]]
    problems = []
    allowed_top = set(UNIVERSAL_KEYS) | {"hookSpecificOutput"}
    if event_name in TOP_LEVEL_DECISION_EVENTS:
        allowed_top |= {"decision", "reason"}
    extra = set(obj) - allowed_top
    if extra:
        problems.append("top-level keys not accepted for %s: %s" % (event_name, sorted(extra)))
    hso = obj.get("hookSpecificOutput")
    if hso is not None:
        if not isinstance(hso, dict) or hso.get("hookEventName") != event_name:
            problems.append("hookSpecificOutput.hookEventName must be %r: %r" % (event_name, hso))
        else:
            bad = set(hso) - {"hookEventName"} - HOOK_SPECIFIC_KEYS.get(event_name, set())
            if bad:
                problems.append("hookSpecificOutput keys not accepted for %s: %s" % (event_name, sorted(bad)))
            ctx = hso.get("additionalContext")
            if isinstance(ctx, str) and len(ctx) > CONTEXT_CAP:
                problems.append("additionalContext %d chars > %d cap" % (len(ctx), CONTEXT_CAP))
    for k in ("systemMessage",):
        if isinstance(obj.get(k), str) and len(obj[k]) > CONTEXT_CAP:
            problems.append("%s over the %d cap" % (k, CONTEXT_CAP))
    return problems
