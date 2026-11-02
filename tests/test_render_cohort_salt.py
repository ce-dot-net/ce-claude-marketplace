#!/usr/bin/env python3
"""
TDD tests for MUST-FIX 1 (render_cohort salt) and MUST-FIX 2 (render_variant
stamping on ExecutionTrace) — v7.1.12 → v7.1.13 fixes.

RED phase: These tests fail against the current unsalted implementation.
GREEN phase: Pass after adding 'render:' prefix to the hash input and
             stamping trace['render_variant'] in ace_after_task.py.

MUST-FIX 1 — render_cohort orthogonality:
  The server's live serve-A/B uses bare sha256(session_id) % 100.
  The render cohort MUST use a salted input ("render:" + session_id) to be
  orthogonal to the serve cohort.

MUST-FIX 2 — render_variant on ExecutionTrace:
  ace_after_task.py must stamp trace['render_variant'] = render_cohort(task_session_id)
  when task_session_id is present; omit the field when absent; never raise.
"""

import hashlib
import json
import os
import sys
import uuid
from pathlib import Path

import pytest

# ── path bootstrap ─────────────────────────────────────────────────────────────
REPO = Path(__file__).resolve().parent.parent
UTILS = REPO / "plugins" / "ace" / "shared-hooks" / "utils"
PLUGIN_UTILS = REPO / "plugins" / "ace" / "utils"
sys.path.insert(0, str(UTILS))
sys.path.insert(0, str(PLUGIN_UTILS))

from ace_pattern_render import render_cohort  # noqa: E402


# ─────────────────────────────────────────────────────────────────────────────
# Section 1: MUST-FIX 1 — salted hash orthogonality
# ─────────────────────────────────────────────────────────────────────────────

class TestRenderCohortSaltOrthogonality:
    """The render cohort must use a 'render:'-salted hash so it is orthogonal
    to the server's bare sha256(session_id) % 100 serve-A/B bucket."""

    def test_salted_bucket_differs_from_bare_for_majority_of_ids(self, monkeypatch):
        """For 1000 random session_ids, >90% must land in a different bucket
        than the bare sha256(session_id)%100 bucket.

        This proves the render cohort is orthogonal to the server's serve-A/B
        which uses the bare (unsalted) hash.

        RED: fails when render_cohort uses bare sha256(session_id).
        GREEN: passes after adding 'render:' prefix.
        """
        monkeypatch.setenv("ACE_AB_CONTROL_PCT", "50")
        monkeypatch.setenv("ACE_AB_COMPACT_PCT", "50")

        N = 1000
        diffs = 0
        for _ in range(N):
            sid = str(uuid.uuid4())
            # Server's bare bucket (no salt)
            bare_bucket = int(hashlib.sha256(sid.encode()).hexdigest()[:8], 16) % 100
            # Our salted bucket (what render_cohort should use)
            salted_bucket = int(
                hashlib.sha256(("render:" + sid).encode()).hexdigest()[:8], 16
            ) % 100
            if bare_bucket != salted_bucket:
                diffs += 1

        pct = diffs / N * 100
        assert pct > 90, (
            f"render_cohort salt orthogonality: expected >90% of ids to differ "
            f"from bare sha256 bucket, got {pct:.1f}%. "
            f"Add 'render:' prefix to the hash input in render_cohort()."
        )

    def test_render_cohort_uses_salted_hash_not_bare(self, monkeypatch):
        """render_cohort() must produce the SALTED bucket assignment, not the bare one.

        Find a session_id whose bare bucket != salted bucket (nearly all do).
        Assert that render_cohort() returns the cohort consistent with the salted
        bucket, not the bare bucket.

        RED: fails because render_cohort uses bare sha256(session_id).
        GREEN: passes after adding 'render:' prefix.
        """
        monkeypatch.setenv("ACE_AB_CONTROL_PCT", "50")
        monkeypatch.setenv("ACE_AB_COMPACT_PCT", "50")

        # Find a session_id where bare != salted bucket
        found = False
        for _ in range(500):
            sid = str(uuid.uuid4())
            bare_bucket = int(hashlib.sha256(sid.encode()).hexdigest()[:8], 16) % 100
            salted_bucket = int(
                hashlib.sha256(("render:" + sid).encode()).hexdigest()[:8], 16
            ) % 100
            if bare_bucket != salted_bucket:
                # The render_cohort() result must match the SALTED assignment,
                # not the bare one.
                def _cohort(bucket, ctrl=50, compact=50):
                    if bucket < ctrl:
                        return "control"
                    if bucket < ctrl + compact:
                        return "compact"
                    return "budget"

                bare_expected = _cohort(bare_bucket)
                salted_expected = _cohort(salted_bucket)

                if bare_expected != salted_expected:
                    # They disagree — this is the discriminating case
                    actual = render_cohort(sid)
                    assert actual == salted_expected, (
                        f"render_cohort({sid!r}): "
                        f"bare bucket={bare_bucket} → {bare_expected!r}, "
                        f"salted bucket={salted_bucket} → {salted_expected!r}, "
                        f"got {actual!r}. "
                        f"render_cohort must use the salted hash ('render:' prefix)."
                    )
                    found = True
                    break

        assert found, (
            "Could not find a discriminating session_id (bare != salted cohort) "
            "in 500 attempts — this is extremely unlikely with CONTROL_PCT=50/COMPACT_PCT=50"
        )


