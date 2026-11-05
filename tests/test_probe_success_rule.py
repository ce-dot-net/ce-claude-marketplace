"""tests/probe_success_rule.py prints counts only: no prompt, command, file content or path text, ever."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CANARY = 'Zq7canaryXv'


def _tool(tuid, name, inp, out, err=False):
    return [{'type': 'assistant', 'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
             'message': {'role': 'assistant', 'content': [{'type': 'tool_use', 'id': tuid, 'name': name, 'input': inp}]}},
            {'type': 'user', 'message': {'role': 'user', 'content': [
                {'type': 'tool_result', 'tool_use_id': tuid, 'content': out, 'is_error': err}]}}]


def test_probe_prints_no_transcript_text(tmp_path):
    proj = tmp_path / ('-Users-x-%s' % CANARY)
    proj.mkdir()
    now = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    lines = [{'type': 'user', 'timestamp': now, 'message': {'role': 'user', 'content': 'please %s fix it' % CANARY}}]
    lines += _tool('t1', 'Read', {'file_path': '/p/%s/a.py' % CANARY}, 'secret %s body' % CANARY)
    lines += _tool('t2', 'Bash', {'command': 'python3 /p/%s.py && echo %s' % (CANARY, CANARY)}, 'Exit code 1\n%s' % CANARY, True)
    lines += _tool('t3', 'Bash', {'command': 'gh pr merge %s' % CANARY.lower()}, 'Exit code 1\n%s' % CANARY, True)
    lines += _tool('t4', 'mcp__srv__save_%s' % CANARY.lower(), {'title': CANARY}, CANARY, True)
    lines += [{'type': 'user', 'timestamp': now, 'message': {'role': 'user', 'content': 'next %s' % CANARY}}]
    lines += _tool('t5', 'mcp__%s__save_%s' % (CANARY, CANARY.lower()), {'title': CANARY}, CANARY, True)  # flips: SF4
    lines += [{'type': 'user', 'timestamp': now, 'message': {'role': 'user', 'content': 'again %s' % CANARY}}]
    lines += _tool('t6', 'Bash', {'command': 'cat %s | kubectl apply -f %s' % (CANARY, CANARY)}, 'Exit code 1\n%s' % CANARY, True)
    (proj / ('%s.jsonl' % CANARY)).write_text('\n'.join(json.dumps(x) for x in lines) + '\n')
    old = tmp_path / 'old_rule.py'  # an old rule that never fails a task: every new false is a flip (no git history needed)
    old.write_text("from ace_after_task import *\nfrom ace_after_task import _step_status\n"
                   "def task_outcome(tools):\n    return True, 0, False\n")
    p = subprocess.run([sys.executable, str(REPO / 'tests/probe_success_rule.py'), '--days', '3', '--root', str(tmp_path),
                        '--old-file', str(old)], capture_output=True, text=True, timeout=120, cwd=str(REPO),
                       env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
    out = p.stdout + p.stderr
    assert p.returncode == 0, out[-2000:]
    assert 'total' in out and 'bash actions: 3 steps' in out and 'SF4 mcp write' in out and "('kubectl apply', 1)" in out
    assert CANARY.lower() not in out.lower(), 'the probe printed transcript text'
