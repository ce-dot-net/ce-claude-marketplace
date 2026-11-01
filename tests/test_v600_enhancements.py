"""
Tests for v6.0.0 CC 2.1.69+ Enhancements:
1. Async PostToolUse (non-blocking tool accumulation)
2. Consolidated SessionStart with source field
3. agent_id capture in tool accumulator
"""

import json
import os

PLUGIN_DIR = os.path.join(os.path.dirname(__file__), '..', 'plugins', 'ace')
HOOKS_JSON = os.path.join(PLUGIN_DIR, 'hooks', 'hooks.json')
POSTTOOLUSE_WRAPPER = os.path.join(PLUGIN_DIR, 'scripts', 'ace_posttooluse_wrapper.sh')
INSTALL_CLI = os.path.join(PLUGIN_DIR, 'scripts', 'ace_install_cli.sh')
ACCUMULATOR = os.path.join(PLUGIN_DIR, 'shared-hooks', 'ace_tool_accumulator.py')
AFTER_TASK = os.path.join(PLUGIN_DIR, 'shared-hooks', 'ace_after_task.py')


def _read(path):
    with open(path) as f:
        return f.read()


# ===========================================================================
# 1. Async PostToolUse
# ===========================================================================


class TestAsyncPostToolUse:
    """PostToolUse should be async for non-blocking tool accumulation."""

    def test_wrapper_outputs_async_true(self):
        """Wrapper must output {"async": true} for non-blocking execution."""
        content = _read(POSTTOOLUSE_WRAPPER)
        assert '"async"' in content, \
            "PostToolUse wrapper should output async flag"

    def test_async_output_before_accumulator_run(self):
        """Async output must be emitted BEFORE the accumulator python3 run."""
        content = _read(POSTTOOLUSE_WRAPPER)
        lines = content.splitlines()
        async_line = None
        accumulator_run_line = None
        for i, line in enumerate(lines):
            if '"async"' in line and 'echo' in line.lower():
                async_line = i
            if 'python3' in line and 'ACCUMULATOR' in line:
                accumulator_run_line = i
        assert async_line is not None, "No async echo found"
        assert accumulator_run_line is not None, "No accumulator call found"
        assert async_line < accumulator_run_line, \
            f"Async output (line {async_line}) must come before accumulator (line {accumulator_run_line})"

    def test_posttooluse_timeout_reasonable(self):
        """PostToolUse timeout should be <=30s (async, just SQLite writes)."""
        data = json.loads(_read(HOOKS_JSON))
        post_tool = data['hooks']['PostToolUse']
        hook = post_tool[0]['hooks'][0]
        # v8 (DESIGN §3): the accumulator is async, which carries no timeout (hooks doc :414)
        assert hook.get('async') is True and hook.get('timeout', 0) <= 30

    def test_no_empty_systemmessage_output(self):
        """Async hooks should not output empty systemMessage (use async flag instead)."""
        content = _read(POSTTOOLUSE_WRAPPER)
        assert '{"systemMessage": ""}' not in content, \
            "Async hook should use {\"async\": true} instead of empty systemMessage"


# ===========================================================================
# 2. Consolidated SessionStart
# ===========================================================================


class TestConsolidatedSessionStart:
    """SessionStart should be consolidated (single matcher with source branching)."""

    def test_single_sessionstart_matcher(self):
        """v8 (DESIGN §3): source routing moved into matchers: startup|clear, startup (async), compact."""
        data = json.loads(_read(HOOKS_JSON))
        matchers = [g['matcher'] for g in data['hooks']['SessionStart']]
        assert matchers == ['startup|clear', 'startup', 'compact']

    def test_sessionstart_reads_source_field(self):
        """No source branching left in the CLI check: resume never matches."""
        assert 'resume' not in [g['matcher'] for g in json.loads(_read(HOOKS_JSON))['hooks']['SessionStart']]

    def test_sessionstart_handles_compact_source(self):
        """compact is its own matcher routed to the re-inject shim."""
        groups = json.loads(_read(HOOKS_JSON))['hooks']['SessionStart']
        assert any(g['matcher'] == 'compact' and 'ace_sessionstart_compact.sh' in g['hooks'][0]['command']
                   for g in groups)

    def test_sessionstart_handles_resume_source(self):
        """The CLI check does not run on resume (matcher startup|clear only)."""
        groups = json.loads(_read(HOOKS_JSON))['hooks']['SessionStart']
        assert not any('resume' in g['matcher'] for g in groups)

    def test_no_separate_compact_in_hooks_json(self):
        """v8: the compact matcher exists and is NOT the CLI-check script."""
        groups = json.loads(_read(HOOKS_JSON))['hooks']['SessionStart']
        compact = [g for g in groups if g['matcher'] == 'compact']
        assert len(compact) == 1 and 'ace_install_cli' not in compact[0]['hooks'][0]['command']


# ===========================================================================
# 3. agent_id Capture
# ===========================================================================


class TestAgentIdCapture:
    """agent_id should be captured in tool accumulator for per-agent trajectory."""

    def test_accumulator_schema_has_agent_id(self):
        """Tool accumulator CREATE TABLE should include agent_id column."""
        content = _read(ACCUMULATOR)
        # Check in the CREATE TABLE statement
        create_idx = content.index('CREATE TABLE')
        create_end = content.index(')', create_idx)
        create_stmt = content[create_idx:create_end]
        assert 'agent_id' in create_stmt, \
            "CREATE TABLE should include agent_id column"

    def test_accumulator_append_accepts_agent_id(self):
        """append_tool function signature should include agent_id parameter."""
        content = _read(ACCUMULATOR)
        # Find append_tool def
        func_idx = content.index('def append_tool(')
        func_end = content.index(')', func_idx)
        func_sig = content[func_idx:func_end]
        assert 'agent_id' in func_sig, \
            "append_tool() should accept agent_id parameter"

    def test_accumulator_cli_has_agent_id_flag(self):
        """Accumulator CLI append command should have --agent-id flag."""
        content = _read(ACCUMULATOR)
        assert '--agent-id' in content, \
            "CLI should have --agent-id flag for append command"

    def test_posttooluse_extracts_agent_id(self):
        """PostToolUse wrapper should extract agent_id from hook event JSON."""
        content = _read(POSTTOOLUSE_WRAPPER)
        assert 'agent_id' in content, \
            "Wrapper should extract agent_id from event"

    def test_posttooluse_passes_agent_id_to_accumulator(self):
        """PostToolUse wrapper should pass agent_id to accumulator CLI."""
        content = _read(POSTTOOLUSE_WRAPPER)
        assert '--agent-id' in content, \
            "Wrapper should pass --agent-id to accumulator"

    def test_get_session_tools_returns_agent_id(self):
        """get_session_tools SELECT should include agent_id."""
        content = _read(ACCUMULATOR)
        # Find the SELECT in get_session_tools
        func_idx = content.index('def get_session_tools')
        func_region = content[func_idx:func_idx + 500]
        assert 'agent_id' in func_region, \
            "get_session_tools SELECT should include agent_id"
