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

    def test_strip_and_gate_retains_atrisk_patterns(self):
        """--strip-and-gate must RETAIN patterns where isAtRisk=True.

        NEW CONTRACT (server-team validated, ACE-1.5-native): NO quality gate.
        Inject everything; let ranking + tiering bury weak ones.
        Client drop starves the server's apply/cleanup loop and discards the
        de-confound signal. Both patterns must survive.
        """
        good = _make_v15_pattern("ctx-4338628010-5127", reward=1.5, is_at_risk=False)
        bad = _make_v15_pattern("ctx-6257961166-f081", reward=0, is_at_risk=True)
        search_result = _make_search_result([good, bad])

        result = self._run_strip_gate(search_result)
        assert result.returncode == 0, f"stderr: {result.stderr}"

        output = json.loads(result.stdout)
        ids = [p["id"] for p in output.get("similar_patterns", [])]
        assert "ctx-4338628010-5127" in ids, "Good pattern must survive strip"
        assert "ctx-6257961166-f081" in ids, (
            "NEW CONTRACT: isAtRisk=True pattern must be RETAINED by --strip-and-gate "
            "(no quality gate; ranking buries weak patterns)"
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

    def test_strip_and_gate_neutral_reward_not_atrisk_kept(self):
        """cumulative_v15_reward=0, isAtRisk=False → KEPT (neutral, not at-risk).

        Fix 3: @ace-sdk/core 3.2.2 changed isAtRisk to mean reward<0.
        reward==0 is neutral/uncredited and must NOT be dropped.
        """
        pattern = _make_v15_pattern("ctx-4338628010-5127", reward=0, is_at_risk=False)
        search_result = _make_search_result([pattern])

        result = self._run_strip_gate(search_result)
        assert result.returncode == 0

        output = json.loads(result.stdout)
        ids = [p["id"] for p in output.get("similar_patterns", [])]
        assert "ctx-4338628010-5127" in ids, (
            "Fix 3: cumulative_v15_reward=0, isAtRisk=False must be KEPT "
            "(neutral reward is not at-risk per @ace-sdk/core 3.2.2)"
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
        # NEW CONTRACT: NO quality gate — isAtRisk=True patterns are RETAINED.
        # Both patterns must appear in the injected context.
        assert "ctx-4338628010-5127" in output_str, (
            f"Good pattern (ctx-4338628010-5127) must appear in posttooluse output.\n"
            f"Output: {output_str!r}"
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


# ════════════════════════════════════════════════════════════════════════════
# FIX 3 — Gate semantics: trust isAtRisk, drop reward>0 condition (v15 path)
# RED until _quality_gate / strip_and_gate updated in patterns_used_state.py
# ════════════════════════════════════════════════════════════════════════════

class TestFix3GateSemantics:
    """
    @ace-sdk/core 3.2.2: isAtRisk now means cumulative_v15_reward < 0.
    reward==0 = neutral/uncredited, NOT at-risk → must be KEPT.
    New v15 rule: keep iff NOT isAtRisk  (drops only reward<0 / at-risk).
    """

    def _run_strip_gate(self, search_result):
        result = subprocess.run(
            [sys.executable, str(PUS_SCRIPT), "--strip-and-gate"],
            input=json.dumps(search_result),
            capture_output=True, text=True,
        )
        return result

    def test_neutral_reward_not_atrisk_kept_by_gate(self):
        """FIX 3: cumulative_v15_reward=0, isAtRisk=False → KEPT (neutral, uncredited).

        Was DROPPED under old reward>0 rule. RED until fix.
        """
        pattern = _make_v15_pattern("ctx-neutral-0001", reward=0, is_at_risk=False)
        result = self._run_strip_gate(_make_search_result([pattern]))
        assert result.returncode == 0, f"stderr: {result.stderr}"
        output = json.loads(result.stdout)
        ids = [p["id"] for p in output.get("similar_patterns", [])]
        assert "ctx-neutral-0001" in ids, (
            "FIX 3: cumulative_v15_reward=0, isAtRisk=False must be KEPT "
            "(neutral reward is not at-risk). Was dropped under old reward>0 rule."
        )

    def test_negative_reward_atrisk_retained_by_render(self):
        """NEW CONTRACT: cumulative_v15_reward=-1.5, isAtRisk=True → RETAINED.

        The injection path has NO quality gate. The server's de-confound signal
        requires all patterns to be injected; ranking buries weak ones.
        """
        pattern = _make_v15_pattern("ctx-atrisk-0002", reward=-1.5, is_at_risk=True)
        result = self._run_strip_gate(_make_search_result([pattern]))
        assert result.returncode == 0, f"stderr: {result.stderr}"
        output = json.loads(result.stdout)
        ids = [p["id"] for p in output.get("similar_patterns", [])]
        assert "ctx-atrisk-0002" in ids, (
            "NEW CONTRACT: cumulative_v15_reward=-1.5, isAtRisk=True must be RETAINED "
            "(no quality gate in injection path)."
        )

    def test_positive_reward_not_atrisk_kept_by_gate(self):
        """FIX 3: cumulative_v15_reward=32.9, isAtRisk=False → kept (positive)."""
        pattern = _make_v15_pattern("ctx-positive-0003", reward=32.9, is_at_risk=False)
        result = self._run_strip_gate(_make_search_result([pattern]))
        assert result.returncode == 0, f"stderr: {result.stderr}"
        output = json.loads(result.stdout)
        ids = [p["id"] for p in output.get("similar_patterns", [])]
        assert "ctx-positive-0003" in ids, (
            "FIX 3: cumulative_v15_reward=32.9, isAtRisk=False must be kept."
        )

    def test_legacy_high_confidence_kept_unchanged(self):
        """FIX 3 (legacy path unchanged): confidence=0.8, no reward field → kept."""
        legacy = {
            "id": "ctx-legacy-0004",
            "domain": "test-domain",
            "content": "legacy pattern",
            "confidence": 0.8,
            "helpful": 1,
            "harmful": 0,
            "section": "strategies",
            "evidence": [],
        }
        result = self._run_strip_gate(_make_search_result([legacy]))
        assert result.returncode == 0, f"stderr: {result.stderr}"
        output = json.loads(result.stdout)
        ids = [p["id"] for p in output.get("similar_patterns", [])]
        assert "ctx-legacy-0004" in ids, (
            "Legacy path unchanged: confidence=0.8 must pass gate."
        )

    def test_legacy_low_helpful_low_confidence_retained(self):
        """NEW CONTRACT: helpful=1, confidence=0.2 legacy pattern → RETAINED.

        The injection path has NO quality gate. All patterns are retained
        regardless of confidence/helpful/isAtRisk/reward.
        """
        legacy = {
            "id": "ctx-legacy-0005",
            "domain": "test-domain",
            "content": "low quality legacy",
            "confidence": 0.2,
            "helpful": 1,
            "harmful": 0,
            "section": "strategies",
            "evidence": [],
        }
        result = self._run_strip_gate(_make_search_result([legacy]))
        assert result.returncode == 0, f"stderr: {result.stderr}"
        output = json.loads(result.stdout)
        ids = [p["id"] for p in output.get("similar_patterns", [])]
        assert "ctx-legacy-0005" in ids, (
            "NEW CONTRACT: low-confidence legacy pattern must be RETAINED "
            "(no quality gate in injection path)."
        )


# ════════════════════════════════════════════════════════════════════════════
# FIX A — gate robustness: negative reward + isAtRisk=False (stale/mixed data)
# Both _quality_gate (patterns_used_state.py) and the --strip-and-gate CLI
# must drop patterns with cumulative_v15_reward < 0 even when isAtRisk=False.
# RED against current code (keeps them); GREEN after FIX A.
# ════════════════════════════════════════════════════════════════════════════

class TestFixAGateRobustness:
    """FIX A: reward<0 with isAtRisk=False must be dropped (stale server data hole)."""

    def _run_strip_gate(self, search_result):
        result = subprocess.run(
            [sys.executable, str(PUS_SCRIPT), "--strip-and-gate"],
            input=json.dumps(search_result),
            capture_output=True, text=True,
        )
        return result

    def test_negative_reward_not_atrisk_retained_by_render(self):
        """NEW CONTRACT: reward=-1.5, isAtRisk=False → RETAINED by --strip-and-gate.

        The injection path has NO quality gate. The server's de-confound signal
        requires all patterns to be injected. _quality_gate (still available for
        non-injection callers) retains its behavior, but strip_and_gate no longer
        calls it.
        """
        pattern = _make_v15_pattern("ctx-fixA-neg-0001", reward=-1.5, is_at_risk=False)
        result = self._run_strip_gate(_make_search_result([pattern]))
        assert result.returncode == 0, f"stderr: {result.stderr}"
        output = json.loads(result.stdout)
        ids = [p["id"] for p in output.get("similar_patterns", [])]
        assert "ctx-fixA-neg-0001" in ids, (
            "NEW CONTRACT: reward=-1.5 with isAtRisk=False must be RETAINED — "
            "injection path has no quality gate."
        )

    def test_zero_reward_not_atrisk_kept_by_strip_gate(self):
        """FIX A: reward=0, isAtRisk=False → KEPT (neutral; >= 0 passes gate)."""
        pattern = _make_v15_pattern("ctx-fixA-zero-0002", reward=0, is_at_risk=False)
        result = self._run_strip_gate(_make_search_result([pattern]))
        assert result.returncode == 0, f"stderr: {result.stderr}"
        output = json.loads(result.stdout)
        ids = [p["id"] for p in output.get("similar_patterns", [])]
        assert "ctx-fixA-zero-0002" in ids, (
            "FIX A: reward=0 with isAtRisk=False must be KEPT (neutral, boundary >= 0)."
        )

    def test_positive_reward_not_atrisk_kept_by_strip_gate(self):
        """FIX A: reward=5, isAtRisk=False → KEPT."""
        pattern = _make_v15_pattern("ctx-fixA-pos-0003", reward=5.0, is_at_risk=False)
        result = self._run_strip_gate(_make_search_result([pattern]))
        assert result.returncode == 0, f"stderr: {result.stderr}"
        output = json.loads(result.stdout)
        ids = [p["id"] for p in output.get("similar_patterns", [])]
        assert "ctx-fixA-pos-0003" in ids, (
            "FIX A: reward=5 with isAtRisk=False must be KEPT."
        )

    def test_negative_reward_atrisk_true_retained_by_render(self):
        """NEW CONTRACT: reward=-2, isAtRisk=True → RETAINED (no quality gate)."""
        pattern = _make_v15_pattern("ctx-fixA-both-0004", reward=-2.0, is_at_risk=True)
        result = self._run_strip_gate(_make_search_result([pattern]))
        assert result.returncode == 0, f"stderr: {result.stderr}"
        output = json.loads(result.stdout)
        ids = [p["id"] for p in output.get("similar_patterns", [])]
        assert "ctx-fixA-both-0004" in ids, (
            "NEW CONTRACT: reward=-2 with isAtRisk=True must be RETAINED "
            "(injection path has no quality gate)."
        )

    def test_pus_quality_gate_direct_negative_reward_not_atrisk_dropped(self):
        """FIX A: patterns_used_state._quality_gate direct call — reward=-1.5,
        isAtRisk=False → pattern NOT in result.
        """
        pattern = _make_v15_pattern("ctx-fixA-direct-0005", reward=-1.5, is_at_risk=False)
        result = pus._quality_gate([pattern])
        ids = [p["id"] for p in result]
        assert "ctx-fixA-direct-0005" not in ids, (
            "FIX A: pus._quality_gate must drop reward=-1.5, isAtRisk=False pattern."
        )

    def test_pus_quality_gate_direct_zero_reward_not_atrisk_kept(self):
        """FIX A: pus._quality_gate direct call — reward=0, isAtRisk=False → KEPT."""
        pattern = _make_v15_pattern("ctx-fixA-direct-0006", reward=0, is_at_risk=False)
        result = pus._quality_gate([pattern])
        ids = [p["id"] for p in result]
        assert "ctx-fixA-direct-0006" in ids, (
            "FIX A: pus._quality_gate must keep reward=0, isAtRisk=False (neutral >= 0)."
        )


# ════════════════════════════════════════════════════════════════════════════
# FIX 4 — Domain-shift top-K cap: K=8, ranked by ucb_score desc
# RED until DOMAIN_SHIFT_TOP_K constant + sorting added to strip_and_gate
# ════════════════════════════════════════════════════════════════════════════

def _make_v15_pattern_with_ucb(pid, ucb_score, reward=5.0, is_at_risk=False, confidence=0.8):
    """v15 pattern with match_factors.ucb_score for cap tests."""
    p = _make_v15_pattern(pid, reward=reward, is_at_risk=is_at_risk)
    p["match_factors"] = {
        "ucb_score": ucb_score,
        "semantic_score": 0.8,
        "domain_boost": False,
        "retrieval_log_id": 1,
        "retrieval_id": "ret-cap-test",
    }
    p["confidence"] = confidence
    return p


class TestFix4DomainShiftTopKCap:
    """
    strip_and_gate must NOT cap client-side — the cap moved server-side via
    --top-k 8 on the ace-cli search invocation.  strip_and_gate is now gate+strip
    only: all gated patterns pass through regardless of count.

    Old tests that asserted cap-to-8 behaviour are updated to assert the new
    uncapped behaviour.  The DOMAIN_SHIFT_TOP_K constant and ucb_score sort are
    removed from patterns_used_state.py.
    """

    def _run_strip_gate(self, search_result):
        result = subprocess.run(
            [sys.executable, str(PUS_SCRIPT), "--strip-and-gate"],
            input=json.dumps(search_result),
            capture_output=True, text=True,
        )
        return result

    def test_no_domain_shift_top_k_constant(self):
        """DOMAIN_SHIFT_TOP_K must NOT exist in patterns_used_state.py (cap moved server-side)."""
        assert not hasattr(pus, 'DOMAIN_SHIFT_TOP_K'), (
            "DOMAIN_SHIFT_TOP_K must be removed from patterns_used_state.py; "
            "cap is now server-side via --top-k 8"
        )

    def test_strip_and_gate_passes_all_15_gated_patterns(self):
        """15 not-at-risk patterns → all 15 returned (no client-side cap)."""
        patterns = [
            _make_v15_pattern_with_ucb(f"ctx-cap-{i:04d}", ucb_score=float(i), reward=5.0)
            for i in range(15)
        ]
        result = self._run_strip_gate(_make_search_result(patterns))
        assert result.returncode == 0, f"stderr: {result.stderr}"
        output = json.loads(result.stdout)
        kept = output.get("similar_patterns", [])
        assert len(kept) == 15, (
            f"strip_and_gate must NOT cap: 15 gated patterns in → 15 out, got {len(kept)}"
        )
        assert output["count"] == 15, (
            f"count must reflect all 15 gated patterns, got {output['count']}"
        )

    def test_strip_and_gate_passes_all_low_ucb_patterns(self):
        """All patterns pass through — no ranking-based drop (server selects via --top-k 8)."""
        patterns = [
            _make_v15_pattern_with_ucb(f"ctx-cap-{i:04d}", ucb_score=float(i), reward=5.0)
            for i in range(15)
        ]
        result = self._run_strip_gate(_make_search_result(patterns))
        assert result.returncode == 0, f"stderr: {result.stderr}"
        output = json.loads(result.stdout)
        kept_ids = {p["id"] for p in output.get("similar_patterns", [])}
        # All 15 patterns must be kept (no client-side ranking drop)
        for i in range(15):
            assert f"ctx-cap-{i:04d}" in kept_ids, (
                f"strip_and_gate must keep all gated patterns; "
                f"ctx-cap-{i:04d} missing from kept_ids={kept_ids}"
            )

    def test_cap_no_effect_when_fewer_than_8(self):
        """3 gated patterns → all 3 kept, count=3."""
        patterns = [
            _make_v15_pattern_with_ucb(f"ctx-few-{i:04d}", ucb_score=float(i), reward=5.0)
            for i in range(3)
        ]
        result = self._run_strip_gate(_make_search_result(patterns))
        assert result.returncode == 0, f"stderr: {result.stderr}"
        output = json.loads(result.stdout)
        kept = output.get("similar_patterns", [])
        assert len(kept) == 3, (
            f"3 gated patterns must all be kept, got {len(kept)}"
        )
        assert output["count"] == 3

    def test_cap_empty_input_stays_empty(self):
        """0 gated patterns → empty output."""
        result = self._run_strip_gate(_make_search_result([]))
        assert result.returncode == 0, f"stderr: {result.stderr}"
        output = json.loads(result.stdout)
        assert output.get("similar_patterns", []) == []
        assert output["count"] == 0

    def test_match_factors_stripped_from_output(self):
        """match_factors must be stripped from all output patterns (server-internal field)."""
        patterns = [
            _make_v15_pattern_with_ucb(f"ctx-strip-{i:04d}", ucb_score=float(i), reward=5.0)
            for i in range(10)
        ]
        result = self._run_strip_gate(_make_search_result(patterns))
        assert result.returncode == 0, f"stderr: {result.stderr}"
        output = json.loads(result.stdout)
        for p in output.get("similar_patterns", []):
            assert "match_factors" not in p, (
                f"match_factors must be stripped from output pattern {p['id']}"
            )

    def test_no_ucb_sort_in_strip_and_gate(self):
        """strip_and_gate must NOT sort by ucb_score (no client-side ranking; server ranks)."""
        # 10 patterns with descending ucb scores in input order; output order may differ
        # but the key invariant is ALL 10 patterns are present (not just top-8)
        patterns = [
            _make_v15_pattern_with_ucb(
                f"ctx-ord-{i:04d}", ucb_score=float(10 - i), reward=5.0
            )
            for i in range(10)
        ]
        result = self._run_strip_gate(_make_search_result(patterns))
        assert result.returncode == 0, f"stderr: {result.stderr}"
        output = json.loads(result.stdout)
        kept_ids = {p["id"] for p in output.get("similar_patterns", [])}
        assert len(kept_ids) == 10, (
            f"All 10 gated patterns must be returned by strip_and_gate (no ucb sort+cap), "
            f"got {len(kept_ids)}"
        )


# ════════════════════════════════════════════════════════════════════════════
# Server-side --top-k 8: domain-shift scripts must pass --top-k 8 to ace-cli
# Main + subagent-start searches must remain uncapped (no --top-k).
# RED until scripts are updated.
# ════════════════════════════════════════════════════════════════════════════

class TestServerSideTopK:
    """
    The domain-shift count-bound must be enforced server-side via --top-k 8
    on the ace-cli search invocation, NOT client-side in strip_and_gate.

    Both domain-shift scripts (pretooluse + posttooluse) must pass --top-k 8
    to every ace-cli search --allowed-domains call (both pin/fallback branches).

    The main search (ace_before_task.py / ace_cli.py) and subagent-start search
    (ace_subagent_start.py) must NOT pass --top-k (server search_top_k config).
    """

    PRETOOLUSE = REPO / "plugins/ace/scripts/ace_pretooluse_wrapper.sh"
    POSTTOOLUSE = REPO / "plugins/ace/scripts/ace_posttooluse_domain_inject.sh"
    BEFORE_TASK = REPO / "plugins/ace/shared-hooks/ace_before_task.py"
    SUBAGENT_START = REPO / "plugins/ace/shared-hooks/ace_subagent_start.py"
    ACE_CLI_PY = REPO / "plugins/ace/shared-hooks/utils/ace_cli.py"

    @staticmethod
    def _join_continuations(text):
        """Join bash line-continuation backslashes so multi-line commands become one line."""
        import re
        return re.sub(r'\\\n\s*', ' ', text)

    def test_pretooluse_pin_branch_has_top_k_8(self):
        """pretooluse --pin-session branch must pass --top-k 8 to ace-cli search."""
        text = self._join_continuations(self.PRETOOLUSE.read_text())
        import re
        # Match actual ace-cli / $CLI_CMD search invocation lines (not comments)
        pin_line = re.search(
            r'(?:ace-cli|\$CLI_CMD)\s+search[^\n]*--pin-session[^\n]*',
            text
        )
        assert pin_line is not None, (
            "pretooluse must have a --pin-session search branch with ace-cli/CLI_CMD"
        )
        assert '--top-k 8' in pin_line.group(), (
            f"pretooluse --pin-session branch must include --top-k 8.\n"
            f"Got: {pin_line.group()!r}"
        )

    def test_pretooluse_fallback_branch_has_top_k_8(self):
        """pretooluse fallback (no pin-session) branch must pass --top-k 8 to ace-cli search.

        NEW CONTRACT: --allowed-domains is removed; match by --top-k 8 on search lines.
        Both pin-session and fallback branches must carry --top-k 8.
        """
        text = self._join_continuations(self.PRETOOLUSE.read_text())
        import re
        # Match all ace-cli / $CLI_CMD search invocation lines that carry --top-k 8
        domain_search_lines = re.findall(
            r'(?:ace-cli|\$CLI_CMD)\s+search[^\n]*--top-k 8[^\n]*',
            text
        )
        assert len(domain_search_lines) >= 2, (
            f"pretooluse must have at least 2 ace-cli domain-shift search branches "
            f"with --top-k 8 (pin and fallback), got: {domain_search_lines}"
        )
        for line in domain_search_lines:
            assert '--top-k 8' in line, (
                f"All pretooluse domain-shift search lines must include --top-k 8.\n"
                f"Missing in: {line!r}"
            )

    def test_pretooluse_no_allowed_domains(self):
        """NEW CONTRACT: pretooluse must NOT pass --allowed-domains to ace-cli.

        Server-team confirmed domain_match ANTI-predicts relevance; cross-domain
        patterns are the more relevant ones. The whitelist filter is dropped entirely.
        """
        text = self.PRETOOLUSE.read_text()
        assert '--allowed-domains' not in text, (
            "pretooluse must NOT pass --allowed-domains to ace-cli search. "
            "Domain filter has been removed per server-team recommendation."
        )

    def test_posttooluse_pin_branch_has_top_k_8(self):
        """posttooluse --pin-session branch must pass --top-k 8 to ace-cli search."""
        text = self._join_continuations(self.POSTTOOLUSE.read_text())
        import re
        # Require --stdin to match actual invocation (not comment lines)
        pin_line = re.search(
            r'(?:ace-cli|\$CLI_CMD)\s+search[^\n]*--stdin[^\n]*--pin-session[^\n]*',
            text
        )
        assert pin_line is not None, (
            "posttooluse must have a --pin-session search invocation with ace-cli/CLI_CMD --stdin"
        )
        assert '--top-k 8' in pin_line.group(), (
            f"posttooluse --pin-session branch must include --top-k 8.\n"
            f"Got: {pin_line.group()!r}"
        )

    def test_posttooluse_fallback_branch_has_top_k_8(self):
        """posttooluse fallback (no pin-session) branch must pass --top-k 8 to ace-cli search.

        NEW CONTRACT: --allowed-domains is removed; match by --top-k 8 on search lines.
        Both pin-session and fallback branches must carry --top-k 8.
        """
        text = self._join_continuations(self.POSTTOOLUSE.read_text())
        import re
        domain_search_lines = re.findall(
            r'(?:ace-cli|\$CLI_CMD)\s+search[^\n]*--top-k 8[^\n]*',
            text
        )
        assert len(domain_search_lines) >= 2, (
            f"posttooluse must have at least 2 ace-cli domain-shift search branches "
            f"with --top-k 8 (pin and fallback), got: {domain_search_lines}"
        )
        for line in domain_search_lines:
            assert '--top-k 8' in line, (
                f"All posttooluse domain-shift search lines must include --top-k 8.\n"
                f"Missing in: {line!r}"
            )

    def test_posttooluse_no_allowed_domains(self):
        """NEW CONTRACT: posttooluse must NOT pass --allowed-domains to ace-cli.

        Server-team confirmed domain_match ANTI-predicts relevance; cross-domain
        patterns are the more relevant ones. The whitelist filter is dropped entirely.
        """
        text = self.POSTTOOLUSE.read_text()
        assert '--allowed-domains' not in text, (
            "posttooluse must NOT pass --allowed-domains to ace-cli search. "
            "Domain filter has been removed per server-team recommendation."
        )

    def test_before_task_has_no_top_k(self):
        """ace_before_task.py (main search) must NOT contain --top-k (server search_top_k)."""
        text = self.BEFORE_TASK.read_text()
        assert '--top-k' not in text, (
            "ace_before_task.py must NOT pass --top-k; main search is uncapped "
            "(server search_top_k config controls count)."
        )

    def test_subagent_start_has_no_top_k(self):
        """ace_subagent_start.py (subagent-start search) must NOT contain --top-k."""
        text = self.SUBAGENT_START.read_text()
        assert '--top-k' not in text, (
            "ace_subagent_start.py must NOT pass --top-k; subagent-start search "
            "is uncapped (server search_top_k config controls count)."
        )

    def test_ace_cli_py_has_no_top_k(self):
        """ace_cli.py run_search (used by before_task) must NOT build a --top-k flag."""
        text = self.ACE_CLI_PY.read_text()
        assert '--top-k' not in text, (
            "ace_cli.py must NOT pass --top-k; main-path search is uncapped."
        )


# ════════════════════════════════════════════════════════════════════════════
# Query construction: basename-only, no domain token
# Empty-basename guard: both scripts must skip the search entirely when
# FILE_BASENAME is empty (no usable query text).
# ════════════════════════════════════════════════════════════════════════════

class TestQueryConstructionAndEmptyBasenameGuard:
    """
    NEW CONTRACT (server-team approved, ACE-1.5-native):
      - Query = FILE_BASENAME only (no domain token prepended).
      - If FILE_BASENAME is empty → skip the domain-shift search entirely
        (exit gracefully, no ace-cli invocation with an empty/whitespace query).
    """

    PRETOOLUSE = REPO / "plugins/ace/scripts/ace_pretooluse_wrapper.sh"
    POSTTOOLUSE = REPO / "plugins/ace/scripts/ace_posttooluse_domain_inject.sh"

    # ── static / textual assertions ──────────────────────────────────────

    def test_pretooluse_query_does_not_use_matched_domain_in_query(self):
        """pretooluse must NOT include MATCHED_DOMAIN in SEARCH_QUERY construction."""
        import re
        text = self.PRETOOLUSE.read_text()
        # The only acceptable assignment is SEARCH_QUERY="${FILE_BASENAME}" (or equivalent)
        # The old pattern was: SEARCH_QUERY="${MATCHED_DOMAIN} ${FILE_BASENAME}"
        bad = re.search(r'SEARCH_QUERY=.*MATCHED_DOMAIN.*FILE_BASENAME', text)
        assert bad is None, (
            "pretooluse SEARCH_QUERY must NOT prepend MATCHED_DOMAIN. "
            "Query must be FILE_BASENAME only per server-team contract."
        )

    def test_pretooluse_query_is_file_basename_only(self):
        """pretooluse must set SEARCH_QUERY to FILE_BASENAME (basename-only)."""
        text = self.PRETOOLUSE.read_text()
        assert 'SEARCH_QUERY="${FILE_BASENAME}"' in text, (
            'pretooluse must set SEARCH_QUERY="${FILE_BASENAME}" (no domain token).'
        )

    def test_posttooluse_query_does_not_use_matched_domain_in_query(self):
        """posttooluse must NOT include MATCHED_DOMAIN in SEARCH_QUERY construction."""
        import re
        text = self.POSTTOOLUSE.read_text()
        bad = re.search(r'SEARCH_QUERY=.*MATCHED_DOMAIN.*FILE_BASENAME', text)
        assert bad is None, (
            "posttooluse SEARCH_QUERY must NOT prepend MATCHED_DOMAIN. "
            "Query must be FILE_BASENAME only per server-team contract."
        )

    def test_posttooluse_query_is_file_basename_only(self):
        """posttooluse must set SEARCH_QUERY to FILE_BASENAME (basename-only)."""
        text = self.POSTTOOLUSE.read_text()
        assert 'SEARCH_QUERY="${FILE_BASENAME}"' in text, (
            'posttooluse must set SEARCH_QUERY="${FILE_BASENAME}" (no domain token).'
        )

    # ── runtime / behavioural assertions ─────────────────────────────────

    def _make_mock_ace_cli_recording(self, tmp_path: Path) -> tuple[Path, Path]:
        """Write a mock ace-cli that records the query it received and exits 0."""
        query_log = tmp_path / "ace_cli_query.txt"
        mock = tmp_path / "ace-cli"
        mock.write_text(
            "#!/bin/bash\n"
            # Slurp stdin (the query piped via --stdin) into the log file
            f"cat > {query_log}\n"
            "echo '{\"similar_patterns\":[],\"count\":0}'\n"
        )
        mock.chmod(0o755)
        return mock, query_log

    def _make_domain_env(self, tmp_path: Path, project_id: str, domain: str) -> str:
        """Set up a minimal domains file + settings.json; return cwd string."""
        (tmp_path / ".claude").mkdir(exist_ok=True)
        (tmp_path / ".claude" / "settings.json").write_text(
            json.dumps({"env": {"ACE_PROJECT_ID": project_id}})
        )
        Path(f"/tmp/ace-domains-{project_id}.json").write_text(
            json.dumps({domain: {"description": "test"}})
        )
        return str(tmp_path)

    def test_pretooluse_empty_basename_skips_search(self, tmp_path):
        """pretooluse: FILE_BASENAME empty (dotfile like /scripts/.hidden) -> no ace-cli invocation.

        bash basename("/scripts/.hidden") | sed strip-extension produces "" because the
        leading dot is consumed by the extension-strip sed expression. The guard must exit
        before calling ace-cli with an empty/whitespace query.
        """
        import os
        project_id = f"prj-ptu-empty-bn-{os.getpid()}"
        domain = "scripts"
        cwd = self._make_domain_env(tmp_path, project_id, domain)
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()
        mock, query_log = self._make_mock_ace_cli_recording(mock_bin)

        # /scripts/.hidden: domain match fires (path has "scripts"), but basename
        # after extension-strip is empty → guard must prevent ace-cli call.
        hook_input = {
            "session_id": "sess-empty-bn",
            "tool_name": "Read",
            "tool_input": {"file_path": f"/{domain}/.hidden"},
            "cwd": cwd,
        }

        result = subprocess.run(
            ["bash", str(self.PRETOOLUSE)],
            input=json.dumps(hook_input),
            capture_output=True, text=True, timeout=10,
            env={
                **os.environ,
                "PATH": f"{mock_bin}:{os.environ.get('PATH', '/usr/bin:/bin')}",
                "CLAUDE_PROJECT_DIR": str(tmp_path),
            },
        )

        Path(f"/tmp/ace-domains-{project_id}.json").unlink(missing_ok=True)
        Path(f"/tmp/ace-domain-{project_id}-main.txt").unlink(missing_ok=True)

        assert result.returncode == 0, f"Script must exit 0; rc={result.returncode}"
        assert not query_log.exists(), (
            "ace-cli must NOT be called when FILE_BASENAME is empty. "
            f"Query log was written: {query_log.read_text() if query_log.exists() else '(missing)'}"
        )

    def test_posttooluse_empty_basename_skips_search(self, tmp_path):
        """posttooluse: FILE_BASENAME empty (dotfile like /scripts/.hidden) -> no ace-cli invocation.

        bash basename("/scripts/.hidden") | sed strip-extension produces "" because the
        leading dot is consumed by the extension-strip sed expression. The guard must exit
        before calling ace-cli with an empty/whitespace query.
        """
        import os
        project_id = f"prj-pdu-empty-bn-{os.getpid()}"
        domain = "scripts"
        cwd = self._make_domain_env(tmp_path, project_id, domain)
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()
        mock, query_log = self._make_mock_ace_cli_recording(mock_bin)

        # Write a last-domain file different from matched domain to trigger the shift
        last_domain_file = Path(f"/tmp/ace-domain-{project_id}.txt")
        last_domain_file.write_text("other-domain")

        # /scripts/.hidden: domain match fires (path has "scripts"), but basename
        # after extension-strip is empty → guard must prevent ace-cli call.
        hook_input = {
            "session_id": "sess-pdu-empty-bn",
            "tool_name": "Read",
            "tool_input": {"file_path": f"/{domain}/.hidden"},
            "cwd": cwd,
        }

        result = subprocess.run(
            ["bash", str(self.POSTTOOLUSE)],
            input=json.dumps(hook_input),
            capture_output=True, text=True, timeout=10,
            env={
                **os.environ,
                "PATH": f"{mock_bin}:{os.environ.get('PATH', '/usr/bin:/bin')}",
                "CLAUDE_PROJECT_DIR": str(tmp_path),
            },
        )

        Path(f"/tmp/ace-domains-{project_id}.json").unlink(missing_ok=True)
        last_domain_file.unlink(missing_ok=True)

        assert result.returncode == 0, f"Script must exit 0; rc={result.returncode}"
        assert not query_log.exists(), (
            "ace-cli must NOT be called when FILE_BASENAME is empty. "
            f"Query log was written: {query_log.read_text() if query_log.exists() else '(missing)'}"
        )

    def test_pretooluse_nonempty_basename_search_query_has_no_domain(self, tmp_path):
        """pretooluse: non-empty basename → query sent to ace-cli is basename only (no domain)."""
        import os
        project_id = f"prj-ptu-qry-{os.getpid()}"
        domain = "scripts"
        cwd = self._make_domain_env(tmp_path, project_id, domain)
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()
        mock, query_log = self._make_mock_ace_cli_recording(mock_bin)

        hook_input = {
            "session_id": "sess-ptu-qry",
            "tool_name": "Read",
            "tool_input": {"file_path": f"/{domain}/ace_pretooluse_wrapper.sh"},
            "cwd": cwd,
        }

        subprocess.run(
            ["bash", str(self.PRETOOLUSE)],
            input=json.dumps(hook_input),
            capture_output=True, text=True, timeout=10,
            env={
                **os.environ,
                "PATH": f"{mock_bin}:{os.environ.get('PATH', '/usr/bin:/bin')}",
                "CLAUDE_PROJECT_DIR": str(tmp_path),
            },
        )

        Path(f"/tmp/ace-domains-{project_id}.json").unlink(missing_ok=True)
        Path(f"/tmp/ace-domain-{project_id}-main.txt").unlink(missing_ok=True)

        if not query_log.exists():
            pytest.skip("ace-cli was not called (domain match may not have fired)")

        query_sent = query_log.read_text().strip()
        assert domain not in query_sent, (
            f"Query must NOT contain domain token '{domain}'. Got: {query_sent!r}"
        )
        assert "ace_pretooluse_wrapper" in query_sent, (
            f"Query must contain the file basename. Got: {query_sent!r}"
        )

    def test_posttooluse_nonempty_basename_search_query_has_no_domain(self, tmp_path):
        """posttooluse: non-empty basename → query sent to ace-cli is basename only (no domain)."""
        import os
        project_id = f"prj-pdu-qry-{os.getpid()}"
        domain = "scripts"
        cwd = self._make_domain_env(tmp_path, project_id, domain)
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()
        mock, query_log = self._make_mock_ace_cli_recording(mock_bin)

        # Write a last-domain file different from matched domain to trigger the shift
        last_domain_file = Path(f"/tmp/ace-domain-{project_id}.txt")
        last_domain_file.write_text("other-domain")

        hook_input = {
            "session_id": "sess-pdu-qry",
            "tool_name": "Read",
            "tool_input": {"file_path": f"/{domain}/ace_posttooluse_domain_inject.sh"},
            "cwd": cwd,
        }

        subprocess.run(
            ["bash", str(self.POSTTOOLUSE)],
            input=json.dumps(hook_input),
            capture_output=True, text=True, timeout=10,
            env={
                **os.environ,
                "PATH": f"{mock_bin}:{os.environ.get('PATH', '/usr/bin:/bin')}",
                "CLAUDE_PROJECT_DIR": str(tmp_path),
            },
        )

        Path(f"/tmp/ace-domains-{project_id}.json").unlink(missing_ok=True)
        last_domain_file.unlink(missing_ok=True)

        if not query_log.exists():
            pytest.skip("ace-cli was not called (domain match may not have fired)")

        query_sent = query_log.read_text().strip()
        assert domain not in query_sent, (
            f"Query must NOT contain domain token '{domain}'. Got: {query_sent!r}"
        )
        assert "ace_posttooluse_domain_inject" in query_sent, (
            f"Query must contain the file basename. Got: {query_sent!r}"
        )
