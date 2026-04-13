#!/usr/bin/env python3
"""TDD RED: spec-05 Phase 1 — Context Injection Optimization.

Tests for:
  A1: Skip empty injection when pattern_count == 0
  A2: Strip internal metadata fields from patterns before injection
  A3: Compact JSON (no indent)
  B1: sessionTitle in UserPromptSubmit hookSpecificOutput
  B3: refreshInterval in statusline setup
  A5: Log pattern content (truncated) in top_patterns
"""

import ast
import json
import re
import textwrap
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

PLUGIN_ROOT = Path(__file__).parent.parent / 'plugins' / 'ace'
BEFORE_TASK = PLUGIN_ROOT / 'shared-hooks' / 'ace_before_task.py'
RELEVANCE_LOGGER = PLUGIN_ROOT / 'shared-hooks' / 'utils' / 'ace_relevance_logger.py'
STATUSLINE_SETUP = PLUGIN_ROOT / 'commands' / 'ace-statusline-setup.md'

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_source(path: Path) -> str:
    """Read a source file and return its text."""
    assert path.exists(), f"Source file not found: {path}"
    return path.read_text()


def _parse_ast(path: Path) -> ast.Module:
    """Parse a Python source file into an AST."""
    return ast.parse(_read_source(path), filename=str(path))


# Fields that MUST be stripped before injection (internal / server-only metadata)
FIELDS_TO_STRIP = {
    'created_at', 'updated_at', 'last_used', 'impressions',
    'retrieval_count', 'root_cause', 'error_context', 'source',
    'source_project_id', 'source_project_name', 'local_helpful',
    'local_harmful', 'match_factors', 'observations', 'name',
}

# Fields that MUST survive stripping (essential for Claude context)
FIELDS_TO_KEEP = {
    'id', 'domain', 'content', 'confidence', 'helpful', 'harmful',
    'section', 'evidence',
}


# ===========================================================================
# A1: Skip empty injection when count == 0
# ===========================================================================

class TestSkipEmptyInjection:
    """When the server returns 0 patterns, the hook should NOT inject
    additionalContext at all — only a systemMessage informing the user."""

    def test_no_additional_context_when_zero_patterns(self):
        """Output JSON must NOT contain hookSpecificOutput.additionalContext
        when pattern_count == 0."""
        source = _read_source(BEFORE_TASK)

        # The current code always builds hookSpecificOutput with additionalContext
        # (lines 351-357) regardless of pattern_count.
        # After the fix, the code should gate additionalContext on pattern_count > 0.

        # Strategy: look for an explicit guard that skips additionalContext when
        # pattern_count == 0 or when there are no patterns.
        # We search for a conditional that prevents additionalContext when empty.
        has_skip_guard = bool(
            re.search(
                r'if\s+pattern_count\s*(==\s*0|<=\s*0|<\s*1)',
                source,
            )
            or re.search(
                r'if\s+not\s+pattern_list',
                source,
            )
        )

        # The guard must result in output WITHOUT additionalContext.
        # Check that there's a code path producing output without additionalContext
        # when no patterns are found.
        has_output_without_context = bool(
            re.search(
                r'output\s*=\s*\{[^}]*"systemMessage"[^}]*\}',
                source,
            )
            and re.search(
                r'(?:pattern_count\s*==\s*0|not\s+pattern_list).*?output\s*=',
                source,
                re.DOTALL,
            )
        )

        assert has_skip_guard and has_output_without_context, (
            "ace_before_task.py should skip additionalContext when pattern_count == 0. "
            "Currently it always includes hookSpecificOutput.additionalContext."
        )

    def test_zero_pattern_output_has_system_message_only(self):
        """When pattern_count == 0, the output should contain only systemMessage,
        without hookSpecificOutput."""
        source = _read_source(BEFORE_TASK)

        # After the fix, when pattern_count == 0 we expect the output block to
        # be: {"systemMessage": "..."} (no hookSpecificOutput key).
        # Look for the zero-pattern branch building a minimal output dict.
        pattern = re.compile(
            r'pattern_count\s*==\s*0.*?output\s*=\s*\{\s*"systemMessage"',
            re.DOTALL,
        )
        match = pattern.search(source)
        assert match is not None, (
            "Expected a code path that builds output = {\"systemMessage\": ...} "
            "when pattern_count == 0, but none found."
        )


# ===========================================================================
# A2: Strip internal metadata from patterns before injection
# ===========================================================================

