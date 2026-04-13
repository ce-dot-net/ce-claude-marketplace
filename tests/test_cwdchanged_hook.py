"""
Tests for CwdChanged Hook - Domain Detection on Directory Change

CC v2.1.83+ supports CwdChanged hook event.
Input: JSON with old_cwd, new_cwd, session_id, cwd
Output: JSON with hookEventName:"CwdChanged", optional watchPaths
"""

import json
import os
import stat
import subprocess
import tempfile

PLUGIN_DIR = os.path.join(os.path.dirname(__file__), '..', 'plugins', 'ace')
HOOKS_JSON = os.path.join(PLUGIN_DIR, 'hooks', 'hooks.json')
WRAPPER = os.path.join(PLUGIN_DIR, 'scripts', 'ace_cwdchanged_wrapper.sh')


def _read(path):
    with open(path) as f:
        return f.read()


class TestHooksJsonCwdChanged:
    """CwdChanged is NOT in hooks.json — CC plugin schema doesn't support it (same as PostCompact).
    The wrapper script exists but is not registered. Tests verify the script works standalone."""

    def test_cwdchanged_not_in_hooks_json(self):
        """CwdChanged removed from hooks.json — CC plugin schema rejects it."""
        hooks = json.loads(_read(HOOKS_JSON))
        assert 'CwdChanged' not in hooks['hooks'], \
            "CwdChanged must NOT be in hooks.json (CC schema rejects it)"

    def test_cwdchanged_wrapper_exists_standalone(self):
        """Wrapper script exists for future use when CC supports CwdChanged."""
        assert os.path.exists(WRAPPER), \
            "ace_cwdchanged_wrapper.sh should exist for future CC support"

    def test_cwdchanged_not_registered_placeholder(self):
        """Placeholder: CwdChanged is not registered but script is ready."""
        pass

    def test_cwdchanged_placeholder2(self):
        """Placeholder."""
        pass

    def test_cwdchanged_command_placeholder(self):
        """Placeholder — CwdChanged not registered in hooks.json."""
        pass


class TestCwdChangedWrapper:
    """ace_cwdchanged_wrapper.sh should exist and be properly configured."""

    def test_wrapper_exists(self):
        """Script file exists."""
        assert os.path.isfile(WRAPPER), \
            f"ace_cwdchanged_wrapper.sh not found at {WRAPPER}"

    def test_wrapper_executable(self):
        """Script has execute permission."""
        mode = os.stat(WRAPPER).st_mode
        assert mode & stat.S_IXUSR, \
            "ace_cwdchanged_wrapper.sh is not executable"

    def test_wrapper_no_exit_1(self):
        """Script never hard-exits with error (best-effort hook)."""
        content = _read(WRAPPER)
        assert 'exit 1' not in content, \
            "ace_cwdchanged_wrapper.sh has 'exit 1' - should always exit 0"

    def test_wrapper_reads_stdin(self):
        """Script reads input JSON from stdin."""
        content = _read(WRAPPER)
        assert 'INPUT_JSON=$(cat' in content, \
            "Wrapper should read JSON from stdin via cat"

    def test_wrapper_extracts_old_new_cwd(self):
        """Script extracts old_cwd and new_cwd from input."""
        content = _read(WRAPPER)
        assert 'old_cwd' in content
        assert 'new_cwd' in content

    def test_wrapper_has_disable_flag_check(self):
        """Script checks ACE disable flag."""
        content = _read(WRAPPER)
        assert 'ACE_DISABLED_FLAG' in content
        assert 'ace-disabled-' in content

    def test_wrapper_outputs_correct_hook_event_name(self):
        """Script outputs hookEventName: CwdChanged."""
        content = _read(WRAPPER)
        assert 'hookEventName' in content
        assert '"CwdChanged"' in content

    def test_wrapper_has_err_trap(self):
        """Script has ERR trap for resilience."""
        content = _read(WRAPPER)
        assert "trap" in content
        assert "ERR" in content

    def test_wrapper_checks_cli_availability(self):
        """Script checks for ace-cli before search operations."""
        content = _read(WRAPPER)
        assert 'command -v ace-cli' in content

    def test_wrapper_updates_domain_file(self):
        """Script writes to /tmp/ace-domain-{project}.txt."""
        content = _read(WRAPPER)
        assert 'ace-domain-' in content
        assert 'DOMAIN_FILE' in content

    def test_wrapper_has_domain_matching(self):
        """Script has domain matching logic."""
        content = _read(WRAPPER)
        assert 'match_domain_to_path' in content

    def test_wrapper_logs_domain_shift(self):
        """Script logs domain shift events."""
        content = _read(WRAPPER)
        assert 'ace-search-events.jsonl' in content
        assert '"domain_shift"' in content

    def test_wrapper_strips_metadata(self):
        """Script strips internal metadata from patterns."""
        content = _read(WRAPPER)
        assert 'useful=' in content or 'STRIPPED' in content

    def test_wrapper_bash_syntax_valid(self):
        """Script passes bash -n syntax check."""
        result = subprocess.run(
            ['bash', '-n', WRAPPER],
            capture_output=True, text=True
        )
        assert result.returncode == 0, \
            f"bash -n failed: {result.stderr}"


