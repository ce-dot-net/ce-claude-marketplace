"""The suite must stay hermetic once a developer ran `npm ci` in plugins/ace (release-manager pin bump, DESIGN §17):
the hooks would find the REAL ace-cli next to their own code and bypass every fake (89 failures, measured)."""
import pytest

from plugin_copy import REPO_PLUGIN, hermetic_root


def _fake_plugin(tmp_path, with_modules):
    root = tmp_path / "ace"
    (root / "shared-hooks" / "utils").mkdir(parents=True)
    (root / "shared-hooks" / "utils" / "ace_cli.py").write_text("# x\n")
    (root / "package.json").write_text("{}")
    if with_modules:
        (root / "node_modules" / "@ace-sdk" / "cli" / "dist").mkdir(parents=True)
    return root


def test_clean_checkout_runs_the_repo_plugin_itself(tmp_path):
    root = _fake_plugin(tmp_path, with_modules=False)
    assert hermetic_root(root) == root


def test_checkout_with_node_modules_runs_a_copy_without_them(tmp_path):
    root = _fake_plugin(tmp_path, with_modules=True)
    h = hermetic_root(root)
    assert h != root and (h / "package.json").is_file() and not (h / "node_modules").exists()
    assert (root / "node_modules").is_dir(), "the developer's install is never touched"


def test_hooks_never_resolve_the_real_cli_when_node_modules_exist(tmp_path):
    """In-process: ace_cli beside a populated node_modules still falls to the fakes under the suite's env."""
    if (REPO_PLUGIN / "node_modules").exists():
        import ace_cli
        argv, src = ace_cli._resolve()
        assert src != "plugin-local", (argv, src)
    else:
        pytest.skip("no node_modules here: nothing to isolate from (the CI order)")
