#!/usr/bin/env python3
"""R3c RED — DESIGN §14: plugins/ace/engine/ layout + resolve.js version/export gate.

resolve.js contract (pinned here):
  `node engine/resolve.js` prints ONE JSON object on stdout
    {"ok": bool, "reason": str, "cli_path": str|null, "core_dir": str|null,
     "core_version": str|null, "min_core": "3.2.2"}
  and exits 0 when ok, 3 when the gate fails (3 = "engine unavailable, use ace-cli").
  Resolution: realpath(which ace-cli) -> @ace-sdk/cli package dir -> @ace-sdk/core
  (nested node_modules first, then hoisted next to the CLI) -> both
  dist/cjs/client/ace-client.js and dist/cjs/config/context.js exist -> core version >= 3.2.2
  -> requiring them yields a constructor `AceClient` (with searchPatterns/storeExecutionTrace/
  getConfig on its prototype) and a function `createContext`.
  `reason` codes: "ok" | "no_cli" | "core_missing" | "file_missing" | "core_too_old" | "core_too_new" | "export_missing".
  §23: a core under <plugin root>/node_modules wins over any ace-cli on PATH; cli_path is then optional.
"""
import json
import os
import subprocess
from pathlib import Path

import pytest

import engine_harness as E

pytestmark = pytest.mark.skipif(E.node_bin() is None, reason="node not installed")


def _resolve(bin_dir, **env):
    e = dict(os.environ, PATH=E.path_with(bin_dir))
    e.update(env)
    r = subprocess.run([E.node_bin(), str(E.ENGINE / "resolve.js")], capture_output=True, text=True,
                       env=e, timeout=20)
    return r.returncode, json.loads(r.stdout or "null"), r.stderr


def test_engine_dir_is_plain_node_no_build_no_deps():
    """§14/§23: plain Node files, no build step, no engine package.json/node_modules; the plugin package.json
    pins ONLY @ace-sdk/cli (the engine reads the core that CLI installs, never its own dependency)."""
    for f in ("search.js", "learn.js", "resolve.js"):
        assert (E.ENGINE / f).is_file(), "missing plugins/ace/engine/" + f
    assert not (E.ENGINE / "package.json").exists()
    assert not (E.ENGINE / "node_modules").exists()
    deps = json.loads((E.PLUGIN / "package.json").read_text())
    assert list(deps.get("dependencies", {})) == ["@ace-sdk/cli"], "§23: only the CLI pin, no engine dependency"
    assert not deps.get("devDependencies") and not deps.get("overrides")
    assert not list(E.ENGINE.glob("*.ts")), "no build step: plain .js only"


@pytest.mark.parametrize("layout", ["nested", "hoisted"])
def test_resolve_ok_nested_and_hoisted(tmp_path, layout):
    bin_dir = E.make_prefix(tmp_path, layout=layout)
    rc, out, err = _resolve(bin_dir)
    assert rc == 0, err
    assert out["ok"] is True and out["reason"] == "ok"
    assert out["core_version"] == "3.3.2"
    assert out["min_core"] == "3.2.2"
    assert os.path.realpath(out["core_dir"]).endswith(os.path.join("@ace-sdk", "core"))
    assert os.path.realpath(out["cli_path"]).endswith(os.path.join("@ace-sdk", "cli", "dist", "cli.js"))


def test_resolve_prefers_nested_over_hoisted(tmp_path):
    """The CLI uses its own nested copy; the engine must load the SAME copy."""
    bin_dir = E.make_prefix(tmp_path, layout="nested", version="3.3.2")
    hoisted = tmp_path / "npm-prefix" / "lib" / "node_modules" / "@ace-sdk" / "core"
    E._write_fake_core(hoisted, "3.2.9")
    rc, out, _ = _resolve(bin_dir)
    assert rc == 0 and out["core_version"] == "3.3.2"


def test_resolve_floor_version_is_accepted(tmp_path):
    rc, out, _ = _resolve(E.make_prefix(tmp_path, version="3.2.2"))
    assert rc == 0 and out["ok"] is True


