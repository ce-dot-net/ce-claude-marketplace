"""8.1.0 audit: the recap/insights text report reads the v8 log schema. Tasks group by task_session_id; main searches are
UserPromptSubmit rows of the main agent that are no cache hit; "used" = used_ids_count / used_source; sections for
evidenced use per arm, learn health, skips/rejections/context/domain-shift cache."""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'plugins/ace/shared-hooks/utils'))
import ace_insights_analyzer as ai  # noqa: E402

NOW = datetime.now(timezone.utc)
ts = lambda m: (NOW - timedelta(minutes=m)).isoformat().replace('+00:00', 'Z')
ROWS = [
    {'timestamp': ts(50), 'event': 'context', 'session_id': 's', 'state': 'ok', 'source': 'repo_file'},
    {'timestamp': ts(49), 'event': 'search', 'hook': 'UserPromptSubmit', 'agent_type': 'main', 'session_id': 's', 'task_session_id': 't1',
     'user_prompt': 'fix the resolver', 'patterns_injected': 8, 'render_cohort': 'budget', 'engine': 'lib', 'engine_reason': 'ok'},
    {'timestamp': ts(48), 'event': 'search', 'hook': 'SubagentStart', 'agent_type': 'Explore', 'session_id': 's', 'patterns_injected': 50},
    {'timestamp': ts(47), 'event': 'search', 'hook': 'UserPromptSubmit', 'agent_type': 'main', 'session_id': 's', 'cache_hit': True,
     'engine': 'cache', 'patterns_injected': 3},
    {'timestamp': ts(46), 'event': 'domain_shift', 'session_id': 's', 'cache_hit': True},
    {'timestamp': ts(45), 'event': 'domain_shift', 'session_id': 's', 'cache_hit': False},
    {'timestamp': ts(40), 'event': 'execution', 'agent_type': 'main', 'session_id': 's', 'task_session_id': 't1', 'render_cohort': 'budget',
     'patterns_used_count': 8, 'used_ids_count': 2, 'used_source': 'tokens', 'learning_sent': True, 'success': True},
    {'timestamp': ts(39), 'event': 'learn_dispatched', 'session_id': 's', 'task_session_id': 't1', 'applied_log_ids_count': 2},
    {'timestamp': ts(30), 'event': 'search', 'hook': 'UserPromptSubmit', 'agent_type': 'main', 'session_id': 's', 'task_session_id': 't2',
     'user_prompt': 'second task', 'patterns_injected': 100, 'render_cohort': 'full', 'engine': 'cli', 'engine_reason': 'lib failed: exit 1'},
    {'timestamp': ts(20), 'event': 'execution', 'agent_type': 'main', 'session_id': 's', 'task_session_id': 't2', 'render_cohort': 'full',
     'patterns_used_count': 100, 'used_ids_count': 0, 'used_source': 'none', 'learning_sent': False, 'success': True},
    {'timestamp': ts(19), 'event': 'learn_dispatched', 'session_id': 's', 'task_session_id': 't2', 'applied_log_ids_count': 0},
    {'timestamp': ts(18), 'event': 'search_skipped', 'session_id': 's', 'reason': 'machine_prompt'},
    {'timestamp': ts(17), 'event': 'learn_skipped', 'session_id': 's', 'reason': 'no_substantial_work'},
    {'timestamp': ts(16), 'event': 'rejection_detected', 'session_id': 's', 'downvote_sent': True},
]


def test_report_sections_and_numbers():
    t = ai.generate_text_report(ROWS, hours=12)
    assert 'Tasks: 2' in t and 'Main searches: 2' in t           # the cache hit and the subagent search are not main searches
    assert 'Last task: second task' in t and 'used 0/100' in t
    assert 'budget: 1/1 tasks with evidenced use (tokens 1, model 0, both 0)' in t
    assert 'full: 0/1 tasks with evidenced use' in t
    assert 'learning_sent false: 1' in t and 'learns with 0 applied ids: 1' in t and 'learn retries: 0' in t
    assert 'engine lib 1 · cli 1' in t and 'lib failed: exit 1' in t
    assert 'machine_prompt 1' in t and 'no_substantial_work 1' in t and 'rejections 1 (downvotes sent 1)' in t
    assert 'context: repo_file/ok 1' in t and 'domain-shift cache hits: 1/2' in t
    for stale in ('h=', '% rel', 'helpful'):
        assert stale not in t


def test_empty_and_old_rows():
    assert 'No telemetry' in ai.generate_text_report([], hours=12)
    assert 'No events' in ai.generate_text_report([{'timestamp': ts(60 * 48), 'event': 'search'}], hours=12)
