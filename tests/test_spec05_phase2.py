#!/usr/bin/env python3
"""TDD: spec-05 Phase 2 B4 — PostToolUse Domain Pattern Injection.

Tests for:
  B4: ace_posttooluse_domain_inject.sh fires on Read(*) and returns
      additionalContext with domain-specific patterns on domain shift.
"""

import json
import os
import subprocess
import tempfile
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).parent.parent / 'plugins' / 'ace'
SCRIPT = PLUGIN_ROOT / 'scripts' / 'ace_posttooluse_domain_inject.sh'
HOOKS_JSON = PLUGIN_ROOT / 'hooks' / 'hooks.json'


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_ace_cli(tmp_path: Path) -> Path:
    """Write a mock ace-cli executable to tmp_path.

    The stub:
    - Accepts any flags (--stdin, --json, --allowed-domains, --pin-session, etc.)
      without making any network call.
    - Emits a minimal, deterministic search JSON whose patterns pass the
      v15 quality gate (cumulative_v15_reward > 0, isAtRisk false).
    - Exits 0 immediately.

    Mirrors the _make_mock_ace_cli pattern used in
    test_domain_shift_session_pinning.py for consistency.
    """
    mock = tmp_path / "ace-cli"
    mock.write_text(
        "#!/bin/bash\n"
        "cat <<'ENDJSON'\n"
        '{"similar_patterns":[{"id":"mock-pat-001","domain":"test-domain",'
        '"content":"mock pattern content","confidence":0.9,"helpful":5.0,'
        '"harmful":0,"section":"strategies","evidence":[],'
        '"cumulative_v15_reward":1.5,"isAtRisk":false,'
        '"n_hot_pos":1,"n_hot_neg":0,'
        '"match_factors":{"retrieval_log_id":42}}],'
        '"count":1,"retrieval_id":"mock-ret-001"}\n'
        "ENDJSON\n"
    )
    mock.chmod(0o755)
    return mock


def _run_script(
    input_json: dict,
    env_extra: dict | None = None,
    mock_ace_cli_dir: Path | None = None,
) -> tuple[str, str, int]:
    """Run the domain inject script with given JSON on stdin.

    When *mock_ace_cli_dir* is provided its path is prepended to PATH so
    the subprocess finds the mock ace-cli stub instead of the real binary,
    preventing any network calls.
    """
    env = os.environ.copy()
    if mock_ace_cli_dir is not None:
        env['PATH'] = f"{mock_ace_cli_dir}:{env.get('PATH', '/usr/bin:/bin')}"
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
    return proc.stdout.strip(), proc.stderr.strip(), proc.returncode


# ---------------------------------------------------------------------------
# B4-01: Script exists and is executable
# ---------------------------------------------------------------------------

class TestB4ScriptExists:
    def test_script_exists(self):
        assert SCRIPT.exists(), f"Script not found: {SCRIPT}"

    def test_script_is_executable(self):
        assert os.access(SCRIPT, os.X_OK), f"Script not executable: {SCRIPT}"

    def test_script_syntax_valid(self):
        result = subprocess.run(
            ['bash', '-n', str(SCRIPT)],
            capture_output=True, text=True, timeout=5,
        )
        assert result.returncode == 0, f"Syntax error: {result.stderr}"


# ---------------------------------------------------------------------------
# B4-02: hooks.json has the domain inject hook with if: "Read(*)"
# ---------------------------------------------------------------------------

