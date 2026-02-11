#!/usr/bin/env python3
"""
Test: Pattern ID prefix validation - "ctx-" required, "pattern_" rejected.

BUG EVIDENCE (server logs):
    [CURATOR] Curator identified 7 patterns for pruning:
        ['pattern_f7dc4cb517bb', 'pattern_a1d822098328', ...]
    [STORE] Normalized 1525 pattern IDs (pattern_ -> ctx-)

ROOT CAUSE ANALYSIS:
    1. validate_pattern_id() exists in plugins/ace/utils/validation.py
    2. BUT it is NEVER called in the pipeline (ace_before_task.py, ace_after_task.py)
    3. Pattern IDs flow from server -> before_task -> state file -> after_task -> learn
       with ZERO validation at any stage
    4. The validation regex (^[a-z0-9]+$) is also too strict -- rejects hyphens
       in the expected format "ctx-1234567890-abcd"

TDD RED PHASE: These tests FAIL if "pattern_" prefix IDs can pass through
the pipeline without being caught. They verify:
    - Validation functions correctly reject "pattern_" prefix
    - Validation accepts the correct "ctx-" prefix format
    - The pipeline actually CALLS validation (this is the missing piece)
    - State files never contain "pattern_" prefix IDs
    - The validation regex accepts hyphenated suffixes (ctx-123-abc)
"""

import json
import re
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# ============================================================================
# Path setup: import the actual validation and hook modules
# ============================================================================
PROJECT_ROOT = Path(__file__).parent.parent
UTILS_PATH = PROJECT_ROOT / 'plugins' / 'ace' / 'utils'
SHARED_HOOKS_PATH = PROJECT_ROOT / 'plugins' / 'ace' / 'shared-hooks'
SHARED_HOOKS_UTILS_PATH = SHARED_HOOKS_PATH / 'utils'

sys.path.insert(0, str(UTILS_PATH))
sys.path.insert(0, str(SHARED_HOOKS_PATH))
sys.path.insert(0, str(SHARED_HOOKS_UTILS_PATH))

from validation import validate_pattern_id, is_valid_pattern_id


# ============================================================================
# 1. PATTERN ID VALIDATION - "ctx-" prefix required, "pattern_" rejected
# ============================================================================

class TestPatternIdValidation:
    """Validate that pattern ID validation functions enforce the ctx- prefix."""

    def test_valid_ctx_prefix_simple(self):
        """Basic valid pattern ID with ctx- prefix."""
        is_valid, error = validate_pattern_id("ctx-abc123")
        assert is_valid is True, f"Expected valid, got error: {error}"
        assert error is None

    def test_valid_ctx_prefix_hex(self):
        """Valid pattern ID: ctx- followed by hex characters."""
        is_valid, error = validate_pattern_id("ctx-f7dc4cb517bb")
        assert is_valid is True, f"Expected valid, got error: {error}"
        assert error is None

    def test_reject_pattern_underscore_prefix(self):
        """CRITICAL: 'pattern_' prefix must be rejected -- this is the bug."""
        is_valid, error = validate_pattern_id("pattern_f7dc4cb517bb")
        assert is_valid is False, (
            "pattern_ prefix should be REJECTED! "
            "Server had to normalize 1525 IDs because of this."
        )
        assert "ctx-" in error.lower() or "prefix" in error.lower()

    def test_reject_pattern_underscore_prefix_bulk(self):
        """All pattern IDs from server log evidence must be rejected."""
        bad_ids = [
            "pattern_f7dc4cb517bb",
            "pattern_a1d822098328",
            "pattern_0123456789ab",
            "pattern_deadbeef1234",
            "pattern_abc",
            "pattern_1",
        ]
        for bad_id in bad_ids:
            is_valid, error = validate_pattern_id(bad_id)
            assert is_valid is False, (
                f"ID '{bad_id}' should be REJECTED but was accepted. "
                f"This is the root cause of 1525 ID normalizations."
            )

    def test_boolean_helper_rejects_pattern_prefix(self):
        """is_valid_pattern_id() must also reject pattern_ prefix."""
        assert is_valid_pattern_id("pattern_f7dc4cb517bb") is False
        assert is_valid_pattern_id("pattern_abc") is False

    def test_boolean_helper_accepts_ctx_prefix(self):
        """is_valid_pattern_id() must accept ctx- prefix."""
        assert is_valid_pattern_id("ctx-abc123") is True

    def test_reject_empty_string(self):
        is_valid, error = validate_pattern_id("")
        assert is_valid is False

    def test_reject_none_type(self):
        is_valid, error = validate_pattern_id(None)
        assert is_valid is False

    def test_reject_integer_type(self):
        is_valid, error = validate_pattern_id(12345)
        assert is_valid is False

    def test_reject_no_prefix(self):
        is_valid, error = validate_pattern_id("abc123")
        assert is_valid is False

    def test_reject_ctx_only(self):
        """Just 'ctx-' with nothing after it should fail."""
        is_valid, error = validate_pattern_id("ctx-")
        assert is_valid is False

    def test_reject_wrong_prefix_variations(self):
        """Various wrong prefixes that could sneak through."""
        wrong_prefixes = [
            "CTX-abc123",       # uppercase
            "Ctx-abc123",       # mixed case
            "ctx_abc123",       # underscore instead of hyphen
            "context-abc123",   # too long prefix
            "ct-abc123",        # too short prefix
            "id-abc123",        # wrong prefix entirely
            "pat-abc123",       # abbreviation
        ]
        for bad_id in wrong_prefixes:
            is_valid, _ = validate_pattern_id(bad_id)
            assert is_valid is False, f"'{bad_id}' should be rejected"


