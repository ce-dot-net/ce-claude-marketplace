"""8.1.0 (cli 4.4.1): where a binding write lands (spec/project-context.md §9). `ace-cli init --json` does it when the
CLI has it; ace_project_context.fallback_init is our writer for a CLI without it and must behave the same.
Fixtures: plugins/ace/tests-fixtures/project-context/init-target.json (real CLI: tests/test_cli_contract.py).
Mirror: plugins/ace/mod/tests/init_target.test.ts."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PLUGIN = REPO / 'plugins/ace'
sys.path.insert(0, str(PLUGIN / 'shared-hooks/utils'))
import ace_project_context as apc  # noqa: E402

CASES = json.loads((PLUGIN / 'tests-fixtures/project-context/init-target.json').read_text())['cases']
ORG, PRJ = 'org_a', 'prj_a'


def build(base, layout):
    """The fixture layout on disk (realpath'd base): str = file content, None = directory."""
    base = Path(os.path.realpath(base))
    for rel, content in layout.items():
        p = base / rel
        if content is None:
            p.mkdir(parents=True, exist_ok=True)
        else:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)
    return base


def check(base, case, out):
    """The result fields every engine must agree on (paths realpath'd: the CLI reports process.cwd())."""
    e = case['expect']
    rp = os.path.realpath
    assert rp(os.path.dirname(os.path.dirname(out['path']))) == rp(base / e['root'])
    assert bool(out.get('mainCheckout')) == e['mainCheckout']
    assert ('worktree_topology_untrusted' in out['warnings']) == bool(e.get('untrusted'))
    assert ('written_to_main_checkout' in out['warnings']) == e['mainCheckout']
    if 'shadowedBy' in e:
        assert rp(out['shadowedBy']) == rp(base / e['shadowedBy'])
        assert 'worktree_file_shadows_main' in out['warnings']
        assert json.loads((base / e['shadowedBy']).read_text())['projectId'] == 'p_old'  # never modified
    else:
        assert not out.get('shadowedBy')
    assert json.loads(Path(out['path']).read_text()) == {'orgId': ORG, 'projectId': PRJ}


@pytest.fixture(autouse=True)
def _clean(monkeypatch, tmp_path):
    apc._CACHE.clear()
    for k in ('ACE_ORG_ID', 'ACE_PROJECT_ID', 'ACE_CONTEXT', 'ACE_AUTO_ADOPT'):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv('ACE_CONFIG_PATH', str(tmp_path / 'no-global.json'))
    monkeypatch.setenv('CLAUDE_PLUGIN_DATA', str(tmp_path / 'ace-data'))


@pytest.mark.parametrize('case', CASES, ids=[c['name'] for c in CASES])
def test_target_matches_the_spec(tmp_path, case):
    base = build(tmp_path, case['layout'])
    root, main, untrusted = apc.init_target(str(base / case['cwd']))
    assert (os.path.realpath(root), main, untrusted) == (str(base / case['expect']['root']), case['expect']['mainCheckout'],
                                                          bool(case['expect'].get('untrusted')))


@pytest.mark.parametrize('case', CASES, ids=[c['name'] for c in CASES])
def test_fallback_writer_matches_the_spec(tmp_path, case):
    base = build(tmp_path, case['layout'])
    out = apc.fallback_init(str(base / case['cwd']), ORG, PRJ)
    assert out['via'] == 'fallback'
    check(base, case, out)


# ---- the chain on real git worktrees: CLI first, our writer only when the CLI has no `init --json` ----

def git(cwd, *a):
    return subprocess.run(['git', '-C', str(cwd), *a], capture_output=True, text=True, check=True).stdout


def worktree(tmp_path):
    main = Path(os.path.realpath(tmp_path)) / 'main'
    main.mkdir()
    git(main, 'init', '-q')
    git(main, '-c', 'user.email=t@example.invalid', '-c', 'user.name=t', 'commit', '-q', '--allow-empty', '-m', 'i')
    git(main, 'worktree', 'add', '-q', str(main.parent / 'wt'), '-b', 'wt')
    return main, main.parent / 'wt'


def test_bind_without_cli_init_falls_back_to_our_writer(tmp_path):
    """The hermetic fake ace-cli answers `init` with `{}` (no init --json): our writer, same target."""
    main, wt = worktree(tmp_path)
    out = apc.bind(str(wt), ORG, PRJ)
    assert out['via'] == 'fallback' and out['mainCheckout'] is True
    assert (main / '.ace/config.json').is_file() and not (wt / '.ace').exists()


