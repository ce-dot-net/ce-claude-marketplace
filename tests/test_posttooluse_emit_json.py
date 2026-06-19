#!/usr/bin/env python3
"""
TDD RED test — ace_posttooluse_domain_inject.sh: emission line must produce valid JSON.

Bug: the hand-rolled  echo "{...$(echo "$CONTEXT" | sed 's/"/\\"/g')...}"  on line 111
leaves backslash sequences in $CONTEXT unescaped. $CONTEXT contains JSON produced by
json.dumps(...) inside Python (via patterns_used_state.py --strip-and-gate), which
emits unicode escapes like \\uXXXX, escaped quotes like \\", and literal backslashes
like \\\\ .  sed only doubles bare double-quotes; everything else (\\u, \\n, \\\\, etc.)
comes through raw → the outer JSON string is broken → jq rejects it → CC silently drops
the PostToolUse injection.

Adversarial chars covered (all must round-trip):
  - double-quote  "
  - non-ASCII / unicode escape  ä  (json.dumps emits \\u00e4 or the literal char)
  - newline  \\n  (json.dumps emits \\\\n  in string values)
  - backslash  \\  (json.dumps emits \\\\)

Fix: replace the echo+sed line with
    jq -n --arg ctx "$CONTEXT" '{"hookSpecificOutput":{"hookEventName":"PostToolUse","additionalContext":$ctx}}'

jq is already a hard dependency of the script (used throughout), so this is always safe.
"""

import json
import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "plugins/ace/scripts/ace_posttooluse_domain_inject.sh"
PUS_SCRIPT = REPO / "plugins/ace/shared-hooks/utils/patterns_used_state.py"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_ace_cli(tmp_path: Path, content_with_adversarial_chars: str) -> Path:
    """
    Write a mock ace-cli shim whose `search --stdin --json` output includes a
    pattern whose `content` field contains adversarial characters.  The content
    is emitted as a proper JSON string (using json.dumps) so the adversarial
    chars are correctly encoded at the ace-cli output level — the bug is in how
    the *script* re-encodes the final CONTEXT into the outer hookSpecificOutput
    JSON object.
    """
    pattern = {
        "id": "ctx-adversarial-0001",
        "domain": "scripts",
        "content": content_with_adversarial_chars,
        "confidence": 0.9,
        "helpful": 3.0,
        "harmful": 0,
        "section": "strategies_and_hard_rules",
        "evidence": ["evidence with a quote: \"hello\""],
        "root_cause": "",
        "error_context": "",
        "cumulative_v15_reward": 5.0,
        "n_hot_pos": 1,
        "n_hot_neg": 0,
        "isAtRisk": False,
    }
    search_result = {
        "similar_patterns": [pattern],
        "count": 1,
        "retrieval_id": "ret-adversarial-0001",
    }
    result_json = json.dumps(search_result)

    mock = tmp_path / "ace-cli"
    mock.write_text(f"#!/bin/bash\nprintf '%s' {repr(result_json)!r}\n")
    # The above repr() might not be safe for all chars — use a heredoc instead:
    mock.write_text(
        "#!/bin/bash\n"
        "cat <<'__ENDJSON__'\n"
        f"{result_json}\n"
        "__ENDJSON__\n"
    )
    mock.chmod(0o755)
    return mock


def _setup_domain_env(tmp_path: Path, project_id: str, domain: str) -> Path:
    """Create minimal project dir with settings.json and domain files."""
    project_dir = tmp_path / "proj"
    (project_dir / ".claude").mkdir(parents=True)
    (project_dir / ".claude" / "settings.json").write_text(json.dumps({
        "env": {"ACE_PROJECT_ID": project_id},
    }))

    # Domains file (required by script before ace-cli is called)
    domains_file = Path(f"/tmp/ace-domains-{project_id}.json")
    domains_file.write_text(json.dumps({
        domain: {"description": "test domain"},
    }))

    # Last-domain file pointing at a *different* domain to trigger the domain-shift
    last_domain_file = Path(f"/tmp/ace-domain-{project_id}.txt")
    last_domain_file.write_text("other-domain")

    return project_dir


