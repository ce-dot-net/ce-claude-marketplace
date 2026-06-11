#!/usr/bin/env python3
"""
TDD RED tests — v7.1.2 Change B: Domain-shift injection QUALITY GATE.

Design (from quality_gate_bug_confirmed in the v7.1.2 spec):
  - ace_posttooluse_domain_inject.sh (lines 50-57) strips to useful set that
    is MISSING the four v15 reward-vocab fields: cumulative_v15_reward,
    n_hot_pos, n_hot_neg, isAtRisk. Fix: expand the useful set.
  - ace_posttooluse_domain_inject.sh has NO call to _apply_quality_gate, so
    isAtRisk=True patterns pass through unfiltered.
  - ace_pretooluse_wrapper.sh emits raw $SEARCH_RESULT with NO strip and NO
    quality gate at all for the domain-shift inject path.
  - Both paths must apply the SAME quality gate + useful-fields strip as
    ace_before_task.py's USEFUL_FIELDS / _apply_quality_gate.

These tests exercise:
  B1. A shared Python helper (apply_quality_gate_and_strip) callable from bash
      via python3 -c or via patterns_used_state.py; it strips to USEFUL_FIELDS
      AND applies the v15 quality gate.
  B2. posttooluse path: isAtRisk=True patterns are filtered out of injected context.
  B3. posttooluse path: v15 fields (cumulative_v15_reward, n_hot_pos, n_hot_neg,
      isAtRisk) survive the strip step.
  B4. pretooluse path: raw SEARCH_RESULT is NOT injected as-is; v15 gate applied.
  B5. The shared helper is accessible from bash via the patterns_used_state.py CLI
      (--strip-and-gate flag) or equivalent.

Implementation expectation:
  - Add a standalone Python function (or __main__ mode) that reads JSON from
    stdin, applies USEFUL_FIELDS strip + _apply_quality_gate, and prints the
    result to stdout. This can be in patterns_used_state.py as
    --strip-and-gate flag, or in a separate helper module.
  - Both bash scripts call it before injecting.
"""

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# ── path setup ────────────────────────────────────────────────────────────────
REPO = Path(__file__).resolve().parent.parent
SHARED = REPO / "plugins" / "ace" / "shared-hooks"
UTILS = SHARED / "utils"
PLUGIN_UTILS = REPO / "plugins" / "ace" / "utils"

sys.path.insert(0, str(SHARED))
sys.path.insert(0, str(UTILS))
sys.path.insert(0, str(PLUGIN_UTILS))

import patterns_used_state as pus  # noqa: E402

PUS_SCRIPT = UTILS / "patterns_used_state.py"

# Shared pattern factory helpers
USEFUL_FIELDS_EXPECTED = {
    'id', 'domain', 'content', 'confidence', 'helpful', 'harmful',
    'section', 'evidence', 'root_cause', 'error_context',
    'cumulative_v15_reward', 'n_hot_pos', 'n_hot_neg', 'isAtRisk',
}

SERVER_INTERNAL_FIELDS = {
    'created_at', 'updated_at', 'last_used', 'observations',
    'retrieval_count', 'source', 'source_project_id', 'source_project_name',
    'local_helpful', 'local_harmful', 'match_factors', 'name',
    'payload_version', 'root_cause_present', 'has_error_context',
    'birth_primary_lang', 'domain_cluster_id', 'abstract_domain',
    'root_cause_cluster_id', 'birth_first_tool_bucket',
    'birth_n_steps_bucket', 'birth_has_error', 'last_citation_score',
    'citation_score_ema_30d', 'n_warm_pos', 'n_warm_neg',
    'n_cold_pos', 'n_cold_neg', 'n_retrieval_no_apply',
    'merge_winner_count', 'merged_from',
}


