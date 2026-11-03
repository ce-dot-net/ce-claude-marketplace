"""
Tests for v6.0.0 CC 2.1.69+ Enhancements (v8: WP-C removed the stdout
`{"async": true}` echo assertions and the bash agent_id/argv assertions):
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

    def test_posttooluse_accumulator_is_async_or_bounded(self):
        """v8 (DESIGN §3): the accumulator handler is `async: true` in hooks.json
        (the stdout `{"async": true}` echo was never an output field, critic V3);
        until then its timeout must stay <= 30 s."""
        data = json.loads(_read(HOOKS_JSON))
        handlers = [h for grp in data['hooks']['PostToolBatch'] for h in grp['hooks']
                    if 'ace_posttooluse_wrapper.sh' in json.dumps(h)]
        assert handlers, "accumulator handler missing from PostToolBatch (DESIGN §9 G4)"
        # v8 (DESIGN §3): the accumulator is async, which carries no timeout (hooks doc :414)
        assert handlers[0].get('async') is True and handlers[0].get('timeout', 0) <= 30

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
        assert matchers == ['startup|clear|resume', 'startup', 'compact']

    def test_sessionstart_reads_source_field(self):
        """No source branching left in the CLI check: the source is the matcher."""
        assert 'startup|clear|resume' in [g['matcher'] for g in json.loads(_read(HOOKS_JSON))['hooks']['SessionStart']]

    def test_sessionstart_handles_compact_source(self):
        """compact is its own matcher routed to the re-inject shim."""
        groups = json.loads(_read(HOOKS_JSON))['hooks']['SessionStart']
        assert any(g['matcher'] == 'compact' and 'ace_sessionstart_compact.sh' in g['hooks'][0]['command']
                   for g in groups)

    def test_sessionstart_handles_resume_source(self):
        """The floor check + stale old-CC disabled.flag clearing also run on resume (CC updated between sessions)."""
        groups = json.loads(_read(HOOKS_JSON))['hooks']['SessionStart']
        assert any('resume' in g['matcher'] and 'ace_install_cli.sh' in g['hooks'][0]['command'] for g in groups)

    def test_no_separate_compact_in_hooks_json(self):
        """v8: the compact matcher exists and is NOT the CLI-check script."""
        groups = json.loads(_read(HOOKS_JSON))['hooks']['SessionStart']
        compact = [g for g in groups if g['matcher'] == 'compact']
        assert len(compact) == 1 and 'ace_install_cli' not in compact[0]['hooks'][0]['command']
        owners = [g['matcher'] for g in groups if 'ace_sessionstart_compact' in json.dumps(g)]
        assert owners == ['compact'], owners


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

    def test_record_tool_accepts_agent_id(self):
        """v8 C4: record_tool(session_id, agent_id, ...) is the accumulator API;
        agent_id comes from the stdin event inside Python (no bash/argv)."""
        content = _read(ACCUMULATOR)
        func_idx = content.index('def record_tool(')
        func_sig = content[func_idx:content.index(')', func_idx)]
        assert 'agent_id' in func_sig

    def test_get_session_tools_returns_agent_id(self):
        """get_session_tools SELECT should include agent_id."""
        content = _read(ACCUMULATOR)
        # Find the SELECT in get_session_tools
        func_idx = content.index('def get_session_tools')
        func_region = content[func_idx:func_idx + 500]
        assert 'agent_id' in func_region, \
            "get_session_tools SELECT should include agent_id"
