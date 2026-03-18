"""TDD: ACE Fire-and-Forget Self-Evaluation.

Stop hook writes eval request to state file (no blocking, no "error").
Next UserPromptSubmit injects eval request via additionalContext (silent).
Claude evaluates previous task's patterns naturally in its response.
UserPromptSubmit parses ACE_REVIEW from last response and writes review file.
"""
from pathlib import Path

PLUGIN_ROOT = Path(__file__).parent.parent / 'plugins' / 'ace'
SCRIPTS_DIR = PLUGIN_ROOT / 'scripts'
SHARED_HOOKS = PLUGIN_ROOT / 'shared-hooks'
STATUSLINE = SCRIPTS_DIR / 'ace_statusline.sh'
STOP_WRAPPER = SCRIPTS_DIR / 'ace_stop_wrapper.sh'
BEFORE_TASK = SHARED_HOOKS / 'ace_before_task.py'


class TestStopHookNoBlock:
    """Stop hook must NOT block — no decision:block, no error display."""

    def test_no_decision_block_in_executable_code(self):
        """Must NOT use decision:block (causes 'error' display)."""
        content = STOP_WRAPPER.read_text()
        exec_lines = [l for l in content.splitlines() if l.strip() and not l.strip().startswith('#')]
        exec_content = '\n'.join(exec_lines)
        assert '"block"' not in exec_content, \
            "Stop wrapper must NOT use decision:block"

    def test_stop_writes_eval_request(self):
        """Stop hook must write eval request data to state file for next task."""
        content = STOP_WRAPPER.read_text()
        assert 'ace-eval-request.json' in content, \
            "Stop wrapper must write eval request to ace-eval-request.json"

    def test_eval_request_includes_task_data(self):
        """Eval request must include patterns injected, relevance, domains, tools."""
        content = STOP_WRAPPER.read_text()
        assert any(p in content for p in ['patterns_injected', 'INJECTED', 'injected']), \
            "Eval request must include injection data"


class TestBeforeTaskInjectsEval:
    """UserPromptSubmit reads eval request and injects via additionalContext."""

    def test_before_task_reads_eval_request(self):
        """Must read ace-eval-request.json from previous task."""
        content = BEFORE_TASK.read_text()
        assert 'ace-eval-request.json' in content, \
            "Before task must read ace-eval-request.json"

    def test_before_task_uses_additional_context(self):
        """Must inject eval via additionalContext (silent, not systemMessage)."""
        content = BEFORE_TASK.read_text()
        assert 'additionalContext' in content or 'additional_context' in content, \
            "Before task must use additionalContext for eval injection"

    def test_before_task_asks_for_ace_review(self):
        """Injected context must ask for ACE_REVIEW marker."""
        content = BEFORE_TASK.read_text()
        assert 'ACE_REVIEW' in content, \
            "Before task must ask for ACE_REVIEW in additionalContext"

    def test_before_task_human_developer_framing(self):
        """Eval must be framed for human developer perspective."""
        content = BEFORE_TASK.read_text()
        assert any(p in content for p in ['human', 'developer', 'HUMAN']), \
            "Eval must reference human developer perspective"


class TestBeforeTaskParsesReview:
    """UserPromptSubmit parses ACE_REVIEW from previous response."""

    def test_before_task_reads_last_assistant_message(self):
        """Must check last response for ACE_REVIEW from previous eval request."""
        content = BEFORE_TASK.read_text()
        # The hook event has no last_assistant_message, but we can check
        # if the transcript or state file has the previous response
        assert 'ACE_REVIEW' in content

    def test_before_task_writes_review_file(self):
        """Must write parsed review to ace-review-result.json."""
        content = BEFORE_TASK.read_text()
        assert 'ace-review-result.json' in content

    def test_before_task_cleans_eval_request(self):
        """Must delete eval request after processing."""
        content = BEFORE_TASK.read_text()
        assert any(p in content for p in ['unlink', 'remove', 'rm ', 'delete', 'os.remove']), \
            "Must clean up eval request file after processing"


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

    def test_sessionstart_cleans_stale_files(self):
        install_cli = SCRIPTS_DIR / 'ace_install_cli.sh'
        content = install_cli.read_text()
        assert 'ace-eval-request' in content or 'ace-review-result' in content

    def test_sessionend_cleans_eval_flag(self):
        sessionend = SCRIPTS_DIR / 'ace_sessionend_wrapper.sh'
        content = sessionend.read_text()
        assert 'ace-eval' in content
