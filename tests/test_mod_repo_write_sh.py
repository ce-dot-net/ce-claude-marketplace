"""The mod's REPO_WRITE_SH (plugins/ace/mod/lib/sh.ts) on a real filesystem: the same refusals as
ace_project_context.safe_repo_write (security review 8.1.0). The mod's in-memory test host cannot run a shell."""
import re
import subprocess
from pathlib import Path

import pytest

SH_TS = Path(__file__).resolve().parents[1] / 'plugins/ace/mod/lib/sh.ts'


def _script():
    block = SH_TS.read_text().split('export const REPO_WRITE_SH = ', 1)[1].split('\nexport const REPO_WRITE_WHY', 1)[0]
    return ''.join(re.findall(r"'((?:[^'\\]|\\.)*)'", block))


def run(main, rel, text='{"orgId": "org_a", "projectId": "prj_a"}\n'):
    return subprocess.run(['/bin/sh', '-c', _script(), 'sh', str(main), rel], input=text, text=True,
                          capture_output=True).returncode


@pytest.fixture
def box(tmp_path):
    main, out = tmp_path / 'repo', tmp_path / 'outside'
    main.mkdir()
    out.mkdir()
    (out / 'victim').write_text('keep')
    return main, out


def test_writes_atomically(box):
    main, _ = box
    assert run(main, '.ace/config.json') == 0
    assert '"prj_a"' in (main / '.ace/config.json').read_text()
    assert [p.name for p in (main / '.ace').iterdir()] == ['config.json']


def test_symlinked_ace_dir(box):
    main, out = box
    (main / '.ace').symlink_to(out)
    assert run(main, '.ace/config.json') == 3
    assert sorted(p.name for p in out.iterdir()) == ['victim']


def test_symlinked_target(box):
    main, out = box
    (main / '.ace').mkdir()
    (main / '.ace/config.json').symlink_to(out / 'victim')
    assert run(main, '.ace/config.json') == 3
    assert (out / 'victim').read_text() == 'keep'


def test_symlinked_gitignore(box):
    main, out = box
    (main / '.gitignore').symlink_to(out / 'victim')
    assert run(main, '.gitignore', '.ace/*\n') == 3
    assert (out / 'victim').read_text() == 'keep'


def test_preplanted_tmp_is_never_used(box):
    main, out = box
    (main / '.ace').mkdir()
    (main / '.ace/config.json.tmp').symlink_to(out / 'victim')
    assert run(main, '.ace/config.json') == 0
    assert (out / 'victim').read_text() == 'keep'


def test_traversal(box):
    main, _ = box
    assert run(main, '../x') == 4


# ---- 8.1.0 (cli 4.4.1): REMOVE_SHADOW_SH, the band's [Entfernen] for a worktree-local .ace/config.json ----

def _const(name):
    """A single-line `export const NAME = '...'` (+ '...') string from sh.ts."""
    block = SH_TS.read_text().split('export const %s = ' % name, 1)[1].split('\nexport const ', 1)[0]
    return ''.join(re.findall(r"'((?:[^'\\]|\\.)*)'", block))


def rm_shadow(path, root):
    return subprocess.run(['/bin/sh', '-c', _const('REMOVE_SHADOW_SH'), 'sh', str(path), str(root)],
                          capture_output=True, text=True).returncode


@pytest.fixture
def wt(tmp_path):
    root, out = tmp_path / 'wt', tmp_path / 'outside'
    (root / '.ace').mkdir(parents=True)
    (root / '.ace/config.json').write_text('{}')
    out.mkdir()
    (out / 'config.json').write_text('keep')
    return root, out


def test_remove_shadow_deletes_only_that_file(wt):
    root, _ = wt
    (root / 'keep').write_text('x')
    assert rm_shadow(root / '.ace/config.json', root) == 0
    assert not (root / '.ace/config.json').exists() and (root / 'keep').exists() and (root / '.ace').is_dir()


def test_remove_shadow_refuses_other_files_and_outside(wt):
    root, out = wt
    assert rm_shadow(root / 'keep', root) == 4
    assert rm_shadow(out / 'config.json', root) == 4  # not an .ace/config.json
    (out / '.ace').mkdir()
    (out / '.ace/config.json').write_text('keep')
    assert rm_shadow(out / '.ace/config.json', root) == 4  # outside the worktree root
    assert (out / '.ace/config.json').exists()


def test_remove_shadow_refuses_symlinks(wt):
    root, out = wt
    (root / '.ace/config.json').unlink()
    (root / '.ace/config.json').symlink_to(out / 'config.json')
    assert rm_shadow(root / '.ace/config.json', root) == 3
    (root / '.ace/config.json').unlink()
    (root / '.ace').rmdir()
    (root / '.ace').symlink_to(out)
    assert rm_shadow(root / '.ace/config.json', root) == 3
    assert (out / 'config.json').read_text() == 'keep'


def test_realpath_sh(tmp_path):
    (tmp_path / 'real').mkdir()
    (tmp_path / 'link').symlink_to(tmp_path / 'real')
    rp = lambda p: subprocess.run(['/bin/sh', '-c', _const('REALPATH_SH'), 'sh', str(p)], capture_output=True, text=True).stdout.strip()
    real = str((tmp_path / 'real').resolve())
    assert rp(tmp_path / 'link') == real
    assert rp(tmp_path / 'link' / '.git') == real + '/.git'  # a file path: its dir resolved, the name kept
    assert rp(tmp_path / 'nope' / 'x') == ''
    # a symlinked FILE resolves too (relative and absolute targets, chained): the repo-file outside-root check needs it
    (tmp_path / 'out').mkdir()
    (tmp_path / 'out/c.json').write_text('{}')
    (tmp_path / 'real/abs.json').symlink_to(tmp_path / 'out/c.json')
    (tmp_path / 'real/rel.json').symlink_to('../out/c.json')
    (tmp_path / 'real/chain.json').symlink_to('rel.json')
    target = str((tmp_path / 'out/c.json').resolve())
    for n in ('abs.json', 'rel.json', 'chain.json'):
        assert rp(tmp_path / 'link' / n) == target, n
