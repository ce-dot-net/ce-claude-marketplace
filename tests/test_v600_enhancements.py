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
        """Async output must be emitted BEFORE the accumulator uv run."""
        content = _read(POSTTOOLUSE_WRAPPER)
        lines = content.splitlines()
        async_line = None
        accumulator_run_line = None
        for i, line in enumerate(lines):
            if '"async"' in line and 'echo' in line.lower():
                async_line = i
            if 'uv run' in line and 'ACCUMULATOR' in line:
                accumulator_run_line = i
        assert async_line is not None, "No async echo found"
        assert accumulator_run_line is not None, "No accumulator call found"
        assert async_line < accumulator_run_line, \
            f"Async output (line {async_line}) must come before accumulator (line {accumulator_run_line})"

    def test_posttooluse_timeout_reasonable(self):
        """PostToolUse timeout should be <=30s (async, just SQLite writes)."""
        data = json.loads(_read(HOOKS_JSON))
        post_tool = data['hooks']['PostToolUse']
        timeout = post_tool[0]['hooks'][0]['timeout']
        assert timeout <= 30000, \
            f"PostToolUse timeout {timeout}ms too high for async hook"

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
        """hooks.json should have exactly 1 SessionStart entry."""
        data = json.loads(_read(HOOKS_JSON))
        session_start = data['hooks']['SessionStart']
        assert len(session_start) == 1, \
            f"Expected 1 SessionStart matcher (consolidated), got {len(session_start)}"

    def test_sessionstart_reads_source_field(self):
        """SessionStart script should read source field from stdin JSON."""
        content = _read(INSTALL_CLI)
        # Must extract .source from the input JSON
        assert '.source' in content, \
            "Script should read .source field from event JSON"

    def test_sessionstart_handles_compact_source(self):
        """SessionStart script should handle source=compact for pattern restoration."""
        content = _read(INSTALL_CLI)
        # Must have a branch for compact source
        assert 'compact' in content.lower(), \
            "Script should handle compact source for pattern restoration"

    def test_sessionstart_handles_resume_source(self):
        """SessionStart script should handle source=resume (skip heavy checks)."""
        content = _read(INSTALL_CLI)
        assert 'resume' in content.lower(), \
            "Script should handle resume source"

    def test_no_separate_compact_in_hooks_json(self):
        """hooks.json should NOT have a separate compact matcher."""
        data = json.loads(_read(HOOKS_JSON))
        hooks_str = json.dumps(data)
        assert 'ace_sessionstart_compact' not in hooks_str, \
            "Separate compact script should be consolidated into main SessionStart"


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
