#!/usr/bin/env python3
"""Tests for ace_cli.py - CLI subprocess wrapper (mocked).

v8 (DESIGN §5 C2): run_search returns (result_or_None, duration_ms) and spawns
ace-cli exactly once. Full contract: tests/test_ace_cli_v8.py.
"""

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent / 'shared-hooks' / 'utils'))

from ace_cli import run_search


def _res(rc, stdout, stderr=b''):
    r = MagicMock()
    r.returncode = rc
    r.stdout = stdout
    r.stderr = stderr
    return r


def test_run_search_success():
    payload = {'patterns': [{'content': 'Test pattern', 'helpful': 5}]}
    with patch('subprocess.run', return_value=_res(0, json.dumps(payload).encode())) as run:
        result, ms = run_search('test query', hook_event_name='UserPromptSubmit')
    assert result == payload
    assert isinstance(ms, int)
    assert run.call_count == 1
    assert run.call_args.args[0] == ['ace-cli', 'search', '--stdin', '--json']


def test_run_search_failure():
    with patch('subprocess.run', return_value=_res(1, b'', b'')):
        result, _ = run_search('test query', hook_event_name='UserPromptSubmit')
    assert result is None


def test_run_search_auth_failure():
    with patch('subprocess.run', return_value=_res(1, b'{"error": "Not logged in"}')):
        result, _ = run_search('test query', hook_event_name='UserPromptSubmit')
    assert result.get('error') == 'not_authenticated'
    assert 'ace-login' in result.get('message', '')


def test_run_search_timeout():
    with patch('subprocess.run', side_effect=subprocess.TimeoutExpired('ace-cli', 15)):
        result, _ = run_search('test query', hook_event_name='UserPromptSubmit')
    assert result.get('error') == 'timeout'
    assert 'timed out' in result.get('message', '').lower()


def test_run_search_invalid_json():
    with patch('subprocess.run', return_value=_res(0, b'{ invalid json }')):
        result, _ = run_search('test query', hook_event_name='UserPromptSubmit')
    assert result is None