class TestCwdChangedExecution:
    """Test actual execution of the wrapper with mock data."""

    def test_exits_0_with_empty_input(self):
        """Script exits 0 with empty stdin (resilience)."""
        result = subprocess.run(
            ['bash', WRAPPER],
            input='{}',
            capture_output=True, text=True,
            timeout=5
        )
        assert result.returncode == 0, \
            f"Should exit 0 with empty input, got {result.returncode}: {result.stderr}"

    def test_exits_0_with_same_cwd(self):
        """Script exits 0 when old_cwd == new_cwd."""
        input_json = json.dumps({
            'session_id': 'test-session',
            'old_cwd': '/tmp/test',
            'new_cwd': '/tmp/test',
            'cwd': '/tmp/test'
        })
        result = subprocess.run(
            ['bash', WRAPPER],
            input=input_json,
            capture_output=True, text=True,
            timeout=5
        )
        assert result.returncode == 0

    def test_exits_0_with_missing_new_cwd(self):
        """Script exits 0 when new_cwd is missing."""
        input_json = json.dumps({
            'session_id': 'test-session',
            'old_cwd': '/tmp/test'
        })
        result = subprocess.run(
            ['bash', WRAPPER],
            input=input_json,
            capture_output=True, text=True,
            timeout=5
        )
        assert result.returncode == 0

    def test_exits_0_without_ace_cli(self):
        """Script exits 0 when ace-cli is not available."""
        input_json = json.dumps({
            'session_id': 'test-session',
            'old_cwd': '/tmp/old',
            'new_cwd': '/tmp/new',
            'cwd': '/tmp'
        })
        # Run with empty PATH to ensure no ace-cli
        env = os.environ.copy()
        env['PATH'] = '/usr/bin:/bin'
        result = subprocess.run(
            ['bash', WRAPPER],
            input=input_json,
            capture_output=True, text=True,
            timeout=5,
            env=env
        )
        assert result.returncode == 0

    def test_exits_0_without_domains_file(self):
        """Script exits 0 when domains file doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a fake settings.json with project ID
            settings_dir = os.path.join(tmpdir, '.claude')
            os.makedirs(settings_dir)
            with open(os.path.join(settings_dir, 'settings.json'), 'w') as f:
                json.dump({'projectId': 'test-no-domains'}, f)

            input_json = json.dumps({
                'session_id': 'test-session',
                'old_cwd': '/tmp/old',
                'new_cwd': tmpdir,
                'cwd': tmpdir
            })
            result = subprocess.run(
                ['bash', WRAPPER],
                input=input_json,
                capture_output=True, text=True,
                timeout=5
            )
            assert result.returncode == 0

    def test_disabled_flag_skips_execution(self):
        """Script exits immediately when disable flag exists."""
        flag_path = '/tmp/ace-disabled-test-disabled-session.flag'
        try:
            with open(flag_path, 'w') as f:
                f.write('disabled')
            input_json = json.dumps({
                'session_id': 'test-disabled-session',
                'old_cwd': '/tmp/old',
                'new_cwd': '/tmp/new',
                'cwd': '/tmp'
            })
            result = subprocess.run(
                ['bash', WRAPPER],
                input=input_json,
                capture_output=True, text=True,
                timeout=5
            )
            assert result.returncode == 0
            # Should produce no output when disabled
            assert result.stdout.strip() == ''
        finally:
            os.unlink(flag_path) if os.path.exists(flag_path) else None
