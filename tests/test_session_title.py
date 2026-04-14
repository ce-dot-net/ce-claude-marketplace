#!/usr/bin/env python3
"""TDD: State-driven sessionTitle port from cache to repo.

Tests the build_session_title() helper in ace_before_task.py which computes
a CC sessionTitle based on pattern state (count, confidence, top domain,
agent_type) plus optional ROI suffix from last self-eval result.
"""

import json
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).parent.parent / 'plugins' / 'ace'
SHARED_HOOKS = PLUGIN_ROOT / 'shared-hooks'

# Ensure we can import ace_before_task as a module
sys.path.insert(0, str(SHARED_HOOKS))
sys.path.insert(0, str(SHARED_HOOKS / 'utils'))

import ace_before_task  # noqa: E402


def _pat(confidence=0.8, helpful=10, domain='git-workflow'):
    return {
        'confidence': confidence,
        'helpful': helpful,
        'domain': domain,
        'content': 'x',
    }


# ---------------------------------------------------------------------------
# Agent variant
# ---------------------------------------------------------------------------

def test_subagent_variant(tmp_path):
    patterns = [_pat() for _ in range(3)]
    title = ace_before_task.build_session_title(
        pattern_list=patterns,
        pattern_count=3,
        agent_type='researcher',
        review_file=tmp_path / 'no-such.json',
    )
    assert title == "ACE/sub · 3"


def test_agent_type_none_defaults_to_main(tmp_path):
    # agent_type None should NOT be treated as subagent
    patterns = [_pat(confidence=0.4) for _ in range(2)]
    title = ace_before_task.build_session_title(
        pattern_list=patterns,
        pattern_count=2,
        agent_type=None,
        review_file=tmp_path / 'no-such.json',
    )
    assert not title.startswith("ACE/sub")
    assert title.startswith("ACE low")


# ---------------------------------------------------------------------------
# Low-confidence state
# ---------------------------------------------------------------------------

def test_low_confidence(tmp_path):
    patterns = [_pat(confidence=0.3) for _ in range(4)]
    title = ace_before_task.build_session_title(
        pattern_list=patterns,
        pattern_count=4,
        agent_type='main',
        review_file=tmp_path / 'no-such.json',
    )
    assert title == "ACE low · 4"


# ---------------------------------------------------------------------------
# Strong session
# ---------------------------------------------------------------------------

def test_strong_session_no_roi(tmp_path):
    # 5+ patterns, avg conf >= 0.70, top domain helpful >= 20
    patterns = [_pat(confidence=0.8, helpful=5, domain='git-workflow') for _ in range(5)]
    title = ace_before_task.build_session_title(
        pattern_list=patterns,
        pattern_count=5,
        agent_type='main',
        review_file=tmp_path / 'no-such.json',
    )
    assert title == "ACE ready · git"


def test_strong_session_with_roi(tmp_path):
    review = tmp_path / 'ace-review-result.json'
    review.write_text(json.dumps({'helpful_pct': 80, 'time_saved': '15m'}))
    patterns = [_pat(confidence=0.8, helpful=5, domain='git-workflow') for _ in range(5)]
    title = ace_before_task.build_session_title(
        pattern_list=patterns,
        pattern_count=5,
        agent_type='main',
        review_file=review,
    )
    assert title == "ACE ready · git · +15m"


# ---------------------------------------------------------------------------
# Typical state
# ---------------------------------------------------------------------------

def test_typical_session(tmp_path):
    # Decent conf, below strong thresholds
    patterns = [_pat(confidence=0.75, helpful=2, domain='testing-framework') for _ in range(3)]
    title = ace_before_task.build_session_title(
        pattern_list=patterns,
        pattern_count=3,
        agent_type='main',
        review_file=tmp_path / 'no-such.json',
    )
    assert title == "ACE · 3 · testing"


def test_typical_with_roi(tmp_path):
    review = tmp_path / 'ace-review-result.json'
    review.write_text(json.dumps({'time_saved': '7m'}))
    patterns = [_pat(confidence=0.75, helpful=2, domain='testing-framework') for _ in range(3)]
    title = ace_before_task.build_session_title(
        pattern_list=patterns,
        pattern_count=3,
        agent_type='main',
        review_file=review,
    )
    assert title == "ACE · 3 · testing · +7m"


# ---------------------------------------------------------------------------
# Topic shortening
# ---------------------------------------------------------------------------

def test_topic_shortening_long_hyphenated(tmp_path):
    patterns = [
        _pat(confidence=0.8, helpful=5, domain='git-and-github-release-management')
        for _ in range(5)
    ]
    title = ace_before_task.build_session_title(
        pattern_list=patterns,
        pattern_count=5,
        agent_type='main',
        review_file=tmp_path / 'no-such.json',
    )
    assert title == "ACE ready · git"


# ---------------------------------------------------------------------------
# ROI parsing
# ---------------------------------------------------------------------------

def test_roi_tilde_prefix(tmp_path):
    review = tmp_path / 'ace-review-result.json'
    review.write_text(json.dumps({'time_saved': '~45m'}))
    patterns = [_pat(confidence=0.75, helpful=2, domain='git-workflow') for _ in range(3)]
    title = ace_before_task.build_session_title(
        pattern_list=patterns,
        pattern_count=3,
        agent_type='main',
        review_file=review,
    )
    assert title.endswith("· +45m")


def test_roi_zero_minutes_no_suffix(tmp_path):
    review = tmp_path / 'ace-review-result.json'
    review.write_text(json.dumps({'time_saved': '0m'}))
    patterns = [_pat(confidence=0.75, helpful=2, domain='git-workflow') for _ in range(3)]
    title = ace_before_task.build_session_title(
        pattern_list=patterns,
        pattern_count=3,
        agent_type='main',
        review_file=review,
    )
    assert '+' not in title
    assert title == "ACE · 3 · git"


def test_roi_missing_file_no_suffix(tmp_path):
    patterns = [_pat(confidence=0.75, helpful=2, domain='git-workflow') for _ in range(3)]
    title = ace_before_task.build_session_title(
        pattern_list=patterns,
        pattern_count=3,
        agent_type='main',
        review_file=tmp_path / 'does-not-exist.json',
    )
    assert '+' not in title


def test_roi_malformed_file_no_crash(tmp_path):
    review = tmp_path / 'ace-review-result.json'
    review.write_text("not json{{{")
    patterns = [_pat(confidence=0.75, helpful=2, domain='git-workflow') for _ in range(3)]
    # Should not raise
    title = ace_before_task.build_session_title(
        pattern_list=patterns,
        pattern_count=3,
        agent_type='main',
        review_file=review,
    )
    assert title == "ACE · 3 · git"


# ---------------------------------------------------------------------------
# Empty patterns — no sessionTitle
# ---------------------------------------------------------------------------

def test_empty_patterns_returns_none(tmp_path):
    # Convention: helper returns None when no patterns, caller omits key
    title = ace_before_task.build_session_title(
        pattern_list=[],
        pattern_count=0,
        agent_type='main',
        review_file=tmp_path / 'no-such.json',
    )
    assert title is None