class TestStripMetadata:
    """Patterns sent to Claude should NOT contain server-internal metadata.
    Only essential fields should survive."""

    def test_stripping_logic_exists(self):
        """ace_before_task.py must contain logic to strip metadata fields
        from each pattern before building ace_context."""
        source = _read_source(BEFORE_TASK)

        # Look for any of these indicators of stripping logic:
        # 1. A set/list/tuple of fields to strip
        # 2. A dict comprehension filtering keys
        # 3. Explicit `del pattern[field]` or `pattern.pop(field)`
        has_strip_set = any(
            field in source for field in [
                'created_at', 'updated_at', 'last_used',
                'match_factors', 'retrieval_count',
            ]
        )

        has_strip_logic = bool(
            re.search(r'\.pop\(', source)
            or re.search(r'del\s+\w+\[', source)
            or re.search(r'\{k:\s*v\s+for\s+k,\s*v\s+in.*if\s+k\s+(not\s+)?in', source)
            or re.search(r'FIELDS_TO_STRIP|STRIP_FIELDS|METADATA_FIELDS', source)
        )

        assert has_strip_set and has_strip_logic, (
            "ace_before_task.py should strip internal metadata fields "
            "(created_at, updated_at, last_used, match_factors, etc.) from "
            "patterns before injection. No stripping logic found."
        )

    def test_kept_fields_are_preserved(self):
        """The stripping logic should explicitly keep essential fields:
        id, domain, content, confidence, helpful, harmful, section, evidence."""
        source = _read_source(BEFORE_TASK)

        # Look for the kept-fields set or the strip logic referencing them
        kept_fields_mentioned = sum(
            1 for f in FIELDS_TO_KEEP if f"'{f}'" in source or f'"{f}"' in source
        )

        # At minimum, the kept fields should appear in a whitelist or the
        # strip logic should reference most of the stripped fields
        assert kept_fields_mentioned >= 6, (
            f"Expected at least 6 of the 8 essential fields to be referenced "
            f"in the stripping/whitelist logic, found {kept_fields_mentioned}."
        )

    def test_all_metadata_fields_are_stripped(self):
        """Every field in FIELDS_TO_STRIP must be handled by the stripping logic."""
        source = _read_source(BEFORE_TASK)

        # Check that each metadata field appears somewhere in the stripping context
        missing = []
        for field in FIELDS_TO_STRIP:
            # Field should appear in a strip set, pop call, or del statement
            if f"'{field}'" not in source and f'"{field}"' not in source:
                missing.append(field)

        assert not missing, (
            f"These metadata fields are not referenced in the stripping logic: "
            f"{sorted(missing)}"
        )


# ===========================================================================
# A3: Compact JSON (no indent)
# ===========================================================================

class TestCompactJSON:
    """The ace-patterns XML block should use compact JSON (no indent=2)
    to reduce token usage."""

    def test_no_indent_in_json_dumps(self):
        """json.dumps of the patterns response must NOT use indent=2."""
        source = _read_source(BEFORE_TASK)

        # Find the line that builds ace_context with json.dumps
        # Current code (line ~307): json.dumps(patterns_response, indent=2)
        # After fix: json.dumps(patterns_response) — no indent keyword
        ace_context_match = re.search(
            r'json\.dumps\(patterns_response\s*,\s*indent\s*=\s*2\)',
            source,
        )
        assert ace_context_match is None, (
            "ace_before_task.py still uses json.dumps(patterns_response, indent=2). "
            "Should use compact JSON: json.dumps(patterns_response) without indent."
        )

    def test_compact_json_used_for_ace_context(self):
        """The ace-patterns block should use json.dumps(response) without indent."""
        source = _read_source(BEFORE_TASK)

        # After the fix, the ace_context line should call json.dumps without indent
        compact_call = re.search(
            r'ace_context\s*=.*json\.dumps\(patterns_response\)(?!\s*,)',
            source,
        )
        assert compact_call is not None, (
            "Expected ace_context to use json.dumps(patterns_response) "
            "(compact, no indent), but this pattern was not found."
        )


# ===========================================================================
# B1: sessionTitle in UserPromptSubmit output
# ===========================================================================