@pytest.mark.parametrize("version", ["3.2.1", "3.1.9", "2.9.0"])
def test_resolve_rejects_core_below_floor(tmp_path, version):
    rc, out, _ = _resolve(E.make_prefix(tmp_path, version=version))
    assert rc == 3
    assert out["ok"] is False and out["reason"] == "core_too_old"
    assert out["core_version"] == version


def test_resolve_semver_compare_is_numeric(tmp_path):
    """3.10.0 >= 3.2.2 (string compare would say no)."""
    rc, out, _ = _resolve(E.make_prefix(tmp_path, version="3.10.0"))
    assert rc == 0 and out["ok"] is True


def test_resolve_no_ace_cli(tmp_path):
    rc, out, _ = _resolve(E.make_prefix(tmp_path, with_cli=False))
    assert rc == 3 and out["ok"] is False and out["reason"] == "no_cli"


def test_resolve_core_missing(tmp_path):
    rc, out, _ = _resolve(E.make_prefix(tmp_path, core=None))
    assert rc == 3 and out["ok"] is False and out["reason"] == "core_missing"


@pytest.mark.parametrize("missing", ["client/ace-client.js", "config/context.js"])
def test_resolve_private_file_missing(tmp_path, missing):
    rc, out, _ = _resolve(E.make_prefix(tmp_path, missing=missing))
    assert rc == 3 and out["ok"] is False and out["reason"] == "file_missing"


def test_resolve_export_missing(tmp_path):
    """The private file exists but no longer exports AceClient (a core refactor) -> gate fails."""
    rc, out, _ = _resolve(E.make_prefix(tmp_path, no_export=True))
    assert rc == 3 and out["ok"] is False and out["reason"] == "export_missing"


def test_resolve_does_not_execute_searches(tmp_path):
    """The gate only loads modules; it never calls the client (no network, no core log)."""
    log = tmp_path / "core.log"
    rc, _, _ = _resolve(E.make_prefix(tmp_path), ACE_FAKE_CORE_LOG=str(log))
    assert rc == 0
    assert not [r for r in E.read_jsonl(log) if r.get("op") in ("search", "learn", "learn_stream")]


@pytest.mark.skipif(E.real_core_dir() is None, reason="real ace-cli/@ace-sdk/core not installed")
def test_resolve_real_installed_cli():
    """The developer's real install (ace-cli 4.2.x + core 3.3.x, nested) passes the gate."""
    e = dict(os.environ)
    real_bin = os.path.join(E.real_cli_path().split("/lib/node_modules/")[0], "bin")  # npm prefix/bin
    e["PATH"] = os.pathsep.join([real_bin, "/usr/bin", "/bin"])
    r = subprocess.run([E.node_bin(), str(E.ENGINE / "resolve.js")], capture_output=True, text=True,
                       env=e, timeout=20)
    out = json.loads(r.stdout)
    assert r.returncode == 0 and out["ok"] is True
    assert os.path.realpath(out["core_dir"]) == os.path.realpath(str(E.real_core_dir()))


@pytest.mark.parametrize("version", ["4.0.0", "10.0.0"])
def test_resolve_rejects_unverified_major(tmp_path, version):
    """The export gate only checks method names on a private path: a new major is unverified."""
    rc, out, _ = _resolve(E.make_prefix(tmp_path, version=version))
    assert rc == 3 and out["reason"] == "core_too_new" and out["core_version"] == version


def test_resolve_skips_a_directory_named_ace_cli(tmp_path):
    """Like shutil.which: a directory with x-bit earlier on PATH is not the CLI."""
    bin_dir = E.make_prefix(tmp_path)
    decoy = tmp_path / "decoy"
    (decoy / "ace-cli").mkdir(parents=True)
    e = dict(os.environ, PATH=os.pathsep.join([str(decoy), str(bin_dir), "/usr/bin", "/bin"]))
    r = subprocess.run([E.node_bin(), str(E.ENGINE / "resolve.js")], capture_output=True, text=True, env=e, timeout=20)
    assert r.returncode == 0 and json.loads(r.stdout)["reason"] == "ok", r.stdout


def _resolve_local(plugin, path="/usr/bin:/bin"):
    r = subprocess.run([E.node_bin(), str(plugin / "engine" / "resolve.js")], capture_output=True, text=True,
                       env=dict(os.environ, PATH=path), timeout=20)
    return r.returncode, json.loads(r.stdout)


