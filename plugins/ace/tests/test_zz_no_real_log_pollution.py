"""Guard (runs last): the plugin-local suite must not write the developer's real <repo>/.claude/data/logs/ace-relevance.jsonl."""
from conftest import REAL_LOG, REAL_LOG_WRITES


def test_real_repo_relevance_log_not_written():
    assert not REAL_LOG_WRITES, "plugin-local tests wrote %d rows into %s" % (len(REAL_LOG_WRITES), REAL_LOG)
