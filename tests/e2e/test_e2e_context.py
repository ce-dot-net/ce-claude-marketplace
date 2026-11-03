"""8.1.0 hermetic e2e for the one binding core (Python chain): real git repos with a linked worktree, the real hooks
through their shims with the fake ace-cli, scripts/ace-context, and the verify states of a real ace-cli against
tests/engine_fake_server.py. Attack cases: shell-metacharacter dir names, a refused/broken config, no CLI.

Gated: ACE_E2E=1. The real-CLI part runs when a real ace-cli is found (ACE_E2E_CLI=<cli.js>, the plugin-local pin,
or the active plugin cache); the SDK-prerelease parity part only with ACE_PRERELEASE_PREFIX=<npm prefix>.
"""
import glob
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PLUGIN = REPO / 'plugins/ace'
sys.path.insert(0, str(PLUGIN / 'shared-hooks/utils'))
import ace_project_context as apc  # noqa: E402

pytestmark = pytest.mark.skipif(os.environ.get('ACE_E2E') != '1', reason='e2e: set ACE_E2E=1')
ORG, PRJ = 'org_e2e', 'prj_e2e'


def git(cwd, *a):
    return subprocess.run(['git', '-C', str(cwd), *a], capture_output=True, text=True, check=True).stdout


def mkrepo(p, remote='git@github.com:acme/e2e.git'):
    p.mkdir(parents=True)
    git(p, 'init', '-q')
    git(p, 'config', 'user.email', 't@example.invalid')
    git(p, 'config', 'user.name', 't')
    git(p, 'remote', 'add', 'origin', remote)
    (p / 'README').write_text('x')
    git(p, 'add', 'README')
    git(p, 'commit', '-qm', 'init')
    return p


def legacy(p):
    (p / '.claude').mkdir(exist_ok=True)
    (p / '.claude/settings.json').write_text(json.dumps({'env': {'ACE_ORG_ID': ORG, 'ACE_PROJECT_ID': PRJ}}))


@pytest.fixture
def box(tmp_path, monkeypatch):
    monkeypatch.setenv('CLAUDE_PLUGIN_DATA', str(tmp_path / 'ace-data'))
    monkeypatch.setenv('ACE_CONFIG_PATH', str(tmp_path / 'no-global.json'))
    for k in ('ACE_ORG_ID', 'ACE_PROJECT_ID', 'ACE_CONTEXT'):
        monkeypatch.delenv(k, raising=False)
    apc._CACHE.clear()
    return tmp_path


def ctx_cli(cwd, *a, env=None):
    return subprocess.run([str(PLUGIN / 'scripts/ace-context'), *a], cwd=str(cwd), capture_output=True, text=True,
                          env=dict(os.environ, **(env or {})))


def ups(cwd, sid, prompt='please refactor the hook so it injects patterns when reading plugin files'):
    ev = {'hook_event_name': 'UserPromptSubmit', 'session_id': sid, 'cwd': str(cwd), 'prompt': prompt,
          'transcript_path': '/dev/null', 'prompt_id': 'p-' + sid}
    return subprocess.run([str(PLUGIN / 'scripts/ace_before_task_wrapper.sh')], input=json.dumps(ev), cwd=str(cwd),
                          capture_output=True, text=True, timeout=60, env=dict(os.environ, CLAUDE_PLUGIN_ROOT=str(PLUGIN)))


def rows(main):
    f = main / '.claude/data/logs/ace-relevance.jsonl'
    return [json.loads(l) for l in f.read_text().splitlines()] if f.exists() else []


# ---- the must-have: already-bound repos, worktrees and subfolders, zero manual steps ----

def test_worktree_and_subfolder_of_a_legacy_bound_repo(box):
    main = mkrepo(box / 'ace-web')
    legacy(main)
    (main / '.claude/data/logs').mkdir(parents=True)
    wt = box / 'wts' / 'AOP-1-umsetzer'
    git(main, 'worktree', 'add', '-q', str(wt))
    (wt / 'src/deep').mkdir(parents=True)
    for cwd in (wt, wt / 'src/deep', main / '.claude'):
        r = json.loads(ctx_cli(cwd, '--json', env={'ACE_AUTO_ADOPT': '0'}).stdout)
        assert (r['bound'], r['source'], r['projectId']) == (True, 'settings_file', PRJ), cwd
        assert os.path.realpath(r['path']) == os.path.realpath(main / '.claude/settings.json')


