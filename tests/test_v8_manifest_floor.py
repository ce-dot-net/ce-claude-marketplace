"""WP-E (v8.0.0) — manifest `Requires:` floor text.

§16 P6 + §23: floor is Claude Code >= 2.1.311; the ace-cli floor is the pin in plugins/ace/package.json; @ace-sdk/core >= the core the pinned cli locks (3.8.1 since cli 4.4.1).
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
def test_manifest_requires_claude_code_2_1_311(name):
    """§16 P6: Requires: Claude Code >= 2.1.311 in every manifest description."""
    assert _floor(_entry(name)["description"], "Claude Code") == "2.1.311"


@pytest.mark.parametrize("name", sorted(MANIFESTS))
def test_manifest_keeps_ace_cli_and_core_floors(name):
    """§23: `Requires:` ace-cli text comes from package.json; the core floor is the core in package-lock.json."""
    desc = _entry(name)["description"]
    pkg = Path(__file__).resolve().parent.parent / "plugins" / "ace" / "package.json"
    assert _floor(desc, "ace-cli") == json.loads(pkg.read_text())["dependencies"]["@ace-sdk/cli"]
    lock = json.loads((pkg.parent / "package-lock.json").read_text())["packages"]
    assert _floor(desc, "@ace-sdk/core") == lock["node_modules/@ace-sdk/core"]["version"]


@pytest.mark.parametrize("name", sorted(MANIFESTS))
def test_manifest_description_mentions_its_own_version(name):
    """Guard (test_v600_version_bump): WP-E must not bump versions nor drop the vX.Y.Z mention."""
    e = _entry(name)
    assert ("v" + e["version"]) in e["description"]


def test_pin_supports_search_session_id():
    """The CLI search path passes `--session-id` (unpinned session stamp): needs @ace-sdk/cli >= 4.3.1, pinned exactly."""
    pin = json.loads((REPO / "plugins" / "ace" / "package.json").read_text())["dependencies"]["@ace-sdk/cli"]
    assert re.fullmatch(r"\d+\.\d+\.\d+", pin), pin
    assert tuple(map(int, pin.split("."))) >= (4, 3, 1)


def test_pin_is_at_least_4_3_2():
    """SDK asked for cli >= 4.3.2 (learn Idempotency-Key, search session_id validation; core ^3.5.0)."""
    pin = json.loads((REPO / "plugins" / "ace" / "package.json").read_text())["dependencies"]["@ace-sdk/cli"]
    assert tuple(map(int, pin.split("."))) >= (4, 3, 2)


def test_pin_is_at_least_4_3_4():
    """SDK 4.3.4 / core 3.7.0: learn retries POST /traces (4 attempts, same Idempotency-Key), one stderr line per retry."""
    pin = json.loads((REPO / "plugins" / "ace" / "package.json").read_text())["dependencies"]["@ace-sdk/cli"]
    assert tuple(map(int, pin.split("."))) >= (4, 3, 4)


def test_pin_is_exactly_4_4_1_with_core_3_8_1():
    """8.1.0: SDK 4.4.1 / core 3.8.1 (context --json, init --json writes the main checkout of a worktree, exit codes 3-9). Exact pin, lock to npmjs."""
    pin = json.loads((REPO / "plugins" / "ace" / "package.json").read_text())["dependencies"]["@ace-sdk/cli"]
    assert pin == "4.4.1"
    lock = json.loads((REPO / "plugins" / "ace" / "package-lock.json").read_text())["packages"]
    assert lock["node_modules/@ace-sdk/cli"]["version"] == "4.4.1" and lock["node_modules/@ace-sdk/core"]["version"] == "3.8.1"
    assert all(v.get("resolved", "https://registry.npmjs.org/").startswith("https://registry.npmjs.org/") for v in lock.values() if v.get("resolved"))
