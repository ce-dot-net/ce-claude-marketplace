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