def test_hooks_in_a_worktree_search_with_explicit_ids_log_at_the_main_root_and_adopt(box, monkeypatch):
    main = mkrepo(box / 'web')
    legacy(main)
    (main / '.gitignore').write_text('.claude/\n.ace/\n')
    git(main, 'add', '.gitignore')
    git(main, 'commit', '-qm', 'ignore')
    (main / '.claude/data/logs').mkdir(parents=True)
    wt = box / 'wt'
    git(main, 'worktree', 'add', '-q', str(wt))
    log = box / 'cli.log'
    monkeypatch.setenv('ACE_FAKE_CLI_LOG', str(log))
    p = ups(wt / '', 'sess-e2e-1')
    assert p.returncode == 0, p.stderr
    calls = [json.loads(l) for l in log.read_text().splitlines()]
    search = [c for c in calls if c['argv'][:1] == ['search']]
    assert search and '--org' in search[0]['argv'] and search[0]['argv'][search[0]['argv'].index('--project') + 1] == PRJ
    ctx = [x for x in rows(main) if x.get('event') == 'context']
    assert not (wt / '.claude/data').exists()  # one log for the repo: the main checkout's
    assert json.loads((main / '.ace/config.json').read_text()) == {'orgId': ORG, 'projectId': PRJ}
    assert '!.ace/config.json' in (main / '.gitignore').read_text()
    assert git(main, 'diff', '--cached', '--name-only') == ''  # never staged
    assert '.ace/' in git(main, 'status', '--porcelain', '--untracked-files=all')
    out = json.loads(p.stdout) if p.stdout.strip() else {}
    assert apc.ADOPT_LINE in out.get('systemMessage', '')
    # the detached verify writes the one context row
    for _ in range(100):
        ctx = [x for x in rows(main) if x.get('event') == 'context']
        if ctx:
            break
        time.sleep(0.1)
    # verify runs after the adoption: the binding is the adopted tracked file by then
    assert len(ctx) == 1 and ctx[0]['source'] in ('settings_file', 'repo_file') and ctx[0]['root'] == str(main)


def test_unbound_temp_dir_one_line_no_log_dir(box):
    d = box / 'plain'
    d.mkdir()
    p = ctx_cli(d, '--shell')
    assert p.returncode == 5 and p.stdout == '' and p.stderr.strip() == apc.LINES['unbound']
    assert ups(d, 'sess-e2e-2').stdout.strip() == json.dumps({'systemMessage': apc.LINES['unbound']})
    assert ups(d, 'sess-e2e-2').stdout.strip() == ''
    assert not (d / '.claude').exists()


@pytest.mark.parametrize('body,state', [('{"orgId":"org_a","projectId":"prj_a","apiToken":"ace_user_secret"}', 'config_refused'),
                                        ('{"orgId": "org_a", ', 'config_invalid'),
                                        ('{"orgId":"org_a","projectId":"prj_a/../../etc"}', 'config_invalid')])
def test_bad_config_never_reaches_the_cli(box, monkeypatch, body, state):
    main = mkrepo(box / 'r')
    (main / '.ace').mkdir()
    (main / '.ace/config.json').write_text(body)
    log = box / 'cli.log'
    monkeypatch.setenv('ACE_FAKE_CLI_LOG', str(log))
    p = ups(main, 'sess-e2e-3', )
    assert json.loads(p.stdout)['systemMessage'] == apc.LINES[state]
    assert not log.exists() or not [l for l in log.read_text().splitlines() if '"search"' in l]


def test_shell_metacharacters_in_a_path_never_execute(box):
    weird = box / 'x$(touch CANARY)`touch CANARY2`;y'
    main = mkrepo(weird)
    (main / '.ace').mkdir()
    (main / '.ace/config.json').write_text(json.dumps({'orgId': ORG, 'projectId': PRJ}))
    out = ctx_cli(main, '--shell').stdout
    subprocess.run(['bash', '-c', 'eval "$1"; printf %s "$ACE_PROJECT_ID"', 'bash', out], cwd=str(box), check=True)
    assert not list(box.glob('CANARY*')) and not list(Path.cwd().glob('CANARY*'))


def test_cli_missing_is_its_own_state(box, monkeypatch):
    main = mkrepo(box / 'r')
    (main / '.ace').mkdir()
    (main / '.ace/config.json').write_text(json.dumps({'orgId': ORG, 'projectId': PRJ}))
    monkeypatch.setenv('PATH', '/usr/bin:/bin')
    monkeypatch.setenv('ACE_PLUGIN_ROOT_UNDER_TEST', '')
    monkeypatch.setenv('CLAUDE_PLUGIN_ROOT', str(box / 'no-plugin'))
    import ace_cli
    monkeypatch.setattr(ace_cli, 'cli_argv', lambda: None)
    assert apc.verify(apc.context(str(main))) == 'cli_missing'


# ---- a real ace-cli against the fake server: every verify state ----

def real_cli():
    c = os.environ.get('ACE_E2E_CLI') or str(PLUGIN / 'node_modules/@ace-sdk/cli/dist/cli.js')
    if Path(c).exists():
        return c
    import pwd
    home = pwd.getpwuid(os.getuid()).pw_dir  # conftest sandboxes HOME
    for p in sorted(glob.glob(home + '/.claude/plugins/cache/*/ace/*/node_modules/@ace-sdk/cli/dist/cli.js'), reverse=True):
        return p
    return None


def fake_server(tmp, mode):
    port = tmp / ('port-' + mode)
    env = dict(os.environ, FAKE_STATUS=mode)
    proc = subprocess.Popen([sys.executable, str(REPO / 'tests/engine_fake_server.py'), '0', str(tmp / 'srv.log'), str(port)], env=env)
    for _ in range(100):
        if port.exists():
            return proc, 'http://127.0.0.1:%s' % port.read_text().strip()
        time.sleep(0.05)
    proc.kill()
    raise RuntimeError('fake server did not start')