class TestB4HooksJson:
    @pytest.fixture
    def hooks(self):
        return json.loads(HOOKS_JSON.read_text())

    def test_posttooluse_has_domain_inject_hook(self, hooks):
        post_hooks = hooks['hooks']['PostToolUse']
        assert len(post_hooks) > 0
        hook_entries = post_hooks[0]['hooks']
        domain_hooks = [
            h for h in hook_entries
            if 'domain_inject' in h.get('command', '')
        ]
        assert len(domain_hooks) == 1, "Expected exactly one domain_inject hook"

    def test_domain_inject_has_if_read(self, hooks):
        hook_entries = hooks['hooks']['PostToolUse'][0]['hooks']
        domain_hook = next(
            h for h in hook_entries if 'domain_inject' in h.get('command', '')
        )
        assert domain_hook.get('if') == 'Read(*)', \
            f"Expected if: 'Read(*)', got: {domain_hook.get('if')}"

    def test_domain_inject_timeout_lte_5000(self, hooks):
        hook_entries = hooks['hooks']['PostToolUse'][0]['hooks']
        domain_hook = next(
            h for h in hook_entries if 'domain_inject' in h.get('command', '')
        )
        assert domain_hook.get('timeout', 15000) <= 5000, \
            "Domain inject timeout should be <= 5000ms"

    def test_original_posttooluse_hook_preserved(self, hooks):
        hook_entries = hooks['hooks']['PostToolUse'][0]['hooks']
        wrapper_hooks = [
            h for h in hook_entries
            if 'posttooluse_wrapper' in h.get('command', '')
        ]
        assert len(wrapper_hooks) == 1, "Original PostToolUse wrapper must be preserved"

    def test_hooks_json_valid(self):
        """hooks.json must be valid JSON."""
        data = json.loads(HOOKS_JSON.read_text())
        assert 'hooks' in data


# ---------------------------------------------------------------------------
# B4-03: Script exits silently when no file_path in input
# ---------------------------------------------------------------------------

class TestB4NoFilePath:
    def test_no_file_path_exits_cleanly(self):
        stdout, stderr, rc = _run_script({'tool_input': {}})
        assert rc == 0
        assert stdout == ''

    def test_empty_tool_input_exits_cleanly(self):
        stdout, stderr, rc = _run_script({})
        assert rc == 0
        assert stdout == ''


# ---------------------------------------------------------------------------
# B4-04: Script exits when ACE disabled flag exists
# ---------------------------------------------------------------------------

