"""TDD RED: Deferred Learning Display — show async learning results.

Tests for:
- ace_stop_wrapper.sh: saves background learning results to state file
- ace_before_task.py: reads deferred results on next UserPromptSubmit
- ace_sessionend_wrapper.sh: cleans up state files
- ace_install_cli.sh: writes initial state on SessionStart
"""
from pathlib import Path

PLUGIN_ROOT = Path(__file__).parent.parent / 'plugins' / 'ace'
SCRIPTS_DIR = PLUGIN_ROOT / 'scripts'
SHARED_HOOKS_DIR = PLUGIN_ROOT / 'shared-hooks'


class TestStopWrapperSavesResults:
    """Stop hook async branch must save learning results instead of discarding"""

    def test_stop_wrapper_saves_to_state_file(self):
        script = SCRIPTS_DIR / 'ace_stop_wrapper.sh'
        content = script.read_text()
        assert 'ace-statusline-state.json' in content, \
            "Stop wrapper must save results to ace-statusline-state.json"

    def test_stop_wrapper_state_captures_output(self):
        """Background learning output must be written to state file, not discarded"""
        script = SCRIPTS_DIR / 'ace_stop_wrapper.sh'
        content = script.read_text()
        # Should save TEMP_OUTPUT or RESULT to state file
        assert any(p in content for p in ['TEMP_OUTPUT', 'LEARN_RESULT', 'learn_output']), \
            "Stop wrapper must capture learning output for state file"

    def test_stop_wrapper_state_includes_timestamp(self):
        """State file must include timestamp for freshness checking"""
        script = SCRIPTS_DIR / 'ace_stop_wrapper.sh'
        content = script.read_text()
        # Must write timestamp to state for staleness detection
        assert any(p in content for p in ['timestamp', 'date', 'TIME']), \
            "State file must include timestamp"

    def test_stop_wrapper_state_includes_pattern_stats(self):
        """State should include pattern created/updated/pruned counts"""
        script = SCRIPTS_DIR / 'ace_stop_wrapper.sh'
        content = script.read_text()
        assert any(p in content for p in ['patterns_created', 'created', 'updated', 'systemMessage']), \
            "State must include learning statistics"


class TestBeforeTaskReadsDeferred:
    """UserPromptSubmit handler reads deferred learning results"""

    def test_before_task_reads_state_file(self):
        script = SHARED_HOOKS_DIR / 'ace_before_task.py'
        content = script.read_text()
        assert 'ace-statusline-state.json' in content, \
            "Before task must read ace-statusline-state.json"

    def test_before_task_shows_deferred_learning(self):
        """Deferred learning message must appear in output"""
        script = SHARED_HOOKS_DIR / 'ace_before_task.py'
        content = script.read_text()
        assert any(p in content for p in ['last_learn', 'deferred', 'learning_result']), \
            "Before task must show deferred learning results"

    def test_before_task_marks_as_shown(self):
        """After displaying, mark results as shown to avoid repetition"""
        script = SHARED_HOOKS_DIR / 'ace_before_task.py'
        content = script.read_text()
        assert any(p in content for p in ['shown', 'displayed', 'cleared']), \
            "Before task must mark deferred results as shown"

    def test_before_task_skips_stale_results(self):
        """Ignore results older than 1 hour"""
        script = SHARED_HOOKS_DIR / 'ace_before_task.py'
        content = script.read_text()
        assert any(p in content for p in ['3600', 'stale', 'expired', 'max_age']), \
            "Before task must skip stale results (>1 hour)"


class TestSessionEndCleanup:
    """SessionEnd hook cleans up state files"""

    def test_sessionend_cleans_state_file(self):
        script = SCRIPTS_DIR / 'ace_sessionend_wrapper.sh'
        content = script.read_text()
        assert 'ace-statusline-state.json' in content, \
            "SessionEnd must clean up ace-statusline-state.json"


class TestSessionStartWritesInitialState:
    """SessionStart writes initial state with cached ace-cli status data"""

    def test_sessionstart_writes_state_on_startup(self):
        """On source=startup, write initial state with pattern stats"""
        script = SCRIPTS_DIR / 'ace_install_cli.sh'
        content = script.read_text()
        assert 'ace-statusline-state.json' in content, \
            "SessionStart must write initial state file"

    def test_sessionstart_queries_status_for_state(self):
        """Must query ace-cli status --json to populate state"""
        script = SCRIPTS_DIR / 'ace_install_cli.sh'
        content = script.read_text()
        # Must call ace-cli status to get pattern counts for state file
        assert 'status --json' in content, \
            "SessionStart must query ace-cli status --json for initial state"

    def test_sessionstart_state_includes_patterns_total(self):
        """Initial state must include total patterns count"""
        script = SCRIPTS_DIR / 'ace_install_cli.sh'
        content = script.read_text()
        assert any(p in content for p in ['total_patterns', 'patterns_total', 'TOTAL']), \
            "Initial state must include patterns total"

    def test_sessionstart_state_includes_helpful_total(self):
        """Initial state must include helpful total score"""
        script = SCRIPTS_DIR / 'ace_install_cli.sh'
        content = script.read_text()
        assert any(p in content for p in ['helpful_total', 'helpful', 'HELPFUL']), \
            "Initial state must include helpful total"


class TestStatuslineStateSchema:
    """Validate the shared state file schema"""

    def test_state_file_has_required_fields(self):
        """State file must contain all required fields for statusline display"""
        # This test validates the schema contract between:
        # - ace_stop_wrapper.sh (writer after learning)
        # - ace_install_cli.sh (writer on startup)
        # - ace_statusline.sh (reader on every refresh)
        # - ace_before_task.py (reader for deferred display)
        required_fields = [
            'patterns_total',
            'helpful_total',
            'last_learn_result',
            'last_learn_timestamp',
            'session_searches',
            'session_patterns_injected',
        ]
        # Read the statusline script to verify it reads these fields
        script = SCRIPTS_DIR / 'ace_statusline.sh'
        content = script.read_text()
        for field in required_fields:
            assert field in content, \
                f"Statusline must read '{field}' from state file"
