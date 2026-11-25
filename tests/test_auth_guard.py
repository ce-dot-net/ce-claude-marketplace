#!/usr/bin/env python3
"""8.4.0: after an auth failure (401 / not logged in / session expired) the search path makes NO further authenticated
call (engine or ace-cli: each one is a GET /config on the server) until the token file changes.
Marker <data root>/auth-rejected holds sha256 of ~/.config/ace/config.json (never the token). Mod twin: mod/tests/auth_guard.test.ts."""
import hashlib
import importlib
import os
import sys
from pathlib import Path

import pytest

import test_pin_backoff as T  # fake ace-cli fixture (mode via ACE_FAKE_PIN_MODE)

fake = T.fake
_search = T._search


def _cfg(tmp_path, text):
    p = Path(os.environ["XDG_CONFIG_HOME"]) / "ace" / "config.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    return p


def test_cli_auth_failure_holds_until_token_changes(fake, monkeypatch, tmp_path):
    monkeypatch.setenv("ACE_ENGINE", "cli")
    monkeypatch.setenv("ACE_FAKE_PIN_MODE", "auth")
    _cfg(tmp_path, '{"auth":{"token":"dead"}}')
    r, _ = fake.cli.run_search("q", session_id="s1", hook_event_name="UserPromptSubmit")
    assert r.get("error") == "not_authenticated" and len(_search(fake)) == 1
    marker = fake.pdd.data_root() / "auth-rejected"
    assert marker.read_text().strip() == hashlib.sha256(b'{"auth":{"token":"dead"}}').hexdigest()
    assert "dead" not in marker.read_text()
    for _ in range(3):  # held: no spawn at all
        r, _ = fake.cli.run_search("q", session_id="s1", hook_event_name="UserPromptSubmit")
        assert r.get("error") == "not_authenticated"
    assert len(_search(fake)) == 1
    _cfg(tmp_path, '{"auth":{"token":"fresh"}}')  # a login: the guard lets one call through again
    monkeypatch.setenv("ACE_FAKE_PIN_MODE", "ok")
    r, _ = fake.cli.run_search("q", session_id="s1", hook_event_name="UserPromptSubmit")
    assert r.get("similar_patterns") and len(_search(fake)) == 2


def test_engine_auth_failure_still_tries_cli_then_holds(fake, monkeypatch, tmp_path):
    """The engine's auth-looking failure is not final (a refresh problem the CLI can survive: test_engine_token_refresh):
    the CLI fallback runs; only its auth failure holds."""
    monkeypatch.setattr(fake.cli.ace_engine, "preflight", lambda: ("node", "ok"))
    monkeypatch.setattr(fake.cli, "_search_lib", lambda *a, **k: (None, "exit 1: Session expired - please log in again"))
    monkeypatch.setenv("ACE_FAKE_PIN_MODE", "auth")
    _cfg(tmp_path, "{}")
    r, _ = fake.cli.run_search("q", session_id="s1", hook_event_name="UserPromptSubmit")
    assert r.get("error") == "not_authenticated" and len(_search(fake)) == 1
    assert (fake.pdd.data_root() / "auth-rejected").exists()
    monkeypatch.setattr(fake.cli, "_search_lib", lambda *a, **k: pytest.fail("held: no engine spawn"))
    r, _ = fake.cli.run_search("q", session_id="s1", hook_event_name="UserPromptSubmit")
    assert r.get("error") == "not_authenticated" and len(_search(fake)) == 1


def test_no_token_file_is_a_stable_fingerprint(fake, monkeypatch):
    monkeypatch.setenv("ACE_ENGINE", "cli")
    monkeypatch.setenv("ACE_FAKE_PIN_MODE", "auth")
    fake.cli.run_search("q", session_id="s1", hook_event_name="UserPromptSubmit")
    fake.cli.run_search("q", session_id="s1", hook_event_name="UserPromptSubmit")
    assert len(_search(fake)) == 1
