"""8.1.0: the fallback hooks need Python >= 3.10. scripts/ace-python picks the cached python_path, then python3.15 ...
python3.10, then python3 if >= 3.10; with only a 3.9 it exits 1 and writes one hook-error line, the shims exit 0."""
import os
import subprocess
import sys
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1] / 'plugins/ace'


def fake_py(d, name, minor):
    p = d / name
    p.write_text('#!/bin/sh\n[ "$1" = "-c" ] && exit %d\nexit 0\n' % (0 if minor >= 10 else 1))
    p.chmod(0o755)
    return p


def run(tmp, path, cached=None):
    data = tmp / 'data'
    data.mkdir(exist_ok=True)
    if cached:
        (data / 'python_path').write_text(str(cached) + '\n')
    tools = tmp / 'tools'  # only what the picker may call: no system python3.x can win the test
    if not tools.exists():
        tools.mkdir()
        (tools / 'mkdir').symlink_to('/bin/mkdir')
    env = {'PATH': '%s:%s' % (path, tools), 'HOME': str(tmp), 'CLAUDE_PLUGIN_DATA': str(data)}
    return subprocess.run(['/bin/bash', str(PLUGIN / 'scripts/ace-python')], capture_output=True, text=True, env=env), data


def test_newest_versioned_python_wins(tmp_path):
    b = tmp_path / 'bin'
    b.mkdir()
    fake_py(b, 'python3.11', 11)
    fake_py(b, 'python3.13', 13)
    fake_py(b, 'python3', 9)
    p, _ = run(tmp_path, b)
    assert p.returncode == 0 and p.stdout.strip() == str(b / 'python3.13')


def test_cached_python_path_first_but_only_when_new_enough(tmp_path):
    b = tmp_path / 'bin'
    b.mkdir()
    fake_py(b, 'python3.12', 12)
    good, old = fake_py(tmp_path, 'cached-good', 12), fake_py(tmp_path, 'cached-old', 9)
    assert run(tmp_path, b, good)[0].stdout.strip() == str(good)
    assert run(tmp_path, b, old)[0].stdout.strip() == str(b / 'python3.12')


def test_only_a_system_3_9_exits_1_with_one_error_line(tmp_path):
    b = tmp_path / 'bin'
    b.mkdir()
    fake_py(b, 'python3', 9)
    p, data = run(tmp_path, b)
    assert p.returncode == 1 and p.stdout == ''
    lines = (data / 'logs/ace-hook-errors.log').read_text().splitlines()
    assert len(lines) == 1 and 'Python >= 3.10' in lines[0]


def test_a_shim_exits_0_silently_without_a_new_enough_python(tmp_path):
    b = tmp_path / 'bin'
    b.mkdir()
    fake_py(b, 'python3', 9)
    env = {'PATH': str(b), 'HOME': str(tmp_path), 'CLAUDE_PLUGIN_DATA': str(tmp_path / 'd'),
           'CLAUDE_PLUGIN_ROOT': str(PLUGIN)}
    p = subprocess.run(['/bin/bash', str(PLUGIN / 'scripts/ace_before_task_wrapper.sh')], input='{}', capture_output=True, text=True, env=env)
    assert (p.returncode, p.stdout) == (0, '')


def test_the_real_interpreter_is_accepted():
    assert sys.version_info >= (3, 10)
