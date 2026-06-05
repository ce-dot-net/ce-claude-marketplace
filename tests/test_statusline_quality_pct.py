"""TDD RED: #30 — Statusline/stop-wrapper: rename helpful_pct → quality_pct with fallback.

SCOPE:
  - ace_stop_wrapper.sh: self-eval block must write quality_pct (not helpful_pct)
  - ace_statusline.sh: must read quality_pct with .helpful_pct fallback
    i.e. quality=(.quality_pct // .helpful_pct // 0)
  - test_ace_self_eval.py::TestStatuslineReadsReview::test_shows_helpful_pct
    renamed → test_shows_quality_pct, assertions updated

These tests will FAIL against current code (which uses helpful_pct throughout)
and pass once the rename + fallback are implemented.
"""
from pathlib import Path

PLUGIN_ROOT = Path(__file__).parent.parent / 'plugins' / 'ace'
SCRIPTS_DIR = PLUGIN_ROOT / 'scripts'
STOP_WRAPPER = SCRIPTS_DIR / 'ace_stop_wrapper.sh'
STATUSLINE = SCRIPTS_DIR / 'ace_statusline.sh'


# ── Stop-wrapper: must write quality_pct ─────────────────────────────────────

class TestStopWrapperWritesQualityPct:
    """ace_stop_wrapper.sh self-eval block must write quality_pct key."""

    def test_review_file_uses_quality_pct_key(self):
        """jq expression that builds review JSON must produce quality_pct key, not helpful_pct."""
        content = STOP_WRAPPER.read_text()
        # The jq -n call that writes REVIEW_FILE must use quality_pct
        assert 'quality_pct' in content, (
            "ace_stop_wrapper.sh must write 'quality_pct' key in review JSON "
            "(rename from helpful_pct)"
        )

    def test_stop_wrapper_no_longer_writes_only_helpful_pct(self):
        """The primary review-file write must NOT use the old helpful_pct key name.

        After the rename the jq -n block should produce quality_pct.
        The old key may appear in a legacy-compat comment but NOT as the
        jq output field name in the write path.
        """
        content = STOP_WRAPPER.read_text()
        lines = content.splitlines()
        # Find the jq -n line that writes the review file
        jq_write_lines = [
            l for l in lines
            if 'helpful_pct' in l
            and 'jq' in l
            and not l.strip().startswith('#')
        ]
        assert len(jq_write_lines) == 0, (
            f"ace_stop_wrapper.sh still writes 'helpful_pct' via jq on line(s):\n"
            + '\n'.join(jq_write_lines)
        )

    def test_systemmessage_uses_quality_pct_read(self):
        """The REVIEW_PCT read from review file must use quality_pct (with fallback)."""
        content = STOP_WRAPPER.read_text()
        # After the rename, reading the review file for the system message
        # should reference quality_pct
        assert '.quality_pct' in content, (
            "ace_stop_wrapper.sh must read '.quality_pct' from review file "
            "when building the systemMessage (was '.helpful_pct')"
        )


# ── Statusline: must read quality_pct with helpful_pct fallback ───────────────

