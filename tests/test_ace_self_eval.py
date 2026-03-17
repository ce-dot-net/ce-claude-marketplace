"""TDD RED: ACE Self-Evaluation via Stop Hook Block.

Stop hook blocks once asking Claude to rate pattern helpfulness (0-100%).
On second stop, parses the response and writes result to state file.
"""
from pathlib import Path

PLUGIN_ROOT = Path(__file__).parent.parent / 'plugins' / 'ace'
SCRIPTS_DIR = PLUGIN_ROOT / 'scripts'
STATUSLINE = SCRIPTS_DIR / 'ace_statusline.sh'
STOP_WRAPPER = SCRIPTS_DIR / 'ace_stop_wrapper.sh'


class TestStopHookBlockForEval:
    """Stop hook should block once for self-evaluation when patterns were injected."""

    def test_stop_wrapper_checks_patterns_injected(self):
        """Must check if patterns were injected before blocking."""
        content = STOP_WRAPPER.read_text()
        assert any(p in content for p in ['ace-patterns-used', 'patterns_injected', 'PATTERNS_INJECTED']), \
            "Stop wrapper must check if patterns were injected"

    def test_stop_wrapper_has_block_decision(self):
        """Must return decision: block on first stop when patterns exist."""
        content = STOP_WRAPPER.read_text()
        assert '"decision"' in content and '"block"' in content, \
            "Stop wrapper must return decision: block"

    def test_stop_wrapper_block_reason_asks_evaluation(self):
        """Block reason must instruct Claude to rate helpfulness."""
        content = STOP_WRAPPER.read_text()
        assert any(p in content for p in ['ACE_REVIEW', 'ace_review', 'helpfulness', 'helpful']), \
            "Block reason must ask Claude to evaluate helpfulness"

    def test_stop_wrapper_has_approve_on_second_stop(self):
        """Must approve on second stop (after evaluation received)."""
        content = STOP_WRAPPER.read_text()
        assert '"approve"' in content, \
            "Stop wrapper must approve on second stop"

    def test_stop_wrapper_skips_eval_when_no_patterns(self):
        """Must skip evaluation (approve immediately) when no patterns injected."""
        content = STOP_WRAPPER.read_text()
        # Should have a fast-path for no patterns
        lines = content.splitlines()
        has_skip_logic = any(
            ('approve' in line and ('no_pattern' in line.lower() or 'skip' in line.lower() or '0' in line))
            or ('PATTERNS_INJECTED' in line and '0' in line)
            or ('ace-patterns-used' in line and 'not' in line.lower())
            for line in lines
        )
        # Alternative: check for conditional around the block
        has_conditional_block = 'if' in content and ('block' in content) and ('approve' in content)
        assert has_skip_logic or has_conditional_block, \
            "Stop wrapper must skip eval when no patterns were injected"


class TestStopHookParsesResponse:
    """Stop hook must parse Claude's self-evaluation from last_assistant_message."""

    def test_stop_wrapper_reads_last_assistant_message(self):
        """Must read last_assistant_message from event JSON."""
        content = STOP_WRAPPER.read_text()
        assert 'last_assistant_message' in content, \
            "Stop wrapper must read last_assistant_message"

    def test_stop_wrapper_parses_ace_review(self):
        """Must parse ACE_REVIEW: N% from the response."""
        content = STOP_WRAPPER.read_text()
        assert 'ACE_REVIEW' in content, \
            "Stop wrapper must parse ACE_REVIEW marker"

    def test_stop_wrapper_extracts_percentage(self):
        """Must extract the percentage number from ACE_REVIEW response."""
        content = STOP_WRAPPER.read_text()
        # Must have ACE_REVIEW extraction logic (grep/sed for the marker + number)
        assert 'ACE_REVIEW' in content and any(p in content for p in ['grep.*ACE_REVIEW', 'sed.*ACE_REVIEW', 'helpful_pct']), \
            "Stop wrapper must extract percentage from ACE_REVIEW marker"


class TestStopHookWritesResult:
    """Stop hook must write evaluation result to state file."""

    def test_stop_wrapper_writes_review_file(self):
        """Must write result to ace-review-result.json."""
        content = STOP_WRAPPER.read_text()
        assert 'ace-review-result.json' in content, \
            "Stop wrapper must write to ace-review-result.json"

    def test_review_file_in_project_logs(self):
        """Review file must be in .claude/data/logs/ (project-relative)."""
        content = STOP_WRAPPER.read_text()
        assert '.claude/data/logs/ace-review-result.json' in content, \
            "Review file must be in .claude/data/logs/"

    def test_stop_wrapper_includes_helpful_pct_in_systemmessage(self):
        """systemMessage must include the helpfulness percentage."""
        content = STOP_WRAPPER.read_text()
        assert any(p in content for p in ['helpful', 'HELPFUL_PCT', 'helpful_pct']), \
            "systemMessage must include helpfulness percentage"


class TestStatuslineReadsReview:
    """Statusline must read the evaluation result."""

    def test_statusline_reads_review_file(self):
        """Statusline must read ace-review-result.json."""
        content = STATUSLINE.read_text()
        assert 'ace-review-result.json' in content, \
            "Statusline must read ace-review-result.json"

    def test_statusline_shows_helpful_pct_from_review_file(self):
        """Statusline must read helpful_pct from ace-review-result.json, not just display it."""
        content = STATUSLINE.read_text()
        # Must actually source the value from the review result file
        assert 'ace-review-result' in content and 'helpful_pct' in content, \
            "Statusline must read helpful_pct from ace-review-result.json"


class TestEvalStateManagement:
    """State file management for evaluation flow."""

    def test_stop_wrapper_uses_eval_flag(self):
        """Must use a flag to track if eval was already requested."""
        content = STOP_WRAPPER.read_text()
        assert any(p in content for p in ['ace-eval-requested', 'EVAL_REQUESTED', 'eval_flag', 'ACE_EVAL']), \
            "Stop wrapper must use a flag to track eval state"

    def test_eval_flag_is_session_keyed(self):
        """Eval flag must be keyed by session to avoid cross-task contamination."""
        content = STOP_WRAPPER.read_text()
        # The eval flag path itself must contain SESSION_ID (not just any SESSION_ID usage)
        assert any(p in content for p in ['ace-eval-requested-${SESSION', 'ace-eval-${SESSION', 'ACE_EVAL.*SESSION']), \
            "Eval flag must be session-keyed"

    def test_sessionend_cleans_eval_flag(self):
        """SessionEnd must clean up eval flag."""
        sessionend = SCRIPTS_DIR / 'ace_sessionend_wrapper.sh'
        content = sessionend.read_text()
        assert any(p in content for p in ['ace-eval', 'eval-requested', 'ACE_EVAL']), \
            "SessionEnd must clean up eval flag"
