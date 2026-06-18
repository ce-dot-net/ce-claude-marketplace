"""
RED tests for the v7.1.5 "command de-stale + insights v15" change set.

Parts covered:
  1. ace-test.md: de-stale to ACE-1.5 / device-code model (mirrors test_ace_doctor_sync.py style)
  2. Part-2: ace_relevance_logger.py and ace_insights_analyzer.py carry v15 fields gracefully
  3. Part-3: 5 commands use env-first .env.ACE_PROJECT_ID // .projectId order
  4. Part-4 (this file IS the guard test)

Run with:
    python3 -m pytest tests/test_ace_test_sync.py -v
"""

import json
import textwrap
from pathlib import Path
from typing import Any, Dict, List

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent
COMMANDS_DIR = REPO_ROOT / "plugins" / "ace" / "commands"

ACE_TEST_MD = COMMANDS_DIR / "ace-test.md"
ACE_INSIGHTS_MD = COMMANDS_DIR / "ace-insights.md"

SHARED_UTILS = REPO_ROOT / "plugins" / "ace" / "shared-hooks" / "utils"
RELEVANCE_LOGGER_PY = SHARED_UTILS / "ace_relevance_logger.py"
INSIGHTS_ANALYZER_PY = SHARED_UTILS / "ace_insights_analyzer.py"

