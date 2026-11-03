#!/usr/bin/env python3
"""WP-D (v8) — the ONE domain-shift path: PostToolUse Read|Glob|Grep →
scripts/ace_posttooluse_domain_inject.sh (thin shim) → shared-hooks/ace_domain_shift.py.

DESIGN §3 (topology row "PostToolUse Read|Glob|Grep"), §3.1 (shim contract),
§4 (state layout), §5 C1/C3, §6 WP-D. Critic: T9 (PreToolUse `*` matcher cost),
T10 (double-fire, two last-domain files), T21 (machine-global /tmp state),
V13. CC doc facts: PostToolUse output shape cc_hooks_reference.md:2220-2245
(hookSpecificOutput.additionalContext), file-tool paths absolute :2193.

Every subprocess test runs the shim with the process cwd OUTSIDE the project:
v8 shims never `cd`, so the Python must resolve the project from the hook `cwd`.
The fake ace-cli (tests/wpd_harness.py) logs argv + stdin; the real one is never called.
"""
import importlib.util
import json
import uuid
from pathlib import Path

import pytest

from wpd_harness import HookEnv, SCRIPTS, SHARED, flag_value, shim_violations

SHIM = "ace_posttooluse_domain_inject.sh"
MODULE = SHARED / "ace_domain_shift.py"
SID = "sess-wpd-domain-shift"


