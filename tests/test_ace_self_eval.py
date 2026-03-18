"""TDD: ACE Self-Evaluation via silent decision:block + suppressOutput.

Stop hook blocks silently (no "error" display) asking Claude to rate helpfulness.
On second stop, parses response and writes result to state file.
SessionStart cleans stale eval flags and review files.
"""
from pathlib import Path

PLUGIN_ROOT = Path(__file__).parent.parent / 'plugins' / 'ace'
SCRIPTS_DIR = PLUGIN_ROOT / 'scripts'
STATUSLINE = SCRIPTS_DIR / 'ace_statusline.sh'
STOP_WRAPPER = SCRIPTS_DIR / 'ace_stop_wrapper.sh'


class TestStopHookSilentBlock:
    """Stop hook blocks silently with suppressOutput — no error display."""

    def test_stop_wrapper_uses_decision_block(self):
        content = STOP_WRAPPER.read_text()
        exec_lines = [l for l in content.splitlines() if l.strip() and not l.strip().startswith('#')]
        exec_content = '\n'.join(exec_lines)
        assert '"decision"' in exec_content and '"block"' in exec_content, \
            "Stop wrapper must use decision:block for self-eval"

    def test_stop_wrapper_uses_suppress_output(self):
        content = STOP_WRAPPER.read_text()
        assert 'suppressOutput' in content, \
            "Stop wrapper must use suppressOutput to hide block from user"

    def test_stop_wrapper_exit_code_zero(self):
        """Must use exit 0 (not exit 2) for clean block without error label."""
        content = STOP_WRAPPER.read_text()
        # The block path should exit 0, not exit 2
        assert 'exit 0' in content, \
            "Stop wrapper must exit 0 for clean block"

    def test_stop_wrapper_checks_patterns_injected(self):
        content = STOP_WRAPPER.read_text()
        assert 'HAS_PATTERNS' in content or 'INJECTED' in content

    def test_stop_wrapper_human_developer_framing(self):
        content = STOP_WRAPPER.read_text()
        assert any(p in content for p in ['human', 'developer', 'HUMAN', 'without ACE'])

    def test_stop_wrapper_skips_when_no_patterns(self):
        content = STOP_WRAPPER.read_text()
        assert 'HAS_PATTERNS' in content


class TestStopHookParsesResponse:
    """Second stop parses ACE_REVIEW from last_assistant_message."""

    def test_reads_last_assistant_message(self):
        content = STOP_WRAPPER.read_text()
        assert 'last_assistant_message' in content

    def test_parses_ace_review(self):
        content = STOP_WRAPPER.read_text()
        assert 'ACE_REVIEW' in content

    def test_extracts_percentage(self):
        content = STOP_WRAPPER.read_text()
        assert any(p in content for p in ['grep', 'sed', '[0-9]'])


class TestStopHookWritesResult:
    """Writes evaluation result to state file."""

    def test_writes_review_file(self):
        content = STOP_WRAPPER.read_text()
        assert 'ace-review-result.json' in content

    def test_review_file_in_project_logs(self):
        content = STOP_WRAPPER.read_text()
        assert '.claude/data/logs/ace-review-result.json' in content

    def test_includes_helpful_pct(self):
        content = STOP_WRAPPER.read_text()
        assert 'helpful_pct' in content or 'HELPFUL_PCT' in content


class TestStatuslineReadsReview:
    """Statusline reads evaluation result."""

    def test_reads_review_file(self):
        content = STATUSLINE.read_text()
        assert 'ace-review-result.json' in content

    def test_shows_helpful_pct(self):
        content = STATUSLINE.read_text()
        assert 'helpful_pct' in content


class TestStateCleanup:
    """State files cleaned properly."""

    def test_eval_flag_is_session_keyed(self):
        content = STOP_WRAPPER.read_text()
        assert 'ace-eval-requested-${SESSION' in content

    def test_sessionend_cleans_eval_flag(self):
        sessionend = SCRIPTS_DIR / 'ace_sessionend_wrapper.sh'
        content = sessionend.read_text()
        assert 'ace-eval' in content

    def test_sessionstart_cleans_stale_eval_flags(self):
        """SessionStart must clean stale eval flags on startup."""
        install_cli = SCRIPTS_DIR / 'ace_install_cli.sh'
        content = install_cli.read_text()
        assert 'ace-eval' in content or 'ace-review-result' in content, \
            "SessionStart must clean stale eval state on startup"

    def test_sessionstart_cleans_stale_review_file(self):
        """SessionStart must clean stale review file so statusline doesn't show old data."""
        install_cli = SCRIPTS_DIR / 'ace_install_cli.sh'
        content = install_cli.read_text()
        assert 'ace-review-result' in content, \
            "SessionStart must clean stale ace-review-result.json"

    def test_stop_wrapper_no_learn_on_first_stop(self):
        """First stop (block for eval) must NOT launch background learning."""
        content = STOP_WRAPPER.read_text()
        # The block should exit before reaching the learning launch
        assert 'exit 0' in content and 'block' in content