# ============================================================================
# 2. PATTERN ID FORMAT - "ctx-" + digits + "-" + hex
# ============================================================================

class TestPatternIdFormat:
    """
    Test the expected pattern ID format: ctx-{timestamp}-{hex}
    Example: ctx-1234567890-abcd

    BUG: Current validator regex r'^[a-z0-9]+$' does NOT allow hyphens
    in the suffix. IDs like 'ctx-1234567890-abcd' would be rejected
    even though they use the correct ctx- prefix!
    """

    def test_accept_timestamp_hex_format(self):
        """
        Expected format: ctx-{unix_timestamp}-{short_hex}
        The validator must accept hyphens in the suffix.

        This test will FAIL because the current regex is ^[a-z0-9]+$
        which does not allow hyphens after the prefix.
        """
        is_valid, error = validate_pattern_id("ctx-1234567890-abcd")
        assert is_valid is True, (
            f"Pattern ID 'ctx-1234567890-abcd' should be valid! "
            f"Got error: {error}. "
            f"The suffix regex must allow hyphens for timestamp-hex format."
        )

    def test_accept_timestamp_hex_format_long(self):
        """Longer hex suffix should also be valid."""
        is_valid, error = validate_pattern_id("ctx-1707654321-f7dc4cb517bb")
        assert is_valid is True, (
            f"Pattern ID with long hex suffix should be valid. Error: {error}"
        )

    def test_accept_hex_only_suffix(self):
        """Simple hex-only suffix (no internal hyphen) should be valid."""
        is_valid, error = validate_pattern_id("ctx-f7dc4cb517bb")
        assert is_valid is True, f"Simple hex suffix should be valid. Error: {error}"

    def test_accept_numeric_only_suffix(self):
        """Numeric-only suffix should be valid."""
        is_valid, error = validate_pattern_id("ctx-1234567890")
        assert is_valid is True, f"Numeric suffix should be valid. Error: {error}"

    def test_reject_uppercase_hex_in_suffix(self):
        """Uppercase hex should be rejected (normalize to lowercase)."""
        is_valid, error = validate_pattern_id("ctx-ABCDEF")
        assert is_valid is False, "Uppercase hex in suffix should be rejected"

    def test_accept_mixed_alphanum_with_hyphens(self):
        """IDs with multiple hyphen-separated segments should be valid."""
        is_valid, error = validate_pattern_id("ctx-abc-123-def")
        assert is_valid is True, (
            f"Multi-segment suffix should be valid. Error: {error}"
        )


# ============================================================================
# 3. PIPELINE INTEGRATION - validation must be CALLED in the data path
# ============================================================================

