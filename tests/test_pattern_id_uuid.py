#!/usr/bin/env python3
"""
Test: Pattern ID validator accepts UUID v4/v5 format (post spec-06 Qdrant migration).

BUG:
    After the 2026-03-29 Qdrant migration, the ACE server returns UUID-format
    pattern IDs (e.g., '326df3ab-4d4c-5f16-8f63-3847cb2b9ac3') alongside the
    legacy 'ctx-*' format. The validator in plugins/ace/utils/validation.py
    only accepts 'ctx-*' IDs, so UUID IDs are silently filtered out in
    ace_before_task.py:260, the state file is never written, and
    playbook_used stays empty -> no reinforcement learning.

SERVER CONTRACT:
    Both formats are first-class and permanent.

TDD RED PHASE: These tests fail until validate_pattern_id accepts UUIDs.
"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
UTILS_PATH = PROJECT_ROOT / 'plugins' / 'ace' / 'utils'
sys.path.insert(0, str(UTILS_PATH))

from validation import validate_pattern_id, is_valid_pattern_id


class TestUuidPatternIds:
    """UUID v4/v5 pattern IDs (post-Qdrant migration) must be accepted."""

    def test_accept_uuid_v4(self):
        assert is_valid_pattern_id("326df3ab-4d4c-5f16-8f63-3847cb2b9ac3") is True

    def test_accept_uuid_v5(self):
        assert is_valid_pattern_id("09787e23-bd24-5550-b4b8-815f6ff7e87c") is True

    def test_accept_uppercase_uuid(self):
        # Server may send mixed/upper case for UUIDs
        assert is_valid_pattern_id("2A87D8E6-7F13-58BC-AB62-CF588D1CA33F") is True

    def test_accept_mixed_case_uuid(self):
        assert is_valid_pattern_id("326DF3ab-4d4C-5f16-8F63-3847cb2b9AC3") is True

    def test_validate_uuid_returns_no_error(self):
        is_valid, error = validate_pattern_id(
            "326df3ab-4d4c-5f16-8f63-3847cb2b9ac3"
        )
        assert is_valid is True
        assert error is None

    def test_reject_non_uuid_string(self):
        assert is_valid_pattern_id("not-a-uuid") is False

    def test_reject_truncated_uuid(self):
        assert is_valid_pattern_id("326df3ab-4d4c-5f16-8f63") is False

    def test_reject_uuid_with_extra_chars(self):
        assert is_valid_pattern_id(
            "326df3ab-4d4c-5f16-8f63-3847cb2b9ac3-extra"
        ) is False

    def test_reject_uuid_with_wrong_group_length(self):
        # 7 chars in first group instead of 8
        assert is_valid_pattern_id("326df3a-4d4c-5f16-8f63-3847cb2b9ac3") is False

    def test_reject_uuid_with_non_hex(self):
        assert is_valid_pattern_id("326df3ag-4d4c-5f16-8f63-3847cb2b9ac3") is False

    def test_reject_empty(self):
        assert is_valid_pattern_id("") is False

    def test_reject_none(self):
        assert is_valid_pattern_id(None) is False

    def test_ctx_format_still_accepted(self):
        # Backward compat
        assert is_valid_pattern_id("ctx-1234-abcd") is True
        assert is_valid_pattern_id("ctx-f7dc4cb517bb") is True

    def test_ctx_uppercase_still_rejected(self):
        # ctx-* path keeps lowercase-only rule
        assert is_valid_pattern_id("ctx-ABC") is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