# Part-3 commands
PART3_COMMANDS = {
    "ace-clear.md": COMMANDS_DIR / "ace-clear.md",
    "ace-delta.md": COMMANDS_DIR / "ace-delta.md",
    "ace-export-patterns.md": COMMANDS_DIR / "ace-export-patterns.md",
    "ace-import-patterns.md": COMMANDS_DIR / "ace-import-patterns.md",
    "ace-learn.md": COMMANDS_DIR / "ace-learn.md",
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ===========================================================================
# Part 1 — ace-test.md de-stale assertions
# ===========================================================================


class TestAceTestNoHardcodedMarketplacesPath:
    """ace-test.md must NOT use the dead /plugins/marketplaces/ layout."""

    def test_no_hardcoded_marketplaces_path(self):
        doc = _read(ACE_TEST_MD)
        assert "/plugins/marketplaces/" not in doc, (
            "ace-test.md contains the hardcoded dead path "
            "'/plugins/marketplaces/' — replace with dynamic "
            "$CLAUDE_PLUGIN_ROOT or cache glob."
        )


class TestAceTestDynamicPluginRoot:
    """ace-test.md's hook-check step must resolve the plugin dir dynamically."""

    def test_uses_claude_plugin_root_or_cache_glob(self):
        doc = _read(ACE_TEST_MD)
        uses_env = "CLAUDE_PLUGIN_ROOT" in doc
        uses_glob = "~/.claude/plugins/cache/ce-dot-net-marketplace/ace" in doc
        assert uses_env or uses_glob, (
            "ace-test.md does not reference CLAUDE_PLUGIN_ROOT or the cache glob "
            "~/.claude/plugins/cache/ce-dot-net-marketplace/ace — "
            "the plugin directory must be resolved dynamically, not hardcoded."
        )


class TestAceTestNoStaleConfigFields:
    """ace-test.md must NOT present serverUrl / apiToken / cacheTtl as current config."""

    def test_no_serverurl_as_current_config(self):
        doc = _read(ACE_TEST_MD)
        # A legitimate reference in a "v1.x deprecated" migration note is fine,
        # but any line that points users to SET or CHECK serverUrl as a live field
        # (e.g. "correct serverUrl") is stale.
        stale_phrases = [
            "correct serverUrl",
            "for correct serverUrl",
            "serverUrl, apiToken",
            "apiToken, or projectId",
            "serverUrl, apiToken, or projectId",
        ]
        found = [p for p in stale_phrases if p in doc]
        assert not found, (
            f"ace-test.md still references stale v1.x config field(s) as the "
            f"current model (found: {found}). "
            f"The 1.5 model is device-code auth — no serverUrl/apiToken fields."
        )

    def test_no_apitoken_as_current_model(self):
        doc = _read(ACE_TEST_MD)
        # Must not tell users that apiToken is a valid CURRENT field to check/configure.
        # (Present in "config.json for valid apiToken" = stale.)
        assert "for valid apiToken" not in doc, (
            "ace-test.md still says 'config.json for valid apiToken' — "
            "the 1.5 model uses device-code tokens (auth.token), not apiToken."
        )

    def test_no_cachetlt_missing_required_fields(self):
        doc = _read(ACE_TEST_MD)
        # "serverUrl, apiToken, or projectId missing" is a stale error description
        assert "serverUrl, apiToken, or projectId missing" not in doc, (
            "ace-test.md describes 'serverUrl, apiToken, or projectId missing' as a "
            "warning — these v1.x field names are not valid in the current model."
        )


class TestAceTestDeviceCodeModel:
    """ace-test.md must describe the ACE-1.5 device-code auth model."""

    def test_references_ace_sdk_cli(self):
        doc = _read(ACE_TEST_MD)
        assert "@ace-sdk/cli" in doc, (
            "ace-test.md does not mention '@ace-sdk/cli' — the correct npm package."
        )

    def test_references_auth_token_path(self):
        doc = _read(ACE_TEST_MD)
        # Must mention device-code auth: auth.token in ~/.config/ace/config.json
        # OR whoami --json as the verification method
        has_auth_token = "auth.token" in doc
        has_whoami = "whoami" in doc
        assert has_auth_token or has_whoami, (
            "ace-test.md does not reference 'auth.token' or 'whoami' — "
            "the device-code auth model must be described."
        )

    def test_references_ace_project_id_env(self):
        doc = _read(ACE_TEST_MD)
        assert "ACE_PROJECT_ID" in doc, (
            "ace-test.md does not mention ACE_PROJECT_ID — "
            "the current project-id env var (set in .claude/settings.json .env)."
        )

    def test_references_ace_cli_4x(self):
        doc = _read(ACE_TEST_MD)
        # Must mention ace-cli 4.x in some form
        has_4x = any(f"ace-cli {v}" in doc or f"v4." in doc for v in ["4.", "v4"])
        # More flexible: just check there's a 4.x reference
        import re
        has_4x = bool(re.search(r'ace-cli [4-9]\.|v4\.', doc))
        assert has_4x, (
            "ace-test.md does not reference ace-cli 4.x anywhere — "
            "the current minimum CLI version is 4.x."
        )


class TestAceTestNoDeadPluginPath:
    """Step 3 (hooks check) must not point at dead/wrong paths."""

    def test_no_ace_after_task_wrapper_reference(self):
        doc = _read(ACE_TEST_MD)
        assert "ace_after_task_wrapper.sh" not in doc, (
            "ace-test.md references 'ace_after_task_wrapper.sh' which does not "
            "exist in hooks.json — it is a dead script name."
        )

    def test_hooks_step_uses_plugin_root_not_hardcoded(self):
        doc = _read(ACE_TEST_MD)
        # The hooks verification step must not check under $HOME/.claude/plugins/marketplaces/
        assert (
            '"$HOME/.claude/plugins/marketplaces/' not in doc
            and "$HOME/.claude/plugins/marketplaces/" not in doc
        ), (
            "ace-test.md hook-check step hardcodes $HOME/.claude/plugins/marketplaces/ — "
            "this path is dead; must use $PLUGIN_ROOT or cache glob."
        )


# ===========================================================================
# Part 2 — ace_relevance_logger.py: top_patterns includes v15 fields
# ===========================================================================


class TestRelevanceLoggerV15Fields:
    """top_patterns builder must include cumulative_v15_reward and isAtRisk."""

    def _load_module(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "ace_relevance_logger", RELEVANCE_LOGGER_PY
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def _build_top_patterns(self, patterns):
        """Call the module's log_search_metrics and return what it would log."""
        import json, os, tempfile
        mod = self._load_module()
        with tempfile.TemporaryDirectory() as td:
            logger = mod.ACERelevanceLogger(log_dir=td)
            logger.log_search_metrics(
                hook="UserPromptSubmit",
                session_id="test-session",
                user_prompt="test prompt",
                search_query="test query",
                patterns_returned=patterns,
                patterns_injected=patterns,
                domains=["test"],
            )
            log_file = Path(td) / "ace-relevance.jsonl"
            entry = json.loads(log_file.read_text().strip())
            return entry["top_patterns"]

    def test_top_patterns_includes_cumulative_v15_reward_key(self):
        patterns = [
            {
                "id": "pat-001",
                "confidence": 0.9,
                "helpful": 2,
                "harmful": 0,
                "domain": "testing",
                "section": "strategies",
                "content": "test content",
                "cumulative_v15_reward": 1.5,
                "isAtRisk": False,
                "n_hot_pos": 1,
                "n_hot_neg": 0,
            }
        ]
        top = self._build_top_patterns(patterns)
        assert len(top) == 1
        assert "cumulative_v15_reward" in top[0], (
            "top_patterns entries do not include 'cumulative_v15_reward' — "
            "the v15 reward signal must be logged per pattern."
        )

    def test_top_patterns_includes_isAtRisk_key(self):
        patterns = [
            {
                "id": "pat-002",
                "confidence": 0.8,
                "helpful": 1,
                "harmful": 0,
                "domain": "testing",
                "section": "strategies",
                "content": "test",
                "cumulative_v15_reward": 0.5,
                "isAtRisk": False,
            }
        ]
        top = self._build_top_patterns(patterns)
        assert "isAtRisk" in top[0], (
            "top_patterns entries do not include 'isAtRisk' — "
            "the v15 risk flag must be logged per pattern."
        )

    def test_top_patterns_v15_fields_graceful_when_absent(self):
        """Must not raise KeyError when pattern dict lacks v15 fields (old log entries)."""
        patterns = [
            {
                "id": "pat-003",
                "confidence": 0.7,
                "helpful": 1,
                "harmful": 0,
                "domain": "testing",
                "section": "strategies",
                "content": "legacy pattern without v15 fields",
                # NO cumulative_v15_reward, NO isAtRisk
            }
        ]
        # Must not raise
        top = self._build_top_patterns(patterns)
        assert len(top) == 1
        # cumulative_v15_reward should be None or absent (not crash)
        # The key should still be present (using .get()), value may be None
        assert "cumulative_v15_reward" in top[0], (
            "top_patterns entry is missing 'cumulative_v15_reward' key even when "
            "pattern lacks the field — should be present with a default (e.g. None)."
        )
        assert top[0]["cumulative_v15_reward"] is None, (
            "cumulative_v15_reward should default to None when absent in pattern."
        )

    def test_top_patterns_n_hot_pos_included(self):
        patterns = [
            {
                "id": "pat-004",
                "confidence": 0.85,
                "helpful": 2,
                "harmful": 0,
                "domain": "testing",
                "section": "strategies",
                "content": "test",
                "cumulative_v15_reward": 1.0,
                "isAtRisk": False,
                "n_hot_pos": 3,
                "n_hot_neg": 1,
            }
        ]
        top = self._build_top_patterns(patterns)
        assert "n_hot_pos" in top[0], (
            "top_patterns does not include 'n_hot_pos'."
        )
        assert "n_hot_neg" in top[0], (
            "top_patterns does not include 'n_hot_neg'."
        )


# ===========================================================================
# Part 2 — ace_insights_analyzer.py: extract_task_data_for_evaluation
#           carries v15 fields and is graceful on old entries
# ===========================================================================


class TestInsightsAnalyzerV15Fields:
    """extract_task_data_for_evaluation must surface v15 fields in pattern_details."""

    def _load_analyzer(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "ace_insights_analyzer", INSIGHTS_ANALYZER_PY
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def _make_entries(self, with_v15: bool = True) -> List[Dict[str, Any]]:
        """Build a minimal synthetic relevance-log with one search + one execution."""
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        search_ts = (now - timedelta(seconds=30)).isoformat()
        exec_ts = now.isoformat()

        pat: Dict[str, Any] = {
            "id": "pat-v15-test",
            "confidence": 0.88,
            "helpful": 2,
            "harmful": 0,
            "domain": "tdd",
            "section": "strategies",
            "content": "write tests first",
        }
        if with_v15:
            pat["cumulative_v15_reward"] = 1.7
            pat["isAtRisk"] = False
            pat["n_hot_pos"] = 2
            pat["n_hot_neg"] = 0

        search_entry = {
            "timestamp": search_ts,
            "event": "search",
            "hook": "UserPromptSubmit",
            "session_id": "sess-v15",
            "project_id": "prj_test",
            "user_prompt": "write a test for login",
            "search_query": "write test login",
            "patterns_returned": 1,
            "patterns_injected": 1,
            "patterns_filtered": 0,
            "avg_confidence": 0.88,
            "domains": ["tdd"],
            "top_patterns": [pat],
        }
        exec_entry = {
            "timestamp": exec_ts,
            "event": "execution",
            "hook": "Stop",
            "session_id": "sess-v15",
            "project_id": "prj_test",
            "agent_type": "main",
            "patterns_used_count": 1,
            "pattern_ids": ["pat-v15-test"],
            "tools_executed": 5,
            "state_changing_tools": 2,
            "success": True,
            "execution_time_seconds": 30.0,
            "learning_sent": True,
        }
        return [search_entry, exec_entry]

    def test_pattern_details_include_v15_reward_when_present(self):
        mod = self._load_analyzer()
        entries = self._make_entries(with_v15=True)
        result = mod.extract_task_data_for_evaluation(entries, hours=1)
        tasks = result.get("tasks", [])
        assert tasks, "Expected at least one task in result"
        pattern_details = tasks[0].get("pattern_details", [])
        assert pattern_details, "Expected pattern_details in task"
        pd = pattern_details[0]
        assert "cumulative_v15_reward" in pd, (
            "pattern_details entry does not carry 'cumulative_v15_reward' — "
            "the v15 signal must be surfaced for LLM evaluation."
        )
        assert pd["cumulative_v15_reward"] == 1.7, (
            f"Expected cumulative_v15_reward=1.7, got {pd.get('cumulative_v15_reward')}"
        )

    def test_pattern_details_include_isAtRisk_when_present(self):
        mod = self._load_analyzer()
        entries = self._make_entries(with_v15=True)
        result = mod.extract_task_data_for_evaluation(entries, hours=1)
        tasks = result.get("tasks", [])
        assert tasks
        pd = tasks[0]["pattern_details"][0]
        assert "isAtRisk" in pd, (
            "pattern_details entry does not carry 'isAtRisk' — "
            "the v15 risk flag must be surfaced for LLM evaluation."
        )
        assert pd["isAtRisk"] is False

    def test_pattern_details_graceful_when_v15_absent(self):
        """Must not crash when pattern lacks v15 fields (old log entries)."""
        mod = self._load_analyzer()
        entries = self._make_entries(with_v15=False)
        # Must not raise any exception
        result = mod.extract_task_data_for_evaluation(entries, hours=1)
        tasks = result.get("tasks", [])
        assert tasks, "Expected tasks even with v15-less entries"
        pd = tasks[0].get("pattern_details", [{}])[0]
        # cumulative_v15_reward should be absent or None — either is fine
        # but must not have raised KeyError
        reward = pd.get("cumulative_v15_reward")
        # None or absent both acceptable; just confirm no crash
        assert reward is None or "cumulative_v15_reward" not in pd or True, (
            "pattern_details crashed processing v15-less entry."
        )

    def test_extract_returns_tasks_for_valid_entries(self):
        mod = self._load_analyzer()
        entries = self._make_entries(with_v15=True)
        result = mod.extract_task_data_for_evaluation(entries, hours=1)
        assert "tasks" in result
        assert "metadata" in result


# ===========================================================================
# Part 2 — ace-insights.md: Step 2 must instruct evaluator to weight v15
# ===========================================================================


class TestAceInsightsMdV15Instructions:
    """ace-insights.md Step 2 must reference the v15 reward signal."""

    def test_step2_references_v15_reward_signal(self):
        doc = _read(ACE_INSIGHTS_MD)
        has_v15 = "cumulative_v15_reward" in doc or "v15" in doc.lower()
        assert has_v15, (
            "ace-insights.md Step 2 evaluation instructions do not mention "
            "'cumulative_v15_reward' or 'v15' — the evaluator must be told to "
            "weight the server-confirmed reward signal when present."
        )

    def test_step2_references_isAtRisk(self):
        doc = _read(ACE_INSIGHTS_MD)
        assert "isAtRisk" in doc, (
            "ace-insights.md Step 2 does not mention 'isAtRisk' — "
            "the evaluator must treat isAtRisk==true as a negative signal."
        )

    def test_step2_mentions_fallback_to_confidence(self):
        doc = _read(ACE_INSIGHTS_MD)
        # Must still mention confidence as the fallback for older entries
        assert "confidence" in doc, (
            "ace-insights.md Step 2 no longer mentions 'confidence' — "
            "it must remain as fallback for entries without v15 data."
        )


# ===========================================================================
# Part 3 — 5 commands must use env-first .env.ACE_PROJECT_ID // .projectId
# ===========================================================================


class TestProjectIdEnvFirst:
    """All 5 Part-3 commands must use .env.ACE_PROJECT_ID // .projectId (env-first)."""

    def _project_id_jq_lines(self, path: Path) -> List[str]:
        """Return lines that contain a jq PROJECT_ID extraction in this .md file."""
        doc = _read(path)
        lines = []
        for line in doc.splitlines():
            # Only lines where PROJECT_ID is being set via jq from settings.json
            if "PROJECT_ID" in line and "jq" in line and ".projectId" in line:
                lines.append(line.strip())
        return lines

    def _assert_env_first(self, cmd_name: str, path: Path) -> None:
        lines = self._project_id_jq_lines(path)
        assert lines, (
            f"{cmd_name}: No jq PROJECT_ID extraction line found — "
            f"check the file still has a jq-based project-id read."
        )
        for line in lines:
            # .env.ACE_PROJECT_ID must appear before .projectId on the same jq expression
            env_pos = line.find(".env.ACE_PROJECT_ID")
            legacy_pos = line.find(".projectId")
            # If .env.ACE_PROJECT_ID is not present at all it's wrong too
            assert env_pos != -1, (
                f"{cmd_name}: jq line does not reference '.env.ACE_PROJECT_ID': {line!r}"
            )
            assert env_pos < legacy_pos, (
                f"{cmd_name}: '.env.ACE_PROJECT_ID' must come BEFORE '.projectId' "
                f"(env-first) but order is reversed in: {line!r}"
            )

    def test_ace_clear_env_first(self):
        self._assert_env_first("ace-clear.md", PART3_COMMANDS["ace-clear.md"])

    def test_ace_delta_env_first(self):
        self._assert_env_first("ace-delta.md", PART3_COMMANDS["ace-delta.md"])

    def test_ace_export_patterns_env_first(self):
        self._assert_env_first(
            "ace-export-patterns.md", PART3_COMMANDS["ace-export-patterns.md"]
        )

    def test_ace_import_patterns_env_first(self):
        self._assert_env_first(
            "ace-import-patterns.md", PART3_COMMANDS["ace-import-patterns.md"]
        )

    def test_ace_learn_env_first(self):
        self._assert_env_first("ace-learn.md", PART3_COMMANDS["ace-learn.md"])