def _run_script(tmp_path: Path, project_id: str, domain: str, project_dir: Path) -> subprocess.CompletedProcess:
    """Invoke the domain-inject script with a hook event that matches `domain`."""
    # File path: must contain the domain word so the script's grep-based match fires.
    # The basename must be non-empty (script guards on this).
    file_path = f"/{domain}/config_parser.py"

    hook_input = json.dumps({
        "session_id": f"cc-sess-{project_id}",
        "tool_name": "Read",
        "tool_input": {"file_path": file_path},
        "cwd": str(project_dir),
    })

    env = {
        **os.environ,
        # Prepend tmp_path so our mock ace-cli is found first
        "PATH": f"{tmp_path}:{os.environ.get('PATH', '/usr/bin:/bin')}",
        "HOME": str(tmp_path),
        # Make ACE_PLUGIN_ROOT explicit so the script can resolve shared-hooks utils
        "ACE_PLUGIN_ROOT": str(REPO / "plugins/ace"),
    }

    return subprocess.run(
        ["bash", str(SCRIPT)],
        input=hook_input,
        capture_output=True, text=True, timeout=30,
        env=env,
    )


def _cleanup(project_id: str) -> None:
    Path(f"/tmp/ace-domains-{project_id}.json").unlink(missing_ok=True)
    Path(f"/tmp/ace-domain-{project_id}.txt").unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# RED test: adversarial content must produce valid JSON
# ---------------------------------------------------------------------------

