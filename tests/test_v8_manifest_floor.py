"""WP-E (v8.0.0) — manifest `Requires:` floor text.

DESIGN §1: floor is Claude Code >= 2.1.300, ace-cli >= 4.1.2, @ace-sdk/core >= 3.2.2.
WP-E updates ONLY the floor text/description, NOT the version number (release-manager does).
Supersedes tests/test_v712_features.py::TestFloorBump::test_plugin_json_description_cc_floor_2_1_163
(merge agent: that 2.1.163 pin must be rewritten/removed).
"""
import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
MANIFESTS = {
    "plugin.json": REPO / "plugins" / "ace" / ".claude-plugin" / "plugin.json",
    "plugin.template.json": REPO / "plugins" / "ace" / ".claude-plugin" / "plugin.template.json",
    "marketplace.json": REPO / ".claude-plugin" / "marketplace.json",
}


def _entry(name):
    data = json.loads(MANIFESTS[name].read_text())
    if "plugins" in data:
        data = next(p for p in data["plugins"] if p["name"] == "ace")
    return data


def _floor(desc, pkg):
    m = re.search(r"Requires:.*?%s\s*>=\s*v?([\d.]+)" % re.escape(pkg), desc)
    return m.group(1) if m else None


@pytest.mark.parametrize("name", sorted(MANIFESTS))
def test_manifest_requires_claude_code_2_1_300(name):
    """DESIGN §1: Requires: Claude Code >= 2.1.300 in every manifest description."""
    assert _floor(_entry(name)["description"], "Claude Code") == "2.1.300"


@pytest.mark.parametrize("name", sorted(MANIFESTS))
def test_manifest_keeps_ace_cli_and_core_floors(name):
    """DESIGN §0/§1: ace-cli / core floors unchanged (4.1.2 / 3.2.2) — SDK is off-limits."""
    desc = _entry(name)["description"]
    assert _floor(desc, "ace-cli") == "4.1.2"
    assert _floor(desc, "@ace-sdk/core") == "3.2.2"


@pytest.mark.parametrize("name", sorted(MANIFESTS))
def test_manifest_description_mentions_its_own_version(name):
    """Guard (test_v600_version_bump): WP-E must not bump versions nor drop the vX.Y.Z mention."""
    e = _entry(name)
    assert ("v" + e["version"]) in e["description"]
