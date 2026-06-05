"""
Tests for ace-delta.md vocabulary hygiene — issue #23.

Scope:
- `helpful` and `harmful` must NOT appear as keys in any write-payload
  jq/JSON block (add / update / batch examples).
- A deprecation / migration note referencing F-080 or the reward model
  must be present somewhere in the file.

These are RED tests: they are expected to FAIL until ace-delta.md is updated.
"""

import re
from pathlib import Path

ACE_DELTA_MD = (
    Path(__file__).parent.parent / "plugins" / "ace" / "commands" / "ace-delta.md"
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_md() -> str:
    assert ACE_DELTA_MD.exists(), f"File not found: {ACE_DELTA_MD}"
    return ACE_DELTA_MD.read_text(encoding="utf-8")


def _extract_code_blocks(text: str, fence: str = "```") -> list[str]:
    """Return the body of every fenced code block in *text*."""
    pattern = re.compile(
        r"```(?:bash|json|sh|javascript|js)?\n(.*?)```",
        re.DOTALL,
    )
    return [m.group(1) for m in pattern.finditer(text)]


def _write_payload_blocks(blocks: list[str]) -> list[str]:
    """
    Filter to blocks that contain a write-style payload — i.e. JSON with a
    'bullets' array being piped to `ace-cli … delta (add|update)`.
    We detect them by the presence of both a bullets key and ace-cli delta.
    """
    return [
        b for b in blocks
        if '"bullets"' in b and "ace-cli" in b and "delta" in b
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestAceDeltaVocab:
    """Vocabulary hygiene checks for ace-delta.md (#23)."""

    def test_helpful_not_in_write_payload_blocks(self):
        """
        'helpful' must not appear as a JSON key in any write-payload example
        (add / update / batch blocks that include a bullets array sent to
        ace-cli delta).
        """
        md = _load_md()
        blocks = _extract_code_blocks(md)
        payload_blocks = _write_payload_blocks(blocks)

        assert payload_blocks, (
            "No write-payload code blocks found — check extraction logic."
        )

        violations = [b for b in payload_blocks if '"helpful"' in b]
        assert not violations, (
            f"Found 'helpful' key in {len(violations)} write-payload block(s).\n"
            "These fields are deprecated in ACE 1.5 — remove them per issue #23.\n"
            "Offending block(s):\n"
            + "\n---\n".join(violations)
        )

    def test_harmful_not_in_write_payload_blocks(self):
        """
        'harmful' must not appear as a JSON key in any write-payload example
        (add / update / batch blocks that include a bullets array sent to
        ace-cli delta).
        """
        md = _load_md()
        blocks = _extract_code_blocks(md)
        payload_blocks = _write_payload_blocks(blocks)

        assert payload_blocks, (
            "No write-payload code blocks found — check extraction logic."
        )

        violations = [b for b in payload_blocks if '"harmful"' in b]
        assert not violations, (
            f"Found 'harmful' key in {len(violations)} write-payload block(s).\n"
            "These fields are deprecated in ACE 1.5 — remove them per issue #23.\n"
            "Offending block(s):\n"
            + "\n---\n".join(violations)
        )

    def test_f080_or_reward_migration_note_present(self):
        """
        The file must contain a deprecation / migration note for helpful/harmful.
        Accepted signals (case-insensitive):
          - the tag 'F-080'
          - the phrase 'reward model'
          - the phrase 'deprecated in ACE'
        """
        md = _load_md()
        has_note = bool(
            re.search(r"F-080", md, re.IGNORECASE)
            or re.search(r"reward model", md, re.IGNORECASE)
            or re.search(r"deprecated in ACE", md, re.IGNORECASE)
        )
        assert has_note, (
            "ace-delta.md is missing a migration note for the deprecated "
            "helpful/harmful fields.\n"
            "Add a comment referencing F-080 or directing users to the reward "
            "model (ACE 1.5+). See issue #23."
        )