def auth_config(path, url, expired=False, token=True):
    when = '2020-01-01T00:00:00Z' if expired else '2099-01-01T00:00:00Z'
    d = {'serverUrl': url, 'defaultOrgId': ORG, 'auth': {'token': 'ace_user_FAKE_TOKEN_0000000000', 'refresh_token': 'rfk_FAKE',
         'user_id': 'u', 'email': 't@example.invalid', 'organizations': [{'org_id': ORG, 'name': 'E2E', 'role': 'owner'}],
         'authenticated_at': '2026-11-01T00:00:00Z', 'expires_at': when, 'refresh_expires_at': when, 'absolute_expires_at': when}}
    if not token:
        d.pop('auth')
    path.write_text(json.dumps(d))


@pytest.mark.skipif(real_cli() is None, reason='no real ace-cli (ACE_E2E_CLI / plugin pin / plugin cache)')
@pytest.mark.parametrize('mode,state,cfg', [('ok', 'ok', {}), ('401', 'expired', {}), ('403', 'no_access', {}), ('404', 'project_not_found', {}),
                                            ('500', 'server_error', {}), ('ok', 'not_logged_in', {'token': False}), ('dead', 'server_error', {})])
def test_real_cli_verify_states_against_the_fake_server(box, monkeypatch, mode, state, cfg):
    main = mkrepo(box / 'r')
    (main / '.ace').mkdir()
    (main / '.ace/config.json').write_text(json.dumps({'orgId': ORG, 'projectId': PRJ}))
    if mode == 'dead':
        s = socket.socket()
        s.bind(('127.0.0.1', 0))
        url, proc = 'http://127.0.0.1:%d' % s.getsockname()[1], None
        s.close()
    else:
        proc, url = fake_server(box, mode)
    try:
        conf = box / 'ace-config.json'
        auth_config(conf, url, **cfg)
        monkeypatch.setenv('ACE_CONFIG_PATH', str(conf))
        monkeypatch.setenv('ACE_SERVER_URL', url)
        monkeypatch.setenv('HOME', str(box / 'home'))
        import ace_cli
        monkeypatch.setattr(ace_cli, 'cli_argv', lambda: ['node', real_cli()])
        assert apc.verify(apc.context(str(main))) == state
    finally:
        if proc:
            proc.kill()


# ---- SDK prerelease (`ace-cli context --json`): the same answer as our resolver ----

PRE = os.environ.get('ACE_PRERELEASE_PREFIX')


@pytest.mark.skipif(not PRE, reason='set ACE_PRERELEASE_PREFIX=<npm --prefix dir of the SDK prerelease tarballs>')
@pytest.mark.parametrize('case', ['repo_file', 'settings_worktree', 'subfolder', 'unbound', 'refused', 'invalid', 'env'])
def test_prerelease_context_matches_our_resolver(box, case):
    main = mkrepo(box / 'm')
    cwd, env = main, {}
    if case == 'repo_file':
        (main / '.ace').mkdir()
        (main / '.ace/config.json').write_text(json.dumps({'orgId': ORG, 'projectId': PRJ}))
    elif case in ('settings_worktree', 'subfolder'):
        legacy(main)
        if case == 'settings_worktree':
            cwd = box / 'wt'
            git(main, 'worktree', 'add', '-q', str(cwd))
        else:
            cwd = main / 'a/b'
            cwd.mkdir(parents=True)
    elif case == 'refused':
        (main / '.ace').mkdir()
        (main / '.ace/config.json').write_text(json.dumps({'orgId': ORG, 'projectId': PRJ, 'apiToken': 'ace_user_x'}))
    elif case == 'invalid':
        (main / '.ace').mkdir()
        (main / '.ace/config.json').write_text('{nope')
    elif case == 'env':
        env = {'ACE_ORG_ID': ORG, 'ACE_PROJECT_ID': PRJ}
    full = dict(os.environ, HOME=str(box / 'home'), ACE_CONFIG_PATH=str(box / 'no-global.json'), **env)
    for k in ('ACE_ORG_ID', 'ACE_PROJECT_ID'):
        if k not in env:
            full.pop(k, None)
    cli = subprocess.run([str(Path(PRE) / 'node_modules/.bin/ace-cli'), 'context', '--json'], cwd=str(cwd), capture_output=True,
                         text=True, env=full, timeout=30)
    theirs = json.loads(cli.stdout)
    ours = apc.context(str(cwd), env=full)
    keys = ('bound', 'reason', 'orgId', 'projectId', 'source', 'warnings')
    assert {k: theirs.get(k) for k in keys} == {k: ours.get(k) for k in keys}, (theirs, ours)
    rp = lambda p: os.path.realpath(p) if p else p  # the SDK may realpath (/private/var/...); ours stays as given
    assert rp(theirs.get('path')) == rp(ours.get('path'))
    assert cli.returncode == (0 if ours['bound'] else 5)
