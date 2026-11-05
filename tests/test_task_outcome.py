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
RANDOM_FILE = FIX / 'random_cases.json'
RANDOM = json.loads(RANDOM_FILE.read_text()) if RANDOM_FILE.exists() else []


def wrapper_text():
    return ('// GENERATED from tests-fixtures/task-outcome/{cases,tables}.json (mods load only .ts); '
            'tests/test_task_outcome.py guards the sync.\n'
            'export const CASES = %s\nexport const TABLES = %s\nexport const RANDOM = %s\n'
            % (json.dumps(CASES), json.dumps(TABLES), json.dumps(RANDOM)))


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
    assert dict(a.SUBCOMMAND_TOOLS) == TABLES['subcommand_tools']
    assert list(a.MCP_WRITE_VERBS) == TABLES['mcp_write_verbs']


@pytest.mark.parametrize('cmd,action', TABLES['actions'], ids=[repr(c)[:40] for c, _ in TABLES['actions']])
def test_bash_action(cmd, action):
    """Bash trajectory action: '<family> :: <redacted command, whitespace collapsed, <= 200 chars>'; 'unknown' if none."""
    from ace_after_task import summarize_tool_action
    assert summarize_tool_action('Bash', {} if cmd is None else {'command': cmd}) == action


@pytest.mark.parametrize('cmd,key', TABLES['keys'], ids=[c[:40] for c, _ in TABLES['keys']])
def test_bash_recovery_key(cmd, key):
    """The recovery key: the family, plus a script hash (interpreter -c/-e/heredoc) or method+host (curl/wget)."""
    from ace_after_task import bash_step
    assert bash_step(cmd)[2] == key


def test_family_never_holds_a_secret_or_userinfo():
    from ace_after_task import command_family
    for cmd in ['git clone https://u:Zq7c@github.com/o/r', 'git push https://Zq7c@h/o/r', 'gh auth login Zq7cZq7cZq7cZq7cZq7cZq7c0',
                'curl -u a:Zq7c https://h', 'npm publish --token=Zq7c', 'docker login ghp_Zq7cZq7cZq7c']:
        assert 'Zq7c' not in command_family(cmd), cmd


@pytest.mark.parametrize('text,out', TABLES['redact'], ids=[t[:30] for t, _ in TABLES['redact']])
def test_redact(text, out):
    from ace_after_task import redact
    assert redact(text) == out


# ---- property test: random step sequences, Python computes, the mod must agree (outcome.test.ts runs RANDOM) ----
_CMDS = ['curl -X POST https://a.x/y', 'curl -X POST https://b.x/y', 'awk 1 a > out', 'sed -i s/a/b/ f', 'bash -c "echo hi"', 'make', 'make test', 'make && echo done', 'npm test', 'npm publish', 'echo y | npm publish', 'rstest tests',
         'rstest tests | grep FAIL', 'grep -rn x src', 'cd /p && grep x f', 'cat cfg | kubectl apply -f -', 'kubectl get pods',
         'gh pr merge 1', 'gh pr view 1', 'git push origin main', 'git diff --quiet', 'git commit -m "a && b"',
         'python3 deploy.py', 'python3 -c "x"', "python3 - <<'EOF'\nimport a && b\nEOF", '(cd sub && make test)',
         'echo $(make && echo ok)', 'make || true', 'make; make install', 'ls /missing', 'cat a | sort | head -1',
         'docker compose up', 'bash -c "make"', 'echo "unterminated && make', 'FOO=1 ./run.sh', '']
_TOOLS = ['Read', 'Edit', 'Write', 'Glob', 'Agent', 'Workflow', 'WebFetch', 'mcp__plugin_linear_linear__save_issue',
          'mcp__plugin_linear_linear__list_issues', 'mcp__srv__sendMessage']


def random_cases(n=400, seed=813):
    import random
    from ace_after_task import task_outcome
    rnd = random.Random(seed)
    out = []
    for k in range(n):
        steps = []
        for _ in range(rnd.randint(1, 7)):
            if rnd.random() < 0.6:
                st = {'tool': 'Bash', 'command': rnd.choice(_CMDS)}
                r = rnd.random()
                if r < 0.45:
                    st['exit'] = 0
                elif r < 0.9:
                    st['exit'], st['is_error'] = rnd.choice([1, 1, 2, 127]), True
                elif r < 0.95:
                    st['denied'] = True
                else:
                    st['interrupted'] = True
            else:
                st = {'tool': rnd.choice(_TOOLS)}
                if st['tool'] in ('Read', 'Edit', 'Write'):
                    st['file_path'] = rnd.choice(['/p/a.py', '/p/b.py'])
                r = rnd.random()
                if r < 0.3:
                    st['is_error'] = True
                elif r < 0.35:
                    st['denied'] = True
            steps.append(st)
        success, failed, aborted = task_outcome([native(s, i) for i, s in enumerate(steps)])
        exp = {'success': success, 'failed_steps': failed}
        if aborted:
            exp['aborted'] = True
        out.append({'name': 'random %d' % k, 'steps': steps, 'expect': exp})
    return out


