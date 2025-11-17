#!/usr/bin/env python3
"""Tests for ace_cli.py - CLI subprocess wrapper (mocked)"""

import json
import sys
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Add shared-hooks to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / 'shared-hooks' / 'utils'))

from ace_cli import run_search, run_learn, run_status


def test_run_search_success():
    """Test successful search call"""
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = json.dumps({
        'patterns': [
            {'content': 'Test pattern', 'helpful': 5}
        ]
    }).encode('utf-8')

    with patch('subprocess.run', return_value=mock_result) as mock_run:
        result = run_search('test query', 'org_123', 'prj_456')

        assert result is not None
        assert 'patterns' in result
        assert len(result['patterns']) == 1
        assert result['patterns'][0]['content'] == 'Test pattern'

        # Verify subprocess call
        args, kwargs = mock_run.call_args
        assert args[0][0] == 'ce-ace'
        assert args[0][1] == 'search'
        assert args[0][2] == '--stdin'
        assert '--org' in args[0]
        assert 'org_123' in args[0]

        print("✅ test_run_search_success passed")


def test_run_search_failure():
    """Test search call with non-zero exit code"""
    mock_result = MagicMock()
    mock_result.returncode = 1

    with patch('subprocess.run', return_value=mock_result):
        result = run_search('test query', 'org_123', 'prj_456')

        assert result is None
        print("✅ test_run_search_failure passed")


def test_run_search_timeout():
    """Test search call timeout"""
    import subprocess

    with patch('subprocess.run', side_effect=subprocess.TimeoutExpired('ce-ace', 10)):
        result = run_search('test query', 'org_123', 'prj_456')

        assert result is None
        print("✅ test_run_search_timeout passed")


def test_run_search_invalid_json():
    """Test search call with invalid JSON response"""
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = b'{ invalid json }'

    with patch('subprocess.run', return_value=mock_result):
        result = run_search('test query', 'org_123', 'prj_456')

        assert result is None
        print("✅ test_run_search_invalid_json passed")


def test_run_learn_success():
    """Test successful learn call"""
    mock_result = MagicMock()
    mock_result.returncode = 0

    with patch('subprocess.run', return_value=mock_result) as mock_run:
        result = run_learn(
            task='Test task',
            trajectory='Step 1, Step 2',
            success=True,
            org='org_123',
            project='prj_456'
        )

        assert result is True

        # Verify subprocess call
        args, kwargs = mock_run.call_args
        assert args[0][0] == 'ce-ace'
        assert args[0][1] == 'learn'
        assert args[0][2] == '--stdin'

        print("✅ test_run_learn_success passed")


def test_run_learn_failure():
    """Test learn call with non-zero exit code"""
    mock_result = MagicMock()
    mock_result.returncode = 1

    with patch('subprocess.run', return_value=mock_result):
        result = run_learn(
            task='Test task',
            trajectory='Steps',
            success=True,
            org='org_123',
            project='prj_456'
        )

        assert result is False
        print("✅ test_run_learn_failure passed")


def test_run_status_success():
    """Test successful status call"""
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = json.dumps({
        'total_patterns': 42,
        'sections': {}
    }).encode('utf-8')

    with patch('subprocess.run', return_value=mock_result):
        result = run_status('org_123', 'prj_456')

        assert result is not None
        assert result['total_patterns'] == 42

        print("✅ test_run_status_success passed")


if __name__ == '__main__':
    print("Running ace_cli tests (mocked)...")
    print()

    test_run_search_success()
    test_run_search_failure()
    test_run_search_timeout()
    test_run_search_invalid_json()
    test_run_learn_success()
    test_run_learn_failure()
    test_run_status_success()

    print()
    print("✅ All tests passed!")
