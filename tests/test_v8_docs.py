"""WP-E (v8.0.0) — CHANGELOG, README, ARCHITECTURE, ADR-001.

DESIGN §6 WP-E: CHANGELOG backfill 7.1.7–7.1.14 + [8.0.0] entry (critic T25: "CHANGELOG
stale since 7.1.6"); ARCHITECTURE.md to v8; new docs/technical/ADR-001-language.md (§2 + §8
deferred items); README floor text; statusline user-copy note.
"""
import re
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parent.parent / "plugins" / "ace"
CHANGELOG = PLUGIN / "CHANGELOG.md"
README = PLUGIN / "README.md"
ARCH = PLUGIN / "docs" / "technical" / "ARCHITECTURE.md"
ADR = PLUGIN / "docs" / "technical" / "ADR-001-language.md"


def _read(p):
    return p.read_text(encoding="utf-8")


def test_changelog_has_8_0_0_entry():
    """DESIGN §6 WP-E: CHANGELOG gets a [8.0.0] entry naming the new CC floor."""
    text = _read(CHANGELOG)
    m = re.search(r"^## \[8\.0\.0\][^\n]*\n(.*?)(?=^## \[)", text, re.S | re.M)
    assert m, "CHANGELOG.md has no `## [8.0.0]` section"
    assert "2.1.300" in m.group(1)


@pytest.mark.parametrize("ver", ["7.1.%d" % n for n in range(7, 15)])
def test_changelog_backfills_7_1_x(ver):
    """DESIGN §6 WP-E / critic T25: backfill 7.1.7–7.1.14 one-liners from git log."""
    assert re.search(r"^## \[%s\]" % re.escape(ver), _read(CHANGELOG), re.M), (
        "CHANGELOG.md missing `## [%s]`" % ver
    )


def test_changelog_8_0_0_is_newest_entry():
    """Keep-a-Changelog order: 8.0.0 is the first version heading."""
    first = re.search(r"^## \[(\d+\.\d+\.\d+)\]", _read(CHANGELOG), re.M)
    assert first and first.group(1) == "8.0.0"


def test_adr_001_language_exists_with_verdict():
    """DESIGN §2: ADR-001 summarizes the four advocates and the verdict (Python stays)."""
    assert ADR.exists(), "docs/technical/ADR-001-language.md missing"
    text = _read(ADR)
    for word in ("Python", "TypeScript", "Go", "Rust", "mods"):
        assert word in text, "ADR-001 must discuss " + word
    assert re.search(r"(?i)verdict|decision", text)


def test_adr_001_records_deferred_followups():
    """DESIGN §8: prompt_id pinning, PostToolBatch, UserPromptExpansion, CC mods, in-process core are deferred in ADR-001."""
    text = _read(ADR) if ADR.exists() else ""
    for item in ("prompt_id", "PostToolBatch", "UserPromptExpansion", "@ace-sdk/core"):
        assert item in text, "ADR-001 must record deferred item " + item


def test_architecture_describes_v8():
    """DESIGN §6 WP-E: ARCHITECTURE.md updated to v8 (was 'Current Version: 5.1.4')."""
    text = _read(ARCH)
    assert re.search(r"Current Version\**:?\**\s*8\.0\.0", text)
    assert "CLAUDE_PLUGIN_DATA" in text
    assert "PostToolUseFailure" in text


def test_architecture_has_no_tmp_state_paths():
    """DESIGN §4: state lives under CLAUDE_PLUGIN_DATA, not /tmp/ace-*."""
    assert "/tmp/ace" not in _read(ARCH)


def test_architecture_does_not_describe_removed_hooks():
    """DESIGN §3 REMOVED: no PreToolUse / PreCompact hook boxes in the v8 architecture."""
    text = _read(ARCH)
    for ev in ("PreToolUse Hook", "PreCompact Hook"):
        assert ev not in text


def test_readme_states_v8_floor():
    """DESIGN §1: README Requires text is CC >= 2.1.300 (was 'ace-cli >= v3.4.1')."""
    text = _read(README)
    assert "2.1.300" in text
    assert "ace-cli >= v3.4.1" not in text


def test_docs_mention_statusline_user_copy_refresh():
    """DESIGN §6 WP-E: ~/.claude/ace_statusline.sh is a user copy; `/ace:ace-statusline-setup update` refreshes it."""
    text = _read(README)
    assert "~/.claude/ace_statusline.sh" in text
    assert "/ace:ace-statusline-setup update" in text