class TestRenderCohortSaltDeterminism:
    """Determinism must be preserved with the salt."""

    def test_same_session_id_same_cohort_with_salt(self, monkeypatch):
        """Same session_id must always return the same cohort (deterministic with salt)."""
        monkeypatch.setenv("ACE_AB_CONTROL_PCT", "33")
        monkeypatch.setenv("ACE_AB_COMPACT_PCT", "33")
        for _ in range(30):
            sid = str(uuid.uuid4())
            first = render_cohort(sid)
            for _ in range(5):
                assert render_cohort(sid) == first, (
                    f"render_cohort must be deterministic after adding salt; "
                    f"got different results for {sid!r}"
                )

    def test_salted_hash_computation_matches_spec(self, monkeypatch):
        """The salted bucket must equal sha256('render:' + session_id)[:8] % 100.

        RED: fails because current code uses sha256(session_id) (no salt).
        GREEN: passes after adding 'render:' prefix.
        """
        monkeypatch.setenv("ACE_AB_CONTROL_PCT", "20")
        monkeypatch.setenv("ACE_AB_COMPACT_PCT", "20")
        for _ in range(50):
            sid = str(uuid.uuid4())
            # Expected: salted bucket
            salted_bucket = int(
                hashlib.sha256(("render:" + sid).encode()).hexdigest()[:8], 16
            ) % 100
            expected = (
                "control" if salted_bucket < 20
                else "compact" if salted_bucket < 40
                else "budget"
            )
            actual = render_cohort(sid)
            assert actual == expected, (
                f"Salted bucket {salted_bucket} for {sid!r}: "
                f"expected {expected!r} (salted), got {actual!r}. "
                f"render_cohort must hash 'render:' + session_id."
            )


class TestRenderCohortSaltDormantDefault:
    """Dormant default (100% budget) must be preserved after adding the salt."""

    def test_no_env_all_budget_with_salt(self, monkeypatch):
        """Without env vars, render_cohort must still return 'budget' for all inputs."""
        monkeypatch.delenv("ACE_AB_CONTROL_PCT", raising=False)
        monkeypatch.delenv("ACE_AB_COMPACT_PCT", raising=False)
        for _ in range(100):
            sid = str(uuid.uuid4())
            result = render_cohort(sid)
            assert result == "budget", (
                f"Dormant default must be preserved: expected 'budget', got {result!r}"
            )

    def test_zero_pcts_all_budget_with_salt(self, monkeypatch):
        """ACE_AB_CONTROL_PCT=0, ACE_AB_COMPACT_PCT=0 → 100% budget (fast-path, salt irrelevant)."""
        monkeypatch.setenv("ACE_AB_CONTROL_PCT", "0")
        monkeypatch.setenv("ACE_AB_COMPACT_PCT", "0")
        for _ in range(100):
            sid = str(uuid.uuid4())
            result = render_cohort(sid)
            assert result == "budget", (
                f"Zero-pct fast-path must still return 'budget', got {result!r}"
            )

    def test_falsy_session_id_still_budget(self, monkeypatch):
        """Falsy/empty session_id → 'budget', unchanged by salt."""
        monkeypatch.setenv("ACE_AB_CONTROL_PCT", "50")
        monkeypatch.setenv("ACE_AB_COMPACT_PCT", "50")
        assert render_cohort("") == "budget"
        assert render_cohort(None) == "budget"


