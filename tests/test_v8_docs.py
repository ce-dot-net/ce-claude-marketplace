"""WP-E (v8.0.0) — CHANGELOG, README, ARCHITECTURE, ADR-001.

DESIGN §6 WP-E: CHANGELOG backfill 7.1.7–7.1.14 + [8.0.0] entry (critic T25: "CHANGELOG
stale since 7.1.6"); ARCHITECTURE.md to v8; new docs/technical/ADR-001-language.md (§2 + §8
deferred items); README floor text; statusline user-copy note.
"""
import json
import re
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parent.parent / "plugins" / "ace"
CHANGELOG = PLUGIN / "CHANGELOG.md"
README = PLUGIN / "README.md"
ARCH = PLUGIN / "docs" / "technical" / "ARCHITECTURE.md"
ADR = PLUGIN / "docs" / "technical" / "ADR-001-language.md"


def _read(p):
    return p.read_text(encoding="utf-8")


def test_changelog_has_8_0_0_entry():
    """DESIGN §6 WP-E: CHANGELOG gets a [8.0.0] entry naming the new CC floor."""
    text = _read(CHANGELOG)
    m = re.search(r"^## \[8\.0\.0\][^\n]*\n(.*?)(?=^## \[)", text, re.S | re.M)
    assert m, "CHANGELOG.md has no `## [8.0.0]` section"
    assert "2.1.311" in m.group(1)


@pytest.mark.parametrize("ver", ["7.1.%d" % n for n in range(7, 15)])
def test_changelog_backfills_7_1_x(ver):
    """DESIGN §6 WP-E / critic T25: backfill 7.1.7–7.1.14 one-liners from git log."""
    assert re.search(r"^## \[%s\]" % re.escape(ver), _read(CHANGELOG), re.M), (
        "CHANGELOG.md missing `## [%s]`" % ver
    )


def test_changelog_newest_entry_matches_manifest():
    """Keep-a-Changelog order: newest first; the newest dated heading is the plugin.json version
    (an Unreleased entry may sit above it)."""
    version = json.loads(_read(PLUGIN / ".claude-plugin" / "plugin.json"))["version"]
    heads = re.findall(r"^## \[(\d+\.\d+\.\d+)\]( - Unreleased)?", _read(CHANGELOG), re.M)
    released = [v for v, unreleased in heads if not unreleased]
    assert released and released[0] == version


def test_adr_001_language_exists_with_verdict():
    """DESIGN §2: ADR-001 summarizes the four advocates and the verdict (Python stays)."""
    assert ADR.exists(), "docs/technical/ADR-001-language.md missing"
    text = _read(ADR)
    for word in ("Python", "TypeScript", "Go", "Rust", "mods"):
        assert word in text, "ADR-001 must discuss " + word
    assert re.search(r"(?i)verdict|decision", text)


def test_adr_001_records_deferred_followups():
    """DESIGN §8: prompt_id pinning, PostToolBatch, UserPromptExpansion, CC mods, in-process core are deferred in ADR-001."""
    text = _read(ADR) if ADR.exists() else ""
    for item in ("prompt_id", "PostToolBatch", "UserPromptExpansion", "@ace-sdk/core"):
        assert item in text, "ADR-001 must record deferred item " + item


def test_architecture_describes_v8():
    """DESIGN §6 WP-E: ARCHITECTURE.md updated to v8 (was 'Current Version: 5.1.4')."""
    text = _read(ARCH)
    assert re.search(r"Current Version\**:?\**\s*8\.0\.0", text)
    assert "CLAUDE_PLUGIN_DATA" in text
    assert "PostToolUseFailure" in text


def test_architecture_has_no_tmp_state_paths():
    """DESIGN §4: state lives under CLAUDE_PLUGIN_DATA, not /tmp/ace-*."""
    assert "/tmp/ace" not in _read(ARCH)


def test_architecture_does_not_describe_removed_hooks():
    """DESIGN §3 REMOVED: no PreToolUse / PreCompact hook boxes in the v8 architecture."""
    text = _read(ARCH)
    for ev in ("PreToolUse Hook", "PreCompact Hook"):
        assert ev not in text