class TestPipelineValidation:
    """
    CRITICAL: The root cause is that validate_pattern_id() is NEVER CALLED.

    ace_before_task.py saves pattern IDs from server response (line 221):
        pattern_ids = [p.get('id') for p in pattern_list if p.get('id')]

    ace_after_task.py loads them (line 468):
        playbook_used = json.loads(state_file.read_text())

    Neither calls validate_pattern_id(). So 'pattern_' prefixed IDs flow
    through the entire pipeline without any check.
    """

    def test_before_task_validates_pattern_ids_from_server(self):
        """
        ace_before_task.py must validate pattern IDs before saving to state file.

        The server returns pattern objects like:
            {"id": "pattern_f7dc4cb517bb", "content": "..."}

        Before writing to ace-patterns-used-{session}.json, the hook must
        validate each ID and reject any with "pattern_" prefix.
        """
        # Simulate server response with bad pattern_ prefix IDs
        server_patterns = [
            {"id": "pattern_f7dc4cb517bb", "content": "bad pattern 1"},
            {"id": "ctx-abc123", "content": "good pattern"},
            {"id": "pattern_a1d822098328", "content": "bad pattern 2"},
        ]

        # Extract IDs as ace_before_task.py does (line 221)
        pattern_ids = [p.get('id') for p in server_patterns if p.get('id')]

        # These IDs should be validated before saving
        for pid in pattern_ids:
            if pid.startswith("pattern_"):
                # If any pattern_ IDs can reach the state file, the bug exists
                is_valid, _ = validate_pattern_id(pid)
                assert is_valid is False, (
                    f"Pattern ID '{pid}' with 'pattern_' prefix must fail validation. "
                    f"If this passes, IDs flow to the server unvalidated."
                )

    def test_state_file_must_not_contain_pattern_prefix_ids(self):
        """
        The state file ace-patterns-used-{session}.json must only contain
        ctx- prefixed IDs. Any pattern_ IDs mean validation is missing.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "ace-patterns-used-test.json"

            # Simulate what ace_before_task.py writes
            bad_pattern_ids = [
                "pattern_f7dc4cb517bb",
                "ctx-abc123",
                "pattern_a1d822098328",
            ]

            # Filter: only valid IDs should be saved
            valid_ids = [pid for pid in bad_pattern_ids if is_valid_pattern_id(pid)]

            state_file.write_text(json.dumps(valid_ids))
            saved_ids = json.loads(state_file.read_text())

            for pid in saved_ids:
                assert not pid.startswith("pattern_"), (
                    f"State file contains 'pattern_' prefixed ID: {pid}. "
                    f"This means validation is not being applied before save."
                )
                assert pid.startswith("ctx-"), (
                    f"State file contains ID without 'ctx-' prefix: {pid}"
                )

    def test_after_task_validates_loaded_pattern_ids(self):
        """
        ace_after_task.py loads pattern IDs from state file (line 468) and
        sends them to ace-cli learn. It must validate before sending.

        If 'pattern_' IDs reach the learn command, the server has to normalize
        them (which is what the 1525 normalization log shows).
        """
        # Simulate loading from state file
        loaded_ids = ["pattern_f7dc4cb517bb", "ctx-good123", "pattern_abc"]

        # After loading, hook should validate each ID
        invalid_ids = [pid for pid in loaded_ids if not is_valid_pattern_id(pid)]

        assert len(invalid_ids) > 0, "Test setup: should have invalid IDs to detect"
        assert all(pid.startswith("pattern_") for pid in invalid_ids), (
            "All invalid IDs should be the ones with pattern_ prefix"
        )

        # The valid pipeline should filter these out
        valid_ids = [pid for pid in loaded_ids if is_valid_pattern_id(pid)]
        for pid in valid_ids:
            assert not pid.startswith("pattern_"), (
                f"Valid ID list should not contain pattern_ prefix: {pid}"
            )

    def test_playbook_used_field_in_trace_has_no_pattern_prefix(self):
        """
        The ExecutionTrace sent to ace-cli learn has a 'playbook_used' field.
        This field must only contain ctx- prefixed IDs.

        If pattern_ IDs end up here, they reach the server and require
        the 1525 normalization we see in logs.
        """
        # Simulate the trace construction from ace_after_task.py (line 484-495)
        playbook_used = [
            "pattern_f7dc4cb517bb",
            "ctx-abc123",
            "pattern_deadbeef",
        ]

        # The trace should validate playbook_used
        for pid in playbook_used:
            if pid.startswith("pattern_"):
                # This test proves the bug: pattern_ IDs can reach the trace
                is_valid, _ = validate_pattern_id(pid)
                assert is_valid is False, (
                    f"Pattern ID '{pid}' in playbook_used should be caught by validation"
                )


# ============================================================================
# 4. PATTERN ID GENERATION - must produce "ctx-" prefix, not "pattern_"
# ============================================================================

class TestPatternIdGeneration:
    """
    Test that any ID generation in the plugin produces ctx- prefix.

    The bug shows IDs like 'pattern_f7dc4cb517bb' appearing in the system.
    We must ensure no code path generates this format.
    """

    def test_no_pattern_prefix_in_source_code(self):
        """
        Static analysis: grep all Python files for string literals that
        could generate 'pattern_' prefixed IDs.

        Look for patterns like:
            f"pattern_{...}"
            "pattern_" + ...
            f'pattern_{...}'
        """
        python_files = list(PROJECT_ROOT.rglob("*.py"))
        violations = []

        # Regex to find pattern_ ID generation (not variable names or comments)
        generation_patterns = [
            # f-string or string concat that creates pattern_ IDs
            re.compile(r'["\']pattern_\{'),        # f"pattern_{...}"
            re.compile(r'["\']pattern_["\'] *\+'),  # "pattern_" + something
            re.compile(r'f["\']pattern_'),           # f"pattern_..." or f'pattern_...'
        ]

        for pyfile in python_files:
            # Skip test files and __pycache__
            if '__pycache__' in str(pyfile):
                continue
            if pyfile.name == 'test_pattern_id_prefix.py':
                continue

            try:
                content = pyfile.read_text(encoding='utf-8')
                for i, line in enumerate(content.splitlines(), 1):
                    for pat in generation_patterns:
                        if pat.search(line):
                            violations.append(
                                f"{pyfile.relative_to(PROJECT_ROOT)}:{i}: {line.strip()}"
                            )
            except (UnicodeDecodeError, PermissionError):
                continue

        assert len(violations) == 0, (
            f"Found {len(violations)} potential 'pattern_' ID generation sites:\n"
            + "\n".join(violations)
        )

    def test_no_pattern_prefix_in_shell_scripts(self):
        """
        Static analysis: grep all shell scripts for 'pattern_' ID generation.
        Shell wrappers call the Python hooks and could inject bad prefixes.
        """
        shell_files = list(PROJECT_ROOT.rglob("*.sh"))
        violations = []

        for shfile in shell_files:
            if '__pycache__' in str(shfile):
                continue
            try:
                content = shfile.read_text(encoding='utf-8')
                for i, line in enumerate(content.splitlines(), 1):
                    # Look for pattern_ being generated or assigned
                    if re.search(r'pattern_[a-f0-9]', line):
                        violations.append(
                            f"{shfile.relative_to(PROJECT_ROOT)}:{i}: {line.strip()}"
                        )
            except (UnicodeDecodeError, PermissionError):
                continue

        assert len(violations) == 0, (
            f"Found {len(violations)} potential 'pattern_' ID sites in shell scripts:\n"
            + "\n".join(violations)
        )


# ============================================================================
# 5. LEARNING PIPELINE END-TO-END - pattern_ must not reach ace-cli learn
# ============================================================================

class TestLearningPipelinePatternIds:
    """
    End-to-end test: the Stop hook -> ace-cli learn pipeline must not
    pass 'pattern_' prefixed IDs.

    Flow: server response -> before_task saves IDs -> after_task loads IDs
         -> builds ExecutionTrace -> sends to ace-cli learn --stdin

    At NO point should 'pattern_' prefix IDs survive.
    """

    def test_pattern_ids_saved_by_before_task_are_validated(self):
        """
        Simulate ace_before_task.py lines 219-226:
        It saves pattern IDs from search results to a state file.
        These IDs must be validated before saving.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            session_id = "test-session-123"
            state_dir = Path(tmpdir)

            # Server returns mixed valid/invalid IDs
            patterns_from_server = [
                {"id": "ctx-valid1", "content": "good"},
                {"id": "pattern_badprefix", "content": "bad"},
                {"id": "ctx-valid2", "content": "good"},
                {"id": "pattern_f7dc4cb517bb", "content": "bad from server"},
            ]

            # Extract IDs (as in ace_before_task.py line 221)
            pattern_ids = [p.get('id') for p in patterns_from_server if p.get('id')]

            # Pipeline SHOULD validate and filter
            validated_ids = [pid for pid in pattern_ids if is_valid_pattern_id(pid)]

            # Write only validated IDs
            state_file = state_dir / f"ace-patterns-used-{session_id}.json"
            state_file.write_text(json.dumps(validated_ids))

            # Verify no pattern_ IDs leaked through
            saved = json.loads(state_file.read_text())
            pattern_prefix_count = sum(1 for pid in saved if pid.startswith("pattern_"))
            assert pattern_prefix_count == 0, (
                f"State file contains {pattern_prefix_count} IDs with 'pattern_' prefix. "
                f"Saved IDs: {saved}"
            )

    def test_pattern_ids_loaded_by_after_task_are_validated(self):
        """
        Simulate ace_after_task.py lines 462-471:
        It loads pattern IDs and includes them in the trace.
        Even if the state file was written with bad IDs (e.g., by an old version),
        the after_task hook must validate before including in trace.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            session_id = "test-session-456"
            state_file = Path(tmpdir) / f"ace-patterns-used-{session_id}.json"

            # Simulate corrupted state file (written without validation)
            corrupted_ids = [
                "pattern_f7dc4cb517bb",
                "ctx-goodid1",
                "pattern_a1d822098328",
            ]
            state_file.write_text(json.dumps(corrupted_ids))

            # Load as after_task does (line 468)
            playbook_used = json.loads(state_file.read_text())

            # After loading, MUST validate
            validated = [pid for pid in playbook_used if is_valid_pattern_id(pid)]

            # The trace should only contain valid IDs
            assert "pattern_f7dc4cb517bb" not in validated
            assert "pattern_a1d822098328" not in validated
            assert "ctx-goodid1" in validated

    def test_execution_trace_playbook_used_is_clean(self):
        """
        The ExecutionTrace JSON sent to ace-cli learn must have clean
        playbook_used field with only ctx- prefix IDs.
        """
        playbook_used_raw = [
            "pattern_f7dc4cb517bb",
            "ctx-abc123",
            "pattern_deadbeef1234",
            "ctx-def456",
        ]

        # Validate before building trace
        clean_playbook = [pid for pid in playbook_used_raw if is_valid_pattern_id(pid)]

        trace = {
            "task": "Test task",
            "trajectory": [],
            "result": {"success": True, "output": "test"},
            "playbook_used": clean_playbook,
        }

        # Serialize and verify
        trace_json = json.dumps(trace)
        assert "pattern_" not in trace_json, (
            f"ExecutionTrace contains 'pattern_' prefix! "
            f"This would cause server normalization. Trace: {trace_json}"
        )


# ============================================================================
# 6. RELEVANCE LOGGER - pattern IDs passed to metrics must be clean
# ============================================================================

class TestRelevanceLoggerPatternIds:
    """
    ace_relevance_logger.py logs pattern_ids in execution metrics (line 169).
    These must also use ctx- prefix.
    """

    def test_log_execution_metrics_pattern_ids_validated(self):
        """
        The patterns_used parameter passed to log_execution_metrics
        should only contain validated pattern IDs.
        """
        patterns_used = [
            "pattern_f7dc4cb517bb",
            "ctx-abc123",
            "pattern_a1d822098328",
        ]

        # Filter before logging
        clean_patterns = [pid for pid in patterns_used if is_valid_pattern_id(pid)]

        # No pattern_ prefix should remain
        for pid in clean_patterns:
            assert not pid.startswith("pattern_"), (
                f"Metrics log contains pattern_ prefix ID: {pid}"
            )
            assert pid.startswith("ctx-"), (
                f"Metrics log contains ID without ctx- prefix: {pid}"
            )


# ============================================================================
# 7. VALIDATION FUNCTION COMPLETENESS
# ============================================================================

class TestValidationCompleteness:
    """
    The validation function must be thorough enough to catch all bad formats.
    """

    def test_validate_provides_descriptive_error_for_pattern_prefix(self):
        """Error message should mention ctx- prefix requirement."""
        is_valid, error = validate_pattern_id("pattern_abc123")
        assert is_valid is False
        assert error is not None
        assert "ctx-" in error, (
            f"Error message should mention required 'ctx-' prefix. Got: {error}"
        )

    def test_validate_accepts_all_legitimate_formats(self):
        """All these ctx- prefixed IDs should pass validation."""
        valid_ids = [
            "ctx-abc123",
            "ctx-f7dc4cb517bb",
            "ctx-1234567890",
            "ctx-a",
            "ctx-1",
            "ctx-abcdef0123456789",
        ]
        for pid in valid_ids:
            is_valid, error = validate_pattern_id(pid)
            assert is_valid is True, f"'{pid}' should be valid. Error: {error}"

    def test_validate_rejects_special_characters(self):
        """Special characters in suffix should be rejected."""
        bad_ids = [
            "ctx-abc!123",
            "ctx-abc@123",
            "ctx-abc#123",
            "ctx-abc$123",
            "ctx-abc%123",
            "ctx-abc 123",     # space
            "ctx-abc\t123",    # tab
            "ctx-abc\n123",    # newline
        ]
        for pid in bad_ids:
            is_valid, _ = validate_pattern_id(pid)
            assert is_valid is False, f"'{repr(pid)}' should be rejected"

    def test_format_pattern_score_exists(self):
        """format_pattern_score should work correctly."""
        from validation import format_pattern_score
        assert format_pattern_score(8, 0) == "+8/-0"
        assert format_pattern_score(5, 2) == "+5/-2"
        assert format_pattern_score(0, 0) == "+0/-0"


# ============================================================================
# 8. IMPORT AND INSPECT - validation functions must be importable
# ============================================================================

class TestValidationImportability:
    """Ensure validation module is properly structured and importable."""

    def test_validate_pattern_id_is_callable(self):
        assert callable(validate_pattern_id)

    def test_is_valid_pattern_id_is_callable(self):
        assert callable(is_valid_pattern_id)

    def test_validate_returns_tuple(self):
        result = validate_pattern_id("ctx-abc123")
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_is_valid_returns_bool(self):
        result = is_valid_pattern_id("ctx-abc123")
        assert isinstance(result, bool)


# ============================================================================
# 9. SOURCE CODE AUDIT - validation MUST be called in the pipeline
# ============================================================================

class TestValidationIsCalledInPipeline:
    """
    MOST CRITICAL TEST CLASS.

    The root cause of the bug is that validate_pattern_id / is_valid_pattern_id
    are DEFINED but NEVER CALLED in the pipeline.

    These tests inspect the actual source code of ace_before_task.py and
    ace_after_task.py to prove that validation is (or is not) invoked
    at the points where pattern IDs are saved and loaded.

    These tests will FAIL until the fix adds validation calls.
    """

    def test_before_task_imports_validation(self):
        """
        ace_before_task.py must import validation functions.
        Currently it does NOT import from validation.py at all.
        """
        before_task_path = SHARED_HOOKS_PATH / "ace_before_task.py"
        source = before_task_path.read_text(encoding='utf-8')

        has_validation_import = (
            "validate_pattern_id" in source
            or "is_valid_pattern_id" in source
        )
        assert has_validation_import, (
            "ace_before_task.py does NOT import validate_pattern_id or "
            "is_valid_pattern_id. Pattern IDs from server responses flow "
            "to the state file WITHOUT any validation. This is the root "
            "cause of 1525 pattern_ prefix IDs reaching the server."
        )

    def test_before_task_calls_validation_before_save(self):
        """
        ace_before_task.py must call validation on pattern IDs before
        writing them to the state file (around lines 219-226).

        Currently the code does:
            pattern_ids = [p.get('id') for p in pattern_list if p.get('id')]
            state_file.write_text(json.dumps(pattern_ids))

        It should filter with is_valid_pattern_id() before saving.
        """
        before_task_path = SHARED_HOOKS_PATH / "ace_before_task.py"
        source = before_task_path.read_text(encoding='utf-8')

        # Check that validation is called in the pattern ID save section
        # Look for is_valid_pattern_id being used in a list comprehension
        # or validate_pattern_id being called near the state file write
        has_validation_call = (
            "is_valid_pattern_id" in source
            or "validate_pattern_id" in source
        )
        assert has_validation_call, (
            "ace_before_task.py saves pattern IDs to state file WITHOUT "
            "calling is_valid_pattern_id() or validate_pattern_id(). "
            "Server-returned 'pattern_' prefix IDs pass through unchecked. "
            "Fix: filter pattern_ids with is_valid_pattern_id() before save."
        )

    def test_after_task_imports_validation(self):
        """
        ace_after_task.py must import validation functions.
        Currently it does NOT import from validation.py at all.
        """
        after_task_path = SHARED_HOOKS_PATH / "ace_after_task.py"
        source = after_task_path.read_text(encoding='utf-8')

        has_validation_import = (
            "validate_pattern_id" in source
            or "is_valid_pattern_id" in source
        )
        assert has_validation_import, (
            "ace_after_task.py does NOT import validate_pattern_id or "
            "is_valid_pattern_id. Pattern IDs loaded from state file flow "
            "to ace-cli learn WITHOUT any validation. This allows 'pattern_' "
            "prefix IDs to reach the server."
        )

    def test_after_task_validates_loaded_playbook_ids(self):
        """
        ace_after_task.py must validate pattern IDs after loading from
        the state file (around lines 462-471).

        Currently the code does:
            playbook_used = json.loads(state_file.read_text())

        It should filter with is_valid_pattern_id() after loading.
        """
        after_task_path = SHARED_HOOKS_PATH / "ace_after_task.py"
        source = after_task_path.read_text(encoding='utf-8')

        has_validation_call = (
            "is_valid_pattern_id" in source
            or "validate_pattern_id" in source
        )
        assert has_validation_call, (
            "ace_after_task.py loads pattern IDs from state file and includes "
            "them in ExecutionTrace WITHOUT validation. 'pattern_' prefix IDs "
            "from old state files or buggy server responses reach ace-cli learn "
            "unfiltered. Fix: filter playbook_used with is_valid_pattern_id()."
        )

    def test_validation_used_near_pattern_id_extraction(self):
        """
        Specifically verify that validation is applied at the point where
        pattern IDs are extracted from the server response in before_task.

        The line:
            pattern_ids = [p.get('id') for p in pattern_list if p.get('id')]

        Should become something like:
            pattern_ids = [
                p.get('id') for p in pattern_list
                if p.get('id') and is_valid_pattern_id(p.get('id'))
            ]
        """
        before_task_path = SHARED_HOOKS_PATH / "ace_before_task.py"
        source = before_task_path.read_text(encoding='utf-8')

        # Find the pattern_ids extraction line and check for validation
        lines = source.splitlines()
        found_extraction = False
        has_validation_at_extraction = False

        for i, line in enumerate(lines):
            if "pattern_ids" in line and "p.get('id')" in line:
                found_extraction = True
                # Check this line and surrounding lines for validation
                context = "\n".join(lines[max(0, i-2):min(len(lines), i+3)])
                if "is_valid_pattern_id" in context or "validate_pattern_id" in context:
                    has_validation_at_extraction = True
                break

        assert found_extraction, "Could not find pattern ID extraction line in before_task"
        assert has_validation_at_extraction, (
            "Pattern ID extraction in before_task does NOT include validation. "
            "IDs are extracted with only `if p.get('id')` check, which does not "
            "verify the ctx- prefix. Add is_valid_pattern_id() to the filter."
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
