"""
RED tests for ace-doctor.md sync with ground truth.

These tests pin the doctor command to the real hooks.json, real script names,
and real npm package name.  They FAIL against the stale file and pass once
ace-doctor.md is corrected.

Run with:
    python3 -m pytest tests/test_ace_doctor_sync.py -q
"""

import json
import re
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent
HOOKS_JSON = REPO_ROOT / "plugins" / "ace" / "hooks" / "hooks.json"
DOCTOR_MD = REPO_ROOT / "plugins" / "ace" / "commands" / "ace-doctor.md"


def _hooks() -> dict:
    return json.loads(HOOKS_JSON.read_text())


def _doc() -> str:
    return DOCTOR_MD.read_text(encoding="utf-8")


def _wrapper_basenames() -> list[str]:
    """Return every script basename registered in hooks.json (unique, sorted)."""
    data = _hooks()
    scripts: set[str] = set()
    for event_entries in data["hooks"].values():
        for entry in event_entries:
            for hook in entry.get("hooks", []):
                cmd = hook.get("command", "")
                # strip path prefix and flags: take the filename portion only
                script_file = cmd.split("/")[-1].split()[0]
                if script_file.endswith(".sh"):
                    scripts.add(script_file)
    return sorted(scripts)


# ---------------------------------------------------------------------------
# 1. Every wrapper script from hooks.json must appear in ace-doctor.md
# ---------------------------------------------------------------------------

class TestHookScriptsPresent:
    """Every .sh basename registered in hooks.json must appear in ace-doctor.md."""

    def test_all_hook_scripts_mentioned(self):
        doc = _doc()
        missing = [s for s in _wrapper_basenames() if s not in doc]
        assert not missing, (
            f"ace-doctor.md is missing these hook scripts from hooks.json: "
            f"{missing}"
        )


# ---------------------------------------------------------------------------
# 2. Dead script names must NOT appear anywhere
# ---------------------------------------------------------------------------

class TestDeadScriptNamesAbsent:

    def test_ace_task_complete_wrapper_absent(self):
        doc = _doc()
        assert "ace_task_complete_wrapper.sh" not in doc, (
            "ace-doctor.md references 'ace_task_complete_wrapper.sh' which "
            "does not exist in hooks.json or on disk — must be removed."
        )

    def test_ace_after_task_wrapper_absent(self):
        doc = _doc()
        assert "ace_after_task_wrapper.sh" not in doc, (
            "ace-doctor.md references 'ace_after_task_wrapper.sh' which is "
            "NOT registered in hooks.json (orphaned script) — must be removed."
        )


# ---------------------------------------------------------------------------
# 3. npm package must be @ace-sdk/cli; stale names must be absent
# ---------------------------------------------------------------------------

class TestNpmPackageName:

    def test_ace_sdk_cli_present(self):
        doc = _doc()
        assert "@ace-sdk/cli" in doc, (
            "ace-doctor.md does not mention '@ace-sdk/cli' — the correct npm "
            "package name for the ACE CLI."
        )

    def test_ce_dot_net_ace_client_absent(self):
        doc = _doc()
        assert "@ce-dot-net/ace-client" not in doc, (
            "ace-doctor.md still references '@ce-dot-net/ace-client' which is "
            "the stale/superseded package name — must be removed."
        )

    def test_ce_dot_net_ace_sdk_cli_absent(self):
        doc = _doc()
        # The old scoped variant: @ce-dot-net/ace-sdk-cli
        assert "@ce-dot-net/ace-sdk-cli" not in doc, (
            "ace-doctor.md references '@ce-dot-net/ace-sdk-cli' which is wrong; "
            "the correct package is '@ace-sdk/cli'."
        )


# ---------------------------------------------------------------------------
# 4. Install path must be dynamic; hardcoded 'marketplaces/' layout must be absent
# ---------------------------------------------------------------------------