def test_readme_states_v8_floor():
    """§16 P6: README Requires text is CC >= 2.1.311 (was 'ace-cli >= v3.4.1')."""
    text = _read(README)
    assert "2.1.311" in text and "2.1.300" not in text
    assert "ace-cli >= v3.4.1" not in text


def test_docs_mention_statusline_user_copy_refresh():
    """DESIGN §6 WP-E: ~/.claude/ace_statusline.sh is a user copy; `/ace:ace-statusline-setup update` refreshes it."""
    text = _read(README)
    assert "~/.claude/ace_statusline.sh" in text
    assert "/ace:ace-statusline-setup update" in text


# ---------------------------------------------------------------------------
# WP-I (round 2): DESIGN §9, §10 (accepted losses, P-25/P-27), §11 A4/A6/A7, §7 release gate
# ---------------------------------------------------------------------------
REPO = PLUGIN.parent.parent
CONFIG = PLUGIN / "docs" / "guides" / "CONFIGURATION.md"
TROUBLE = PLUGIN / "docs" / "guides" / "TROUBLESHOOTING.md"
GATE = PLUGIN / "docs" / "RELEASE_GATE_v8.md"
RELEASE_MANAGER = REPO / ".claude" / "agents" / "release-manager.md"
CI = REPO / ".github" / "workflows" / "tests.yml"
DASH = "[–-]"  # en dash or hyphen


def _v8_section():
    m = re.search(r"^## \[8\.0\.0\][^\n]*\n(.*?)(?=^## \[)", _read(CHANGELOG), re.S | re.M)
    assert m, "CHANGELOG.md has no `## [8.0.0]` section"
    return m.group(1)


@pytest.mark.parametrize("token", [
    "PostToolBatch",            # G4 accumulator
    "prompt_id",                # G2 task anchor
    "Agent",                    # G1 PreToolUse(Agent) prompt stash for SubagentStart
    "detached",                 # A3 learn survives `claude -p` teardown
    "pin-backoff",              # A1 pin-drop + backoff
    "sessions.db",              # A5 doctor / cleanup
    "--legacy",                 # P-14
    "ACE_ASYNC_LEARNING",       # P-27: removed, learning is always async
])
def test_changelog_8_0_0_names_round2_mechanism(token):
    assert token in _v8_section(), "CHANGELOG [8.0.0] must mention " + token


def test_changelog_8_0_0_does_not_claim_pretooluse_fully_removed():
    """Round 2 re-adds PreToolUse(Agent); only the domain-shift PreToolUse path is gone."""
    for line in _v8_section().splitlines():
        if re.search(r"(?i)removed hooks?", line) and "PreToolUse" in line:
            assert "Agent" in line or "domain" in line.lower(), line


@pytest.mark.parametrize("pattern", [
    r"PreToolUse[^\n]*systemMessage",                        # domain-shift systemMessages
    r"whoami",                                               # startup auth warnings
    r"(?i)troubleshooting[^\n]*injection|Bash.error",        # Bash-error troubleshooting injection
    r"UTC",
    r"~/\.ace/config\.json",                                 # legacy apiToken warnings (P-23)
    r"/rewind",
    r"(?i)deny.rule[^\n]*not learned",                       # §11 A4
])
def test_changelog_8_0_0_lists_accepted_losses(pattern):
    sec = _v8_section()
    m = re.search(r"(?im)^###\s*Accepted losses\s*\n(.*?)(?=^###|\Z)", sec, re.S)
    assert m, "CHANGELOG [8.0.0] needs a `### Accepted losses` subsection (DESIGN §10, §11 A4)"
    assert re.search(pattern, m.group(1)), "accepted losses must cover " + pattern


@pytest.mark.parametrize("num", ["60%s111" % DASH, r"2\.3%s3\.3" % DASH, "27%s37" % DASH])
def test_changelog_8_0_0_has_p7_baseline(num):
    """DESIGN §9: 7.1.14 60–111 s vs v8 2.3–3.3 s blocking hook time; UPS 27–37 s."""
    assert re.search(num, _v8_section()), "CHANGELOG [8.0.0] baseline number missing: " + num


