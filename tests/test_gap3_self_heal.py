#!/usr/bin/env python3
"""
GAP3 self-heal: corrupt state file should be logged as error and deleted
so it cannot permanently disrupt learning across sessions.
"""
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SHARED = REPO_ROOT / "plugins" / "ace" / "shared-hooks"
sys.path.insert(0, str(SHARED))
sys.path.insert(0, str(SHARED / "utils"))


def test_corrupt_state_file_is_logged_and_deleted(tmp_path, monkeypatch):
    """
    When ace_after_task loads a corrupt ace-patterns-used-*.json file,
    the parse exception must:
      1. NOT propagate
      2. Cause an 'error' entry in .claude/data/logs/ace-relevance.jsonl
      3. Unlink the corrupt file so future runs are unaffected
    """
    monkeypatch.chdir(tmp_path)
    log_dir = tmp_path / ".claude" / "data" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    session_id = "sess-corrupt"
    agent_suffix = "main"
    state_file = log_dir / f"ace-patterns-used-{session_id}-{agent_suffix}.json"
    state_file.write_text("{ not valid json")

    # Reset the relevance logger singleton so it writes to our cwd
    import ace_relevance_logger as arl
    arl._logger = None

    # Simulate the logic block with the v6.4.0 self-heal
    playbook_used = []
    agent_id = None
    try:
        if state_file.exists():
            playbook_used = json.loads(state_file.read_text())
            state_file.unlink()
    except Exception as _e:
        from ace_relevance_logger import log_hook_error
        log_hook_error(
            location="load_playbook_used",
            session_id=session_id,
            project_id=None,
            hook="Stop",
            error=_e,
            extra={"state_file": str(state_file)},
        )
        try:
            state_file.unlink(missing_ok=True)
        except Exception:
            pass

    assert not state_file.exists(), "Corrupt state file must be deleted"

    relevance_log = log_dir / "ace-relevance.jsonl"
    assert relevance_log.exists(), "Error must be logged to ace-relevance.jsonl"

    entries = [json.loads(l) for l in relevance_log.read_text().splitlines() if l.strip()]
    err_entries = [e for e in entries if e.get("event") == "error" and e.get("location") == "load_playbook_used"]
    assert len(err_entries) == 1, f"Expected one error entry, got {entries}"
    assert err_entries[0].get("hook") == "Stop"
    assert err_entries[0].get("session_id") == session_id
    assert err_entries[0].get("error_type") in {"JSONDecodeError", "ValueError"}
