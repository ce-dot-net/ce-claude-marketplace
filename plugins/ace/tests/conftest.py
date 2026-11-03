"""These plugin-local tests mock subprocess.run; they must not depend on an ace-cli being installed.
Pin the resolver to the global-name argv so the mocked spawn is reached on any machine (CI has no ace-cli).

Hermetic: every test runs in its own cwd (the relevance logger writes <cwd>/.claude/data/logs) with its own plugin
data, so the suite never appends rows to the developer's real <repo>/.claude/data/logs/ace-relevance.jsonl."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'shared-hooks' / 'utils'))
import ace_cli  # noqa: E402

import plugin_data_dir  # noqa: E402

REAL_LOG = Path(__file__).resolve().parents[3] / '.claude' / 'data' / 'logs' / 'ace-relevance.jsonl'
# Every relevance row goes through plugin_data_dir.open_project_log; record any open that targets the real log.
# (A size check would flake: a live Claude Code session in this repo appends to the same file.)
REAL_LOG_WRITES = []
_open_project_log = plugin_data_dir.open_project_log


def _guarded_open(path, *a, **kw):
    if Path(path).resolve() == REAL_LOG.resolve():
        REAL_LOG_WRITES.append(str(path))
    return _open_project_log(path, *a, **kw)


plugin_data_dir.open_project_log = _guarded_open


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('CLAUDE_PLUGIN_DATA', str(tmp_path / 'ace-plugin-data'))
    monkeypatch.delenv('CLAUDE_PROJECT_DIR', raising=False)
    import ace_relevance_logger
    monkeypatch.setattr(ace_relevance_logger, '_logger', None)


@pytest.fixture(autouse=True)
def _resolved_cli(monkeypatch):
    monkeypatch.setattr(ace_cli, '_resolve', lambda: (['ace-cli'], 'global'))


def pytest_sessionfinish(session, exitstatus):
    if REAL_LOG_WRITES:
        print('\nFAIL: the plugin-local suite wrote to the real %s' % REAL_LOG)
        session.exitstatus = 1
