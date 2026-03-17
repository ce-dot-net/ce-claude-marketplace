"""
Tests for version consistency across all plugin files.

All version files should match the version in plugin.json, descriptions should
mention CC >= 2.1.69, and wrapper version constants should be updated.
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


def _current_version():
    """Read the canonical version from plugin.json."""
    return _read_json(PLUGIN_JSON)['version']


class TestVersionNumbers:
    """All version files should match the canonical plugin.json version."""

    def test_plugin_json_version_is_set(self):
        """plugin.json version field is a valid semver string."""
        version = _current_version()
        parts = version.split('.')
        assert len(parts) == 3, f"Version {version} is not semver"
        assert all(p.isdigit() for p in parts), f"Version {version} has non-numeric parts"

    def test_marketplace_json_version_matches(self):
        """marketplace.json ace plugin version matches plugin.json."""
        expected = _current_version()
        data = _read_json(MARKETPLACE_JSON)
        ace_plugin = next(p for p in data['plugins'] if p['name'] == 'ace')
        assert ace_plugin['version'] == expected, \
            f"marketplace.json version is {ace_plugin['version']}, expected {expected}"

    def test_all_versions_match(self):
        """All version files should be consistent."""
        expected = _current_version()
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
        assert expected in unique, \
            f"Versions are consistent but not {expected}: {unique}"


class TestDescriptions:
    """Descriptions should reference the current version and CC >= 2.1.69."""

    def test_description_mentions_cc_2169(self):
        """Description mentions Claude Code >= 2.1.69."""
        data = _read_json(PLUGIN_JSON)
        desc = data['description']
        assert '2.1.69' in desc, \
            f"Description does not mention CC 2.1.69: {desc}"

    def test_description_mentions_current_version(self):
        """Description mentions the current version."""
        data = _read_json(PLUGIN_JSON)
        version = data['version']
        desc = data['description']
        assert version in desc, \
            f"Description does not mention v{version}: {desc}"


class TestWrapperVersionConstants:
    """All wrappers with ACE_PLUGIN_VERSION should match plugin.json."""

    def test_wrapper_version_constants_updated(self):
        """ACE_PLUGIN_VERSION in stop wrappers should match plugin.json."""
        expected = _current_version()
        for wrapper_path in [STOP_WRAPPER, SUBAGENT_STOP_WRAPPER]:
            content = _read(wrapper_path)
            assert f'ACE_PLUGIN_VERSION="{expected}"' in content, \
                f"{os.path.basename(wrapper_path)} does not have ACE_PLUGIN_VERSION=\"{expected}\""

    def test_all_wrapper_versions_match(self):
        """All wrappers with ACE_PLUGIN_VERSION should match plugin.json."""
        expected = _current_version()
        scripts_dir = os.path.join(PLUGIN_DIR, 'scripts')
        stale = []
        for fname in os.listdir(scripts_dir):
            if not fname.endswith('.sh'):
                continue
            fpath = os.path.join(scripts_dir, fname)
            content = _read(fpath)
            if 'ACE_PLUGIN_VERSION=' in content:
                if f'ACE_PLUGIN_VERSION="{expected}"' not in content:
                    stale.append(fname)
        assert len(stale) == 0, \
            f"Stale ACE_PLUGIN_VERSION in: {stale}"


class TestCeAceRemoved:
    """ce-ace is removed -- no references should remain in scripts or Python."""

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
    """Dev-only plugin files should also match the canonical version."""

    def test_production_json_version(self):
        """plugin.PRODUCTION.json version matches plugin.json."""
        expected = _current_version()
        prod = os.path.join(PLUGIN_DIR, 'plugin.PRODUCTION.json')
        if os.path.exists(prod):
            data = _read_json(prod)
            assert data['version'] == expected, \
                f"plugin.PRODUCTION.json version is {data['version']}, expected {expected}"

    def test_local_json_version(self):
        """plugin.local.json version matches plugin.json."""
        expected = _current_version()
        local = os.path.join(PLUGIN_DIR, 'plugin.local.json')
        if os.path.exists(local):
            data = _read_json(local)
            assert data['version'] == expected, \
                f"plugin.local.json version is {data['version']}, expected {expected}"