class TestStatuslineReadsQualityPct:
    """ace_statusline.sh must read quality_pct with .helpful_pct as fallback."""

    def test_statusline_reads_quality_pct_primary(self):
        """Statusline must use .quality_pct as the primary key from review file."""
        content = STATUSLINE.read_text()
        assert '.quality_pct' in content, (
            "ace_statusline.sh must read '.quality_pct' from ace-review-result.json"
        )

    def test_statusline_has_helpful_pct_fallback(self):
        """Statusline must fall back to .helpful_pct so old stop-wrapper files still work."""
        content = STATUSLINE.read_text()
        # The jq expression should use // operator for fallback:
        # e.g.  .quality_pct // .helpful_pct // 0
        assert '.helpful_pct' in content, (
            "ace_statusline.sh must retain '.helpful_pct' as a fallback key "
            "so output from old stop-wrapper (pre-rename) still works"
        )

    def test_statusline_fallback_order_quality_first(self):
        """quality_pct must appear before helpful_pct in the jq expression."""
        content = STATUSLINE.read_text()
        qp_idx = content.find('.quality_pct')
        hp_idx = content.find('.helpful_pct')
        assert qp_idx != -1, "ace_statusline.sh must contain '.quality_pct'"
        assert hp_idx != -1, "ace_statusline.sh must contain '.helpful_pct' fallback"
        assert qp_idx < hp_idx, (
            "'.quality_pct' must appear before '.helpful_pct' in statusline "
            f"(quality_pct at char {qp_idx}, helpful_pct at char {hp_idx})"
        )

    def test_statusline_jq_fallback_chain(self):
        """The jq expression must use // chain: .quality_pct // .helpful_pct // 0."""
        content = STATUSLINE.read_text()
        # Accept any reasonable spacing around //
        import re
        pattern = r'\.quality_pct\s*//\s*\.helpful_pct'
        assert re.search(pattern, content), (
            "ace_statusline.sh must contain jq fallback expression "
            "'.quality_pct // .helpful_pct' (with optional spaces)"
        )

    def test_statusline_display_label_updated(self):
        """Display label in LINE2 must say 'quality' not 'helpful' (after rename)."""
        content = STATUSLINE.read_text()
        # After the rename the % display label should reflect quality
        assert 'quality' in content, (
            "ace_statusline.sh display text must use 'quality' label "
            "(was 'helpful' in LINE2 output)"
        )


# ── Rename: test_shows_quality_pct replaces test_shows_helpful_pct ────────────

class TestStatuslineShowsQualityPct:
    """Renamed from test_ace_self_eval::TestStatuslineReadsReview::test_shows_helpful_pct.

    After #30: statusline contains quality_pct (primary) + helpful_pct (fallback).
    The old test_shows_helpful_pct checked only for helpful_pct — that test is
    superseded by this one which checks for quality_pct.
    """

    def test_shows_quality_pct(self):
        """Statusline must reference quality_pct (the renamed primary key)."""
        content = STATUSLINE.read_text()
        assert 'quality_pct' in content, (
            "ace_statusline.sh must reference 'quality_pct' "
            "(renamed from helpful_pct — see issue #30)"
        )

    def test_review_file_key_is_quality_pct(self):
        """Stop-wrapper review JSON must have quality_pct as the output field."""
        content = STOP_WRAPPER.read_text()
        assert 'quality_pct' in content, (
            "ace_stop_wrapper.sh review JSON must use 'quality_pct' field name"
        )


# ── Fallback integration: old helpful_pct files still render ─────────────────

class TestHelpfulPctFallbackBehavior:
    """Old stop-wrapper output (.helpful_pct key) must still be readable."""

    def test_statusline_fallback_expression_handles_old_files(self):
        """jq expression must gracefully handle files with only helpful_pct key."""
        content = STATUSLINE.read_text()
        import re
        # Must have the full fallback chain in a single jq expression
        chain = re.search(r'\.quality_pct\s*//\s*\.helpful_pct\s*//\s*0', content)
        assert chain, (
            "ace_statusline.sh must have jq fallback chain "
            "'.quality_pct // .helpful_pct // 0' to handle old review files"
        )

    def test_stop_wrapper_no_helpful_pct_in_jq_write(self):
        """Stop-wrapper jq -n write block must not produce helpful_pct field."""
        content = STOP_WRAPPER.read_text()
        import re
        # Find every jq -n block (multi-line) and ensure none output helpful_pct
        # Simple heuristic: look for lines with both 'jq' and 'helpful_pct' that are not comments
        suspicious = [
            (i + 1, l.rstrip())
            for i, l in enumerate(content.splitlines())
            if 'helpful_pct' in l and not l.strip().startswith('#')
        ]
        assert not suspicious, (
            "ace_stop_wrapper.sh has 'helpful_pct' in non-comment executable lines:\n"
            + '\n'.join(f"  line {n}: {l}" for n, l in suspicious)
        )
