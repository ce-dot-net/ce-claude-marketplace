#!/usr/bin/env python3
"""Round 3d RED: text + repo-tooling parts of DESIGN §15, §16 (P5, P6, P9, P11), §18, §19, §20, §23."""
import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
PLUGIN = REPO / "plugins" / "ace"
COMMANDS = PLUGIN / "commands"
DOCTOR = COMMANDS / "ace-doctor.md"
INSTALL = COMMANDS / "ace-install-cli.md"
GRAPH = COMMANDS / "ace-graph.md"
CLEANUP = COMMANDS / "ace-cleanup.md"
README = PLUGIN / "README.md"
ADR = PLUGIN / "docs" / "technical" / "ADR-001-language.md"
CHANGELOG = PLUGIN / "CHANGELOG.md"
RM = REPO / ".claude" / "agents" / "release-manager.md"
WATCH = REPO / ".github" / "workflows" / "ace-cli-watch.yml"
TESTS_YML = REPO / ".github" / "workflows" / "tests.yml"


def _changelog_800():
    m = re.search(r"^## \[8\.0\.0\][^\n]*\n(.*?)(?=^## \[)", CHANGELOG.read_text(), re.S | re.M)
    assert m
    return m.group(1)


# ── §19 /ace:ace-install-cli: short repair command ──────────────────────────────────────

def test_install_command_is_short():
    assert len(INSTALL.read_text().splitlines()) <= 80, "§19: 278-line wizard -> short repair command"


@pytest.mark.parametrize("word", ["pnpm", "yarn", "sudo"])
def test_install_command_has_no_wizard_left(word):
    assert word not in INSTALL.read_text()


def test_install_command_repair_order():
    t = INSTALL.read_text()
    a = t.find("claude plugin update ace@ce-dot-net-marketplace")
    b = t.find("npm ci --ignore-scripts")
    c = t.find("npm install -g")
    assert -1 < a < b, "plugin update first, then npm ci in the plugin root"
    assert c == -1 or b < c, "global only as the last mention"


def test_install_command_reports_source_and_failure_reasons():
    t = INSTALL.read_text()
    for needle in ("plugin-local", "global", "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC", "${CLAUDE_PLUGIN_ROOT}"):
        assert needle in t, needle


# ── §20.3 C4 docs (the npm install -g hints are in test_docs_no_stale_mechanics.py) ─────

def test_c4_docs_are_marked_historical():
    """§20.3: C4-Documentation/ describes the v7 layout and wrongly says SessionStart auto-installs."""
    missing = [p.name for p in sorted((REPO / "C4-Documentation").glob("*.md"))
               if not re.search(r"historical|v7 layout", "\n".join(p.read_text(errors="replace").splitlines()[:8]), re.I)]
    assert missing == []


# ── §15 / §18 / §23 doctor: one screen a remote user can paste back ─────────────────────

@pytest.mark.parametrize("needle", [
    "2.1.311",                      # P6
    "uname",                        # OS
    "bash --version",
    "python3 --version",
    "node --version",
    "node_modules/@ace-sdk/cli",    # CLI source
    "plugin-local",
    "untested",                     # global != pin (§23)
    "package.json",                 # the pin
    "claude plugin update",         # deps missing
    "packages not installed",
    "better_sqlite3.node",          # sqlite binary present
    "npm rm -g @ace-sdk/cli",       # both present
    "engine",                       # §15 which engine is active
    "ace-cli >= 4.2.1",             # P9 graph cache
])
def test_doctor_reports(needle):
    assert needle in DOCTOR.read_text(), needle


def test_doctor_guards_foreign_plugin_data():
    """P5: other plugins export their CLAUDE_PLUGIN_DATA into every Bash-tool subprocess."""
    assert re.search(r'case\s+"\$DATA"\s+in\s+\*/ace\*\)', DOCTOR.read_text())


@pytest.mark.parametrize("path", [DOCTOR, CLEANUP], ids=lambda p: p.name)
def test_docs_never_offer_cache_clear_for_sessions_db(path):
    """P9: `cache clear` is in-RAM only; the sessions.db remedy is deleting the files."""
    for para in re.split(r"\n\s*\n", path.read_text()):
        if "sessions.db" in para:
            assert not re.search(r"(run|use|try)[^.\n]*`?ace-cli cache clear", para, re.I), para[:200]


def test_doctor_no_longer_presents_cache_clear_as_a_remedy():
    t = DOCTOR.read_text()
    assert "Cleared by: `ace-cli cache clear`" not in t


def test_graph_command_states_the_cli_requirement():
    assert "ace-cli >= 4.2.1" in GRAPH.read_text()


def test_doctor_install_section_uses_the_wrapper_not_a_path_probe():
    assert "command -v ace-cli >/dev/null 2>&1 && echo \"INSTALLED\"" not in DOCTOR.read_text()


# ── P6 floor text ───────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("rel", ["README.md", "docs/guides/TROUBLESHOOTING.md", "docs/technical/ARCHITECTURE.md",
                                 "docs/technical/ADR-001-language.md", "commands/ace-doctor.md"])
def test_floor_text_is_2_1_311(rel):
    t = (PLUGIN / rel).read_text()
    assert "2.1.300" not in t, rel
    assert "2.1.311" in t, rel


def test_ci_validates_with_the_floor_version():
    assert "claude-code@2.1.311" in TESTS_YML.read_text()


def test_troubleshooting_documents_old_cc_behavior():
    """§15: what an older CC does with entries it does not know, and that ACE pauses itself."""
    t = (PLUGIN / "docs" / "guides" / "TROUBLESHOOTING.md").read_text()
    assert re.search(r"older Claude Code", t, re.I) and "paused" in t