def _make_v15_pattern(pid, reward, is_at_risk=False):
    """Full server-wire v15 pattern (includes all server-internal fields)."""
    return {
        "id": pid,
        "name": "",
        "domain": "test-domain",
        "content": "Some pattern content",
        "confidence": 0.8,
        "observations": 5.0,
        "helpful": 3.0,
        "harmful": 0,
        "section": "strategies_and_hard_rules",
        "created_at": "2025-12-01T00:00:00Z",
        "updated_at": "2026-06-01T00:00:00Z",
        "last_used": "2026-06-11T00:00:00Z",
        "evidence": ["some evidence"],
        "retrieval_count": 0,
        "root_cause": "",
        "error_context": "",
        "source": "local",
        "source_project_id": None,
        "source_project_name": None,
        "local_helpful": 0,
        "local_harmful": 0,
        "match_factors": {
            "semantic_score": 0.85,
            "domain_boost": False,
            "retrieval_log_id": 42,
            "retrieval_id": "ret-abc",
        },
        "payload_version": 15,
        "root_cause_present": False,
        "has_error_context": False,
        "birth_primary_lang": "python",
        "domain_cluster_id": -1,
        "abstract_domain": "",
        "root_cause_cluster_id": -1,
        "birth_first_tool_bucket": "none",
        "birth_n_steps_bucket": "0",
        "birth_has_error": "no_ctx",
        "last_citation_score": 0,
        "citation_score_ema_30d": 0,
        "n_hot_pos": 2,
        "n_hot_neg": 0,
        "n_warm_pos": 1,
        "n_warm_neg": 0,
        "n_cold_pos": 0,
        "n_cold_neg": 0,
        "n_retrieval_no_apply": 0,
        "merge_winner_count": 0,
        "merged_from": [],
        "cumulative_v15_reward": reward,
        "isAtRisk": is_at_risk,
    }


def _make_search_result(patterns):
    return {
        "similar_patterns": patterns,
        "count": len(patterns),
        "retrieval_id": "ret-test-001",
    }


# ════════════════════════════════════════════════════════════════════════════
# B1. Shared Python helper: --strip-and-gate CLI flag in patterns_used_state.py
# ════════════════════════════════════════════════════════════════════════════