@pytest.mark.parametrize("layout", ["hoisted", "nested"])
def test_resolve_plugin_local_core_needs_no_cli_on_path(tmp_path, layout):
    plugin = E.make_plugin_local(tmp_path, layout=layout)
    rc, out = _resolve_local(plugin)
    assert rc == 0 and out["ok"] is True, out
    assert out["cli_path"] is None
    assert os.path.realpath(out["core_dir"]).startswith(os.path.realpath(str(plugin)))


def test_resolve_plugin_local_wins_over_global(tmp_path):
    bin_dir = E.make_prefix(tmp_path, version="3.2.9")
    rc, out = _resolve_local(E.make_plugin_local(tmp_path, version="3.3.2"), E.path_with(bin_dir))
    assert rc == 0 and out["core_version"] == "3.3.2"


@pytest.mark.parametrize("version,reason", [("3.2.1", "core_too_old"), ("4.0.0", "core_too_new")])
def test_resolve_plugin_local_keeps_the_version_gate(tmp_path, version, reason):
    rc, out = _resolve_local(E.make_plugin_local(tmp_path, version=version))
    assert rc == 3 and out["reason"] == reason


def test_engine_stderr_names_the_fetch_cause():
    """§26: 'fetch failed' alone made a real-server rc=1 undiagnosable; stderr must carry the cause code."""
    js = ("const {errText}=require(process.argv[1]);"
          "const e=new TypeError('fetch failed');e.cause=Object.assign(new Error('x'),{code:'ECONNRESET'});"
          "console.log(errText(e));console.log(errText(new Error('plain')));")
    r = subprocess.run([E.node_bin(), "-e", js, str(E.ENGINE / "resolve.js")], capture_output=True, text=True, timeout=20)
    assert r.stdout.splitlines() == ["fetch failed (ECONNRESET)", "plain"], r.stderr


# core >= 3.4.0 exports "./client" and "./config": load through them, deep dist/cjs paths only for older cores.
@pytest.mark.parametrize("missing", [None, "client/ace-client.js", "config/context.js"])
def test_resolve_uses_public_exports_when_present(tmp_path, missing):
    rc, out, err = _resolve(E.make_prefix(tmp_path, version="3.4.0", public=True, missing=missing))
    assert rc == 0 and out["ok"] is True, (out, err)
    assert out["load"] == "exports"


def test_resolve_falls_back_to_deep_paths_on_older_core(tmp_path):
    rc, out, _ = _resolve(E.make_prefix(tmp_path, version="3.3.2"))
    assert rc == 0 and out["load"] == "deep"


def test_resolve_public_exports_keep_the_version_and_export_gate(tmp_path):
    rc, out, _ = _resolve(E.make_prefix(tmp_path, version="4.0.0", public=True))
    assert rc == 3 and out["reason"] == "core_too_new"
    rc, out, _ = _resolve(E.make_prefix(tmp_path / "b", version="3.4.0", public=True, no_export=True))
    assert rc == 3 and out["reason"] == "export_missing"


_REPO_PLUGIN = Path(__file__).resolve().parent.parent / "plugins" / "ace"  # E.PLUGIN is a copy without node_modules
_PINNED_CORE = [_REPO_PLUGIN / "node_modules" / "@ace-sdk" / "cli" / "node_modules" / "@ace-sdk" / "core",
                _REPO_PLUGIN / "node_modules" / "@ace-sdk" / "core"]


@pytest.mark.skipif(not any((c / "package.json").is_file() for c in _PINNED_CORE),
                    reason="pinned CLI not installed: npm ci --ignore-scripts in plugins/ace")
def test_resolve_pinned_core_loads_through_public_exports():
    r = subprocess.run([E.node_bin(), str(_REPO_PLUGIN / "engine" / "resolve.js")], capture_output=True, text=True,
                       env=dict(os.environ, PATH="/usr/bin:/bin"), timeout=20)
    out = json.loads(r.stdout)
    assert r.returncode == 0 and out["ok"] is True, out
    assert out["load"] == "exports" and out["core_version"] >= "3.4.0"