# ── P11 text ────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("path", [README, DOCTOR, PLUGIN / ".claude-plugin" / "plugin.template.json"],
                         ids=lambda p: p.name)
def test_windows_not_supported_is_stated(path):
    assert re.search(r"Windows (?:is )?not supported", path.read_text()) and "WSL2" in path.read_text()


def test_adr_user_prompt_expansion_evaluated_not_deferred():
    t = ADR.read_text()
    assert "- `UserPromptExpansion` for matching slash-command names." not in t
    assert re.search(r"UserPromptExpansion.*not useful", t)


def test_adr_async_rewake_rejected():
    assert re.search(r"asyncRewake.*(?:rejected|wakes the model)", ADR.read_text())


def test_no_async_rewake_in_hooks_json():
    assert "asyncRewake" not in (PLUGIN / "hooks" / "hooks.json").read_text()


def test_adr_render_variant_reaches_the_server():
    assert re.search(r"render_variant[^\n]*(?:reaches|forwarded)", ADR.read_text())


def test_adr_effort_is_not_persisted():
    assert re.search(r"effort_(?:level|weight)[^\n]*(?:dropped|not (?:stored|persisted))", ADR.read_text())


def test_adr_states_ace_cli_4_1_2_flag_complete_and_section_23():
    t = ADR.read_text()
    assert re.search(r"4\.1\.2[^\n]*flag-complete", t)
    assert "package-lock.json" in t


def test_changelog_never_claims_client_id_attribution():
    assert not re.search(r"ACE_CLIENT_ID[^\n]*(?:attribut|identif)", _changelog_800().replace("never reaches", ""))


@pytest.mark.parametrize("needle", [
    "2.1.311",                     # P6
    "package-lock.json",           # §23 delivery
    "/ace:ace-install-cli",        # §19
    "SubagentHandback",            # P1
    "learn_deferred",              # P2 + accepted edge
    "parent_agent_id",             # P3
    "fork",                        # P7
    "Windows",                     # P11
])
def test_changelog_8_0_0_mentions(needle):
    assert needle in _changelog_800(), needle


def test_changelog_drops_the_parent_agent_id_accepted_loss():
    losses = _changelog_800().split("### Accepted losses", 1)[-1]
    assert "parent_agent_id" not in losses


def test_changelog_states_deferral_accepted_edge():
    losses = _changelog_800().split("### Accepted losses", 1)[-1]
    assert re.search(r"new human prompt[^\n]*(?:notification|deferred)", losses, re.I)


# ── §23 (b) ace-cli-watch workflow ──────────────────────────────────────────────────────

def _watch():
    assert WATCH.is_file(), "no .github/workflows/ace-cli-watch.yml"
    return WATCH.read_text()


def test_watch_is_daily():
    assert re.search(r"schedule:\s*\n\s*- cron:", _watch()) and "workflow_dispatch" in _watch()


def test_watch_compares_npm_with_the_pin():
    t = _watch()
    assert "npm view @ace-sdk/cli version" in t and "plugins/ace/package.json" in t


def test_watch_regenerates_the_lock_with_ignore_scripts():
    assert "npm install --package-lock-only --ignore-scripts" in _watch()


def test_watch_runs_suite_and_contract_test_against_the_new_pin():
    t = _watch()
    assert "npm ci --ignore-scripts" in t
    assert "test_cli_contract" in t or re.search(r"pytest tests\b", t)


def test_watch_opens_one_pr_never_merges():
    t = _watch()
    assert "pull-requests: write" in t and "contents: write" in t
    assert "gh pr create" in t or "create-pull-request" in t
    assert "GITHUB_TOKEN" in t or "github.token" in t
    assert "gh pr list" in t or "create-pull-request" in t, "one PR: no duplicate per day"
    for bad in ("--auto", "gh pr merge", "automerge", "auto-merge"):
        assert bad not in t, bad


def test_watch_uses_no_other_secret():
    assert set(re.findall(r"secrets\.(\w+)", _watch())) <= {"GITHUB_TOKEN"}


# ── §23 (a)/(c), §18 CI ─────────────────────────────────────────────────────────────────

def test_ci_installs_the_pinned_cli_so_the_contract_test_runs():
    t = TESTS_YML.read_text()
    assert "npm ci --ignore-scripts" in t and "plugins/ace" in t


def test_ci_rebuilds_sqlite_so_the_pinned_contract_case_runs():
    assert "npm rebuild better-sqlite3" in TESTS_YML.read_text()


def test_ci_setup_node_comes_before_the_suite():
    t = TESTS_YML.read_text()
    assert t.index("setup-node") < t.index("pytest tests")


def test_ci_runs_on_the_release_branch():
    assert "v8-modernize" in TESTS_YML.read_text()


def test_release_manager_pin_rule():
    t = RM.read_text()
    assert "package-lock" in t and "test_cli_contract" in t
    assert re.search(r"pin bump.*plugin version bump|plugin version bump.*pin", t, re.S)
    assert re.search(r"Requires[^\n]*package\.json", t)


def test_docs_describe_section_23_delivery():
    t = (PLUGIN / "docs" / "technical" / "ARCHITECTURE.md").read_text()
    assert "node_modules/@ace-sdk/cli" in t and "package-lock.json" in t


def test_plugin_root_gitignore_keeps_node_modules_out():
    root_ignore = (REPO / ".gitignore").read_text()
    assert "node_modules/" in root_ignore