class TestInstallPath:

    def test_no_hardcoded_marketplaces_path(self):
        doc = _doc()
        assert "/plugins/marketplaces/" not in doc, (
            "ace-doctor.md contains a hardcoded '/plugins/marketplaces/' install "
            "path which does not exist.  Use $CLAUDE_PLUGIN_ROOT or the cache "
            "path ~/.claude/plugins/cache/..."
        )


# ---------------------------------------------------------------------------
# 5. Hook event completeness — all 10 events must be mentioned
# ---------------------------------------------------------------------------

EXPECTED_EVENTS = [
    "PreToolUse",
    "PreCompact",
    "SessionStart",
    "UserPromptSubmit",
    "PostToolUse",
    "PermissionRequest",
    "PermissionDenied",
    "Stop",
    "SessionEnd",
    "SubagentStop",
]


class TestHookEventsMentioned:

    def test_all_hook_events_mentioned(self):
        doc = _doc()
        missing = [ev for ev in EXPECTED_EVENTS if ev not in doc]
        assert not missing, (
            f"ace-doctor.md is missing these hook event names: {missing}"
        )


# ---------------------------------------------------------------------------
# 6. Hook count: doc must not claim '5/5' (real total is 10+)
# ---------------------------------------------------------------------------

class TestHookCount:

    def test_no_five_of_five_hook_count(self):
        doc = _doc()
        # Match patterns like "5/5" in hook context
        assert "5/5" not in doc, (
            "ace-doctor.md still uses '5/5' hook count — there are 10 registered "
            "hook events, so the count must be updated (e.g. 10/10)."
        )

    def test_no_three_of_five_hook_count(self):
        doc = _doc()
        assert "3/5" not in doc, (
            "ace-doctor.md still uses '3/5' hook count (warn example) — must be "
            "updated to reflect the real hook total (e.g. n/10)."
        )

    def test_no_zero_of_five_hook_count(self):
        doc = _doc()
        assert "0/5" not in doc, (
            "ace-doctor.md still uses '0/5' hook count — must be updated."
        )

    def test_no_four_of_five_hook_count(self):
        doc = _doc()
        assert "4/5" not in doc, (
            "ace-doctor.md still uses '4/5' hook count — must be updated."
        )


# ---------------------------------------------------------------------------
# 7. Stale version strings must be absent
# ---------------------------------------------------------------------------

class TestVersionStrings:

    def test_no_v5_1_2_plugin_version(self):
        doc = _doc()
        assert "v5.1.2" not in doc, (
            "ace-doctor.md still references plugin version 'v5.1.2' which is "
            "obsolete — current release is v7.0.0."
        )

    def test_no_v5_1_1_plugin_version(self):
        doc = _doc()
        assert "v5.1.1" not in doc, (
            "ace-doctor.md still references plugin version 'v5.1.1' which is "
            "obsolete — current release is v7.0.0."
        )

    def test_no_v1_0_9_cli_version(self):
        doc = _doc()
        assert "v1.0.9" not in doc, (
            "ace-doctor.md still references ace-cli version 'v1.0.9' — floor is "
            "now 4.0.1."
        )

    def test_no_v1_0_8_cli_version(self):
        doc = _doc()
        assert "v1.0.8" not in doc, (
            "ace-doctor.md still references ace-cli version 'v1.0.8' — floor is "
            "now 4.0.1."
        )

    def test_ace_cli_floor_is_4_1_2(self):
        doc = _doc()
        # Must mention 4.1.2 as the minimum CLI version somewhere
        assert "4.1.2" in doc, (
            "ace-doctor.md does not mention ace-cli floor version 4.1.2."
        )


# ---------------------------------------------------------------------------
# 8. Stale auth model: 'apiToken' and 'organizations[0].apiKey' must be absent
# ---------------------------------------------------------------------------

