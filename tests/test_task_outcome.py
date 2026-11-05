"""8.1.3 end-outcome rule: result.success = the END outcome, result.failed_steps = failed steps (informational).

Shared fixture: plugins/ace/tests-fixtures/task-outcome/ (see its README). Mirror runner: plugins/ace/mod/tests/outcome.test.ts.
`python3 tests/test_task_outcome.py --regen` rewrites the mod's .ts wrapper.
"""
import json
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
FIX = REPO / 'plugins/ace/tests-fixtures/task-outcome'
WRAPPER = REPO / 'plugins/ace/mod/tests/fixtures/outcome_cases.ts'
TRACE_TS = REPO / 'plugins/ace/mod/lib/trace.ts'
sys.path.insert(0, str(REPO / 'plugins/ace/shared-hooks'))

CASES = json.loads((FIX / 'cases.json').read_text())['cases']
TABLES = json.loads((FIX / 'tables.json').read_text())


def wrapper_text():
    return ('// GENERATED from tests-fixtures/task-outcome/{cases,tables}.json (mods load only .ts); '
            'tests/test_task_outcome.py guards the sync.\n'
            'export const CASES = %s\nexport const TABLES = %s\n' % (json.dumps(CASES), json.dumps(TABLES)))


def native(step, i):
    """A neutral fixture step -> the accumulator / transcript 8-tuple the Stop hook reads."""
    tool = step['tool']
    tin = {}
    if 'command' in step:
        tin['command'] = step['command']
    if 'file_path' in step:
        tin['file_path'] = step['file_path']
    exit_code, stderr = step.get('exit'), step.get('stderr', '')
    if step.get('interrupted'):
        resp = {'interrupted': True}  # accumulator: PostToolUseFailure is_interrupt
    elif step.get('denied'):  # accumulator: a PostToolBatch deny row (success=0) as get_session_tools returns it
        text = 'Permission to use %s has been denied.' % tool
        resp = {'content': text, 'error': text}
    elif step.get('is_error'):  # PostToolUseFailure `error` text: "Exit code N\n<stderr>" for Bash
        resp = {'error': ('Exit code %d\n%s' % (exit_code, stderr)) if exit_code is not None else (stderr or 'failed')}
    elif tool == 'Bash':
        resp = {'stdout': step.get('stdout', ''), 'stderr': stderr}
        if exit_code is not None:
            resp['exit_code'] = exit_code
    else:
        resp = {'content': 'ok'}
    return (tool, json.dumps(tin), json.dumps(resp), 'toolu_%d' % i, None, None, None, None)


@pytest.mark.parametrize('case', CASES, ids=[c['name'] for c in CASES])
def test_fixture_case(case):
    from ace_after_task import task_outcome
    success, failed, aborted = task_outcome([native(s, i) for i, s in enumerate(case['steps'])])
    got = {'success': success, 'failed_steps': failed}
    if aborted:
        got['aborted'] = True
    assert got == case['expect']


def test_fixture_is_big_enough():
    assert len(CASES) >= 30


@pytest.mark.parametrize('cmd,fam', TABLES['families'])
def test_command_family(cmd, fam):
    from ace_after_task import command_family
    assert command_family(cmd) == fam


def test_python_tables_equal_fixture():
    import ace_after_task as a
    assert list(a.BENIGN_EXIT1) == TABLES['benign_exit1']
    assert list(a.READ_ONLY_BASH) == TABLES['read_only_bash']
    assert list(a.DECISIVE_TOOLS) == TABLES['decisive_tools']


def _ts_array(name):
    m = re.search(r'export const %s = (\[[^\]]*\])' % re.escape(name), TRACE_TS.read_text())
    assert m, name + ' not found in mod/lib/trace.ts'
    return json.loads(m.group(1).replace("'", '"'))


def test_mod_tables_equal_fixture():
    """Parity: the mod keeps its own tables (no shared code across languages); they must equal the fixture."""
    assert _ts_array('BENIGN_EXIT1') == TABLES['benign_exit1']
    assert _ts_array('READ_ONLY_BASH') == TABLES['read_only_bash']
    assert _ts_array('DECISIVE_TOOLS') == TABLES['decisive_tools']


def test_mod_wrapper_in_sync():
    assert WRAPPER.read_text() == wrapper_text(), 'run: python3 tests/test_task_outcome.py --regen'


def test_mod_runs_the_shared_fixture():
    """Parity: the mod suite runs the same cases against the same expectations."""
    t = (REPO / 'plugins/ace/mod/tests/outcome.test.ts').read_text()
    assert "from './fixtures/outcome_cases.ts'" in t and 'taskOutcome' in t and 'toolRec' in t


# ---- shapes beyond the neutral fixture ----

def test_transcript_exit_code_text_and_return_code_interpretation():
    from ace_after_task import task_outcome
    grep = ('Bash', json.dumps({'command': 'grep x f'}), json.dumps({'content': 'Exit code 1', 'error': 'Exit code 1'}), 't1', None, None, None, None)
    make = ('Bash', json.dumps({'command': 'make'}), json.dumps({'content': 'Exit code 2\nboom'}), 't2', None, None, None, None)
    interp = ('Bash', json.dumps({'command': 'make'}), json.dumps({'exitCode': 1, 'returnCodeInterpretation': 'x'}), 't3', None, None, None, None)
    assert task_outcome([grep]) == (True, 0, False)
    assert task_outcome([make]) == (False, 1, False)
    assert task_outcome([interp]) == (True, 0, False)


def test_batch_string_response_is_a_success():
    from ace_after_task import task_outcome
    row = ('Bash', json.dumps({'command': 'rstest'}), json.dumps('3 passed'), 't1', None, None, None, None)
    assert task_outcome([row]) == (True, 0, False)


def test_tool_failed_stderr_alone_is_not_a_failure():
    from ace_after_task import tool_failed
    assert tool_failed({'stdout': 'ok', 'stderr': 'warn', 'exit_code': 0}) is False
    assert tool_failed({'stderr': 'warn'}) is False
    assert tool_failed({'error': 'boom'}) is True


if __name__ == '__main__' and '--regen' in sys.argv:
    WRAPPER.write_text(wrapper_text())
    print('wrote', WRAPPER)
