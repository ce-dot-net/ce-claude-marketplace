"""Conformance: ace_project_context.resolve vs the SDK spec fixtures (76 cases) plus our extra probes.

Fixtures: plugins/ace/tests-fixtures/project-context/ (see its README). In-memory layout, no real FS.
Mirror runner: plugins/ace/mod/tests/project_context.test.ts.
"""
import json
import posixpath
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
FIX = REPO / 'plugins/ace/tests-fixtures/project-context'
sys.path.insert(0, str(REPO / 'plugins/ace/shared-hooks/utils'))
import ace_project_context as apc  # noqa: E402

ROOT = '/r'
SPEC = json.loads((FIX / 'cases.json').read_text())
EXTRA = [dict(c, strict=c.get('strict', True)) for c in json.loads((FIX / 'extra-cases.json').read_text())]  # ours: production strict


def _sub(v):
    return v.replace('$ROOT', ROOT) if isinstance(v, str) else v


def _fs(layout, unreadable):
    """(read, realpath) over the in-memory layout. A value "@symlink:<path relative to the layout root>" is a symlink
    (spec: used by the §9 (e) case); both follow it, like the real reader and os.path.realpath."""
    files, dirs, links = {}, set(), {}
    for rel, content in layout.items():
        p = posixpath.join(ROOT, rel)
        if content is None:
            dirs.add(p)
        elif content.startswith('@symlink:'):
            links[p] = posixpath.join(ROOT, content[len('@symlink:'):])
        else:
            files[p] = _sub(content)
        p = posixpath.dirname(p)
        while p != '/':
            dirs.add(p)
            p = posixpath.dirname(p)
    bad = {posixpath.join(ROOT, u) for u in unreadable}

    def realpath(path, hops=0):
        cur = '/'
        for seg in posixpath.normpath(path).split('/')[1:]:
            cur = posixpath.join(cur, seg)
            if cur in links and hops < 40:
                cur = realpath(links[cur], hops + 1)
        return cur

    def read(path):
        path = realpath(path)
        if path in bad:
            raise PermissionError(13, 'Permission denied', path)
        if path in files:
            return files[path]
        if path in dirs:
            raise IsADirectoryError(21, 'Is a directory', path)
        return None
    return read, realpath


def _rel(p):
    return posixpath.relpath(p, ROOT) if p else p


def run_case(case):
    gc = case.get('globalConfig') or {}
    read, realpath = _fs(case['layout'], case.get('unreadable', []))
    res = apc.resolve(
        posixpath.join(ROOT, case['cwd']),
        {k: _sub(v) for k, v in case['env'].items()},
        flags=case.get('flags'),
        remote_map=gc.get('projects'),
        organizations=(gc.get('auth') or {}).get('organizations'),
        default_org_id=gc.get('default_org_id'),
        global_project_id=gc.get('projectId'),
        read=read, realpath=realpath,
        strict=case.get('strict', False),
    )
    if 'message' in res:
        assert isinstance(res['message'], str) and res['message']
        del res['message']
    if 'path' in res:
        res['path'] = _rel(res['path'])
    for t in res.get('tried', []):
        t['path'] = _rel(t['path'])
    return res


def test_fixture_counts():
    assert len(SPEC) == 76
    assert len(EXTRA) >= 4


@pytest.mark.parametrize('case', SPEC, ids=[c['name'] for c in SPEC])
def test_spec_case(case):
    assert run_case(case) == case['expect']


@pytest.mark.parametrize('case', EXTRA, ids=[c['name'] for c in EXTRA])
def test_extra_case(case):
    assert run_case(case) == case['expect']


def test_default_reader_on_real_fs(tmp_path):
    """read_file contract: missing -> None, directory -> raises (counts as an existing .git dir)."""
    (tmp_path / '.git').mkdir()
    (tmp_path / '.ace').mkdir()
    (tmp_path / '.ace/config.json').write_text('{"orgId": "org_a", "projectId": "prj_a"}')
    (tmp_path / 'src').mkdir()
    res = apc.resolve(str(tmp_path / 'src'), {})
    assert res == {'bound': True, 'orgId': 'org_a', 'projectId': 'prj_a', 'source': 'repo_file',
                   'path': str(tmp_path / '.ace/config.json')}


@pytest.mark.parametrize('src,dst', [('cases', 'project_context_cases'), ('extra-cases', 'project_context_extra'),
                                     ('init-target', 'init_target_cases')])
def test_ts_fixture_wrappers_match_json(src, dst):
    """Mods load only .ts, so the TS runner imports generated wrappers. Regenerate: see the wrapper's header."""
    text = (REPO / f'plugins/ace/mod/tests/fixtures/{dst}.ts').read_text()
    body = text.split('export default ', 1)[1]
    assert json.loads(body) == json.loads((FIX / f'{src}.json').read_text())


def test_symlinked_dotgit_to_a_real_foreign_worktree_is_untrusted_on_real_fs(tmp_path):
    """§9 (e) with the default reader/realpath: a real `git worktree add`, a .git symlinked to its .git file."""
    import os
    import subprocess
    base = tmp_path.resolve()
    g = lambda *a: subprocess.run(['git', '-C', str(base / 'foreign'), *a], capture_output=True, check=True)
    (base / 'foreign').mkdir()
    g('init', '-q')
    g('-c', 'user.email=t@example.invalid', '-c', 'user.name=t', 'commit', '-q', '--allow-empty', '-m', 'i')
    g('worktree', 'add', '-q', str(base / 'foreignwt'), '-b', 'wt')
    (base / 'foreign/.ace').mkdir()
    (base / 'foreign/.ace/config.json').write_text('{"orgId": "org_victim", "projectId": "prj_victim"}')
    assert apc.resolve(str(base / 'foreignwt'), {})['projectId'] == 'prj_victim'  # the genuine worktree is trusted
    (base / 'evil').mkdir()
    os.symlink(base / 'foreignwt/.git', base / 'evil/.git')
    res = apc.resolve(str(base / 'evil'), {})
    assert res['bound'] is False and res['warnings'] == ['worktree_topology_untrusted']
