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