class TestSessionTitle:
    """hookSpecificOutput should include a sessionTitle when patterns are found,
    summarizing the pattern count and domains."""

    def test_session_title_in_output(self):
        """hookSpecificOutput must include 'sessionTitle' key."""
        source = _read_source(BEFORE_TASK)

        has_session_title = bool(
            re.search(r'["\']sessionTitle["\']', source)
        )
        assert has_session_title, (
            "ace_before_task.py should include 'sessionTitle' in "
            "hookSpecificOutput when patterns are found."
        )

    def test_session_title_mentions_pattern_count(self):
        """sessionTitle should reference the number of patterns found."""
        source = _read_source(BEFORE_TASK)

        # The sessionTitle should be built from pattern_count
        has_count_in_title = bool(
            re.search(
                r'sessionTitle.*pattern_count|pattern_count.*sessionTitle',
                source,
                re.DOTALL,
            )
        )
        assert has_count_in_title, (
            "sessionTitle should mention pattern_count (e.g. '5 ACE patterns')."
        )

    def test_session_title_mentions_domains(self):
        """sessionTitle should reference the domains of matched patterns."""
        source = _read_source(BEFORE_TASK)

        # sessionTitle should include domain info
        has_domains_in_title = bool(
            re.search(
                r'sessionTitle.*domain|domain.*sessionTitle',
                source,
                re.DOTALL,
            )
        )
        assert has_domains_in_title, (
            "sessionTitle should mention the domains of matched patterns."
        )


# ===========================================================================
# B3: refreshInterval in statusline setup
# ===========================================================================

class TestRefreshInterval:
    """The statusline setup command should configure refreshInterval
    in the statusLine settings."""

    def test_refresh_interval_in_statusline_setup(self):
        """ace-statusline-setup.md should mention refreshInterval."""
        source = _read_source(STATUSLINE_SETUP)

        has_refresh_interval = 'refreshInterval' in source
        assert has_refresh_interval, (
            "ace-statusline-setup.md should mention 'refreshInterval' "
            "in the statusLine settings configuration."
        )

    def test_refresh_interval_in_jq_config(self):
        """The jq command that writes settings.json should include refreshInterval."""
        source = _read_source(STATUSLINE_SETUP)

        has_refresh_in_jq = bool(
            re.search(r'jq.*refreshInterval', source, re.DOTALL)
        )
        assert has_refresh_in_jq, (
            "The jq command in ace-statusline-setup.md should set "
            "refreshInterval in the statusLine config."
        )


# ===========================================================================
# A5: Log pattern content (truncated) in top_patterns
# ===========================================================================

class TestLogPatternContent:
    """ace_relevance_logger.py should include truncated 'content' field
    in the top_patterns list for debugging/analysis."""

    def test_content_field_in_top_patterns(self):
        """top_patterns entries should include a 'content' key."""
        source = _read_source(RELEVANCE_LOGGER)

        # Find the top_patterns list comprehension
        top_patterns_match = re.search(
            r'top_patterns\s*=\s*\[',
            source,
        )
        assert top_patterns_match is not None, (
            "Could not find top_patterns definition in ace_relevance_logger.py"
        )

        # Check that 'content' is one of the keys in the top_patterns dict
        # Current code only has: id, confidence, helpful, harmful, domain, section
        has_content_key = bool(
            re.search(
                r"top_patterns\s*=\s*\[[\s\S]*?'content'",
                source,
            )
        )
        assert has_content_key, (
            "top_patterns in ace_relevance_logger.py should include 'content' "
            "(truncated) for each pattern. Currently missing."
        )

    def test_content_is_truncated(self):
        """The content field in top_patterns should be truncated to avoid
        bloating the log file."""
        source = _read_source(RELEVANCE_LOGGER)

        # Look for truncation logic near the content key in top_patterns
        # e.g. p.get('content', '')[:100] or content[:80]
        has_truncation = bool(
            re.search(
                r"'content'.*?\[:\d+\]",
                source,
            )
            or re.search(
                r"content.*?\[:\d+\].*?top_patterns",
                source,
                re.DOTALL,
            )
        )
        assert has_truncation, (
            "The 'content' field in top_patterns should be truncated "
            "(e.g. [:100]) to prevent log bloat."
        )

    def test_content_logged_for_analysis(self):
        """Verify that the log_search_metrics method actually writes content
        data by checking the top_patterns dict structure."""
        source = _read_source(RELEVANCE_LOGGER)

        # Count the number of keys in the top_patterns dict comprehension
        # Current: 6 keys (id, confidence, helpful, harmful, domain, section)
        # Expected: 7 keys (+ content)
        key_matches = re.findall(
            r"'(\w+)':\s*p\.get\(",
            source,
        )
        assert 'content' in key_matches, (
            f"top_patterns dict should include 'content' key. "
            f"Found keys: {key_matches}"
        )