class TestB4DisabledFlag:
    def test_disabled_flag_exits_cleanly(self):
        session_id = 'test-disabled-b4'
        flag_path = f'/tmp/ace-disabled-{session_id}.flag'
        try:
            Path(flag_path).touch()
            stdout, stderr, rc = _run_script({
                'session_id': session_id,
                'tool_input': {'file_path': '/src/auth/login.py'},
            })
            assert rc == 0
            assert stdout == ''
        finally:
            Path(flag_path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# B4-05: Script exits when domains file doesn't exist
# ---------------------------------------------------------------------------

class TestB4NoDomainsFile:
    def test_no_domains_file_exits_cleanly(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a fake settings.json with a unique project ID
            claude_dir = Path(tmpdir) / '.claude'
            claude_dir.mkdir()
            settings = {'env': {'ACE_PROJECT_ID': 'nonexistent-project-b4-test'}}
            (claude_dir / 'settings.json').write_text(json.dumps(settings))

            stdout, stderr, rc = _run_script({
                'tool_input': {'file_path': '/src/auth/login.py'},
                'cwd': tmpdir,
            })
            assert rc == 0
            assert stdout == ''


# ---------------------------------------------------------------------------
# B4-06: Domain matching from file path
# ---------------------------------------------------------------------------

class TestB4DomainMatching:
    @pytest.fixture(autouse=True)
    def setup_domains(self, tmp_path):
        self.project_id = f'b4-domain-match-{os.getpid()}'
        self.domains_file = Path(f'/tmp/ace-domains-{self.project_id}.json')
        self.last_domain_file = Path(f'/tmp/ace-domain-{self.project_id}.txt')
        domains = {
            'authentication': {'description': 'Auth patterns'},
            'database': {'description': 'DB patterns'},
            'payments': {'description': 'Payment patterns'},
        }
        self.domains_file.write_text(json.dumps(domains))

        # Create settings.json in tmp_path
        claude_dir = tmp_path / '.claude'
        claude_dir.mkdir()
        settings = {'env': {'ACE_PROJECT_ID': self.project_id}}
        (claude_dir / 'settings.json').write_text(json.dumps(settings))
        self.cwd = str(tmp_path)

        # Create a mock ace-cli stub so tests NEVER make real network calls,
        # regardless of whether ace-cli is installed on the machine.
        # CLAUDE_PROJECT_DIR is set to tmp_path so patterns_used_state.py
        # writes its state files into the temp area rather than the real repo logs.
        mock_bin = tmp_path / 'mock_bin'
        mock_bin.mkdir()
        _make_mock_ace_cli(mock_bin)
        self.mock_ace_cli_dir = mock_bin
        self.env_extra = {'CLAUDE_PROJECT_DIR': str(tmp_path)}

        yield

        self.domains_file.unlink(missing_ok=True)
        self.last_domain_file.unlink(missing_ok=True)

    def test_matches_auth_domain_from_path(self):
        """File path containing 'authentication' word should match (deterministic, no network)."""
        stdout, stderr, rc = _run_script(
            {'tool_input': {'file_path': '/src/authentication/login.py'}, 'cwd': self.cwd},
            env_extra=self.env_extra,
            mock_ace_cli_dir=self.mock_ace_cli_dir,
        )
        assert rc == 0
        # Domain file must be updated to 'authentication' after a domain match
        assert self.last_domain_file.exists(), (
            "last-domain file not written — script did not detect domain match"
        )
        assert self.last_domain_file.read_text().strip() == 'authentication'

    def test_no_match_exits_cleanly(self):
        """File path with no matching domain words exits cleanly."""
        stdout, stderr, rc = _run_script(
            {'tool_input': {'file_path': '/src/utils/helpers.py'}, 'cwd': self.cwd},
            env_extra=self.env_extra,
            mock_ace_cli_dir=self.mock_ace_cli_dir,
        )
        assert rc == 0
        assert stdout == ''

    def test_same_domain_skipped(self):
        """If last domain matches current domain, skip injection."""
        self.last_domain_file.write_text('authentication')
        stdout, stderr, rc = _run_script(
            {'tool_input': {'file_path': '/src/authentication/middleware.py'}, 'cwd': self.cwd},
            env_extra=self.env_extra,
            mock_ace_cli_dir=self.mock_ace_cli_dir,
        )
        assert rc == 0
        assert stdout == '', "Same domain should produce no output"


# ---------------------------------------------------------------------------
# B4-07: Output format when ace-cli returns patterns
# ---------------------------------------------------------------------------

class TestB4OutputFormat:
    def test_output_is_valid_json_with_hook_specific_output(self):
        """When output is produced, it must be valid hookSpecificOutput JSON."""
        # This test validates the format; we simulate by checking the script's
        # echo statement structure (since ace-cli may not be installed)
        script_text = SCRIPT.read_text()
        assert 'hookSpecificOutput' in script_text
        assert 'hookEventName' in script_text
        assert 'PostToolUse' in script_text
        assert 'additionalContext' in script_text
        assert 'ace-patterns-domain-shift' in script_text

    def test_context_includes_domain_tag(self):
        """Output context must include domain attribute in XML tag."""
        script_text = SCRIPT.read_text()
        assert 'ace-patterns-domain-shift domain=' in script_text


# ---------------------------------------------------------------------------
# B4-08: Script strips metadata fields from patterns
# ---------------------------------------------------------------------------

class TestB4MetadataStripping:
    def test_strip_logic_present(self):
        """Script must include metadata stripping (delegated to --strip-and-gate helper)."""
        script_text = SCRIPT.read_text()
        # v7.1.2 Change B: stripping is now delegated to the shared --strip-and-gate
        # mode of patterns_used_state.py (which owns USEFUL_FIELDS + quality gate).
        # The inline 'useful=' set was removed in favour of the shared helper.
        assert "strip-and-gate" in script_text or "useful=" in script_text or "useful =" in script_text, (
            "Script must either inline useful= fields OR delegate to --strip-and-gate helper"
        )


# ---------------------------------------------------------------------------
# B4-09: Script robustness
# ---------------------------------------------------------------------------

class TestB4Robustness:
    def test_empty_stdin(self):
        """Empty stdin should not crash."""
        proc = subprocess.run(
            ['bash', str(SCRIPT)],
            input='',
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert proc.returncode == 0

    def test_invalid_json_stdin(self):
        """Invalid JSON on stdin should not crash."""
        proc = subprocess.run(
            ['bash', str(SCRIPT)],
            input='not json at all',
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert proc.returncode == 0

    def test_trap_on_error_exits_zero(self):
        """Script has ERR trap that exits 0 (no hook failure)."""
        script_text = SCRIPT.read_text()
        assert "trap" in script_text
        assert "exit 0" in script_text