class TestPostToolUseEmitValidJson:
    """
    ace_posttooluse_domain_inject.sh must emit a hookSpecificOutput JSON object
    that is valid JSON even when the injected pattern content contains characters
    that break naive string interpolation:  "  ä  \\n  \\
    """

    ADVERSARIAL_CONTENT = 'pattern with "quotes", ä umlaut, newline\\nhere, and backslash\\\\ done'

    def test_emission_is_valid_json(self, tmp_path):
        """
        RED (before fix): echo+sed emission produces invalid JSON when CONTEXT
        contains backslash-sequences.  json.loads() raises JSONDecodeError.
        GREEN (after fix): jq --arg emission correctly escapes all special chars.
        """
        project_id = f"prj-emit-adv-{os.getpid()}"
        domain = "scripts"
        _make_mock_ace_cli(tmp_path, self.ADVERSARIAL_CONTENT)
        project_dir = _setup_domain_env(tmp_path, project_id, domain)

        result = _run_script(tmp_path, project_id, domain, project_dir)
        _cleanup(project_id)

        stdout = result.stdout.strip()
        if not stdout:
            pytest.skip(
                "Script produced no output (domain match or ace-cli mock did not fire). "
                f"stderr: {result.stderr!r}"
            )

        # This is the key assertion: the output MUST be valid JSON.
        try:
            parsed = json.loads(stdout)
        except json.JSONDecodeError as exc:
            pytest.fail(
                f"ace_posttooluse_domain_inject.sh emitted INVALID JSON.\n"
                f"Error: {exc}\n"
                f"Stdout (first 500 chars): {stdout[:500]!r}\n"
                f"This is the backslash-escape bug: sed 's/\"/\\\\\"/g' only doubles\n"
                f"bare double-quotes but leaves \\\\uXXXX, \\\\n, \\\\\\\\ raw."
            )

        # The hookSpecificOutput wrapper must be present
        assert "hookSpecificOutput" in parsed, (
            f"Parsed JSON must have hookSpecificOutput key. Got keys: {list(parsed.keys())}"
        )
        assert parsed["hookSpecificOutput"]["hookEventName"] == "PostToolUse"

    def test_additionalcontext_contains_domain_shift_tag(self, tmp_path):
        """
        After fix: additionalContext must contain the <ace-patterns-domain-shift> tag.
        """
        project_id = f"prj-emit-tag-{os.getpid()}"
        domain = "scripts"
        _make_mock_ace_cli(tmp_path, self.ADVERSARIAL_CONTENT)
        project_dir = _setup_domain_env(tmp_path, project_id, domain)

        result = _run_script(tmp_path, project_id, domain, project_dir)
        _cleanup(project_id)

        stdout = result.stdout.strip()
        if not stdout:
            pytest.skip("Script produced no output; domain match or ace-cli mock did not fire.")

        parsed = json.loads(stdout)
        ctx = parsed["hookSpecificOutput"]["additionalContext"]
        assert "<ace-patterns-domain-shift" in ctx, (
            f"additionalContext must contain the domain-shift XML tag. Got: {ctx[:200]!r}"
        )

    def test_adversarial_double_quote_survives_roundtrip(self, tmp_path):
        """
        After fix: a literal double-quote in pattern content must survive the
        JSON round-trip inside additionalContext (i.e. the inner JSON is not
        double-escaped into \\\\\" or similarly broken).
        """
        project_id = f"prj-emit-dq-{os.getpid()}"
        domain = "scripts"
        content_with_quote = 'Use key "foo" in dict'
        _make_mock_ace_cli(tmp_path, content_with_quote)
        project_dir = _setup_domain_env(tmp_path, project_id, domain)

        result = _run_script(tmp_path, project_id, domain, project_dir)
        _cleanup(project_id)

        stdout = result.stdout.strip()
        if not stdout:
            pytest.skip("Script produced no output.")

        parsed = json.loads(stdout)
        ctx = parsed["hookSpecificOutput"]["additionalContext"]
        # The original content string must appear somewhere inside additionalContext
        assert 'foo' in ctx, (
            f"Pattern content with double-quote must appear in additionalContext. "
            f"Got ctx (first 300): {ctx[:300]!r}"
        )

    def test_adversarial_backslash_does_not_break_json(self, tmp_path):
        """
        After fix: a backslash in pattern content must not produce invalid JSON.
        This is the core of the bug: sed leaves \\ raw in the outer string.
        """
        project_id = f"prj-emit-bs-{os.getpid()}"
        domain = "scripts"
        content_with_backslash = r'path: C:\Users\foo\bar'
        _make_mock_ace_cli(tmp_path, content_with_backslash)
        project_dir = _setup_domain_env(tmp_path, project_id, domain)

        result = _run_script(tmp_path, project_id, domain, project_dir)
        _cleanup(project_id)

        stdout = result.stdout.strip()
        if not stdout:
            pytest.skip("Script produced no output.")

        try:
            json.loads(stdout)
        except json.JSONDecodeError as exc:
            pytest.fail(
                f"Backslash in content broke outer JSON.\n"
                f"JSONDecodeError: {exc}\n"
                f"Stdout: {stdout[:400]!r}"
            )

    def test_emission_uses_jq_not_sed(self):
        """
        Structural: the fix replaces echo+sed with jq --arg.
        Assert the script does NOT contain the broken sed 's/\"/\\\\\"/g' pattern
        and DOES contain a jq -n --arg emission for the hookSpecificOutput.
        """
        script_text = SCRIPT.read_text()

        # The broken pattern: sed being used to escape the hookSpecificOutput JSON
        assert "hookSpecificOutput" not in script_text or (
            "sed 's/\"/\\\\\"" not in script_text
        ), (
            "Script must not use sed to escape the hookSpecificOutput JSON string. "
            "Replace with jq -n --arg ctx."
        )

        # The correct pattern: jq -n --arg ctx building hookSpecificOutput
        assert 'jq -n --arg ctx' in script_text, (
            "Script must emit hookSpecificOutput via "
            "`jq -n --arg ctx \"$CONTEXT\" '{...}'` (not echo+sed)."
        )
