"""Isolate plugin-data (disk search cache, session state) per test (v8 WP-B)."""
import pytest


@pytest.fixture(autouse=True)
def _isolated_plugin_data(tmp_path, monkeypatch):
    if not __import__("os").environ.get("ACE_TEST_KEEP_PLUGIN_DATA"):
        monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path / "_plugin_data"))
    yield
