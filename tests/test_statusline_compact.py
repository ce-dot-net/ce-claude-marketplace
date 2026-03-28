"""TDD: Statusline shows 'Compact' label like default CC statusline."""
from pathlib import Path

STATUSLINE = Path(__file__).parent.parent / 'plugins' / 'ace' / 'scripts' / 'ace_statusline.sh'


class TestCompactIndicator:
    """Statusline should show 'Compact' label near context % like default CC."""

    def test_statusline_shows_compact_word(self):
        """Must contain the word 'Compact' in the output logic."""
        content = STATUSLINE.read_text()
        assert 'Compact' in content, \
            "Statusline must show 'Compact' label"

    def test_compact_appears_before_percentage(self):
        """Compact label should appear before the percentage in the output."""
        content = STATUSLINE.read_text()
        # The output should have Compact before used_pct
        lines = content.splitlines()
        compact_line = None
        pct_line = None
        for i, line in enumerate(lines):
            if 'Compact' in line and not line.strip().startswith('#'):
                compact_line = i
            if 'used_pct' in line and 'OUT+=' in line:
                if pct_line is None:
                    pct_line = i
        assert compact_line is not None and pct_line is not None, \
            "Both Compact label and percentage must exist in output code"
