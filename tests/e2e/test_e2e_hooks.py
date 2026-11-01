"""v8 target-behavior e2e tests (DESIGN §6 WP-F, §3 hook topology, critic T1/T25).

Gated: run only with ACE_E2E=1 (red on the pre-v8 base by design; WP-A..D turn
them green). Run: ACE_E2E=1 python3 -m pytest tests/e2e -q
Point ACE_PLUGIN_ROOT_UNDER_TEST at another plugin dir (e.g. a deployed cache copy)
to validate that instead of plugins/ace.
"""
import os
import shutil

import pytest

import ace_e2e_harness as H

pytestmark = pytest.mark.skipif(os.environ.get("ACE_E2E") != "1", reason="e2e target tests: set ACE_E2E=1")

FIXTURES = H.fixture_names()
_cache = {}


@pytest.fixture(scope="module", autouse=True)
def _cleanup_sandboxes():
    yield
    for r in _cache.values():
        shutil.rmtree(str(r["sandbox"]), ignore_errors=True)


def result(name):
    if name not in _cache:
        _cache[name] = H.run_fixture(name)
    return _cache[name]


def _cli_summary(r):
    return [c["argv"][:3] for c in r["cli_calls"]]


# DESIGN §3 table: (script, async) pairs each fixture's event must route to.
EXPECTED_ROUTES = {
    "SessionStart_startup": [("ace_install_cli.sh", False), ("ace_install_cli.sh", True)],
    "SessionStart_compact": [("ace_sessionstart_compact.sh", False)],
    "UserPromptSubmit_human": [("ace_before_task_wrapper.sh", False)],
    "UserPromptSubmit_task_notification": [("ace_before_task_wrapper.sh", False)],
    "PostToolUse_Write": [("ace_posttooluse_wrapper.sh", True)],
    "PostToolUse_Read": [("ace_posttooluse_domain_inject.sh", False), ("ace_posttooluse_wrapper.sh", True)],
    "PostToolUseFailure_Bash": [("ace_posttoolusefailure_wrapper.sh", True)],
    "SubagentStart": [("ace_subagent_start_wrapper.sh", False)],
    "SubagentStop": [("ace_subagent_stop_wrapper.sh", True)],
    "SubagentStop_empty_agent_type": [("ace_subagent_stop_wrapper.sh", True)],
    "Stop": [("ace_stop_wrapper.sh", True)],
    "PermissionDenied": [("ace_permission_denied_wrapper.sh", True)],
    "SessionEnd": [("ace_sessionend_wrapper.sh", False)],
}


def test_every_fixture_has_an_expected_route():
    """Harness self-check: each fixture file is covered by EXPECTED_ROUTES."""
    assert sorted(EXPECTED_ROUTES) == FIXTURES


@pytest.mark.parametrize("name", FIXTURES)
def test_e2e_routes_event_to_v8_hooks(name):
    """DESIGN §3 table: hooks.json routes each realistic event to exactly the v8 shims
    with the v8 sync/async mode (PreToolUse/PreCompact/PermissionRequest gone,
    PostToolUseFailure added, domain-shift on Read|Glob|Grep without `if`)."""
    r = result(name)
    got = sorted((s, bool(run["hook"].get("async"))) for run in r["runs"] for s in run["scripts"][:1])
    assert got == sorted(EXPECTED_ROUTES[name]), "routes for %s: got %s" % (name, got)


@pytest.mark.parametrize("name", FIXTURES)
def test_e2e_hook_exits_zero(name):
    """DESIGN §3.1: every shim exits 0 (no documented block is intended in ACE)."""
    r = result(name)
    bad = [(run["scripts"], run["rc"], run["stderr"][-500:]) for run in r["runs"] if run["rc"] != 0]
    assert not bad, bad