class TestAuthModel:

    def test_no_organizations_apikey_format(self):
        doc = _doc()
        assert ".organizations[0].apiKey" not in doc, (
            "ace-doctor.md still checks '.organizations[0].apiKey' — this is "
            "the deprecated ace-cli v1.x format; current auth uses device-code "
            "tokens (ace-cli login)."
        )

    def test_no_stale_multi_org_label(self):
        doc = _doc()
        # "multi-org format (ace-cli v1.x)" is stale labeling
        assert "multi-org format (ace-cli v1.x)" not in doc, (
            "ace-doctor.md still describes 'multi-org format (ace-cli v1.x)' as "
            "the expected CLI config format — this is stale; v4.x uses device-code."
        )

    def test_no_ace_cli_configure_subcommand(self):
        doc = _doc()
        # 'ace-cli configure' doesn't exist; it's 'ace-cli config' or 'ace-cli login'
        assert "ace-cli configure" not in doc, (
            "ace-doctor.md references 'ace-cli configure' which is not a valid "
            "subcommand — use 'ace-cli login' for auth migration."
        )

    def test_check7_pass_label_uses_device_code_not_multi_org(self):
        """Check 7 PASS example must say '(device-code)', not '(multi-org)'."""
        doc = _doc()
        # The old standalone parenthetical survives the broader stale-label removal
        assert "(multi-org)" not in doc, (
            "ace-doctor.md Check 7 PASS example still says '(multi-org)' — "
            "the new auth model is device-code; change it to '(device-code)'."
        )

    def test_no_api_token_in_check2_if_failed(self):
        """Check 2 'If Failed' block must not tell users to supply an API Token."""
        doc = _doc()
        assert "API Token (starts with ace_)" not in doc, (
            "ace-doctor.md Check 2 'If Failed' still says 'API Token (starts with "
            "ace_)' — device-code login does not require a manually provided token; "
            "the correct action is 'run ace-cli login'."
        )

    def test_no_missing_fields_apitoken_in_check2_if_incomplete(self):
        """Check 2 'If Incomplete' block must not list v1.x-only 'apiToken' field."""
        doc = _doc()
        assert "Missing fields: apiToken" not in doc, (
            "ace-doctor.md Check 2 'If Incomplete' still lists 'apiToken' as a "
            "missing field — this is a v1.x-only field that cannot be missing in "
            "a valid v4.x config; remove it and update the remediation to 'ace-cli login'."
        )

    def test_no_verify_server_url_in_config_remediation(self):
        """Network-failure remediation must NOT tell users to verify the dead v1.x serverUrl field.

        In ace-cli 4.x the server URL is baked into the binary; it is NOT a
        user-editable field in ~/.config/ace/config.json (that field is gone).
        The doc itself notes at line ~96 that serverUrl is a dead v1.x field.
        Pointing users there to fix connectivity is wrong and contradictory.
        """
        doc = _doc()
        assert "Verify serverUrl in" not in doc, (
            "ace-doctor.md network-failure block still says 'Verify serverUrl in "
            "~/.config/ace/config.json' — serverUrl is a dead v1.x config field "
            "(the doc says so at line ~96). Replace with v4.x guidance: "
            "confirm auth via 'ace-cli whoami --json'."
        )


# ---------------------------------------------------------------------------
# 9. Project settings key: must use .env.ACE_PROJECT_ID, not top-level .projectId
# ---------------------------------------------------------------------------

class TestProjectConfigKey:

    def test_check3_uses_env_ace_project_id(self):
        doc = _doc()
        # Check 3 bash block must use .env.ACE_PROJECT_ID
        # Find Check 3 section
        match = re.search(
            r"### Check 3:.*?(?=### Check 4:)",
            doc,
            re.DOTALL,
        )
        assert match is not None, "Check 3 section not found in ace-doctor.md"
        check3 = match.group(0)
        # The jq command should use .env.ACE_PROJECT_ID, not bare .projectId
        bash_match = re.search(r"```bash\n(.*?)```", check3, re.DOTALL)
        assert bash_match is not None, "No bash block in Check 3"
        bash = bash_match.group(1)
        assert ".env.ACE_PROJECT_ID" in bash, (
            "Check 3 bash block must use '.env.ACE_PROJECT_ID' (not '.projectId') "
            "to match what ace-configure.md actually writes to settings.json."
        )
