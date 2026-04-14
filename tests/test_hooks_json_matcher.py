#!/usr/bin/env python3
"""
hooks.json: PreToolUse and PostToolUse matchers must be '*' (v6.4.0).
Other matchers unchanged.
"""
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_JSON = REPO_ROOT / "plugins" / "ace" / "hooks" / "hooks.json"


def test_hooks_json_valid_and_matchers():
    data = json.loads(HOOKS_JSON.read_text())
    hooks = data["hooks"]

    def first_matcher(event):
        return hooks[event][0]["matcher"]

    assert first_matcher("PreToolUse") == "*", "PreToolUse matcher must be '*'"
    assert first_matcher("PostToolUse") == "*", "PostToolUse matcher must be '*'"