def test_bind_takes_the_cli_result(tmp_path, monkeypatch):
    main, wt = worktree(tmp_path)
    seen = {}

    def run(argv, **kw):
        seen['argv'], seen['cwd'] = argv, kw.get('cwd')
        return subprocess.CompletedProcess(argv, 0, json.dumps({'path': str(main / '.ace/config.json'), 'orgId': ORG, 'projectId': PRJ,
                                                                'gitignore': 'ok', 'warnings': ['written_to_main_checkout'], 'mainCheckout': True}), '')
    monkeypatch.setattr(apc.subprocess, 'run', run)
    out = apc.bind(str(wt), ORG, PRJ)
    assert out['via'] == 'cli' and out['mainCheckout'] is True
    assert seen['argv'][-7:] == ['init', '--json', '--fix-gitignore', '--org', ORG, '--project', PRJ]
    assert seen['cwd'] == str(wt)


def test_bind_cli_refusal_is_final_no_fallback_write(tmp_path, monkeypatch):
    main, wt = worktree(tmp_path)
    err = json.dumps({'error': {'code': 'generic', 'status': None, 'message': 'Refusing to write x: .ace is a symlink.'}})
    monkeypatch.setattr(apc.subprocess, 'run', lambda argv, **kw: subprocess.CompletedProcess(argv, 1, '', err))
    with pytest.raises(apc.WriteRefused, match='symlink'):
        apc.bind(str(wt), ORG, PRJ)
    assert not (main / '.ace').exists()


def test_bind_cli_reports_the_shadow_and_bind_cli_prints_the_line(tmp_path, capsys):
    main, wt = worktree(tmp_path)
    (wt / '.ace').mkdir()
    (wt / '.ace/config.json').write_text(json.dumps({'orgId': ORG, 'projectId': 'prj_old'}))
    assert apc.main(['--cwd', str(wt), '--bind', ORG, PRJ, '--yes']) == 0
    out = capsys.readouterr().out
    assert apc.WARN_LINES['worktree_file_shadows_main'] in out
    assert '--remove-shadow' in out and str(wt / '.ace/config.json') in out
    assert json.loads((wt / '.ace/config.json').read_text())['projectId'] == 'prj_old'  # never deleted silently
    assert json.loads((main / '.ace/config.json').read_text())['projectId'] == PRJ


def test_remove_shadow_deletes_only_that_file(tmp_path):
    main, wt = worktree(tmp_path)
    (main / '.ace').mkdir()
    (main / '.ace/config.json').write_text('{}')
    (wt / '.ace').mkdir()
    (wt / '.ace/config.json').write_text('{}')
    with pytest.raises(apc.WriteRefused):
        apc.remove_shadow(str(wt), str(main / '.ace/config.json'))  # the main checkout's binding: never
    with pytest.raises(apc.WriteRefused):
        apc.remove_shadow(str(wt), str(wt / 'README'))
    assert apc.main(['--cwd', str(wt), '--remove-shadow', str(wt / '.ace/config.json')]) == 0
    assert not (wt / '.ace/config.json').exists() and (main / '.ace/config.json').exists()


@pytest.mark.parametrize('what', ['dir', 'file'])
def test_remove_shadow_refuses_symlinks(tmp_path, what):
    main, wt = worktree(tmp_path)
    victim = tmp_path / 'victim'
    victim.mkdir()
    (victim / 'config.json').write_text('{}')
    if what == 'dir':
        (wt / '.ace').symlink_to(victim)
    else:
        (wt / '.ace').mkdir()
        (wt / '.ace/config.json').symlink_to(victim / 'config.json')
    with pytest.raises(apc.WriteRefused, match='symlink'):
        apc.remove_shadow(str(wt), str(wt / '.ace/config.json'))
    assert (victim / 'config.json').exists()


def _forged(tmp_path):
    """A worktree .git whose commondir points at an unrelated dir (fixture case 7) plus a legacy settings binding."""
    base = build(tmp_path, {'victim/HEAD': 'ref: refs/heads/main\n', 'victim/config': '[core]\n',
                            'wt/.git': 'gitdir: ../gd\n', 'gd/commondir': '../victim\n',
                            'wt/.claude/settings.json': json.dumps({'env': {'ACE_ORG_ID': ORG, 'ACE_PROJECT_ID': PRJ}})})
    return base


def test_adopt_never_runs_on_an_untrusted_topology(tmp_path):
    base = _forged(tmp_path)
    r = apc.context(str(base / 'wt'))
    assert r['bound'] and r['source'] == 'settings_file'
    a = apc.adopt(r, str(base / 'wt'))
    assert a == {'path': None, 'warnings': ['worktree_topology_untrusted']}
    assert not (base / 'wt/.ace').exists() and not (base / '.ace').exists()


def test_session_notice_shows_the_untrusted_line_once(tmp_path):
    base = _forged(tmp_path)
    (base / 'wt/.claude/data/logs').mkdir(parents=True)
    assert apc.session_notice('s1', str(base / 'wt'), spawn_verify=False) == apc.WARN_LINES['worktree_topology_untrusted']
    assert apc.session_notice('s1', str(base / 'wt'), spawn_verify=False) is None