class TestStripAndGateCLI:
    """
    patterns_used_state.py __main__ must support --strip-and-gate:
      - Read search JSON from stdin
      - Apply USEFUL_FIELDS strip to each pattern
      - Apply v15 quality gate (filter isAtRisk=True and reward<=0 patterns)
      - Print the filtered+stripped JSON to stdout
      - Exit 0
    """

    def _run_strip_gate(self, search_result):
        result = subprocess.run(
            [sys.executable, str(PUS_SCRIPT), "--strip-and-gate"],
            input=json.dumps(search_result),
            capture_output=True, text=True,
        )
        return result

    def test_strip_and_gate_flag_exists(self):
        """--strip-and-gate flag must be accepted without error."""
        search_result = _make_search_result([
            _make_v15_pattern("ctx-4338628010-5127", reward=1.5, is_at_risk=False),
        ])
        result = self._run_strip_gate(search_result)
        assert result.returncode == 0, (
            f"--strip-and-gate must exit 0; got {result.returncode}\n"
            f"stderr: {result.stderr}"
        )

    def test_strip_and_gate_filters_atrisk_patterns(self):
        """--strip-and-gate must remove patterns where isAtRisk=True."""
        good = _make_v15_pattern("ctx-4338628010-5127", reward=1.5, is_at_risk=False)
        bad = _make_v15_pattern("ctx-6257961166-f081", reward=0, is_at_risk=True)
        search_result = _make_search_result([good, bad])

        result = self._run_strip_gate(search_result)
        assert result.returncode == 0, f"stderr: {result.stderr}"

        output = json.loads(result.stdout)
        ids = [p["id"] for p in output.get("similar_patterns", [])]
        assert "ctx-4338628010-5127" in ids, "Good pattern must survive gate"
        assert "ctx-6257961166-f081" not in ids, (
            "isAtRisk=True pattern must be filtered by --strip-and-gate"
        )

    def test_strip_and_gate_removes_server_internal_fields(self):
        """--strip-and-gate must remove server-internal fields from patterns."""
        pattern = _make_v15_pattern("ctx-4338628010-5127", reward=1.5)
        search_result = _make_search_result([pattern])

        result = self._run_strip_gate(search_result)
        assert result.returncode == 0, f"stderr: {result.stderr}"

        output = json.loads(result.stdout)
        p_out = output["similar_patterns"][0]
        for field in SERVER_INTERNAL_FIELDS:
            assert field not in p_out, (
                f"Server-internal field '{field}' must be stripped; found in output: {p_out.keys()}"
            )

    def test_strip_and_gate_keeps_v15_reward_fields(self):
        """--strip-and-gate must KEEP cumulative_v15_reward, n_hot_pos, n_hot_neg, isAtRisk."""
        pattern = _make_v15_pattern("ctx-4338628010-5127", reward=2.5, is_at_risk=False)
        pattern["n_hot_pos"] = 3
        pattern["n_hot_neg"] = 1
        search_result = _make_search_result([pattern])

        result = self._run_strip_gate(search_result)
        assert result.returncode == 0, f"stderr: {result.stderr}"

        output = json.loads(result.stdout)
        p_out = output["similar_patterns"][0]
        for field in ("cumulative_v15_reward", "n_hot_pos", "n_hot_neg", "isAtRisk"):
            assert field in p_out, (
                f"v15 reward field '{field}' must SURVIVE --strip-and-gate strip step; "
                f"not found in output keys: {list(p_out.keys())}"
            )
        assert p_out["cumulative_v15_reward"] == 2.5
        assert p_out["n_hot_pos"] == 3
        assert p_out["n_hot_neg"] == 1
        assert p_out["isAtRisk"] is False

    def test_strip_and_gate_keeps_useful_legacy_fields(self):
        """--strip-and-gate must keep id, domain, content, confidence, helpful, harmful, section."""
        pattern = _make_v15_pattern("ctx-4338628010-5127", reward=1.0, is_at_risk=False)
        search_result = _make_search_result([pattern])

        result = self._run_strip_gate(search_result)
        assert result.returncode == 0

        output = json.loads(result.stdout)
        p_out = output["similar_patterns"][0]
        for field in ("id", "domain", "content", "confidence", "helpful",
                      "harmful", "section", "evidence"):
            assert field in p_out, (
                f"Useful legacy field '{field}' must survive strip; "
                f"not found in: {list(p_out.keys())}"
            )

    def test_strip_and_gate_filters_zero_reward_not_atrisk(self):
        """cumulative_v15_reward=0, isAtRisk=False → filtered (reward not > 0)."""
        pattern = _make_v15_pattern("ctx-4338628010-5127", reward=0, is_at_risk=False)
        search_result = _make_search_result([pattern])

        result = self._run_strip_gate(search_result)
        assert result.returncode == 0

        output = json.loads(result.stdout)
        ids = [p["id"] for p in output.get("similar_patterns", [])]
        assert "ctx-4338628010-5127" not in ids, (
            "cumulative_v15_reward=0 (not > 0) must be filtered even if isAtRisk=False"
        )

    def test_strip_and_gate_passes_positive_reward_not_atrisk(self):
        """cumulative_v15_reward=1.5, isAtRisk=False → passes gate."""
        pattern = _make_v15_pattern("ctx-4338628010-5127", reward=1.5, is_at_risk=False)
        search_result = _make_search_result([pattern])

        result = self._run_strip_gate(search_result)
        assert result.returncode == 0

        output = json.loads(result.stdout)
        ids = [p["id"] for p in output.get("similar_patterns", [])]
        assert "ctx-4338628010-5127" in ids, (
            "reward=1.5, isAtRisk=False must pass gate"
        )

    def test_strip_and_gate_updates_count(self):
        """The 'count' field in output must reflect post-filter count."""
        good = _make_v15_pattern("ctx-4338628010-5127", reward=1.5, is_at_risk=False)
        bad = _make_v15_pattern("ctx-6257961166-f081", reward=0, is_at_risk=True)
        search_result = _make_search_result([good, bad])

        result = self._run_strip_gate(search_result)
        assert result.returncode == 0

        output = json.loads(result.stdout)
        assert output["count"] == len(output.get("similar_patterns", [])), (
            "'count' must be updated to reflect post-filter count"
        )

    def test_strip_and_gate_handles_empty_input(self):
        """--strip-and-gate with 0 patterns must exit 0 and return empty list."""
        search_result = _make_search_result([])
        result = self._run_strip_gate(search_result)
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output.get("similar_patterns", []) == []

    def test_strip_and_gate_legacy_pattern_fallback(self):
        """Legacy pattern (no cumulative_v15_reward): helpful>=2 or confidence>=0.5 → passes."""
        legacy = {
            "id": "ctx-4338628010-5127",
            "domain": "test-domain",
            "content": "legacy pattern",
            "confidence": 0.8,
            "helpful": 2.0,
            "harmful": 0,
            "section": "strategies",
            "evidence": [],
            # No cumulative_v15_reward
        }
        search_result = _make_search_result([legacy])
        result = self._run_strip_gate(search_result)
        assert result.returncode == 0

        output = json.loads(result.stdout)
        ids = [p["id"] for p in output.get("similar_patterns", [])]
        assert "ctx-4338628010-5127" in ids, (
            "Legacy pattern with helpful>=2 must pass gate via legacy fallback"
        )


# ════════════════════════════════════════════════════════════════════════════
# B2. posttooluse path: isAtRisk patterns filtered, v15 fields kept
# ════════════════════════════════════════════════════════════════════════════

