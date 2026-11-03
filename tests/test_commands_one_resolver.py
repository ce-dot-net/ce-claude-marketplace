"""8.1.0: no markdown command reads a binding file itself; each goes through scripts/ace-context (the one core),
and every project-scoped ace-cli call carries the core's --org/--project."""
import re
from pathlib import Path

import pytest

CMDS = Path(__file__).resolve().parents[1] / 'plugins/ace/commands'
FENCE = re.compile(r'```(?:bash|sh|python)?\n(.*?)```', re.S)
SCOPED = re.compile(r'scripts/ace-cli[^\n]*\b(search|patterns|top|status|domains|export|import|delta|learn|bootstrap|tune|clear)\b')


def blocks(p):
    """Code fences (bash/sh/python or bare), parsed line by line."""
    out, cur, lang = [], None, None
    for line in p.read_text().splitlines():
        if line.lstrip().startswith('```'):
            if cur is None:
                cur, lang = [], line.strip()[3:].strip()
            else:
                if lang in ('', 'bash', 'sh', 'python'):
                    out.append('\n'.join(cur))
                cur = None
        elif cur is not None:
            cur.append(line)
    return out


@pytest.mark.parametrize('p', sorted(CMDS.glob('*.md')), ids=lambda p: p.name)
def test_no_command_parses_settings_json(p):
    for b in blocks(p):
        for line in b.splitlines():
            if 'settings.json' in line and p.name != 'ace-statusline-setup.md':
                assert line.lstrip().startswith('#'), '%s: %s' % (p.name, line)


@pytest.mark.parametrize('p', sorted(CMDS.glob('*.md')), ids=lambda p: p.name)
def test_project_scoped_cli_calls_carry_the_core_ids(p):
    for b in blocks(p):
        for line in b.splitlines():
            if SCOPED.search(line) and not line.lstrip().startswith('#') and 'AskUserQuestion' not in line:
                assert '--project' in line, '%s: %s' % (p.name, line)


@pytest.mark.parametrize('p', [p for p in sorted(CMDS.glob('*.md')) if 'ACE_ORG_ID' in p.read_text()], ids=lambda p: p.name)
def test_commands_that_use_the_ids_get_them_from_ace_context(p):
    t = p.read_text()
    assert 'scripts/ace-context' in t
    assert 'scripts/ace-context:*' in t.split('---', 2)[1], 'allowed-tools must name the entrypoint'


def test_removed_shell_scripts_stay_removed():
    scripts = CMDS.parent / 'scripts'
    assert not (scripts / 'ace-tune.sh').exists() and not (scripts / 'ace-bootstrap.sh').exists()
    assert (scripts / 'ace-context').exists() and (scripts / 'ace-cli').exists()
