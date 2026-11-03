"""8.1.0 review: the binding files on a real filesystem, Python chain. Mirror: plugins/ace/mod/tests/security.test.ts.

- forged .git commondir: the resolver, the log root, init target and auto-adopt never climb into another repo
- size cap: .ace/config.json or .claude/settings.json over 64 KiB -> config_invalid + config_too_large (never parsed)
- a symlinked .ace (or config.json) whose realpath leaves the repo root -> config_refused + repo_file_outside_root
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'plugins/ace/shared-hooks/utils'))
import ace_project_context as apc  # noqa: E402

CAP = 64 * 1024
BIND = {'orgId': 'org_a', 'projectId': 'prj_a'}


@pytest.fixture(autouse=True)
def _clean(monkeypatch, tmp_path):
    apc._CACHE.clear()
    for k in ('ACE_ORG_ID', 'ACE_PROJECT_ID', 'ACE_CONTEXT', 'ACE_BIND_ROOT'):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv('ACE_CONFIG_PATH', str(tmp_path / 'no-global.json'))
    monkeypatch.setenv('CLAUDE_PLUGIN_DATA', str(tmp_path / 'ace-data'))
    monkeypatch.setenv('ACE_AUTO_ADOPT', '0')


def plain(p):
    (p / '.git').mkdir(parents=True)
    (p / '.git/HEAD').write_text('ref: refs/heads/main\n')
    (p / '.git/config').write_text('[core]\n')
    return p


def forged(base):
    """repo A whose .git file names a gitdir with commondir -> an unrelated victim/.git (the review's probe)."""
    victim = plain(base / 'victim')
    (victim / '.claude').mkdir()
    (victim / '.claude/settings.json').write_text(json.dumps({'env': {'ACE_ORG_ID': 'org_v', 'ACE_PROJECT_ID': 'prj_v'}}))
    a = base / 'a'
    a.mkdir()
    (base / 'gd').mkdir()
    (base / 'gd/commondir').write_text(str(victim / '.git') + '\n')
    (base / 'gd/gitdir').write_text(str(a / '.git') + '\n')
    (a / '.git').write_text('gitdir: ' + str(base / 'gd') + '\n')
    return a, victim


def test_forged_commondir_binds_nothing_logs_nothing_in_the_victim(tmp_path):
    base = Path(os.path.realpath(tmp_path))
    a, victim = forged(base)
    r = apc.context(str(a))
    assert r['bound'] is False and r['reason'] == 'no_binding'
    assert 'worktree_topology_untrusted' in r['warnings']
    assert r['root'] == str(a)
    assert apc.log_root(str(a)) == str(a)
    assert apc.repo_roots(str(a)) == (str(a), None)
    assert apc.init_target(str(a)) == (str(a), False, True)
    apc.log_context(r, 'unbound')
    assert not (victim / '.claude/data').exists()
    adopted = apc.adopt({'bound': True, 'source': 'settings_file', 'orgId': 'org_v', 'projectId': 'prj_v'}, str(a),
                        env={'ACE_AUTO_ADOPT': '1'})
    assert adopted == {'path': None, 'warnings': ['worktree_topology_untrusted']}
    assert not (victim / '.ace').exists()


@pytest.mark.parametrize('rel', ['.ace/config.json', '.claude/settings.json'])
def test_binding_file_over_64k_is_config_invalid_too_large(tmp_path, rel):
    repo = plain(tmp_path / 'r')
    f = repo / rel
    f.parent.mkdir()
    body = json.dumps(BIND if rel.startswith('.ace') else {'env': {'ACE_ORG_ID': 'org_a', 'ACE_PROJECT_ID': 'prj_a'}})
    f.write_text(body + ' ' * (CAP + 1 - len(body)))
    r = apc.resolve(str(repo), {'ACE_ORG_ID': 'org_e', 'ACE_PROJECT_ID': 'prj_e'})
    assert (r['bound'], r['reason'], r['warnings']) == (False, 'config_invalid', ['config_too_large'])
    f.write_text(body + ' ' * (CAP - len(body)))  # exactly the cap still binds
    assert apc.resolve(str(repo), {})['bound'] is True


def test_injected_reader_over_the_cap_is_too_large_as_well():
    files = {'/r/.git/config': '[core]\n', '/r/.ace/config.json': json.dumps(BIND) + ' ' * CAP}

    def read(p):
        if p == '/r/.git':
            raise IsADirectoryError(p)
        return files.get(p)
    r = apc.resolve('/r', {}, read=read)
    assert (r['reason'], r['warnings']) == ('config_invalid', ['config_too_large'])


def test_a_fifo_is_never_opened(tmp_path):
    repo = plain(tmp_path / 'r')
    (repo / '.ace').mkdir()
    os.mkfifo(repo / '.ace/config.json')
    r = apc.resolve(str(repo), {})
    assert (r['bound'], r['reason']) == (False, 'config_invalid')


@pytest.mark.parametrize('what', ['dir', 'file'])
def test_symlink_out_of_the_repo_is_refused(tmp_path, what):
    repo = plain(tmp_path / 'r')
    out = tmp_path / 'elsewhere'
    out.mkdir()
    (out / 'config.json').write_text(json.dumps(BIND))
    if what == 'dir':
        (repo / '.ace').symlink_to(out)
    else:
        (repo / '.ace').mkdir()
        (repo / '.ace/config.json').symlink_to(out / 'config.json')
    r = apc.resolve(str(repo), {'ACE_ORG_ID': 'org_e', 'ACE_PROJECT_ID': 'prj_e'})
    assert (r['bound'], r['reason'], r['source'], r['warnings']) == (False, 'config_refused', 'repo_file', ['repo_file_outside_root'])
    # lenient (a --project flag decided it): only the warning
    r = apc.resolve(str(repo), {}, flags={'org': 'org_f', 'project': 'prj_f'})
    assert r['bound'] is True and r['warnings'] == ['repo_file_outside_root']


def test_symlink_inside_the_repo_still_binds(tmp_path):
    repo = plain(tmp_path / 'r')
    (repo / 'conf').mkdir()
    (repo / 'conf/config.json').write_text(json.dumps(BIND))
    (repo / '.ace').symlink_to(repo / 'conf')
    assert apc.resolve(str(repo), {})['bound'] is True


def test_ace_context_cli_exit_5_for_too_large_and_outside(tmp_path):
    repo = plain(tmp_path / 'r')
    (repo / '.ace').mkdir()
    (repo / '.ace/config.json').write_text(' ' * (CAP + 1))
    p = subprocess.run([str(REPO / 'plugins/ace/scripts/ace-context'), '--json'], cwd=str(repo), capture_output=True, text=True,
                       env=dict(os.environ, ACE_PROJECT_ID='prj_e', ACE_ORG_ID='org_e'))
    assert p.returncode == 5, p.stderr
    j = json.loads(p.stdout)
    assert (j['reason'], j['warnings']) == ('config_invalid', ['config_too_large'])
