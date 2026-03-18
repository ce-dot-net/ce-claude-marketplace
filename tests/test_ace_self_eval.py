"""TDD: ACE Self-Evaluation via Stop Hook systemMessage.

Stop hook uses systemMessage (no blocking, no "error") to ask Claude to evaluate
pattern helpfulness. On second stop, parses the response and writes result to state file.
"""
from pathlib import Path

PLUGIN_ROOT = Path(__file__).parent.parent / 'plugins' / 'ace'
SCRIPTS_DIR = PLUGIN_ROOT / 'scripts'
STATUSLINE = SCRIPTS_DIR / 'ace_statusline.sh'
STOP_WRAPPER = SCRIPTS_DIR / 'ace_stop_wrapper.sh'


class TestStopHookSystemMessageEval:
    """Stop hook uses systemMessage to request eval — no decision:block, no error."""

    def test_stop_wrapper_uses_systemmessage_for_eval(self):
        """Must use systemMessage (not decision:block) to request evaluation."""
        content = STOP_WRAPPER.read_text()
        assert 'systemMessage' in content and 'ACE_REVIEW' in content, \
            "Stop wrapper must use systemMessage containing ACE_REVIEW request"

    def test_stop_wrapper_no_decision_block(self):
        """Must NOT use decision:block (causes 'error' display)."""
        content = STOP_WRAPPER.read_text()
        # Filter out comments
        exec_lines = [l for l in content.splitlines() if l.strip() and not l.strip().startswith('#')]
        exec_content = '\n'.join(exec_lines)
        assert '"decision"' not in exec_content or '"block"' not in exec_content, \
            "Stop wrapper must NOT use decision:block"

    def test_stop_wrapper_checks_patterns_injected(self):
        """Must check if patterns were injected before requesting eval."""
        content = STOP_WRAPPER.read_text()
        assert 'HAS_PATTERNS' in content or 'INJECTED' in content, \
            "Stop wrapper must check if patterns were injected"

    def test_stop_wrapper_skips_eval_when_no_patterns(self):
        """Must skip evaluation when no patterns injected."""
        content = STOP_WRAPPER.read_text()
        assert 'HAS_PATTERNS' in content, \
            "Stop wrapper must conditionally eval only when patterns exist"

    def test_stop_wrapper_human_developer_framing(self):
        """Eval request must frame helpfulness for human developer, not AI."""
        content = STOP_WRAPPER.read_text()
        assert any(p in content for p in ['human', 'developer', 'without ACE']), \
            "Eval must ask about helpfulness for human developer, not AI"


class TestStopHookParsesResponse:
    """Stop hook parses Claude's self-evaluation from last_assistant_message."""

    def test_stop_wrapper_reads_last_assistant_message(self):
        content = STOP_WRAPPER.read_text()
        assert 'last_assistant_message' in content

    def test_stop_wrapper_parses_ace_review(self):
        content = STOP_WRAPPER.read_text()
        assert 'ACE_REVIEW' in content

    def test_stop_wrapper_extracts_percentage(self):
        content = STOP_WRAPPER.read_text()
        assert any(p in content for p in ['grep', 'sed', '[0-9]']), \
            "Must extract percentage from ACE_REVIEW"


class TestStopHookWritesResult:
    """Stop hook writes evaluation result to state file."""

    def test_stop_wrapper_writes_review_file(self):
        content = STOP_WRAPPER.read_text()
        assert 'ace-review-result.json' in content

    def test_review_file_in_project_logs(self):
        content = STOP_WRAPPER.read_text()
        assert '.claude/data/logs/ace-review-result.json' in content

    def test_stop_wrapper_includes_helpful_pct_in_output(self):
        content = STOP_WRAPPER.read_text()
        assert 'helpful_pct' in content or 'HELPFUL_PCT' in content or 'helpful' in content


class TestStatuslineReadsReview:
    """Statusline reads evaluation result."""

    def test_statusline_reads_review_file(self):
        content = STATUSLINE.read_text()
        assert 'ace-review-result.json' in content

    def test_statusline_shows_helpful_pct(self):
        content = STATUSLINE.read_text()
        assert 'helpful_pct' in content


class TestEvalStateManagement:
    """State file management for evaluation flow."""

    def test_stop_wrapper_uses_eval_flag(self):
        content = STOP_WRAPPER.read_text()
        assert 'ace-eval-requested' in content or 'EVAL_FLAG' in content

    def test_eval_flag_is_session_keyed(self):
        content = STOP_WRAPPER.read_text()
        assert 'ace-eval-requested-${SESSION' in content

    def test_sessionend_cleans_eval_flag(self):
        sessionend = SCRIPTS_DIR / 'ace_sessionend_wrapper.sh'
        content = sessionend.read_text()
        assert 'ace-eval' in content
