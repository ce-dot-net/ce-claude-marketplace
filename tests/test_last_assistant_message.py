#!/usr/bin/env python3
"""
TDD RED tests for last_assistant_message support (v5.5.0).

Tests that ace_after_task.py extracts last_assistant_message from the hook event
and includes it as trace.result.summary in the ExecutionTrace.
"""

import json
import os
import sys
import unittest
from unittest.mock import patch, MagicMock
from io import StringIO

# Add paths for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'plugins', 'ace', 'shared-hooks'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'plugins', 'ace', 'shared-hooks', 'utils'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'plugins', 'ace', 'utils'))


class TestLastAssistantMessage(unittest.TestCase):
    """Test last_assistant_message extraction and trace inclusion."""

    def _build_event(self, last_assistant_message=None, session_id="test-session"):
        """Build a minimal hook event for testing."""
        event = {
            "hook_event_name": "Stop",
            "session_id": session_id,
            "transcript_path": "/tmp/fake-transcript.jsonl",
        }
        if last_assistant_message is not None:
            event["last_assistant_message"] = last_assistant_message
        return event

    def _run_main_and_capture_trace(self, event, tools=None):
        """
        Run main() with mocked dependencies and capture the trace sent to ace-cli.

        Returns the trace dict that would be sent to ace-cli learn --stdin.
        """
        if tools is None:
            # Default: one Edit tool (passes substantial work check)
            tools = [
                ("Edit", '{"file_path": "/tmp/test.py"}', '{"success": true}', "tool-1"),
            ]

        # Mock all external dependencies
        with patch('ace_after_task.get_context', return_value={'org': 'test-org', 'project': 'test-project'}), \
             patch('ace_after_task.build_trajectory_from_accumulated_tools', return_value=(
                 [{"step": 1, "tool": "Edit", "action": "Edited test.py", "result": "Success"}],
                 tools
             )), \
             patch('ace_after_task.get_user_prompt_from_transcript', return_value="implement feature X"), \
             patch('ace_after_task.recall_session', return_value=None), \
             patch('ace_after_task.log_execution_metrics'), \
             patch('ace_after_task.is_valid_pattern_id', return_value=True), \
             patch('ace_tool_accumulator.clear_session'), \
             patch('subprocess.run') as mock_run, \
             patch('sys.stdin', StringIO(json.dumps(event))), \
             patch('builtins.print') as mock_print:

            # Make subprocess.run return success
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=json.dumps({"learning_statistics": {"patterns_created": 1}}),
                stderr=""
            )

            # Import and run main
            from ace_after_task import main
            try:
                main()
            except SystemExit:
                pass

            # Extract the trace from subprocess.run call
            if mock_run.called:
                call_kwargs = mock_run.call_args
                trace_json = call_kwargs.kwargs.get('input') or call_kwargs[1].get('input', '')
                return json.loads(trace_json)

        return None

    def test_last_assistant_message_included_in_trace(self):
        """When event has last_assistant_message, trace.result.summary contains it."""
        event = self._build_event(last_assistant_message="I fixed the authentication bug by updating the JWT validation logic.")
        trace = self._run_main_and_capture_trace(event)

        self.assertIsNotNone(trace, "Trace should be sent to ace-cli")
        self.assertIn("summary", trace["result"], "trace.result should have 'summary' field")
        self.assertEqual(
            trace["result"]["summary"],
            "I fixed the authentication bug by updating the JWT validation logic."
        )

    def test_last_assistant_message_missing_gracefully(self):
        """When event lacks the field, trace.result.summary is None."""
        event = self._build_event()  # No last_assistant_message
        trace = self._run_main_and_capture_trace(event)

        self.assertIsNotNone(trace, "Trace should be sent to ace-cli")
        self.assertIn("summary", trace["result"], "trace.result should have 'summary' field")
        self.assertIsNone(trace["result"]["summary"], "summary should be None when field is missing")

    def test_last_assistant_message_truncated(self):
        """Message > 2000 chars is truncated to 2000."""
        long_message = "A" * 3000
        event = self._build_event(last_assistant_message=long_message)
        trace = self._run_main_and_capture_trace(event)

        self.assertIsNotNone(trace, "Trace should be sent to ace-cli")
        self.assertEqual(len(trace["result"]["summary"]), 2000, "summary should be truncated to 2000 chars")
        self.assertEqual(trace["result"]["summary"], "A" * 2000)

    def test_last_assistant_message_empty_string(self):
        """Empty string results in None (falsy check)."""
        event = self._build_event(last_assistant_message="")
        trace = self._run_main_and_capture_trace(event)

        self.assertIsNotNone(trace, "Trace should be sent to ace-cli")
        self.assertIsNone(trace["result"]["summary"], "summary should be None for empty string")


if __name__ == '__main__':
    unittest.main()
