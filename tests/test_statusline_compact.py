"""TDD: Statusline 2-line design — no longer shows 'Compact' label.

The statusline was redesigned to 2 lines:
  Line 1: Model · context bar · context%
  Line 2: ACE metrics
The 'Compact' label was removed as it is not provided by CC.
"""
from pathlib import Path

STATUSLINE = Path(__file__).parent.parent / 'plugins' / 'ace' / 'scripts' / 'ace_statusline.sh'


class TestCompactIndicator:
    """Statusline should NOT show 'Compact' label (removed in 2-line redesign)."""

    def test_statusline_no_compact_word(self):
        """Must NOT contain the word 'Compact' in the output logic."""
        content = STATUSLINE.read_text()
        assert 'Compact' not in content, \
            "Statusline should no longer show 'Compact' label"

    def test_context_percentage_in_line1(self):
        """Context percentage should be present in line 1 output."""
        content = STATUSLINE.read_text()
        # LINE1 should reference used_pct
        assert 'LINE1' in content and 'used_pct' in content, \
            "Context percentage must exist in LINE1 output"