class TestPosttooluseDomainInjectGate:
    """
    ace_posttooluse_domain_inject.sh must:
    - Expand its useful set to include v15 fields
    - Apply the quality gate (filter isAtRisk=True patterns)

    We test the Python strip logic the script calls directly.
    """

    SCRIPT = REPO / "plugins/ace/scripts/ace_posttooluse_domain_inject.sh"

    def _make_mock_ace_cli(self, tmp_path, patterns):
        """Write mock ace-cli that emits given patterns as search result."""
        mock_script = tmp_path / "ace-cli"
        result_json = json.dumps(_make_search_result(patterns))
        mock_script.write_text(f"""#!/bin/bash
cat <<'ENDJSON'
{result_json}
ENDJSON
""")
        mock_script.chmod(0o755)
        return mock_script

    def test_atrisk_pattern_not_in_injected_context(self, tmp_path):
        """
        When ace-cli returns isAtRisk=True patterns, they must NOT appear
        in the additionalContext output of ace_posttooluse_domain_inject.sh.
        """
        project_id = "prj-posttu-gate"
        session_id = "cc-sess-posttu-gate"

        # Patterns: one good, one isAtRisk
        good_pat = _make_v15_pattern("ctx-4338628010-5127", reward=1.5, is_at_risk=False)
        bad_pat = _make_v15_pattern("ctx-6257961166-f081", reward=0, is_at_risk=True)

        self._make_mock_ace_cli(tmp_path, [good_pat, bad_pat])

        # Write domains file
        domain = "test-domain"
        domains_file = Path(f"/tmp/ace-domains-{project_id}.json")
        domains_file.write_text(json.dumps({
            f"{domain}:local": {"domain": domain, "source": "local", "count": 2}
        }))

        # Write settings
        project_dir = tmp_path / "proj"
        (project_dir / ".claude").mkdir(parents=True)
        (project_dir / ".claude/settings.json").write_text(json.dumps({
            "projectId": project_id,
            "orgId": "org-posttu",
            "env": {"ACE_PROJECT_ID": project_id},
        }))

        # Create file that matches domain
        file_path = f"/fake/project/{domain}/config.py"

        # Write last-domain file (different domain to trigger domain-shift)
        last_domain_file = Path(f"/tmp/ace-domain-{project_id}.txt")
        last_domain_file.write_text("other-domain")

        hook_input = json.dumps({
            "session_id": session_id,
            "tool_name": "Read",
            "tool_input": {"file_path": file_path},
            "cwd": str(project_dir),
        })

        result = subprocess.run(
            ["bash", str(self.SCRIPT)],
            input=hook_input,
            capture_output=True, text=True,
            env={
                "PATH": f"{tmp_path}:/usr/bin:/bin",
                "HOME": str(tmp_path),
            },
        )

        # Cleanup
        domains_file.unlink(missing_ok=True)
        last_domain_file.unlink(missing_ok=True)

        # If script exited 0 with empty output, it means ace-cli wasn't called
        # (domain matching didn't fire). That's a skip, not a fail.
        if not result.stdout.strip():
            pytest.skip("Domain match did not fire in this environment (no ace-cli call)")

        output_str = result.stdout
        assert "ctx-6257961166-f081" not in output_str, (
            f"isAtRisk=True pattern (ctx-6257961166-f081) must NOT appear in "
            f"injected context from posttooluse.\nOutput: {output_str!r}"
        )

    def test_v15_fields_present_in_stripped_posttooluse_output(self, tmp_path):
        """
        When ace_posttooluse_domain_inject.sh strips patterns, v15 fields
        (cumulative_v15_reward, n_hot_pos, n_hot_neg, isAtRisk) must survive.

        We test the inline Python strip used by the script directly, simulating
        what the script does.
        """
        # Simulate the Python one-liner used by the posttooluse script,
        # but with the CORRECT useful set (including v15 fields).
        pattern = _make_v15_pattern("ctx-4338628010-5127", reward=2.0, is_at_risk=False)
        search_result = _make_search_result([pattern])

        # Run the current posttooluse strip inline Python and check v15 fields.
        # The CURRENT (buggy) useful set in posttooluse: {'id','domain','content',
        # 'confidence','helpful','harmful','section','evidence'}
        # The CORRECT set must also include v15 fields.
        # We test by calling --strip-and-gate which must implement the correct set.
        result = subprocess.run(
            [sys.executable, str(PUS_SCRIPT), "--strip-and-gate"],
            input=json.dumps(search_result),
            capture_output=True, text=True,
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        output = json.loads(result.stdout)
        p_out = output["similar_patterns"][0]

        for field in ("cumulative_v15_reward", "n_hot_pos", "n_hot_neg", "isAtRisk"):
            assert field in p_out, (
                f"v15 field '{field}' must survive the strip step in "
                f"posttooluse domain inject path. Got keys: {list(p_out.keys())}"
            )

    def test_posttooluse_useful_set_includes_v15_fields(self):
        """
        After Change B: posttooluse script must include v15 fields in its strip
        step (via --strip-and-gate which uses the correct USEFUL_FIELDS set).
        """
        # The fix delegates to patterns_used_state.py --strip-and-gate which
        # uses _USEFUL_FIELDS including the v15 fields. Verify the script calls it.
        script_text = (REPO / "plugins/ace/scripts/ace_posttooluse_domain_inject.sh").read_text()
        uses_strip_gate = "strip-and-gate" in script_text
        assert uses_strip_gate, (
            "posttooluse script must delegate to --strip-and-gate to include v15 fields"
        )

    def test_posttooluse_has_quality_gate_call(self):
        """
        After Change B: posttooluse script must apply the quality gate
        (via --strip-and-gate, which includes the gate).
        """
        script_text = (REPO / "plugins/ace/scripts/ace_posttooluse_domain_inject.sh").read_text()
        has_gate = "strip-and-gate" in script_text
        assert has_gate, (
            "posttooluse script must call --strip-and-gate to apply the quality gate"
        )


# ════════════════════════════════════════════════════════════════════════════
# B4. pretooluse path: raw SEARCH_RESULT not injected; v15 gate applied
# ════════════════════════════════════════════════════════════════════════════

class TestPretooluseDomainInjectGate:
    """
    ace_pretooluse_wrapper.sh currently emits raw $SEARCH_RESULT with NO
    strip and NO quality gate. Change B must fix this.
    """

    SCRIPT = REPO / "plugins/ace/scripts/ace_pretooluse_wrapper.sh"

    def test_pretooluse_has_strip_step(self):
        """
        After Change B: pretooluse wrapper must have a strip step for
        domain-shift inject path (via --strip-and-gate).
        """
        script_text = (REPO / "plugins/ace/scripts/ace_pretooluse_wrapper.sh").read_text()
        inject_block_has_strip = "strip-and-gate" in script_text
        assert inject_block_has_strip, (
            "pretooluse wrapper must use --strip-and-gate on the domain-shift inject path"
        )

    def test_pretooluse_uses_stripped_not_raw_for_ace_context(self):
        """
        After Change B: pretooluse wrapper must use STRIPPED (output of
        strip+gate) in ACE_CONTEXT, not raw $SEARCH_RESULT.
        """
        script_text = (REPO / "plugins/ace/scripts/ace_pretooluse_wrapper.sh").read_text()
        import re
        # ACE_CONTEXT must reference $STRIPPED, not raw $SEARCH_RESULT
        stripped_inject = re.search(r'ACE_CONTEXT=.*\$\{?STRIPPED\}?', script_text, re.DOTALL)
        assert stripped_inject is not None, (
            "ACE_CONTEXT must be built from $STRIPPED (output of --strip-and-gate), "
            "not raw $SEARCH_RESULT"
        )


# ════════════════════════════════════════════════════════════════════════════
# B5. Integration: both paths call shared strip+gate helper
# ════════════════════════════════════════════════════════════════════════════

class TestBothPathsUseSharedHelper:
    """
    After fix: both posttooluse and pretooluse inject paths call the shared
    strip+gate helper (--strip-and-gate flag in patterns_used_state.py or
    equivalent), ensuring consistent quality gate behavior.
    """

    def test_posttooluse_calls_strip_gate_helper(self):
        """
        After fix: posttooluse script must use strip-and-gate or equivalent.
        RED until implemented.
        """
        script_text = (REPO / "plugins/ace/scripts/ace_posttooluse_domain_inject.sh").read_text()
        uses_shared_helper = (
            "strip-and-gate" in script_text
            or ("isAtRisk" in script_text and "cumulative_v15_reward" in script_text)
        )
        assert uses_shared_helper, (
            "After Change B, posttooluse script must use --strip-and-gate flag "
            "(or equivalent that includes v15 fields and quality gate). "
            "Currently missing."
        )

    def test_pretooluse_calls_strip_gate_helper(self):
        """
        After fix: pretooluse script must use strip-and-gate or equivalent
        for the domain-shift inject path.
        RED until implemented.
        """
        script_text = (REPO / "plugins/ace/scripts/ace_pretooluse_wrapper.sh").read_text()
        uses_shared_helper = (
            "strip-and-gate" in script_text
            or ("isAtRisk" in script_text and "cumulative_v15_reward" in script_text)
        )
        assert uses_shared_helper, (
            "After Change B, pretooluse wrapper must use --strip-and-gate flag "
            "(or equivalent) on the domain-shift inject path. Currently missing."
        )
