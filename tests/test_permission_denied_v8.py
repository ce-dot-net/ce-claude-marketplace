#!/usr/bin/env python3
"""WP-A RED: PermissionDenied v8 — documented `reason` first, transcript tail as fallback.

cc_hooks_reference.md:2414 "PermissionDenied hooks receive tool_name, tool_input,
tool_use_id, and reason"; :2435 — classifier verdict "[Rule Name]", no-verdict denial
starts "Auto mode could not evaluate this action and is blocking it for safety",
classifier model down = fixed text "Classifier unavailable". Critic V12: v7.1.14
assumed no `reason`, so it scanned the transcript; keep that scan only when `reason`
is absent (DESIGN §3 PermissionDenied row). DESIGN §4: debounce/disabled state under
plugin data, never /tmp/ace-denials-*. Hook is async (DESIGN §3); the shim is §3.1.
"""
import importlib.util
import json
import os
import shutil
from pathlib import Path

import pytest

from wpa_harness import Env, PLUGIN, plugin_version

SCRIPT = "ace_permission_denied_wrapper.sh"
HOOK = PLUGIN / "shared-hooks" / "ace_permission_denied.py"
INFRA_TEXT = ("Claude: the classifier is temporarily unavailable, so auto mode cannot "
              "determine the safety of Bash right now.")