def test_random_property_cases_in_sync():
    """400 seeded random sequences; the stored expectations are what the Python chain computes now, and the mod suite
    asserts it computes the same (parity property test). Regenerate with --regen after a rule change."""
    assert len(RANDOM) == 400 and RANDOM == random_cases(), 'run: python3 tests/test_task_outcome.py --regen'
    assert any(not c['expect']['success'] for c in RANDOM) and any(c['expect']['success'] for c in RANDOM)


def _ts_array(name):
    m = re.search(r'export const %s(?:: [^=]+)? = (\[[^\]]*\]|\{[^}]*\})' % re.escape(name), TRACE_TS.read_text())
    assert m, name + ' not found in mod/lib/trace.ts'
    return json.loads(m.group(1).replace("'", '"'))


def test_mod_tables_equal_fixture():
    """Parity: the mod keeps its own tables (no shared code across languages); they must equal the fixture."""
    assert _ts_array('BENIGN_EXIT1') == TABLES['benign_exit1']
    assert _ts_array('READ_ONLY_BASH') == TABLES['read_only_bash']
    assert _ts_array('DECISIVE_TOOLS') == TABLES['decisive_tools']
    assert _ts_array('SUBCOMMAND_TOOLS') == TABLES['subcommand_tools']
    assert _ts_array('MCP_WRITE_VERBS') == TABLES['mcp_write_verbs']


def test_mod_wrapper_in_sync():
    assert WRAPPER.read_text() == wrapper_text(), 'run: python3 tests/test_task_outcome.py --regen'


def test_mod_runs_the_shared_fixture():
    """Parity: the mod suite runs the same cases against the same expectations."""
    t = (REPO / 'plugins/ace/mod/tests/outcome.test.ts').read_text()
    assert "from './fixtures/outcome_cases.ts'" in t and 'taskOutcome' in t and 'toolRec' in t
    assert 'RANDOM' in t and 'TABLES.actions' in t and 'TABLES.redact' in t


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


def _strings(x):
    if isinstance(x, str):
        yield x
    elif isinstance(x, dict):
        for v in x.values():
            yield from _strings(v)
    elif isinstance(x, list):
        for v in x:
            yield from _strings(v)


def fuzz_fields(pw_triples, templates):
    """Every sent text field the Python chain builds from a command: action, step results, task, summary."""
    from ace_after_task import redact, summarize_tool_action, summarize_tool_response
    leaks = {}
    for pw, pwu, pwq in pw_triples:
        for tpl in templates:
            cmd = tpl.replace('{pwu}', pwu).replace('{pwq}', pwq).replace('{pw}', pw)
            sent = [summarize_tool_action('Bash', {'command': cmd}),
                    summarize_tool_response('Bash', {'error': 'Exit code 1\n' + cmd}),
                    summarize_tool_response('Bash', {'stdout': cmd}), summarize_tool_response('Bash', {'stderr': cmd}),
                    summarize_tool_response('Bash', 'fatal: ' + cmd), summarize_tool_response('mcp__x__save', {'text': cmd}),
                    redact('User request: run ' + cmd)[:2000], redact('ran ' + cmd)[:2000]]
            secret = pwq if '{pwq}' in tpl else pwu if '{pwu}' in tpl else pw
            probes = {secret, ' '.join(secret.split())} - {''}
            if any(p in x for x in sent for p in probes):
                leaks[tpl] = leaks.get(tpl, 0) + 1
    return leaks


def test_fuzz_passwords_reach_no_sent_field():
    """Fail-closed redaction: 500 random passwords (printable ASCII incl. space and quotes, some Unicode) x 31 forms;
    the password is in no sent field. The mod runs the same table through buildTrace. Full size: --fuzz 5000."""
    assert len(TABLES['fuzz_templates']) >= 25
    assert fuzz_fields(TABLES['fuzz_passwords'], TABLES['fuzz_templates']) == {}


def test_unparsable_commands_never_crash():
    from ace_after_task import command_family, summarize_tool_action
    for cmd in ['"', "'", '$(', '`', '((', '))', '<<', '<<EOF', '| |', '&& ;', '\\', 'a |& b', '\x00', 123]:
        command_family(cmd)
        assert summarize_tool_action('Bash', {'command': cmd})


if __name__ == '__main__' and '--fuzz' in sys.argv:
    import random
    import string
    n = int(sys.argv[sys.argv.index('--fuzz') + 1])
    base = [c for c in string.printable if c not in '\n\r\t\x0b\x0c'] + list('éüß€漢Ωж')
    rnd, trip = random.Random(5000), []
    for _ in range(n):
        pw = ''.join(rnd.choice(base) for _ in range(rnd.randint(8, 30)))
        pwu = ''.join(c for c in pw if c not in ' "\'') or 'x'
        trip.append([pw, pwu, ''.join(c for c in pwu if c not in '&#') or 'x'])
    print(n, 'passwords x', len(TABLES['fuzz_templates']), 'forms, leaks:', fuzz_fields(trip, TABLES['fuzz_templates']))

if __name__ == '__main__' and '--regen' in sys.argv:
    RANDOM = random_cases()
    RANDOM_FILE.write_text(json.dumps(RANDOM, separators=(',', ':')) + '\n')
    WRAPPER.write_text(wrapper_text())
    print('wrote', RANDOM_FILE, WRAPPER)
