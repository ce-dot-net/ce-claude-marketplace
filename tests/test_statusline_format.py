"""TDD RED→GREEN: ace_statusline.sh float-percentage + epoch-reset formatting bugs.

BUG 1: used_percentage / rl_5h_pct / rl_7d_pct can be a float (e.g. 28.999999999999996).
       Must be rounded to integer before display and integer comparisons.
BUG 2: rate_limits.*.resets_at is a Unix epoch (e.g. 1781271000) displayed raw.
       Must be formatted to a human-readable local time (e.g. "Thu 15:30").

These tests will FAIL against the unpatched script and PASS after the fix.
"""
import json
import os
import re
import subprocess
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).parent.parent / "plugins" / "ace"
SCRIPT = PLUGIN_ROOT / "scripts" / "ace_statusline.sh"


# ── helpers ──────────────────────────────────────────────────────────────────

def _run_statusline(input_json: dict) -> tuple[str, str, int]:
    """Run the statusline script with given JSON on stdin."""
    proc = subprocess.run(
        ["bash", str(SCRIPT)],
        input=json.dumps(input_json),
        capture_output=True,
        text=True,
        timeout=10,
        env=os.environ.copy(),
    )
    return proc.stdout, proc.stderr, proc.returncode


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape codes."""
    return re.sub(r"\033\[[0-9;]*m", "", text)


def _lines(stdout: str) -> list[str]:
    """Return non-empty stripped lines with ANSI removed."""
    return [_strip_ansi(l) for l in stdout.splitlines() if l.strip()]


# ── RED test 1: float rate-limit percentages + raw epoch resets ──────────────

class TestFloatRateLimitPercentages:
    """BUG 1+2: float pct rendered as float; epoch rendered as raw integer."""

    RL_INPUT = {
        "context_window": {"used_percentage": 10},
        "rate_limits": {
            "five_hour": {
                "used_percentage": 28.999999999999996,
                "resets_at": 1781271000,
            },
            "seven_day": {
                "used_percentage": 44,
                "resets_at": 1781524800,
            },
        },
    }

    def test_5h_percentage_rounded_to_integer(self):
        """LINE3 must show '5h:29%', not '5h:28.9…%'."""
        stdout, _, rc = _run_statusline(self.RL_INPUT)
        assert rc == 0, f"Script exited {rc}: {stdout}"
        lines = _lines(stdout)
        line3 = next((l for l in lines if "5h:" in l), None)
        assert line3 is not None, f"No LINE3 with '5h:' in output: {lines}"
        assert "5h:29%" in line3, (
            f"Expected '5h:29%' (rounded) in LINE3 but got: {line3!r}"
        )
        # Must NOT contain the raw float
        assert "28.999" not in line3, (
            f"Raw float '28.999…' must not appear in LINE3: {line3!r}"
        )

    def test_7d_percentage_is_integer(self):
        """LINE3 must show '7d:44%', not '7d:44.0%'."""
        stdout, _, rc = _run_statusline(self.RL_INPUT)
        assert rc == 0
        lines = _lines(stdout)
        line3 = next((l for l in lines if "7d:" in l), None)
        assert line3 is not None, f"No LINE3 with '7d:' in output: {lines}"
        assert "7d:44%" in line3, f"Expected '7d:44%' in LINE3 but got: {line3!r}"

    def test_5h_resets_not_raw_epoch(self):
        """LINE3 must NOT show the raw epoch '1781271000'."""
        stdout, _, rc = _run_statusline(self.RL_INPUT)
        assert rc == 0
        clean = _strip_ansi(stdout)
        assert "1781271000" not in clean, (
            f"Raw epoch '1781271000' must not appear in output:\n{clean}"
        )

    def test_7d_resets_not_raw_epoch(self):
        """LINE3 must NOT show the raw epoch '1781524800'."""
        stdout, _, rc = _run_statusline(self.RL_INPUT)
        assert rc == 0
        clean = _strip_ansi(stdout)
        assert "1781524800" not in clean, (
            f"Raw epoch '1781524800' must not appear in output:\n{clean}"
        )

    def test_resets_formatted_as_time(self):
        """LINE3 must show a formatted reset time — '→' followed by a non-digit."""
        stdout, _, rc = _run_statusline(self.RL_INPUT)
        assert rc == 0
        line3 = next((l for l in _lines(stdout) if "5h:" in l), "")
        # A formatted reset looks like: →Thu 15:30  or  →Mon 09:00
        # Assert: arrow present, and right after the arrow is NOT only digits
        assert "→" in line3, f"Expected '→' in LINE3 but got: {line3!r}"
        # After the →, there should be a time-like pattern (contains ':')
        match = re.search(r"→(\S.*?)(?:\s{2,}|$)", line3)
        assert match is not None, f"Could not parse reset value after → in: {line3!r}"
        reset_val = match.group(1)
        assert re.match(r"^\d+$", reset_val) is None, (
            f"Reset value after → looks like a raw epoch: {reset_val!r} — expected formatted time"
        )
        assert ":" in reset_val, (
            f"Formatted time should contain ':' (e.g. 'Thu 15:30') but got: {reset_val!r}"
        )


# ── RED test 2: float used_percentage in context_window doesn't crash ─────────

class TestFloatContextWindowPercentage:
    """BUG 1: float context_window.used_percentage must not crash the script."""

    def test_float_used_pct_exits_zero(self):
        """Script must exit 0 even when used_percentage is a float."""
        cc_json = {
            "model": {"display_name": "claude-sonnet-4-5"},
            "context_window": {"used_percentage": 28.999999999999996},
            "session_id": "test-float-session",
        }
        stdout, stderr, rc = _run_statusline(cc_json)
        assert rc == 0, (
            f"Script crashed (rc={rc}) on float used_percentage.\n"
            f"stderr: {stderr}\nstdout: {stdout}"
        )

    def test_float_used_pct_rendered_as_integer(self):
        """LINE1 must show '29%' not '28.999…%'."""
        cc_json = {
            "model": {"display_name": "claude-sonnet-4-5"},
            "context_window": {"used_percentage": 28.999999999999996},
        }
        stdout, _, rc = _run_statusline(cc_json)
        assert rc == 0
        line1 = _lines(stdout)[0] if _lines(stdout) else ""
        assert "29%" in line1, (
            f"Expected '29%' (rounded) in LINE1 but got: {line1!r}"
        )
        assert "28.999" not in line1, (
            f"Raw float must not appear in LINE1: {line1!r}"
        )


# ── RED test 3: backward-compat — absent rate_limits ─────────────────────────

class TestAbsentRateLimits:
    """Backward-compat: empty/absent rate_limits → no LINE3, exit 0."""

    def test_no_rate_limits_exits_zero(self):
        """Script must exit 0 when rate_limits is absent."""
        cc_json = {
            "model": {"display_name": "claude-sonnet-4-5"},
            "context_window": {"used_percentage": 30},
        }
        _, _, rc = _run_statusline(cc_json)
        assert rc == 0

    def test_no_rate_limits_no_line3(self):
        """No LINE3 emitted when both rate-limit percentages are 0/absent."""
        cc_json = {
            "model": {"display_name": "claude-sonnet-4-5"},
            "context_window": {"used_percentage": 30},
        }
        stdout, _, rc = _run_statusline(cc_json)
        assert rc == 0
        lines = _lines(stdout)
        has_limits_line = any("limits" in l or "5h:" in l or "7d:" in l for l in lines)
        assert not has_limits_line, (
            f"LINE3 should not appear when rate_limits absent but got: {lines}"
        )

    def test_explicit_zero_rate_limits_no_line3(self):
        """LINE3 suppressed when both percentages are explicitly 0."""
        cc_json = {
            "model": {"display_name": "claude-sonnet-4-5"},
            "context_window": {"used_percentage": 30},
            "rate_limits": {
                "five_hour": {"used_percentage": 0, "resets_at": 1781271000},
                "seven_day": {"used_percentage": 0, "resets_at": 1781524800},
            },
        }
        stdout, _, rc = _run_statusline(cc_json)
        assert rc == 0
        lines = _lines(stdout)
        has_limits_line = any("5h:" in l or "7d:" in l for l in lines)
        assert not has_limits_line, (
            f"LINE3 should be suppressed when both pcts are 0 but got: {lines}"
        )


# ── FIX B: printf "00" hardening — non-numeric input must yield "0" not "00" ──

class TestPrintfNonNumericHardening:
    """FIX B: `printf '%.0f' "N/A"` emits "" (failure) then `|| echo 0` produces "0",
    but on some shells the compound produces "00" (printf empty-string + echo 0 concat).
    The fix `x=$(printf ...); x=${x:-0}` is immune — always yields "0" or a valid integer.

    Also covers the case where jq passes a string through unchanged (e.g. "N/A" from
    unusual CC payloads): `jq -r '... // 0'` returns "N/A" if the value IS "N/A"
    (jq only applies the default for null/missing).  The rounding idiom must not
    produce "00%" in the rendered output.
    """

    def test_bash_rounding_idiom_non_numeric_no_double_zero(self):
        """FIX B: printf rounding idiom with non-numeric input must not yield '00'.

        Directly tests the bash one-liner used in ace_statusline.sh for all three
        percentage variables (used_pct, rl_5h_pct, rl_7d_pct).
        """
        result = subprocess.run(
            ["bash", "-c",
             "x=$(printf '%.0f' 'N/A' 2>/dev/null); x=${x:-0}; echo \"$x\""],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, f"bash exited {result.returncode}: {result.stderr}"
        value = result.stdout.strip()
        assert value == "0", (
            f"FIX B: rounding idiom with non-numeric 'N/A' input must yield '0', got: {value!r}. "
            f"The old `printf ... || echo 0` pattern can produce '00' on some shells."
        )
        assert value != "00", (
            f"FIX B: '00' artefact detected — the printf hardening fix is not applied."
        )

    def test_bash_rounding_idiom_empty_input_no_double_zero(self):
        """FIX B: empty string input to the rounding idiom must also yield '0'."""
        result = subprocess.run(
            ["bash", "-c",
             "x=$(printf '%.0f' '' 2>/dev/null); x=${x:-0}; echo \"$x\""],
            capture_output=True, text=True,
        )
        value = result.stdout.strip()
        assert value == "0", (
            f"FIX B: empty string input must yield '0', got: {value!r}"
        )

    def test_all_three_pct_vars_non_numeric_no_double_zero(self):
        """FIX B: all three rounding idioms (used_pct, rl_5h_pct, rl_7d_pct) must not
        produce '00' for non-numeric input — tests each in isolation via bash -c.

        The old `printf '%.0f' 'N/A' 2>/dev/null || echo 0` produces '00' on macOS/bash
        because printf fails silently (emits empty), then `|| echo 0` appends "0" to the
        empty cmdsubst result — yielding "0" from echo but the overall assignment gets "0"
        (actually fine on bash 5 but "00" on some versions).  The new idiom:
          x=$(printf '%.0f' "${x:-0}" 2>/dev/null); x=${x:-0}
        is always safe: if printf fails, x is empty, then ${x:-0} substitutes "0".
        """
        for var_name, input_val in [
            ("used_pct", "N/A"),
            ("rl_5h_pct", "N/A"),
            ("rl_7d_pct", "N/A"),
            ("used_pct", ""),
            ("rl_5h_pct", ""),
        ]:
            result = subprocess.run(
                ["bash", "-c",
                 f'x={repr(input_val)}; '
                 f'x=$(printf \'%.0f\' "${{x:-0}}" 2>/dev/null); x=${{x:-0}}; echo "$x"'],
                capture_output=True, text=True,
            )
            value = result.stdout.strip()
            assert value == "0", (
                f"FIX B: rounding idiom for {var_name} with input {input_val!r} must yield '0', "
                f"got: {value!r}. The '00' artefact means the fix is not applied."
            )
            assert value != "00", (
                f"FIX B: '00' artefact for {var_name} with input {input_val!r}"
            )