def _load_module():
    assert MODULE.exists(), "shared-hooks/ace_domain_shift.py missing (DESIGN §6 WP-D, C6)"
    spec = importlib.util.spec_from_file_location("ace_domain_shift_under_test", MODULE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _pattern(pid, content, rank, reward=1.0, at_risk=False, rlid=None):
    return {
        "id": pid, "domain": "auth", "content": content, "section": "strategies",
        "confidence": 0.8, "helpful": 3, "harmful": 0, "evidence": [],
        "cumulative_v15_reward": reward, "isAtRisk": at_risk,
        "n_hot_pos": 1, "n_hot_neg": 0,
        "created_at": "2026-01-01T00:00:00Z", "birth_primary_lang": "python",
        "match_factors": {"bandit_rank": rank, "semantic_score": 0.5,
                          "retrieval_log_id": rlid if rlid is not None else rank + 100},
    }


ADVERSARIAL = 'Use "double quotes", back\\slash \\" esc, unicode é☃ and a\nnewline'

RESPONSE = {
    "similar_patterns": [
        _pattern("ctx-1111111111-aaaa", "second by bandit rank", 2),
        _pattern("ctx-2222222222-bbbb", ADVERSARIAL, 1),
    ],
    "count": 2,
    "retrieval_id": "ret-wpd-ds-001",
}


def _read_event(env, file_path, agent_id=None, tool="Read", tool_input=None):
    ev = {
        "session_id": SID,
        "transcript_path": str(env.tmp / "t.jsonl"),
        "cwd": str(env.proj),
        "permission_mode": "default",
        "hook_event_name": "PostToolUse",
        "tool_name": tool,
        "tool_input": tool_input if tool_input is not None else {"file_path": file_path},
        "tool_response": {"type": "text"},
        "tool_use_id": "toolu_wpd",
    }
    if agent_id:
        ev["agent_id"] = agent_id
        ev["agent_type"] = "general-purpose"
    return ev


@pytest.fixture
def env(tmp_path):
    e = HookEnv(tmp_path, project_id="prj-wpd-ds-%s" % uuid.uuid4().hex[:8])
    e.write_domains({"auth:local": {"count": 3}, "database:local": {"count": 1}})
    e.set_search_response(RESPONSE)
    return e


def _search_calls(env):
    return [c for c in env.cli_calls() if c["argv"][:1] == ["search"]]


def _ctx(proc):
    out = json.loads(proc.stdout)
    return out["hookSpecificOutput"]["additionalContext"]


# ── module / file layout ────────────────────────────────────────────────────

def test_domain_shift_module_exists():
    """WP-D/C6: new shared-hooks/ace_domain_shift.py is the domain-shift entry."""
    assert MODULE.exists(), "shared-hooks/ace_domain_shift.py missing (DESIGN §6 WP-D)"


def test_domain_shift_shim_is_thin_exec_python():
    """DESIGN §3.1: ace_posttooluse_domain_inject.sh is a thin shim (no jq/cat/cd,
    cached python_path, exec ace_domain_shift.py). Critic V13/T10."""
    assert shim_violations(SCRIPTS / SHIM, "ace_domain_shift.py") == []


def test_pretooluse_wrapper_deleted():
    """DESIGN §3 REMOVED: PreToolUse event + scripts/ace_pretooluse_wrapper.sh
    (critic T9: bash + 4-6 jq on every tool call; T10: second domain-shift path)."""
    assert not (SCRIPTS / "ace_pretooluse_wrapper.sh").exists()


# ── match_domain_to_path: identical semantics to the v7.1.14 bash matcher ───
# Expected values computed by running the bash `match_domain_to_path` from
# v7.1.14 scripts/ace_pretooluse_wrapper.sh (path lowercased by its caller).
PARITY = [
    ("auth", "/src/auth/login.py", True),
    ("authentication", "/src/auth/login.py", True),
    ("authentication", "/src/authentication/login.py", True),
    ("auth-core", "/src/authorization/x.py", True),
    ("ace-platform-system", "/ace/scripts/foo.ts", True),
    ("database", "/src/db/models.py", False),
    ("database", "/src/data/models.py", True),
    ("data-pipeline", "/src/datasets/x.py", True),
    ("payments", "/src/payment_service/pay.py", True),
    ("payments", "/src/pay/x.py", False),
    ("api", "/src/api/routes.py", True),
    ("ui", "/src/ui/button.tsx", False),
    ("hooks", "/plugins/ace/hooks/hooks.json", True),
    ("claude-plugins", "/plugins/ace/README.md", True),
    ("testing", "/repo/tests/test_x.py", True),
    ("testing", "/repo/Testing/Thing.py", True),
    ("python-testing", "/repo/src/PYTHON_utils.py", True),
    ("cache", "/src/caching/lru.py", True),
    ("cache", "/src/cac/lru.py", False),
    ("react-native", "/app/node_modules/react/index.js", True),
    ("go", "/src/go/main.go", False),
    ("docs", "/docs/readme.md", True),
    ("docs", "/src/doc/readme.md", False),
    ("security", "/src/secure/x.py", True),
    ("security", "/src/secrets.py", False),
    ("statusline", "/plugins/ace/scripts/ace_statusline.sh", True),
    ("utils", "/my project/utils dir/a.py", True),
]


@pytest.mark.parametrize("domain,path,expected", PARITY)
def test_match_domain_to_path_parity_with_v7_bash(domain, path, expected):
    """WP-D: Python port of match_domain_to_path with identical semantics
    (segments split on / . _ - and whitespace, segment and word >= 3 chars,
    exact word OR common prefix >= 4, case-insensitive)."""
    mod = _load_module()
    assert bool(mod.match_domain_to_path(domain, path)) is expected


# ── end-to-end through the shim ─────────────────────────────────────────────

def test_domain_shift_reads_domains_json_from_plugin_data_and_searches_once(env):
    """C3/§4: domains come from <plugin-data>/projects/<id>/domains.json (not
    /tmp/ace-domains-*); a domain entry triggers exactly ONE ace-cli spawn."""
    proc = env.run(SHIM, _read_event(env, str(env.proj / "src/auth/login_handler.py")))
    assert proc.returncode == 0, proc.stderr
    assert len(env.cli_calls()) == 1, env.cli_calls()
    assert len(_search_calls(env)) == 1


def test_domain_shift_query_is_file_basename_without_extension(env):
    """v7.1.9 contract kept: query = file basename minus extension, no domain token."""
    env.run(SHIM, _read_event(env, str(env.proj / "src/auth/login_handler.py")))
    calls = _search_calls(env)
    assert calls, "no search issued"
    assert calls[0]["stdin"].strip() == "login_handler"


def test_domain_shift_passes_top_k_8(env):
    """WP-D: `--top-k 8` (server-side bound for the per-tool hot path)."""
    env.run(SHIM, _read_event(env, str(env.proj / "src/auth/login_handler.py")))
    calls = _search_calls(env)
    assert calls, "no search issued"
    argv = calls[0]["argv"]
    assert flag_value(argv, "--top-k") == "8"
    assert "--stdin" in argv and "--json" in argv
    assert "--allowed-domains" not in argv and "--task-intent" not in argv


def test_domain_shift_reuses_task_session_id_without_pinning(env):
    """§16 P8: the task's tsid stays for STATE merging, but the search passes NO --pin-session
    (the server never credits domain-shift rows; the sqlite pin is the lock source)."""
    env.write_state(SID, None, task_session_id="tsid-main-from-ups")
    env.run(SHIM, _read_event(env, str(env.proj / "src/auth/login_handler.py")))
    calls = _search_calls(env)
    assert calls, "no search issued"
    assert "--pin-session" not in calls[0]["argv"]
    assert flag_value(calls[0]["argv"], "--session-id") == "tsid-main-from-ups", "unpinned session stamp (cli 4.3.1)"
    assert env.read_state(SID)["task_session_id"] == "tsid-main-from-ups"


def test_domain_shift_seeds_fresh_task_session_id_when_state_has_none(env):
    """v7.1.2 Change A kept for STATE: no tsid in state → fresh uuid4 stored; §16 P8: not pinned."""
    env.run(SHIM, _read_event(env, str(env.proj / "src/auth/login_handler.py")))
    calls = _search_calls(env)
    assert calls, "no search issued"
    assert "--pin-session" not in calls[0]["argv"]
    state = env.read_state(SID)
    assert state, "state not written"
    uuid.UUID(state["task_session_id"])


def test_domain_shift_emits_posttooluse_additional_context_json(env):
    """WP-D: emit {"hookSpecificOutput": {"hookEventName": "PostToolUse",
    "additionalContext": ...}} via json.dumps — valid JSON even for quotes,
    backslashes, unicode and newlines (the v7.1.10 bug class)."""
    proc = env.run(SHIM, _read_event(env, str(env.proj / "src/auth/login_handler.py")))
    out = json.loads(proc.stdout)
    hso = out["hookSpecificOutput"]
    assert hso["hookEventName"] == "PostToolUse"
    ctx = hso["additionalContext"]
    assert ctx.startswith('<ace-patterns-domain-shift domain="auth">')
    assert ctx.rstrip().endswith("</ace-patterns-domain-shift>")
    assert "ctx-2222222222-bbbb" in ctx
    assert len(ctx) <= 10000, "CC caps hook additionalContext at 10,000 chars"


def test_domain_shift_applies_same_strip_and_gate(env):
    """WP-D: same strip-and-gate as v7 (patterns_used_state.strip_and_gate):
    server-internal fields stripped, bandit_rank order kept."""
    proc = env.run(SHIM, _read_event(env, str(env.proj / "src/auth/login_handler.py")))
    ctx = _ctx(proc)
    for internal in ("match_factors", "birth_primary_lang", "created_at"):
        assert internal not in ctx, internal
    assert ctx.index("ctx-2222222222-bbbb") < ctx.index("ctx-1111111111-aaaa"), \
        "bandit_rank ordering lost"


def test_domain_shift_writes_patterns_used_state_with_retrieval_id(env):
    """C1/F-080: injected ids + retrieval_id + retrieval_log_ids land in this
    agent's state file under <plugin-data>/projects/<id>/sessions/<sid>/."""
    env.run(SHIM, _read_event(env, str(env.proj / "src/auth/login_handler.py")))
    state = env.read_state(SID)
    assert state is not None, "state file not written under plugin data"
    assert set(state["pattern_ids"]) >= {"ctx-1111111111-aaaa", "ctx-2222222222-bbbb"}
    assert state["retrieval_id"] == "ret-wpd-ds-001"
    assert state["retrieval_log_ids"], "retrieval_log_ids (F-080) missing"


def test_domain_shift_same_domain_twice_searches_once(env):
    """WP-D/§4: per-agent `domain-last-<agent>.txt` suppresses a repeat of the
    same domain (no second search, no output)."""
    env.run(SHIM, _read_event(env, str(env.proj / "src/auth/login_handler.py")))
    proc2 = env.run(SHIM, _read_event(env, str(env.proj / "src/auth/session_store.py")))
    assert proc2.returncode == 0
    assert proc2.stdout.strip() == ""
    assert len(_search_calls(env)) == 1
    last = env.session_dir(SID) / "domain-last-main.txt"
    assert last.exists() and last.read_text().strip() == "auth"


def test_domain_shift_per_agent_domain_history(env):
    """WP-D/§4: a subagent entering main's domain is a FIRST entry for that
    agent (its own domain-last file), so it gets its own search."""
    env.run(SHIM, _read_event(env, str(env.proj / "src/auth/login_handler.py")))
    proc = env.run(SHIM, _read_event(env, str(env.proj / "src/auth/login_handler.py"),
                                     agent_id="agent-sub-1"), extra_env={"ACE_LOCAL_REUSE": ""})  # §32 reuse off
    assert proc.returncode == 0
    assert len(_search_calls(env)) == 2
    assert (env.session_dir(SID) / "domain-last-agent-sub-1.txt").read_text().strip() == "auth"
    assert env.read_state(SID, "agent-sub-1") is not None


def test_domain_shift_selects_first_sorted_domain_and_strips_source_suffix(env):
    """WP-D parity: keys are `domain:source`; unique domain names are tried in
    sorted (sort -u) order and the first match wins."""
    env.write_domains({"zeta-auth:local": {}, "auth-core:global": {}})
    proc = env.run(SHIM, _read_event(env, str(env.proj / "src/auth/x_mod.py")))
    assert _ctx(proc).startswith('<ace-patterns-domain-shift domain="auth-core">')


def test_domain_shift_no_domains_json_no_cli_call(env):
    """§4/C3: without domains.json (UPS has not searched yet) → silent, 0 spawns."""
    env.domains_json().unlink()
    proc = env.run(SHIM, _read_event(env, str(env.proj / "src/auth/login_handler.py")))
    assert proc.returncode == 0 and proc.stdout.strip() == ""
    assert env.cli_calls() == []


def test_domain_shift_no_matching_domain_no_cli_call(env):
    """WP-D: path with no domain match → silent, 0 spawns."""
    proc = env.run(SHIM, _read_event(env, str(env.proj / "src/utils/helpers.py")))
    assert proc.returncode == 0 and proc.stdout.strip() == ""
    assert env.cli_calls() == []


def test_domain_shift_empty_basename_skips_search(env):
    """v7.1.9 guard kept: basename without its extension is empty → no search."""
    proc = env.run(SHIM, _read_event(env, str(env.proj / "src/auth/.py")))
    assert proc.returncode == 0 and proc.stdout.strip() == ""
    assert env.cli_calls() == []


def test_domain_shift_disabled_flag_short_circuits(env):
    """§4/critic T17: disabled flag at <plugin-data>/projects/<id>/sessions/<sid>/
    disabled.flag (not /tmp/ace-disabled-default.flag) → no spawn, no output."""
    env.disable(SID)
    proc = env.run(SHIM, _read_event(env, str(env.proj / "src/auth/login_handler.py")))
    assert proc.returncode == 0 and proc.stdout.strip() == ""
    assert env.cli_calls() == []


@pytest.mark.parametrize("tool,tool_input,stem", [
    ("Grep", {"pattern": "def foo", "path": "/repo/src/auth/token_utils.py"}, "token_utils"),
    ("Glob", {"pattern": "**/*.py", "path": "/repo/src/auth"}, "auth"),
])
def test_domain_shift_glob_and_grep_inputs(env, tool, tool_input, stem):
    """DESIGN §3 matcher Read|Glob|Grep: path from file_path // path // pattern
    (v7 PreToolUse parity)."""
    env.run(SHIM, _read_event(env, None, tool=tool, tool_input=tool_input))
    calls = _search_calls(env)
    assert len(calls) == 1, env.cli_calls()
    assert calls[0]["stdin"].strip() == stem


def test_domain_shift_logs_domain_shift_event_in_project_log(env):
    """Observability kept from the deleted PreToolUse path (critic T20): a
    `domain_shift` row in the PROJECT's .claude/data/logs/ace-relevance.jsonl
    (resolved from hook `cwd`, not the process cwd)."""
    env.run(SHIM, _read_event(env, str(env.proj / "src/auth/login_handler.py")))
    rows = [r for r in env.relevance_rows() if r.get("event") == "domain_shift"]
    assert rows, "no domain_shift row in the project relevance log"
    assert rows[-1].get("to_domain") == "auth"
    assert rows[-1].get("patterns_found") == 2
    assert not (env.elsewhere / ".claude").exists(), "wrote state relative to process cwd"


def test_domain_shift_no_tmp_state_files(env):
    """§0/§4, critic T21: no /tmp/ace-domain-* / /tmp/ace-domains-* state."""
    env.run(SHIM, _read_event(env, str(env.proj / "src/auth/login_handler.py")))
    leaked = list(Path("/tmp").glob("ace-*%s*" % env.project_id))
    assert leaked == [], leaked


@pytest.mark.parametrize("raw", ["", "not json at all", "{}", '{"tool_input": {}}'])
def test_domain_shift_bad_stdin_exits_zero_silently(env, raw):
    """WP-D: never fail the tool call — rc 0, empty stdout, no spawn."""
    proc = env.run(SHIM, None, raw_stdin=raw)
    assert proc.returncode == 0 and proc.stdout.strip() == ""
    assert env.cli_calls() == []


def test_domain_shift_zero_patterns_no_output(env):
    """WP-D: search returns nothing → no additionalContext emitted."""
    env.set_search_response({"similar_patterns": [], "count": 0})
    proc = env.run(SHIM, _read_event(env, str(env.proj / "src/auth/login_handler.py")))
    assert proc.returncode == 0 and proc.stdout.strip() == ""


def test_domain_shift_cli_failure_exits_zero_silently(env):
    """WP-D: ace-cli non-zero exit → rc 0, no stdout (stdout must stay JSON-only)."""
    proc = env.run(SHIM, _read_event(env, str(env.proj / "src/auth/login_handler.py")),
                   extra_env={"ACE_FAKE_CLI_EXIT": "1"})
    assert proc.returncode == 0 and proc.stdout.strip() == ""
