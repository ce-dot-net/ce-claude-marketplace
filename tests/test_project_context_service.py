"""The Python chain's one core (8.1.0): ace_project_context.context/get_context/verify/adopt/remember/session_notice
and the scripts/ace-context entrypoint, on real git repos (worktrees, subfolders). Mirror: plugins/ace/mod/tests/context.test.ts."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PLUGIN = REPO / 'plugins/ace'
sys.path.insert(0, str(PLUGIN / 'shared-hooks/utils'))
import ace_project_context as apc  # noqa: E402

VERIFY = json.loads((PLUGIN / 'tests-fixtures/project-context/verify-cases.json').read_text())
ORG, PRJ = 'org_test1', 'prj_test1'


def git(cwd, *a):
    return subprocess.run(['git', '-C', str(cwd), *a], capture_output=True, text=True, check=True).stdout


@pytest.fixture(autouse=True)
def _clean(monkeypatch, tmp_path):
    apc._CACHE.clear()
    for k in ('ACE_ORG_ID', 'ACE_PROJECT_ID', 'ACE_CONTEXT', 'ACE_AUTO_ADOPT'):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv('ACE_CONFIG_PATH', str(tmp_path / 'no-global.json'))
    monkeypatch.setenv('CLAUDE_PLUGIN_DATA', str(tmp_path / 'ace-data'))


def mkrepo(path, remote='git@github.com:acme/widget.git'):
    path.mkdir(parents=True)
    git(path, 'init', '-q')
    git(path, 'config', 'user.email', 't@example.invalid')
    git(path, 'config', 'user.name', 't')
    if remote:
        git(path, 'remote', 'add', 'origin', remote)
    (path / 'README').write_text('x')
    git(path, 'add', 'README')
    git(path, 'commit', '-qm', 'init')
    return path


def legacy(path, org=ORG, prj=PRJ):
    (path / '.claude').mkdir(exist_ok=True)
    (path / '.claude/settings.json').write_text(json.dumps({'env': {'ACE_ORG_ID': org, 'ACE_PROJECT_ID': prj}}))


@pytest.mark.parametrize('case', VERIFY, ids=[c['name'] for c in VERIFY])
def test_classify(case):
    assert apc.classify(case['exit'], case['stderr'], case.get('spawnError', False), case.get('timeout', False)) == case['state']


# ---- the user's must-have: already-bound repos work in worktrees and subfolders with zero steps ----

def test_worktree_of_a_legacy_bound_repo_resolves_via_main_settings_file(tmp_path, monkeypatch):
    main = mkrepo(tmp_path / 'ace-web')
    legacy(main)
    wt = tmp_path / 'wts' / 'x-umsetzer'
    git(main, 'worktree', 'add', '-q', str(wt))
    monkeypatch.setenv('ACE_AUTO_ADOPT', '0')
    r = apc.context(str(wt / 'src') if (wt / 'src').exists() else str(wt))
    assert r['bound'] and r['source'] == 'settings_file' and r['projectId'] == PRJ
    assert r['path'] == str(main.resolve() / '.claude/settings.json') or r['path'] == str(main / '.claude/settings.json')
    assert os.path.realpath(r['root']) == os.path.realpath(main)
    assert apc.get_context(str(wt))['project'] == PRJ


def test_subfolder_walks_up_to_the_repo(tmp_path, monkeypatch):
    main = mkrepo(tmp_path / 'r')
    legacy(main)
    (main / 'a/b').mkdir(parents=True)
    monkeypatch.setenv('ACE_AUTO_ADOPT', '0')
    r = apc.context(str(main / 'a/b'))
    assert r['bound'] and r['source'] == 'settings_file' and r['root'] == str(main)
    assert apc.logs_dir(str(main / 'a/b')) == str(main / '.claude/data/logs')


def test_log_root_of_a_worktree_is_the_main_checkout(tmp_path):
    main = mkrepo(tmp_path / 'r')
    wt = tmp_path / 'wt'
    git(main, 'worktree', 'add', '-q', str(wt))
    assert os.path.realpath(apc.log_root(str(wt))) == os.path.realpath(main)


# ---- the mod's export ----

def test_fresh_mod_export_for_the_same_root_is_taken(tmp_path):
    main = mkrepo(tmp_path / 'r')
    m = {'root': str(main), 'source': 'repo_file', 'path': 'p', 'orgId': ORG, 'projectId': PRJ, 'at': time.time() * 1000}
    r = apc.context(str(main), env={'ACE_CONTEXT': json.dumps(m), 'ACE_ORG_ID': ORG, 'ACE_PROJECT_ID': PRJ, 'HOME': str(tmp_path)})
    assert r['via'] == 'mod' and r['projectId'] == PRJ


def test_stale_or_foreign_mod_export_never_leaks_its_ids(tmp_path):
    main = mkrepo(tmp_path / 'r')
    other = mkrepo(tmp_path / 'other')
    m = {'root': str(main), 'source': 'repo_file', 'path': 'p', 'orgId': ORG, 'projectId': PRJ, 'at': time.time() * 1000}
    env = {'ACE_CONTEXT': json.dumps(m), 'ACE_ORG_ID': ORG, 'ACE_PROJECT_ID': PRJ, 'HOME': str(tmp_path)}
    assert apc.context(str(other), env=env) ['bound'] is False  # foreign root: the mod's ids are not "env"
    m['at'] = (time.time() - 3600) * 1000
    env['ACE_CONTEXT'] = json.dumps(m)
    assert apc.context(str(main), env=env)['bound'] is False  # stale


def test_user_env_still_binds_when_no_file(tmp_path):
    d = tmp_path / 'plain'
    d.mkdir()
    r = apc.context(str(d), env={'ACE_ORG_ID': ORG, 'ACE_PROJECT_ID': PRJ, 'HOME': str(tmp_path)})
    assert r['bound'] and r['source'] == 'env'


def test_repo_file_beats_leaked_env(tmp_path):
    main = mkrepo(tmp_path / 'r')
    (main / '.ace').mkdir()
    (main / '.ace/config.json').write_text(json.dumps({'orgId': ORG, 'projectId': PRJ}))
    r = apc.context(str(main), env={'ACE_ORG_ID': 'org_leak', 'ACE_PROJECT_ID': 'prj_leak', 'HOME': str(tmp_path)})
    assert (r['source'], r['projectId']) == ('repo_file', PRJ)


def test_secret_in_repo_file_is_refused_and_env_does_not_take_over(tmp_path):
    main = mkrepo(tmp_path / 'r')
    (main / '.ace').mkdir()
    (main / '.ace/config.json').write_text(json.dumps({'orgId': ORG, 'projectId': PRJ, 'apiToken': 'ace_user_x'}))
    r = apc.context(str(main), env={'ACE_ORG_ID': ORG, 'ACE_PROJECT_ID': PRJ, 'HOME': str(tmp_path)})
    assert (r['bound'], r['reason'], apc.local_state(r)) == (False, 'config_refused', 'config_refused')
    assert apc.get_context(str(main)) is None


# ---- remote map (per machine) and automatic adoption ----

def test_remember_then_a_fresh_clone_binds_via_remote_map(tmp_path, monkeypatch):
    monkeypatch.setenv('ACE_AUTO_ADOPT', '0')
    a = mkrepo(tmp_path / 'a')
    (a / '.ace').mkdir()
    (a / '.ace/config.json').write_text(json.dumps({'orgId': ORG, 'projectId': PRJ}))
    r = apc.context(str(a))
    assert apc.remember(r, str(a)) is True
    assert apc.remember(r, str(a)) is False  # unchanged: no rewrite
    assert json.loads(Path(apc.machine_map_path()).read_text())['github.com/acme/widget']['projectId'] == PRJ
    b = mkrepo(tmp_path / 'b', remote='https://github.com/acme/widget.git')
    apc._CACHE.clear()
    r2 = apc.context(str(b))
    assert (r2['bound'], r2['source'], r2['projectId']) == (True, 'remote_map', PRJ)


def test_adopt_writes_the_tracked_file_once_and_fixes_gitignore(tmp_path):
    main = mkrepo(tmp_path / 'r')
    legacy(main)
    (main / '.gitignore').write_text('.claude/\n.ace/\n')
    wt = tmp_path / 'wt'
    git(main, 'worktree', 'add', '-q', str(wt))
    r = apc.context(str(wt))
    a = apc.adopt(r, str(wt))
    cfg = main / '.ace/config.json'
    assert a['path'] == str(cfg) or os.path.realpath(a['path']) == os.path.realpath(cfg)
    assert json.loads(cfg.read_text()) == {'orgId': ORG, 'projectId': PRJ}
    assert a['gitignore'] == 'fixed' and not apc.ignored(str(main))
    assert '.ace/*\n' in (main / '.gitignore').read_text() and '!.ace/config.json' in (main / '.gitignore').read_text()
    assert git(main, 'diff', '--cached', '--name-only') == ''  # never staged, never committed
    assert apc.untracked(str(main))
    assert apc.adopt(apc.context(str(wt)), str(wt)) is None  # exists now: never rewritten


@pytest.mark.parametrize('why', ['env', 'flag', 'optout', 'nogit', 'repo_file'])
def test_adopt_never_writes(tmp_path, monkeypatch, why):
    main = mkrepo(tmp_path / 'r') if why != 'nogit' else tmp_path / 'plain'
    main.mkdir(exist_ok=True)
    r = {'bound': True, 'orgId': ORG, 'projectId': PRJ, 'source': 'settings_file', 'path': None}
    if why in ('env', 'flag', 'repo_file'):
        r['source'] = why
    if why == 'optout':
        monkeypatch.setenv('ACE_AUTO_ADOPT', '0')
    assert apc.adopt(r, str(main)) is None
    assert not (main / '.ace').exists()


@pytest.mark.parametrize('before,after', [
    ('', '.ace/*\n!.ace/config.json\n'),
    ('.ace/\n', '.ace/*\n!.ace/config.json\n'),
    ('node_modules\n/.ace\n', 'node_modules\n/.ace/*\n!.ace/config.json\n'),
    ('.ace/*\n!.ace/config.json\n', '.ace/*\n!.ace/config.json\n'),
])
def test_fix_gitignore(before, after):
    assert apc.fix_gitignore(before)[0] == after


def test_write_binding_refuses_bad_ids(tmp_path):
    with pytest.raises(ValueError):
        apc.write_binding(str(tmp_path), 'org_a', 'not-a-project')


# ---- the Python chain's one line per session, and the one log row ----

def test_session_notice_unbound_once_and_no_log_litter(tmp_path):
    main = mkrepo(tmp_path / 'r')
    assert apc.session_notice('s1', str(main), spawn_verify=False) == apc.LINES['unbound']
    assert apc.session_notice('s1', str(main), spawn_verify=False) is None
    assert not (main / '.claude/data/logs').exists()  # an unrelated repo gets no log dir


def test_session_notice_adoption_line_once_and_context_row(tmp_path):
    main = mkrepo(tmp_path / 'r')
    legacy(main)
    (main / '.claude/data/logs').mkdir(parents=True)
    assert apc.session_notice('s2', str(main), spawn_verify=False) == apc.ADOPT_LINE
    assert apc.session_notice('s2', str(main), spawn_verify=False) is None
    apc._CACHE.clear()
    s = apc.verify_session('s2', str(main))  # the fake ace-cli (conftest) answers status with exit 0
    rows = [json.loads(l) for l in (main / '.claude/data/logs/ace-relevance.jsonl').read_text().splitlines()]
    ctx = [x for x in rows if x['event'] == 'context']
    assert len(ctx) == 1 and ctx[0]['state'] == s and ctx[0]['source'] == 'repo_file'


def test_config_invalid_line(tmp_path):
    main = mkrepo(tmp_path / 'r')
    (main / '.claude').mkdir()
    (main / '.claude/settings.json').write_text('{broken')
    assert apc.session_notice('s3', str(main), spawn_verify=False) == apc.LINES['config_invalid']


# ---- the entrypoint the markdown commands use ----

def run_ctx(cwd, *a, env=None):
    e = dict(os.environ, **(env or {}))
    return subprocess.run([str(PLUGIN / 'scripts/ace-context'), *a], cwd=str(cwd), capture_output=True, text=True, env=e)


def test_entrypoint_json_and_shell(tmp_path):
    main = mkrepo(tmp_path / 'r')
    (main / '.ace').mkdir()
    (main / '.ace/config.json').write_text(json.dumps({'orgId': ORG, 'projectId': PRJ}))
    (main / 'sub').mkdir()
    p = run_ctx(main / 'sub', '--json')
    assert p.returncode == 0 and json.loads(p.stdout)['projectId'] == PRJ
    p = run_ctx(main / 'sub', '--shell')
    assert p.returncode == 0 and f'export ACE_PROJECT_ID={PRJ}' in p.stdout and 'export ACE_ORG_ID=' in p.stdout


def test_entrypoint_unbound_exits_5_with_one_line(tmp_path):
    d = tmp_path / 'plain'
    d.mkdir()
    p = run_ctx(d, '--shell')
    assert p.returncode == 5 and p.stdout == '' and p.stderr.strip() == apc.LINES['unbound']


def test_lines_match_the_mod():
    text = (PLUGIN / 'mod/context/lines.ts').read_text()
    body = text.split('export const LINES = ', 1)[1].split('\nexport const ADOPT_LINE = ')
    assert json.loads(body[0]) == apc.LINES
    assert json.loads(body[1].strip()) == apc.ADOPT_LINE


# ---- security review: no repo write ever follows a symlink out of the main checkout ----

def _refused_rows(main):
    f = main / '.claude/data/logs/ace-relevance.jsonl'
    return [json.loads(l) for l in f.read_text().splitlines() if '"write_refused"' in l] if f.exists() else []


@pytest.mark.parametrize('what', ['ace_dir', 'config', 'gitignore'])
def test_adopt_refuses_symlinks(tmp_path, what):
    main = mkrepo(tmp_path / 'r')
    legacy(main)
    (main / '.claude/data/logs').mkdir(parents=True)
    outside = tmp_path / 'outside'
    outside.mkdir()
    (outside / 'victim').write_text('keep')
    if what == 'ace_dir':
        (main / '.ace').symlink_to(outside)
    elif what == 'config':
        (main / '.ace').mkdir()
        (main / '.ace/config.json').symlink_to(outside / 'victim')
    else:
        (outside / 'gi').write_text('.ace/\n')
        (main / '.gitignore').symlink_to(outside / 'gi')
    if what == 'gitignore':
        r = apc.write_binding(str(main), ORG, PRJ)
        assert r['gitignore'] == 'refused'
        assert (outside / 'gi').read_text() == '.ace/\n'
    else:
        with pytest.raises(apc.WriteRefused):
            apc.write_binding(str(main), ORG, PRJ)
    assert (outside / 'victim').read_text() == 'keep'
    assert sorted(p.name for p in outside.iterdir()) == (['gi', 'victim'] if what == 'gitignore' else ['victim'])
    rows = _refused_rows(main)
    assert rows and 'symlink' in rows[-1]['reason']


def test_adopt_ignores_a_preplanted_tmp(tmp_path):
    main = mkrepo(tmp_path / 'r')
    outside = tmp_path / 'outside'
    outside.mkdir()
    (outside / 'victim').write_text('keep')
    (main / '.ace').mkdir()
    (main / '.ace/config.json.tmp').symlink_to(outside / 'victim')  # the old predictable name
    apc.write_binding(str(main), ORG, PRJ)
    assert json.loads((main / '.ace/config.json').read_text()) == {'orgId': ORG, 'projectId': PRJ}
    assert (outside / 'victim').read_text() == 'keep'
    assert not [p for p in (main / '.ace').iterdir() if p.name.startswith('.ace-w-')]  # no temp left behind


def test_safe_repo_write_refuses_traversal(tmp_path):
    with pytest.raises(apc.WriteRefused):
        apc.safe_repo_write(str(tmp_path), '../x', 'y')


def test_a_fresh_unbound_mod_export_silences_the_python_notice_and_row(tmp_path):
    main = mkrepo(tmp_path / 'r')
    (main / '.claude/data/logs').mkdir(parents=True)
    env = dict(os.environ, ACE_CONTEXT=json.dumps({'root': str(main), 'bound': False, 'reason': 'no_binding', 'at': time.time() * 1000}))
    assert apc.session_notice('s9', str(main), env=env, spawn_verify=False) is None
    assert not (main / '.claude/data/logs/ace-relevance.jsonl').exists()
    stale = dict(env, ACE_CONTEXT=json.dumps({'root': str(main), 'bound': False, 'at': (time.time() - 3600) * 1000}))
    assert apc.session_notice('s9', str(main), env=stale, spawn_verify=False) == apc.LINES['unbound']


# ---- the markdown export fallback: ace-context --write-export (inside the repo root only) ----

@pytest.mark.parametrize('target,why', [('../../etc/x', 'outside'), ('/etc/passwd', 'outside'), ('out/x.json', 'symlink')])
def test_write_export_refuses(tmp_path, target, why):
    main = mkrepo(tmp_path / 'r')
    outside = tmp_path / 'outside'
    outside.mkdir()
    (main / 'out').symlink_to(outside)
    p = subprocess.run([str(PLUGIN / 'scripts/ace-context'), '--write-export', target], cwd=str(main), input='{"playbook":{}}',
                       capture_output=True, text=True)
    assert p.returncode == 1 and why in p.stdout + p.stderr
    assert list(outside.iterdir()) == []


def test_write_export_needs_force_to_overwrite(tmp_path):
    main = mkrepo(tmp_path / 'r')
    (main / 'sub').mkdir()
    (main / 'pb.json').write_text('old')
    run = lambda *a: subprocess.run([str(PLUGIN / 'scripts/ace-context'), '--write-export', 'pb.json', *a], cwd=str(main / 'sub'),
                                    input='{"playbook":{}}', capture_output=True, text=True)
    p = run()
    assert p.returncode == 1 and 'exists' in p.stdout and (main / 'pb.json').read_text() == 'old'  # relative to the repo root
    assert run('--force').returncode == 0 and (main / 'pb.json').read_text() == '{"playbook":{}}'


def test_bind_root_keeps_an_inherited_export_out_of_other_dirs(tmp_path):
    repo, other = mkrepo(tmp_path / 'repo'), tmp_path / 'elsewhere'
    other.mkdir()
    env = {'ACE_ORG_ID': ORG, 'ACE_PROJECT_ID': PRJ, 'ACE_BIND_ROOT': str(repo), 'HOME': str(tmp_path)}
    assert apc.context(str(other), env=env)['bound'] is False
    assert apc.context(str(repo), env=env)['source'] == 'env'
    env.pop('ACE_BIND_ROOT')  # a deliberate env (herdr, a launcher): spec behaviour
    assert apc.context(str(other), env=env)['source'] == 'env'
