#!/usr/bin/env python3
"""Tests for ace_context.py - Context resolution from .claude/settings.json"""

import json
import sys
import tempfile
from pathlib import Path

# Add shared-hooks to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / 'shared-hooks' / 'utils'))

from ace_context import get_context


def test_get_context_success():
    """Test successful context resolution"""
    # Create temp directory with .claude/settings.json
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        claude_dir = tmppath / '.claude'
        claude_dir.mkdir()

        settings = {
            'orgId': 'org_test123',
            'projectId': 'prj_test456'
        }

        settings_file = claude_dir / 'settings.json'
        settings_file.write_text(json.dumps(settings))

        # Change to temp directory
        import os
        original_dir = os.getcwd()
        try:
            os.chdir(tmpdir)
            context = get_context()

            assert context is not None
            assert context['org'] == 'org_test123'
            assert context['project'] == 'prj_test456'

            print("✅ test_get_context_success passed")

        finally:
            os.chdir(original_dir)


def test_get_context_missing_file():
    """Test when .claude/settings.json doesn't exist"""
    with tempfile.TemporaryDirectory() as tmpdir:
        import os
        original_dir = os.getcwd()
        try:
            os.chdir(tmpdir)
            context = get_context()

            assert context is None
            print("✅ test_get_context_missing_file passed")

        finally:
            os.chdir(original_dir)


def test_get_context_missing_fields():
    """Test when settings.json exists but missing orgId or projectId"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        claude_dir = tmppath / '.claude'
        claude_dir.mkdir()

        # Missing projectId
        settings = {'orgId': 'org_test123'}
        settings_file = claude_dir / 'settings.json'
        settings_file.write_text(json.dumps(settings))

        import os
        original_dir = os.getcwd()
        try:
            os.chdir(tmpdir)
            context = get_context()

            assert context is None
            print("✅ test_get_context_missing_fields passed")

        finally:
            os.chdir(original_dir)


def test_get_context_invalid_json():
    """Test when settings.json has invalid JSON"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        claude_dir = tmppath / '.claude'
        claude_dir.mkdir()

        settings_file = claude_dir / 'settings.json'
        settings_file.write_text("{ invalid json }")

        import os
        original_dir = os.getcwd()
        try:
            os.chdir(tmpdir)
            context = get_context()

            assert context is None
            print("✅ test_get_context_invalid_json passed")

        finally:
            os.chdir(original_dir)


if __name__ == '__main__':
    print("Running ace_context tests...")
    print()

    test_get_context_success()
    test_get_context_missing_file()
    test_get_context_missing_fields()
    test_get_context_invalid_json()

    print()
    print("✅ All tests passed!")
