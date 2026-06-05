#!/usr/bin/env python3
"""
RED tests for issue #28 — ace-learn.md: F-080 doc update.

Scope: plugins/ace/commands/ace-learn.md must be updated to:
  1. Document --retrieval-id flag (new in ace-cli 4.0.1)
  2. Document --applied-log-ids flag (new in ace-cli 4.0.1)
  3. Document --pin-session flag (new in ace-cli 4.0.1)
  4. Describe task_intent as a SEARCH flag only, NOT a learn/trace field
  5. Remove/correct false claim that hooks do NOT send enriched trace
     (they now DO, via #24/#25)

All tests are expected to FAIL (RED) until ace-learn.md is updated.
"""
from pathlib import Path

import pytest

DOC = Path(__file__).resolve().parent.parent / "plugins" / "ace" / "commands" / "ace-learn.md"


@pytest.fixture(scope="module")
def doc_text():
    assert DOC.exists(), f"ace-learn.md not found at {DOC}"
    return DOC.read_text()


# ---------------------------------------------------------------------------
# 1. New flags must be documented
# ---------------------------------------------------------------------------

class TestNewFlagsDocumented:
    """ace-learn.md must document the three new ace-cli 4.0.1 flags."""

    def test_retrieval_id_flag_present(self, doc_text):
        """--retrieval-id flag must appear in ace-learn.md."""
        assert "--retrieval-id" in doc_text, (
            "ace-learn.md is missing '--retrieval-id' — "
            "this flag was added in ace-cli 4.0.1 and must be documented"
        )

    def test_applied_log_ids_flag_present(self, doc_text):
        """--applied-log-ids flag must appear in ace-learn.md."""
        assert "--applied-log-ids" in doc_text, (
            "ace-learn.md is missing '--applied-log-ids' — "
            "this flag was added in ace-cli 4.0.1 and must be documented"
        )

    def test_pin_session_flag_present(self, doc_text):
        """--pin-session flag must appear in ace-learn.md."""
        assert "--pin-session" in doc_text, (
            "ace-learn.md is missing '--pin-session' — "
            "this flag was added in ace-cli 4.0.1 and must be documented"
        )


# ---------------------------------------------------------------------------
# 2. task_intent must be documented as SEARCH-only, not a learn/trace field
# ---------------------------------------------------------------------------

class TestTaskIntentSearchOnly:
    """task_intent is a search flag — doc must not claim it is a learn/trace field."""

    def test_task_intent_described_as_search_flag(self, doc_text):
        """
        task_intent must be mentioned in ace-learn.md AND its description must
        indicate it belongs to the SEARCH command, not to learn/trace.
        The doc should clarify it is passed to ace-cli search (not ace-cli learn).
        """
        assert "task_intent" in doc_text, (
            "ace-learn.md does not mention 'task_intent' at all — "
            "it must be documented as a search-only flag"
        )

    def test_task_intent_not_described_as_learn_field(self, doc_text):
        """
        task_intent must NOT be described as a learn field or trace field.
        Any sentence pairing 'task_intent' with 'learn' as a flag/field is wrong.
        """
        import re
        # Find lines mentioning task_intent
        lines_with_task_intent = [
            line.strip()
            for line in doc_text.splitlines()
            if "task_intent" in line
        ]
        assert lines_with_task_intent, (
            "task_intent not found in ace-learn.md — must be documented as search-only"
        )
        for line in lines_with_task_intent:
            # Must not claim task_intent is a learn flag or trace field
            assert not re.search(
                r"ace-cli\s+learn\s+.*task.intent|task.intent.*learn\s+flag|task.intent.*trace\s+field",
                line, re.IGNORECASE
            ), (
                f"Line '{line}' incorrectly pairs task_intent with ace-cli learn — "
                "task_intent is a SEARCH flag only"
            )

    def test_task_intent_associated_with_search_context(self, doc_text):
        """
        The documentation of task_intent must associate it with search/retrieval,
        not with the learn command payload.
        The word 'search' must appear near 'task_intent' in the doc.
        """
        import re
        # Find a window of text around 'task_intent'
        idx = doc_text.find("task_intent")
        assert idx != -1, "task_intent not found in ace-learn.md"
        # Look in a ±300-character window for the word 'search'
        window_start = max(0, idx - 300)
        window_end = min(len(doc_text), idx + 300)
        window = doc_text[window_start:window_end]
        assert re.search(r"\bsearch\b", window, re.IGNORECASE), (
            "The word 'search' does not appear near 'task_intent' in ace-learn.md — "
            "task_intent must be explicitly associated with search/retrieval, not learn"
        )


# ---------------------------------------------------------------------------
# 3. False claim about enriched trace must be removed / corrected
# ---------------------------------------------------------------------------

class TestEnrichedTraceClaimCorrected:
    """
    ace-learn.md previously claimed hooks do NOT send enriched trace.
    Since #24/#25 landed, hooks DO send enriched trace.
    The old false claim must be absent.
    """

    def test_no_claim_hooks_do_not_send_enriched_trace(self, doc_text):
        """
        The doc must not contain language claiming hooks lack enriched trace data
        or that enriched trace is not sent by hooks.
        """
        import re
        false_claim_patterns = [
            r"hooks?\s+do\s+not\s+send\s+enriched",
            r"hooks?\s+don'?t\s+send\s+enriched",
            r"enriched\s+trace\s+is\s+not\s+sent\s+by\s+hooks?",
            r"no\s+enriched\s+trace\s+from\s+hooks?",
            r"hooks?\s+lack\s+enriched",
        ]
        for pattern in false_claim_patterns:
            assert not re.search(pattern, doc_text, re.IGNORECASE), (
                f"ace-learn.md still contains a false claim matching '{pattern}' — "
                "hooks DO send enriched trace since #24/#25; this claim must be removed"
            )

    def test_enriched_trace_sent_by_hooks_acknowledged(self, doc_text):
        """
        The doc must acknowledge (or at least not contradict) that hooks now
        send enriched trace data (retrieval_id, applied_log_ids).
        At minimum, one of the new flag names (--retrieval-id or --applied-log-ids)
        must appear, proving the enriched-trace flow is documented.
        """
        assert "--retrieval-id" in doc_text or "--applied-log-ids" in doc_text, (
            "ace-learn.md does not document any enriched-trace flags — "
            "hooks now send enriched trace via #24/#25; "
            "--retrieval-id and/or --applied-log-ids must be documented"
        )
