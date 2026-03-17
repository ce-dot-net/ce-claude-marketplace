"""
Tests for Task 4: Version Bump to 6.0.1

All version files should be 6.0.1, descriptions should mention CC >= 2.1.69,
and wrapper version constants should be updated.
"""

import json
import os

PLUGIN_DIR = os.path.join(os.path.dirname(__file__), '..', 'plugins', 'ace')
PLUGIN_JSON = os.path.join(PLUGIN_DIR, '.claude-plugin', 'plugin.json')
TEMPLATE_JSON = os.path.join(PLUGIN_DIR, '.claude-plugin', 'plugin.template.json')
MARKETPLACE_JSON = os.path.join(os.path.dirname(__file__), '..', '.claude-plugin', 'marketplace.json')
STOP_WRAPPER = os.path.join(PLUGIN_DIR, 'scripts', 'ace_stop_wrapper.sh')
SUBAGENT_STOP_WRAPPER = os.path.join(PLUGIN_DIR, 'scripts', 'ace_subagent_stop_wrapper.sh')


def _read(path):
    with open(path) as f:
        return f.read()


def _read_json(path):
    return json.loads(_read(path))


class TestVersionNumbers:
    """All version files should be 6.0.1."""

    def test_plugin_json_version_is_600(self):
        """plugin.json version field is 6.0.1."""
        data = _read_json(PLUGIN_JSON)
        assert data['version'] == '6.0.1', \
            f"plugin.json version is {data['version']}, expected 6.0.1"

    def test_marketplace_json_version_is_600(self):
        """marketplace.json ace plugin version is 6.0.1."""
        data = _read_json(MARKETPLACE_JSON)
        ace_plugin = next(p for p in data['plugins'] if p['name'] == 'ace')
        assert ace_plugin['version'] == '6.0.1', \
            f"marketplace.json version is {ace_plugin['version']}, expected 6.0.1"

    def test_all_versions_match(self):
        """All version files should be consistent (6.0.1)."""
        plugin = _read_json(PLUGIN_JSON)['version']
        template = _read_json(TEMPLATE_JSON)['version']
        marketplace = _read_json(MARKETPLACE_JSON)
        mp_version = next(p for p in marketplace['plugins'] if p['name'] == 'ace')['version']

        versions = {
            'plugin.json': plugin,
            'plugin.template.json': template,
            'marketplace.json': mp_version,
        }
        unique = set(versions.values())
        assert len(unique) == 1, \
            f"Version mismatch: {versions}"
        assert '6.0.1' in unique, \
            f"Versions are consistent but not 6.0.1: {unique}"


class TestDescriptions:
    """Descriptions should reference v6.0.1 and CC >= 2.1.69."""

    def test_description_mentions_cc_2169(self):
        """Description mentions Claude Code >= 2.1.69."""
        data = _read_json(PLUGIN_JSON)
        desc = data['description']
        assert '2.1.69' in desc, \
            f"Description does not mention CC 2.1.69: {desc}"

    def test_description_mentions_v600(self):
        """Description mentions v6.0.1."""
        data = _read_json(PLUGIN_JSON)
        desc = data['description']
        assert 'v6.0.1' in desc or '6.0.1' in desc, \
            f"Description does not mention v6.0.1: {desc}"


class TestWrapperVersionConstants:
    """All wrappers with ACE_PLUGIN_VERSION should have 6.0.1."""

    def test_wrapper_version_constants_updated(self):
        """ACE_PLUGIN_VERSION in stop wrappers should be 6.0.1."""
        for wrapper_path in [STOP_WRAPPER, SUBAGENT_STOP_WRAPPER]:
            content = _read(wrapper_path)
            assert 'ACE_PLUGIN_VERSION="6.0.1"' in content, \
                f"{os.path.basename(wrapper_path)} does not have ACE_PLUGIN_VERSION=\"6.0.1\""

    def test_all_wrapper_versions_are_600(self):
        """All wrappers with ACE_PLUGIN_VERSION should be 6.0.1."""
        scripts_dir = os.path.join(PLUGIN_DIR, 'scripts')
        stale = []
        for fname in os.listdir(scripts_dir):
            if not fname.endswith('.sh'):
                continue
            fpath = os.path.join(scripts_dir, fname)
            content = _read(fpath)
            if 'ACE_PLUGIN_VERSION=' in content:
                if 'ACE_PLUGIN_VERSION="6.0.1"' not in content:
                    stale.append(fname)
        assert len(stale) == 0, \
            f"Stale ACE_PLUGIN_VERSION in: {stale}"


class TestCeAceRemoved:
    """ce-ace is removed — no references should remain in scripts or Python."""

    def test_no_ce_ace_in_scripts(self):
        """No wrapper script should reference ce-ace (removed CLI)."""
        scripts_dir = os.path.join(PLUGIN_DIR, 'scripts')
        found = []
        for fname in os.listdir(scripts_dir):
            if not fname.endswith('.sh'):
                continue
            fpath = os.path.join(scripts_dir, fname)
            content = _read(fpath)
            if 'ce-ace' in content:
                found.append(fname)
        assert len(found) == 0, \
            f"ce-ace references found in scripts (removed CLI): {found}"

    def test_no_ce_ace_in_python(self):
        """No Python shared-hook should reference ce-ace."""
        shared_hooks = os.path.join(PLUGIN_DIR, 'shared-hooks')
        found = []
        for root, dirs, files in os.walk(shared_hooks):
            dirs[:] = [d for d in dirs if d != '__pycache__']
            for fname in files:
                if not fname.endswith('.py'):
                    continue
                fpath = os.path.join(root, fname)
                content = _read(fpath)
                if 'ce-ace' in content:
                    found.append(os.path.relpath(fpath, PLUGIN_DIR))
        assert len(found) == 0, \
            f"ce-ace references found in Python (removed CLI): {found}"


class TestDevPluginFiles:
    """Dev-only plugin files should also have 6.0.1."""

    def test_production_json_version(self):
        """plugin.PRODUCTION.json version is 6.0.1."""
        prod = os.path.join(PLUGIN_DIR, 'plugin.PRODUCTION.json')
        if os.path.exists(prod):
            data = _read_json(prod)
            assert data['version'] == '6.0.1', \
                f"plugin.PRODUCTION.json version is {data['version']}"

    def test_local_json_version(self):
        """plugin.local.json version is 6.0.1."""
        local = os.path.join(PLUGIN_DIR, 'plugin.local.json')
        if os.path.exists(local):
            data = _read_json(local)
            assert data['version'] == '6.0.1', \
                f"plugin.local.json version is {data['version']}"
