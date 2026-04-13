#!/usr/bin/env python3
"""TDD: spec-05 Phase 3 — ACE Statusline 2-Line Redesign.

Tests for:
  - Script exists and is executable
  - Output has 2 lines (model/context on line 1, ACE metrics on line 2)
  - Line 1 has model and context info
  - Line 2 has ACE metrics
  - No "Compact" label anywhere
"""

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).parent.parent / 'plugins' / 'ace'
SCRIPT = PLUGIN_ROOT / 'scripts' / 'ace_statusline.sh'


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_statusline(input_json: dict, env_extra: dict | None = None) -> tuple[str, str, int]:
    """Run the statusline script with given JSON on stdin."""
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    proc = subprocess.run(
        ['bash', str(SCRIPT)],
        input=json.dumps(input_json),
        capture_output=True,
        text=True,
        timeout=10,
        env=env,
    )
    return proc.stdout, proc.stderr, proc.returncode


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape codes from text."""
    return re.sub(r'\033\[[0-9;]*m', '', text)


def _make_cc_json(model_name: str = "Opus", used_pct: int = 53, cwd: str = "") -> dict:
    """Build a minimal CC JSON input."""
    return {
        "model": {"display_name": model_name},
        "context_window": {"used_percentage": used_pct},
        "session_id": "test-session-123",
        "cwd": cwd,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestStatuslineExists:
    """Script exists and is executable."""

    def test_script_exists(self):
        assert SCRIPT.exists(), f"Script not found at {SCRIPT}"

    def test_script_is_executable(self):
        assert os.access(SCRIPT, os.X_OK), f"Script is not executable: {SCRIPT}"


class TestStatuslineTwoLines:
    """Output has exactly 2 lines."""

    def test_output_has_two_lines(self):
        cc_json = _make_cc_json()
        stdout, _, rc = _run_statusline(cc_json)
        assert rc == 0, f"Script failed with rc={rc}"
        lines = stdout.rstrip('\n').split('\n')
        assert len(lines) == 2, f"Expected 2 lines, got {len(lines)}: {lines}"


class TestLine1ModelContext:
    """Line 1 contains model name and context info."""

    def test_line1_has_model_name(self):
        cc_json = _make_cc_json(model_name="Opus")
        stdout, _, rc = _run_statusline(cc_json)
        assert rc == 0
        line1 = _strip_ansi(stdout.rstrip('\n').split('\n')[0])
        assert "Opus" in line1, f"Model name 'Opus' not found in line 1: {line1}"

    def test_line1_has_context_percentage(self):
        cc_json = _make_cc_json(used_pct=53)
        stdout, _, rc = _run_statusline(cc_json)
        assert rc == 0
        line1 = _strip_ansi(stdout.rstrip('\n').split('\n')[0])
        assert "53%" in line1, f"Context percentage '53%' not found in line 1: {line1}"

    def test_line1_has_context_bar(self):
        cc_json = _make_cc_json(used_pct=50)
        stdout, _, rc = _run_statusline(cc_json)
        assert rc == 0
        line1 = _strip_ansi(stdout.rstrip('\n').split('\n')[0])
        # Should contain block chars
        assert "█" in line1 or "░" in line1, f"Context bar chars not found in line 1: {line1}"

    def test_line1_different_model_names(self):
        for name in ["Sonnet", "Haiku", "Opus 4"]:
            cc_json = _make_cc_json(model_name=name)
            stdout, _, rc = _run_statusline(cc_json)
            assert rc == 0
            line1 = _strip_ansi(stdout.rstrip('\n').split('\n')[0])
            assert name in line1, f"Model '{name}' not found in line 1: {line1}"

    def test_line1_fallback_when_no_model(self):
        cc_json = {"context_window": {"used_percentage": 30}, "cwd": ""}
        stdout, _, rc = _run_statusline(cc_json)
        assert rc == 0
        line1 = _strip_ansi(stdout.rstrip('\n').split('\n')[0])
        assert "Claude" in line1, f"Fallback 'Claude' not found in line 1: {line1}"


class TestLine2AceMetrics:
    """Line 2 contains ACE metrics."""

    def test_line2_has_ace_badge(self):
        cc_json = _make_cc_json()
        stdout, _, rc = _run_statusline(cc_json)
        assert rc == 0
        line2 = _strip_ansi(stdout.rstrip('\n').split('\n')[1])
        assert "ACE" in line2, f"ACE badge not found in line 2: {line2}"

    def test_line2_has_diamond(self):
        cc_json = _make_cc_json()
        stdout, _, rc = _run_statusline(cc_json)
        assert rc == 0
        line2 = _strip_ansi(stdout.rstrip('\n').split('\n')[1])
        assert "◆" in line2, f"Diamond not found in line 2: {line2}"


class TestNoCompactLabel:
    """No 'Compact' label appears anywhere in output."""

    def test_no_compact_in_output(self):
        cc_json = _make_cc_json()
        stdout, _, rc = _run_statusline(cc_json)
        assert rc == 0
        plain = _strip_ansi(stdout)
        assert "Compact" not in plain, f"'Compact' found in output: {plain}"

    def test_no_compact_in_script_output_section(self):
        """Verify the script source has no Compact label in the output section."""
        content = SCRIPT.read_text()
        # Should not have Compact in any echo/OUT line
        assert "Compact" not in content, "Script source still contains 'Compact'"


class TestContextBarScaling:
    """Context bar scales properly with usage percentage."""

    def test_zero_percent(self):
        cc_json = _make_cc_json(used_pct=0)
        stdout, _, rc = _run_statusline(cc_json)
        assert rc == 0
        line1 = _strip_ansi(stdout.rstrip('\n').split('\n')[0])
        # All empty blocks
        assert "█" not in line1, f"Filled blocks at 0%: {line1}"

    def test_hundred_percent(self):
        cc_json = _make_cc_json(used_pct=100)
        stdout, _, rc = _run_statusline(cc_json)
        assert rc == 0
        line1 = _strip_ansi(stdout.rstrip('\n').split('\n')[0])
        # All filled blocks
        assert "░" not in line1, f"Empty blocks at 100%: {line1}"