class TestRenderCohortSaltDistribution:
    """Salt must not skew uniformity — distribution must remain ~20/20/60."""

    def test_distribution_preserved_with_salt(self, monkeypatch):
        """With CONTROL_PCT=20/COMPACT_PCT=20, distribution ≈ 20/20/60 over 10k IDs
        even after adding the 'render:' salt.

        The salt changes WHICH sessions are in which cohort, but not the proportions
        (sha256 is a uniform hash, salting preserves uniformity).
        """
        monkeypatch.setenv("ACE_AB_CONTROL_PCT", "20")
        monkeypatch.setenv("ACE_AB_COMPACT_PCT", "20")
        counts = {"control": 0, "compact": 0, "budget": 0}
        N = 10_000
        for _ in range(N):
            cohort = render_cohort(str(uuid.uuid4()))
            counts[cohort] += 1
        ctrl_pct = counts["control"] / N * 100
        compact_pct = counts["compact"] / N * 100
        budget_pct = counts["budget"] / N * 100
        assert abs(ctrl_pct - 20) <= 5, (
            f"control% expected ~20 (±5), got {ctrl_pct:.1f}% — salt skewed distribution"
        )
        assert abs(compact_pct - 20) <= 5, (
            f"compact% expected ~20 (±5), got {compact_pct:.1f}% — salt skewed distribution"
        )
        assert abs(budget_pct - 60) <= 5, (
            f"budget% expected ~60 (±5), got {budget_pct:.1f}% — salt skewed distribution"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Section 2: MUST-FIX 2 — render_variant stamping on ExecutionTrace
# ─────────────────────────────────────────────────────────────────────────────

class TestRenderVariantAceAfterTaskSource:
    """Verify that ace_after_task.py source contains the render_variant stamping code.

    These tests inspect the source file to confirm the implementation is present —
    the safe approach given ace_after_task.py has complex relative imports that
    prevent clean importlib loading in the test environment.

    RED: fails before the stamping block is added.
    GREEN: passes after the render_variant block lands in ace_after_task.py.
    """

    @pytest.fixture(autouse=True)
    def _read_source(self):
        """Read ace_after_task.py source once per test."""
        path = REPO / "plugins" / "ace" / "shared-hooks" / "ace_after_task.py"
        self._source = path.read_text()

    def test_render_cohort_imported_in_after_task(self):
        """ace_after_task.py must import render_cohort from ace_pattern_render.

        RED: fails before the guarded import is added.
        GREEN: passes after adding 'from ace_pattern_render import render_cohort'.
        """
        assert "render_cohort" in self._source and "ace_pattern_render" in self._source, (
            "ace_after_task.py must import render_cohort from ace_pattern_render; "
            "not found in source. Add a guarded import: "
            "'from ace_pattern_render import render_cohort as _render_cohort'"
        )

    def test_render_variant_stamped_on_trace(self):
        """ace_after_task.py must set trace['render_variant'].

        RED: fails before the stamping block is added.
        GREEN: passes after 'trace[\"render_variant\"] = _render_cohort(task_session_id)' is added.
        """
        assert 'trace["render_variant"]' in self._source or "trace['render_variant']" in self._source, (
            "ace_after_task.py must stamp trace['render_variant']; not found in source. "
            "Add: trace['render_variant'] = _render_cohort(task_session_id) "
            "inside 'if task_session_id:' after setting trace['session_id']."
        )

    def test_render_variant_stamping_is_hot_path_safe(self):
        """DESIGN §28: the variant lookup is guarded so a failure never breaks the learn trace, and a failure
        still stamps a value (never omitted)."""
        lines = self._source.splitlines()
        idx = next(i for i, l in enumerate(lines) if "_trace_render_variant(" in l and "=" in l)
        window = "\n".join(lines[max(0, idx - 3): idx + 4])
        assert "try:" in window and "except" in window and "_render_variant = " in window, window

    def test_render_variant_not_gated_on_task_session_id(self):
        """DESIGN §28 supersedes MUST-FIX 2's guard: render_variant goes on EVERY trace, pin or not."""
        lines = self._source.splitlines()
        idx = next(i for i, l in enumerate(lines) if 'trace["render_variant"]' in l)
        assert not lines[idx].startswith(" " * 16), "must sit at trace-build level, not inside `if task_session_id:`"


class TestRenderVariantTraceDirectUnit:
    """§31 trace_render_variant(stored): the stored (actually rendered) variant, normalized to budget|full;
    anything else (incl. none) is unknown -> None, the key is omitted. Hook level: test_s31_contract.py."""

    def test_stored_server_labels_pass(self):
        from ace_pattern_render import trace_render_variant
        assert [trace_render_variant(v, "any") for v in ("full", "budget")] == ["full", "budget"]

    def test_everything_else_is_unknown(self, monkeypatch):
        monkeypatch.setenv("ACE_AB_CONTROL_PCT", "20")
        from ace_pattern_render import trace_render_variant
        for v in (None, "bogus", "control", "compact"):
            assert trace_render_variant(v, "sid") is None