def _mod():
    spec = importlib.util.spec_from_file_location("ace_permission_denied_v8", HOOK)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _transcript(tmp_path, text):
    entry = {"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "content": text, "is_error": True, "tool_use_id": "t1"}]}}
    p = tmp_path / "t.jsonl"
    p.write_text(json.dumps(entry) + "\n")
    return str(p)


# ── reason-based classification (module level) ──────────────────────────────

def test_reason_classifier_unavailable_is_infra():
    """doc :2435 fixed text 'Classifier unavailable' = infra abort, no transcript needed."""
    assert _mod()._is_classifier_infra_denial(
        {"tool_name": "Bash", "reason": "Classifier unavailable"}) is True


def test_reason_could_not_evaluate_is_infra():
    """doc :2435 no-verdict denial prefix = infra abort."""
    ev = {"tool_name": "Bash", "reason": "Auto mode could not evaluate this action and is "
                                         "blocking it for safety. Try again."}
    assert _mod()._is_classifier_infra_denial(ev) is True


def test_reason_rule_verdict_is_genuine_even_if_transcript_has_infra_marker(tmp_path):
    """`reason` is authoritative when present: '[Data Exfiltration]' is a genuine
    boundary even if an older/unrelated infra marker sits in the transcript tail."""
    ev = {"tool_name": "Bash", "reason": "[Data Exfiltration]",
          "transcript_path": _transcript(tmp_path, INFRA_TEXT)}
    assert _mod()._is_classifier_infra_denial(ev) is False


def test_reason_present_skips_transcript_read(tmp_path, monkeypatch):
    """With `reason` present the bounded transcript read is not needed at all."""
    m = _mod()
    called = []
    monkeypatch.setattr(m, "_read_transcript_tail",
                        lambda *a, **k: called.append(a) or [])
    m._is_classifier_infra_denial({"tool_name": "Bash", "reason": "[Irreversible Local Destruction]",
                                   "transcript_path": _transcript(tmp_path, "x")})
    assert called == []


def test_missing_reason_falls_back_to_transcript_tail(tmp_path):
    """v7.1.14 fallback kept for CC builds that do not send `reason`."""
    ev = {"tool_name": "Bash", "transcript_path": _transcript(tmp_path, INFRA_TEXT)}
    assert _mod()._is_classifier_infra_denial(ev) is True


# ── end-to-end through the shim (fake ace-cli) ──────────────────────────────

@pytest.fixture(autouse=True)
def _no_v7_tmp_litter():
    """While RED, the v7 code still writes /tmp/ace-denials-<sid>/; clean it up."""
    yield
    for sid in ("pd-gen", "pd-infra", "pd-off"):
        shutil.rmtree("/tmp/ace-denials-%s" % sid, ignore_errors=True)


def _ev(env, sid, reason, tool="Bash"):
    e = {"session_id": sid, "hook_event_name": "PermissionDenied", "cwd": str(env.project),
         "permission_mode": "auto", "tool_name": tool, "tool_use_id": "toolu_1",
         "tool_input": {"command": "rm -rf build"}, "transcript_path": ""}
    if reason is not None:
        e["reason"] = reason
    return e


def test_shim_infra_reason_does_not_learn(tmp_path):
    env = Env(tmp_path)
    r = env.run(SCRIPT, _ev(env, "pd-infra", "Classifier unavailable"))
    assert r.returncode == 0
    assert env.cli_calls("learn") == []


def test_shim_genuine_reason_learns_once_with_client_id(tmp_path):
    """Genuine deny -> one `ace-cli learn`, carrying ACE_CLIENT_ID=claude-code-plugin/<v>
    (v7 got it from sourcing _ace_env.sh; a §3.1 shim does not source it, so Python must
    set it)."""
    env = Env(tmp_path)
    r = env.run(SCRIPT, _ev(env, "pd-gen", "[Data Exfiltration]"))
    assert r.returncode == 0, r.stderr
    learns = env.cli_calls("learn")
    assert len(learns) == 1
    assert learns[0][0] == "claude-code-plugin/%s" % plugin_version()


def test_shim_debounce_state_lives_in_plugin_data(tmp_path):
    """DESIGN §4: debounce stamps under <data>/projects/<pid>/sessions/<sid>/, no
    /tmp/ace-denials-<sid>/ (critic T21)."""
    env = Env(tmp_path)
    sid = "pd-deb-%d" % os.getpid()
    tmp_leak = Path("/tmp/ace-denials-%s" % sid)
    try:
        env.run(SCRIPT, _ev(env, sid, "[Data Exfiltration]"))
        env.run(SCRIPT, _ev(env, sid, "[Data Exfiltration]"))
        assert len(env.cli_calls("learn")) == 1, "second deny within 60 s must be debounced"
        assert not tmp_leak.exists(), "must not write /tmp"
    finally:
        shutil.rmtree(str(tmp_leak), ignore_errors=True)  # never leave v7 litter behind
    sdir = env.session_dir(sid)
    assert sdir.is_dir() and any(sdir.iterdir()), "debounce stamp not under plugin data"


def test_shim_respects_plugin_data_disabled_flag(tmp_path):
    """DESIGN §4 disabled.flag (written by SessionStart) stops the learn spawn
    (critic T17: the v7 /tmp flag check was effectively dead)."""
    env = Env(tmp_path)
    flag = env.disabled_flag("pd-off")
    flag.parent.mkdir(parents=True)
    flag.write_text("CLI version 4.0.0 < 4.1.2")
    env.run(SCRIPT, _ev(env, "pd-off", "[Data Exfiltration]"))
    assert env.cli_calls("learn") == []


# ── §28: render_variant names what was actually rendered ────────────────────

def _variant(tmp_path, monkeypatch, marker):
    from wpa_harness import PROJECT_ID
    env = Env(tmp_path)
    for k, v in env.env().items():
        monkeypatch.setenv(k, v)
    for k in ("ACE_RENDER_FULL_PCT", "ACE_AB_CONTROL_PCT", "ACE_AB_COMPACT_PCT"):
        monkeypatch.delenv(k, raising=False)
    m = _mod()
    m._PROJECT_ID = PROJECT_ID
    if marker:
        sd = env.session_dir("pd-rv")
        sd.mkdir(parents=True)
        (sd / "mod-active").touch()
    return m._render_variant("pd-rv")


def test_render_variant_full_when_mod_active(tmp_path, monkeypatch):
    assert _variant(tmp_path, monkeypatch, True) == "full"


def test_render_variant_budget_without_mod(tmp_path, monkeypatch):
    assert _variant(tmp_path, monkeypatch, False) == "budget"
