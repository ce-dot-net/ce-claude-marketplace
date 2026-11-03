"""WP-I (v8.0.0 round 2) — no removed mechanics in user-facing docs.

DESIGN §10 P-25/P-27 (MECHANICS_COVERAGE.md O1, P-25, P-27): README, docs/** and commands/*.md
must not describe mechanics that v8 removed. CHANGELOG.md is the ONLY place allowed to name them
(history). Note for /ace:ace-cleanup --legacy: it cleans legacy temp files without spelling the
removed literal path (e.g. `ace-*` files under the system temp dir).
"""
import re
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parent.parent / "plugins" / "ace"

STALE = {
    "PreCompact": r"PreCompact",
    "PermissionRequest": r"PermissionRequest",
    "ace_pretooluse_wrapper": r"ace_pretooluse_wrapper",
    "/tmp/ace-": r"/tmp/ace-",
    "ACE_ASYNC_LEARNING": r"ACE_ASYNC_LEARNING",
    "15000 (ms timeouts)": r"(?<!\d)15000(?!\d)",
    "ce-ace (old CLI name)": r"ce-ace",
    "claude plugin tag": r"claude plugin tag",
}


def _doc_files():
    files = [PLUGIN / "README.md"]
    files += sorted(p for p in (PLUGIN / "docs").rglob("*.md"))
    files += sorted((PLUGIN / "commands").glob("*.md"))
    return [p for p in files if p.name != "CHANGELOG.md"]


@pytest.mark.parametrize("label", sorted(STALE))
def test_no_stale_mechanic_outside_changelog(label):
    rx = re.compile(STALE[label])
    hits = []
    for p in _doc_files():
        for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if rx.search(line):
                hits.append("%s:%d" % (p.relative_to(PLUGIN), i))
    assert not hits, "stale mechanic %r still documented in: %s" % (label, hits)


@pytest.mark.parametrize("rel", [
    ".env.example",                      # P-25: v1-era ACE_SERVER_URL/ACE_API_TOKEN
    "PROMPT_HOOK_SUMMARY.md",            # P-25: v5.2.0 history, /tmp/ace_hook_debug.log
    "docs/V3.3.2_MIGRATION_STATUS.md",   # P-25: v3.3.2 migration status
])
def test_stale_file_deleted(rel):
    assert not (PLUGIN / rel).exists(), "stale file must be deleted: plugins/ace/" + rel


def test_scan_covers_the_expected_files():
    """Guard: the scan must actually include README, docs and commands."""
    names = {p.name for p in _doc_files()}
    assert {"README.md", "ARCHITECTURE.md", "CONFIGURATION.md", "TROUBLESHOOTING.md",
            "ace-doctor.md", "ace-cleanup.md"} <= names


# DESIGN §20.3: every update/install hint points at /ace:ace-install-cli, the one place allowed to
# mention the global fallback (§19). Wider net than _doc_files: hooks, scripts and the release agent too.
def _hint_files():
    repo = PLUGIN.parent.parent
    files = _doc_files() + [repo / ".claude" / "agents" / "release-manager.md"]
    files += sorted((PLUGIN / "shared-hooks").rglob("*.py")) + sorted((PLUGIN / "scripts").glob("*.sh"))
    files += sorted((PLUGIN / "mod").glob("*.ts")) + sorted((PLUGIN / "engine").glob("*.js"))  # the mod's systemMessage too
    return [p for p in files if p.name != "ace-install-cli.md"]


@pytest.mark.parametrize("path", _hint_files(), ids=lambda p: p.name)
def test_no_global_install_hint_outside_the_repair_command(path):
    bad = [i for i, l in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1)
           if re.search(r"npm (?:install|i) -g\b.*@ace-sdk/cli", l)]
    assert bad == [], "%s:%s must point at /ace:ace-install-cli" % (path.name, bad[:5])


def test_commands_never_tell_the_model_to_run_a_bare_ace_cli():
    """A clean machine has no global ace-cli: runnable lines go through the plugin wrapper (DESIGN §17/§23)."""
    bare = re.compile(r"(?:^\s*(?:\$\s*)?|: )ace-cli\s+(?:-|tune|search|learn|login|logout|whoami|bootstrap|status|domains|top|delta|doctor)\b")
    hits = [f"{p.name}:{n}" for p in sorted((PLUGIN / "commands").glob("*.md"))
            for n, l in enumerate(p.read_text().splitlines(), 1) if bare.search(l) and "scripts/ace-cli" not in l]
    assert hits == []
