"""TDD RED: ACE Statusline — CC native statusline integration.

Tests for:
- ace_statusline.sh: statusline script reading CC JSON stdin + ACE state files
- ace-statusline.md: slash command to install the statusline
- SessionStart hint in ace_install_cli.sh
"""
import stat
from pathlib import Path

PLUGIN_ROOT = Path(__file__).parent.parent / 'plugins' / 'ace'
SCRIPTS_DIR = PLUGIN_ROOT / 'scripts'
COMMANDS_DIR = PLUGIN_ROOT / 'commands'


class TestStatuslineScript:
    """Tests for plugins/ace/scripts/ace_statusline.sh"""

    def test_statusline_script_exists(self):
        script = SCRIPTS_DIR / 'ace_statusline.sh'
        assert script.exists(), "ace_statusline.sh must exist in scripts/"

    def test_statusline_script_is_executable(self):
        script = SCRIPTS_DIR / 'ace_statusline.sh'
        assert script.exists()
        mode = script.stat().st_mode
        assert mode & stat.S_IXUSR, "ace_statusline.sh must be executable"

    def test_statusline_reads_stdin_json(self):
        """Statusline receives CC JSON via stdin — must read it"""
        script = SCRIPTS_DIR / 'ace_statusline.sh'
        content = script.read_text()
        # Must read stdin (CC sends JSON with model, context_window, cost, etc.)
        assert any(pattern in content for pattern in ['read ', 'cat', 'INPUT_JSON', '<&0', '/dev/stdin']), \
            "Script must read JSON from stdin"

    def test_statusline_reads_ace_state_file(self):
        """Must read ACE state file for learning results and pattern stats"""
        script = SCRIPTS_DIR / 'ace_statusline.sh'
        content = script.read_text()
        assert 'ace-statusline-state.json' in content, \
            "Script must reference ace-statusline-state.json for ACE state"

    def test_statusline_reads_relevance_jsonl(self):
        """Must read relevance log for live search stats"""
        script = SCRIPTS_DIR / 'ace_statusline.sh'
        content = script.read_text()
        assert 'ace-relevance.jsonl' in content, \
            "Script must reference ace-relevance.jsonl for search stats"

    def test_statusline_shows_pattern_count(self):
        """Must display pattern count from cached status"""
        script = SCRIPTS_DIR / 'ace_statusline.sh'
        content = script.read_text()
        assert any(p in content for p in ['patterns', 'total_patterns', 'PATTERNS']), \
            "Script must display pattern count"

    def test_statusline_shows_learning_result(self):
        """Must show last learning result from state file"""
        script = SCRIPTS_DIR / 'ace_statusline.sh'
        content = script.read_text()
        assert any(p in content for p in ['last_learn', 'learn_result', 'LEARN']), \
            "Script must display last learning result"

    def test_statusline_has_no_network_calls(self):
        """Statusline must be fast — no ace-cli or curl calls (all from local files)"""
        script = SCRIPTS_DIR / 'ace_statusline.sh'
        content = script.read_text()
        # Filter out comments — only check executable lines
        executable_lines = [l for l in content.splitlines() if l.strip() and not l.strip().startswith('#')]
        exec_content = '\n'.join(executable_lines)
        assert 'ace-cli' not in exec_content, \
            "Statusline must not call ace-cli (too slow, use cached state)"
        assert 'curl' not in exec_content, \
            "Statusline must not make network calls"

    def test_statusline_handles_missing_state_gracefully(self):
        """Must handle missing state file without errors"""
        script = SCRIPTS_DIR / 'ace_statusline.sh'
        content = script.read_text()
        # Should check file existence before reading
        assert any(p in content for p in ['-f ', '[ -f', 'test -f', 'if [', '2>/dev/null']), \
            "Script must handle missing state file gracefully"

    def test_statusline_shows_per_task_relevance(self):
        """Must show per-task relevance % from search confidence"""
        script = SCRIPTS_DIR / 'ace_statusline.sh'
        content = script.read_text()
        assert any(p in content for p in ['avg_confidence', 'avg_relevance', 'relevance']), \
            "Script must show per-task relevance from search confidence"

    def test_statusline_shows_domains(self):
        """Must show domain count or domain shifts"""
        script = SCRIPTS_DIR / 'ace_statusline.sh'
        content = script.read_text()
        assert any(p in content for p in ['domains', 'domain_shift', 'shifts']), \
            "Script must show domain activity"


class TestStatuslineCommand:
    """Tests for /ace-statusline install command"""

    def test_statusline_command_exists(self):
        cmd = COMMANDS_DIR / 'ace-statusline.md'
        assert cmd.exists(), "ace-statusline.md command must exist"

    def test_statusline_command_has_frontmatter(self):
        cmd = COMMANDS_DIR / 'ace-statusline.md'
        content = cmd.read_text()
        assert content.startswith('---'), "Command must have YAML frontmatter"
        assert 'name:' in content, "Frontmatter must have name field"
        assert 'description:' in content, "Frontmatter must have description field"

    def test_statusline_command_references_script(self):
        cmd = COMMANDS_DIR / 'ace-statusline.md'
        content = cmd.read_text()
        assert 'ace_statusline.sh' in content, \
            "Command must reference the statusline script"

    def test_statusline_command_writes_settings(self):
        """Command must configure ~/.claude/settings.json"""
        cmd = COMMANDS_DIR / 'ace-statusline.md'
        content = cmd.read_text()
        assert any(p in content for p in ['settings.json', 'statusLine', 'statusline']), \
            "Command must write statusLine to settings.json"

    def test_statusline_command_copies_script(self):
        """Command must copy script to ~/.claude/ for portability"""
        cmd = COMMANDS_DIR / 'ace-statusline.md'
        content = cmd.read_text()
        assert any(p in content for p in ['cp ', 'copy', 'install']), \
            "Command must copy script to ~/.claude/"


class TestSessionStartHint:
    """Tests for one-time statusline hint on SessionStart"""

    def test_sessionstart_has_statusline_hint(self):
        script = SCRIPTS_DIR / 'ace_install_cli.sh'
        content = script.read_text()
        assert any(p in content for p in ['ace-statusline', 'statusline', 'status bar']), \
            "SessionStart must have statusline hint"

    def test_sessionstart_hint_checks_existing_config(self):
        """Don't show hint if user already has a statusline configured"""
        script = SCRIPTS_DIR / 'ace_install_cli.sh'
        content = script.read_text()
        assert any(p in content for p in ['statusLine', '"statusLine"', 'statusline']), \
            "Hint must check if statusline is already configured"

    def test_sessionstart_hint_is_dismissable(self):
        """Hint should use a flag file to avoid repeating"""
        script = SCRIPTS_DIR / 'ace_install_cli.sh'
        content = script.read_text()
        assert any(p in content for p in ['ace-statusline-hint', 'hint-dismissed', 'ACE_STATUSLINE']), \
            "Hint must be dismissable via flag file or env var"