@pytest.mark.parametrize("name", FIXTURES)
def test_e2e_stdout_empty_or_valid_json_with_allowed_fields(name):
    """cc_hooks_reference.md:1048 (JSON alone on stdout), :1050 (10,000-char cap), per-event
    output tables; DESIGN §3: remove the stdout {"async": true} echo of the PostToolUse wrapper."""
    r = result(name)
    problems = {tuple(run["scripts"]): H.output_problems(r["event_name"], run["stdout"]) for run in r["runs"]}
    problems = {k: v for k, v in problems.items() if v}
    assert not problems, problems


@pytest.mark.parametrize("name", FIXTURES)
def test_e2e_no_tmp_or_claude_logs_artifacts(name):
    """DESIGN §0/§4: no writes to /tmp (state lives under CLAUDE_PLUGIN_DATA), no files in
    ~/.claude/logs (critic T25: 84,590 ace-background-subagent-* files), no mktemp leftovers."""
    r = result(name)
    assert r["new_tmp"] == [], "files created under /tmp: %s" % r["new_tmp"]
    assert r["home_claude_logs"] == [], "files created under ~/.claude/logs: %s" % r["home_claude_logs"]
    assert r["tmpdir_leftovers"] == [], "TMPDIR leftovers (mktemp not cleaned): %s" % r["tmpdir_leftovers"]


@pytest.mark.parametrize("name", FIXTURES)
def test_e2e_hook_wall_time_under_budget(name):
    """DESIGN §6 WP-F: each hook < 1.5 s with the fake CLI (measures our code, not Node);
    SessionEnd's hard plugin budget is 1.5 s (cc_hooks_reference.md:3580-3582)."""
    r = result(name)
    slow = [(run["scripts"], round(run["wall_s"], 2)) for run in r["runs"] if run["wall_s"] >= H.WALL_BUDGET_S]
    assert not slow, slow


@pytest.mark.parametrize("name", FIXTURES)
def test_e2e_hook_leaves_no_background_process(name):
    """DESIGN §3 Stop row: learning runs in the hook process itself -- no `&`, nothing left
    running after the hook exits (CC already runs Stop/SubagentStop with async: true)."""
    r = result(name)
    bg = [run["scripts"] for run in r["runs"] if run["left_background_process"]]
    assert not bg, "hooks left background processes: %s" % bg


def test_e2e_machine_prompt_makes_zero_cli_calls():
    """Critic T1 / DESIGN §6 WP-B(1): a <task-notification> UPS prompt (97-99.7 % of
    ace-agile searches) is skipped before any ace-cli spawn."""
    r = result("UserPromptSubmit_task_notification")
    assert r["cli_calls"] == [], _cli_summary(r)


def test_e2e_human_prompt_makes_exactly_one_search():
    """DESIGN §5 C2 / WP-B(2): a human prompt costs exactly ONE ace-cli spawn, a search
    (no --version probe, no whoami pre-check)."""
    r = result("UserPromptSubmit_human")
    calls = r["cli_calls"]
    assert len(calls) == 1 and calls[0]["argv"][:1] == ["search"], _cli_summary(r)


def test_e2e_subagentstop_empty_agent_type_makes_zero_cli_calls():
    """DESIGN §6 WP-C / cc_hooks_reference.md:2593-2595: SubagentStop with empty agent_type
    (CC-internal agents) exits before any learn."""
    r = result("SubagentStop_empty_agent_type")
    assert r["cli_calls"] == [], _cli_summary(r)


def test_e2e_posttooluse_accumulator_makes_zero_cli_calls():
    """DESIGN §3/§6 WP-C: the PostToolUse accumulator only records into sqlite (0 ace-cli)."""
    r = result("PostToolUse_Write")
    assert r["cli_calls"] == [], _cli_summary(r)


def test_e2e_sessionstart_startup_makes_no_whoami_or_network_cli_calls():
    """DESIGN §3 SessionStart row: slim startup -- NO whoami, NO network; only a
    --version read to fill the cli_version cache (§4) is allowed."""
    r = result("SessionStart_startup")
    other = [c["argv"] for c in r["cli_calls"] if c["argv"] != ["--version"]]
    assert other == [], other