@pytest.mark.parametrize("num", [
    r"0\.23%s0\.53" % DASH, r"1\.97", "81%s96" % DASH, "237", r"6\.2 s", "123 MB",   # A7
    "41,579", "94 ms",                                                               # SYNTHESIS §3
])
def test_adr_001_has_final_a7_numbers(num):
    assert re.search(num, _read(ADR)), "ADR-001 missing proven number " + num


@pytest.mark.parametrize("token", ["prompt.submit", "agent.spawn", "tool.call", "npm ci --ignore-scripts",
                                   "2.1.287"])
def test_adr_001_has_mods_inprocess_plan(token):
    """SYNTHESIS §3 + DESIGN §13.1/§14: mods + in-process core with the floor, all in 8.0.0."""
    assert token in _read(ADR), "ADR-001 must carry " + token


@pytest.mark.parametrize("token", ["PostToolBatch", "prompt_id", "agent-prompts", "detached",
                                   "pin-backoff", "PreToolUse"])
def test_architecture_is_v8_final(token):
    """DESIGN §9 G1/G2/G4, §11 A1/A3: ARCHITECTURE describes the round-2 topology."""
    assert token in _read(ARCH), "ARCHITECTURE.md must describe " + token


def test_architecture_failure_hook_matcher_is_star():
    """DESIGN §10 S8: PostToolUseFailure matcher `*`, not Bash only."""
    assert "PostToolUseFailure (Bash)" not in _read(ARCH)


def test_configuration_timeouts_in_seconds():
    """P-25/P-27: hooks.json timeouts are SECONDS (UPS 30); no ms values, no ACE_ASYNC_LEARNING."""
    text = _read(CONFIG)
    assert '"timeout": 30' in text
    assert re.search(r"(?i)seconds", text)
    assert not re.search(r"(?<!\d)\d{4,}ms", text)
    for var in ("ACE_MIN_PROMPT_CHARS", "ACE_PIN_BACKOFF_MIN"):
        assert var in text, "CONFIGURATION.md must document " + var


@pytest.mark.parametrize("token", ["database is locked", "sessions.db", "ace-hook-errors.log",
                                   "CLAUDE_PLUGIN_DATA", "/ace:ace-cleanup --legacy", "/ace:ace-doctor"])
def test_troubleshooting_covers_v8(token):
    assert token in _read(TROUBLE), "TROUBLESHOOTING.md must cover " + token


@pytest.mark.parametrize("token", [
    "python3 -m pytest tests",                 # full suite
    "ACE_E2E=1",                               # e2e
    "claude plugin validate plugins/ace --strict",
    "--debug-file",                            # A6
    "timed out after",                         # A6: 0 timeout lines
    "patterns_injected",                       # A6: > 0 on the human prompt
    "database is locked",                      # A6
    "search_skipped",                          # §7: <task-notification> prompt
    "ACE_CLIENT_ID",                           # S14 CLAUDE_ENV_FILE export
    "SessionEnd",                              # S14 < 0.5 s
    "statusline",                              # S14
    "ACE_REVIEW",                              # S14 self-eval round-trip
    "disabled.flag",                           # S14
    "~/.claude/logs",                          # §7: no growth
])
def test_release_gate_checklist(token):
    assert GATE.exists(), "plugins/ace/docs/RELEASE_GATE_v8.md missing (DESIGN §7 + §11 A6)"
    text = _read(GATE)
    assert "- [ ]" in text, "release gate must be a checklist"
    assert token in text, "release gate must include " + token


@pytest.mark.parametrize("token", ["python3 -m pytest tests", "ACE_E2E=1", "plugin validate",
                                   "RELEASE_GATE_v8.md", "v{VERSION}"])
def test_release_manager_gate(token):
    """WP-I: release-manager runs full suite + e2e + validate and follows the live checklist."""
    assert token in _read(RELEASE_MANAGER), "release-manager.md must include " + token


def test_release_manager_no_stale_cli_name():
    text = _read(RELEASE_MANAGER)
    assert "ce-ace" not in text and "claude plugin tag" not in text


def test_ci_runs_e2e_job():
    """Regression (already at 997c0de): CI runs the ACE_E2E=1 hook e2e suite."""
    text = _read(CI)
    assert "ACE_E2E" in text and "tests/e2e" in text


def test_readme_discloses_the_v8_render_contract_and_drops_the_stale_flow():
    """final review: public README states the mod/Python chains, the budget default, the full split and its cost,
    the trace labels and the X-ACE-Client values; the removed keyword flow is gone."""
    text = _read(README)
    for must in ("ACE_RENDER_FULL_PCT", "budget", "2.1-2.3x", "conversation_id", "applied_log_ids", "render_variant",
                 "X-ACE-Client", "claude-code-plugin/", "mod", "AOP-1333", "untested"):
        assert must in text, must
    for stale in ("Found 3 relevant patterns", "Bash(ace-cli *)", "~/.ace-logs", "Hook detects keywords", "v5.1.17"):
        assert stale not in text, stale


# ---- item 5: docs match the code (marker windows, sync/async of each hook) ----

DOCTOR = PLUGIN / "commands" / "ace-doctor.md"


def _changelog_8():
    return re.search(r"^## \[8\.0\.0\][^\n]*\n(.*?)(?=^## \[)", _read(CHANGELOG), re.S | re.M).group(1)


@pytest.mark.parametrize("doc", ["doctor", "changelog"])
def test_docs_no_longer_say_600_s_or_10_min_marker(doc):
    text = _read(DOCTOR) if doc == "doctor" else _changelog_8()
    assert not re.search(r"600\s*s\b", text), "the mod markers are 15 s / 120 s (plugin_data_dir), not 600 s"
    assert not re.search(r"mod-active[^.\n]{0,40}10 min", text)
    assert "15 s" in text and "120 s" in text


def test_doctor_hook_list_matches_hooks_json_sync_async():
    import json
    hooks = json.loads((PLUGIN / "hooks" / "hooks.json").read_text())["hooks"]
    lines = _read(DOCTOR).splitlines()
    for event in ("Stop", "SubagentStop", "PermissionDenied", "PostToolBatch", "PostToolUseFailure"):
        is_async = all(h.get("async") for g in hooks[event] for h in g["hooks"])
        line = next(l for l in lines if re.match(r"^\d+b?\. `%s`" % event, l))
        assert ("(async" in line) == is_async, line
        assert ("sync" in line), "say sync or async: " + line


# ---- item 6: ace-cleanup / ace-insights describe v8 (no event logger) ----

def test_cleanup_has_no_event_logging_toggle():
    text = _read(PLUGIN / "commands" / "ace-cleanup.md")
    for gone in ("ACE_EVENT_LOGGING", "--enable-logging", "--disable-logging", "Event Logging", "ace-tools.db"):
        assert gone not in text, gone
    assert "ace-relevance." in text and "ace-hook-errors.log" in text


def test_insights_names_the_v8_domain_shift_hook():
    text = _read(PLUGIN / "commands" / "ace-insights.md")
    assert "PreToolUse hook" not in text
    assert "PostToolUse Read/Glob/Grep" in text


def test_doctor_connectivity_probe_uses_ace_cli_not_dead_endpoints():
    """fix 4: /api/projects/<id>/playbook and /api/health are 404 on prod -> check [5] was always WARN."""
    text = _read(DOCTOR)
    check5 = re.search(r"### Check 5:.*?(?=^### Check 6)", text, re.S | re.M).group(0)
    for dead in ("/api/health", "/playbook", "curl"):
        assert dead not in text if dead != "curl" else dead not in check5, dead
    assert re.search(r"\$\{CLAUDE_PLUGIN_ROOT\}/scripts/ace-cli .*status --json", check5)
    assert "(HTTP 200)" not in text
