#!/usr/bin/env python3
"""Round 3d RED: DESIGN §23 (FINAL on CLI delivery, overrides §21/§22), §19, §20.

Exact pin + committed lock, CC-native deps, resolution order plugin-local -> global -> none,
missing CLI never disables ACE, no npm view/install on any hook path, once-per-version sqlite
rebuild, ace-cli's stderr notifier never surfaces.

Contracts fixed here for GREEN:
- ace_cli.cli_argv() -> [node, <root>/node_modules/@ace-sdk/cli/dist/cli.js] | [<global ace-cli>] | None
  (no spawn: search/learn stay exactly one spawn; a global's version comes from the cli_version.json
  cache SessionStart writes). ace_cli.cli_source() -> "plugin-local" | "global" | None.
- scripts/ace-cli: the one wrapper commands call. Plugin-local bin first, then ace-cli on PATH,
  drops the notifier lines from stderr, keeps stdout and the exit code. Needed because §17's
  `node_modules/.bin/ace-cli` + fallback + §23's filter would otherwise be repeated in every
  bash block of 20 command files.
"""
import json
import re
import subprocess
from pathlib import Path

import pytest

from r3d_harness import BASH, NOTIFIER, PLUGIN, REPO, Box3d, system_message

PKG = PLUGIN / "package.json"
LOCK = PLUGIN / "package-lock.json"
PROD = sorted(list((PLUGIN / "shared-hooks").rglob("*.py")) + list((PLUGIN / "scripts").glob("*.sh")))


def _pkg():
    return json.loads(PKG.read_text())


def _lock():
    return json.loads(LOCK.read_text())


def _tup(v):
    return tuple(int(x) for x in v.split("."))


# ── §23: exact pin in package.json + committed lock ─────────────────────────────────────

def test_package_json_exact_pin_only():
    p = _pkg()
    assert p.get("private") is True
    assert list(p["dependencies"]) == ["@ace-sdk/cli"], p["dependencies"]
    assert re.fullmatch(r"\d+\.\d+\.\d+", p["dependencies"]["@ace-sdk/cli"]), "exact pin, no range"
    for key in ("devDependencies", "overrides", "optionalDependencies", "workspaces", "scripts"):
        assert key not in p, key


def test_lock_pin_equals_package_json_pin():
    lock = _lock()
    pin = _pkg()["dependencies"]["@ace-sdk/cli"]
    assert lock["lockfileVersion"] == 3
    assert lock["packages"][""]["dependencies"] == {"@ace-sdk/cli": pin}, "frozen resolution needs identical deps"
    assert lock["packages"]["node_modules/@ace-sdk/cli"]["version"] == pin


def test_lock_has_no_overrides_and_https_registry_only():
    lock = _lock()
    assert "overrides" not in lock and "overrides" not in lock["packages"][""]
    bad = [k for k, v in lock["packages"].items()
           if k and (v.get("link") or not str(v.get("resolved", "https://")).startswith("https://"))]
    assert bad == [], "CC skips the install on non-https / linked deps: %s" % bad[:5]


def test_pin_is_at_least_the_flag_complete_floor():
    assert _tup(_pkg()["dependencies"]["@ace-sdk/cli"]) >= (4, 1, 2)


def test_node_modules_is_git_ignored():
    # read the file, not `git check-ignore`: that exits 128 in a `git archive` export (no .git) - the §18 Linux gate
    lines = [l.strip() for l in (REPO / ".gitignore").read_text().splitlines()]
    assert any(l.rstrip("/") in ("node_modules", "**/node_modules", "plugins/ace/node_modules") for l in lines)


@pytest.mark.parametrize("rel", ["ace-cli-version.json", "shared-hooks/ace_cli_update.py"])
def test_superseded_section_21_22_artifacts_absent(rel):
    assert not (PLUGIN / rel).exists()


def test_no_latest_or_range_install_in_production():
    hits = [str(p) for p in PROD if re.search(r"@ace-sdk/cli@", p.read_text())]
    assert hits == []


# ── §23: resolution order ───────────────────────────────────────────────────────────────

def test_resolution_plugin_local_wins_over_global(tmp_path):
    b = Box3d(tmp_path, local=True, global_version="4.4.2")
    argv, source = b.resolve()
    assert source == "plugin-local"
    assert argv == [str(b.node), str(b.cli_js)]


def test_resolution_global_when_no_plugin_local(tmp_path):
    b = Box3d(tmp_path, global_version="4.4.2")
    argv, source = b.resolve()
    assert source == "global"
    assert len(argv) == 1 and Path(argv[0]).name == "ace-cli"


def test_resolution_none(tmp_path):
    assert tuple(Box3d(tmp_path).resolve()) == (None, None)


def test_resolution_plugin_local_without_node_falls_through_to_global(tmp_path):
    b = Box3d(tmp_path, local=True, global_version="4.4.2", node=False)
    assert b.resolve()[1] == "global"


def test_resolution_plugin_local_without_node_and_global_is_none(tmp_path):
    b = Box3d(tmp_path, local=True, node=False)
    assert tuple(b.resolve()) == (None, None)


def test_cli_argv_spawns_nothing(tmp_path):
    """Search/learn stay exactly ONE spawn (DESIGN §5 C2): no --version probe in the resolver."""
    b = Box3d(tmp_path, global_version="4.4.2")
    b.resolve()
    assert b.cli_calls() == []


def test_run_search_spawns_plugin_local(tmp_path):
    b = Box3d(tmp_path, local=True, global_version="4.4.2")
    res = b.py("import ace_cli; print(json.dumps(ace_cli.run_search('q', org='o', project='p')[0]))")
    assert res["retrieval_id"] == "r-r3d"
    assert [c["source"] for c in b.cli_calls()] == ["plugin-local"]


def test_run_learn_spawns_plugin_local(tmp_path):
    b = Box3d(tmp_path, local=True, global_version="4.4.2")
    b.py("import ace_cli; print(json.dumps(ace_cli.run_learn({'task': 't'}, org='o', project='p')[0]))")
    calls = b.cli_calls("learn")
    assert len(calls) == 1 and calls[0]["source"] == "plugin-local"
    assert "--no-stream" in calls[0]["argv"] and calls[0]["trace"] == {"task": "t"}


def test_check_auth_status_spawns_plugin_local(tmp_path):
    b = Box3d(tmp_path, local=True, global_version="4.4.2")
    b.py("import ace_cli; print(json.dumps(ace_cli.check_auth_status()))")
    assert [c["source"] for c in b.cli_calls("whoami")] == ["plugin-local"]


def test_ups_hook_runs_the_plugin_local_cli(tmp_path):
    b = Box3d(tmp_path, local=True, global_version="4.4.2")
    assert b.ups().returncode == 0
    assert [c["source"] for c in b.cli_calls("search")] == ["plugin-local"]


def test_one_helper_only_no_other_module_locates_the_cli():
    offenders = []
    for p in PROD:
        if p.name == "ace_cli.py":
            continue
        t = p.read_text()
        if re.search(r"which\(\s*['\"]ace-cli|CLI_CMD|\[\s*['\"]ace-cli['\"]|command -v ace-cli", t):
            offenders.append(p.name)
    assert offenders == [], "only ace_cli.cli_argv() may locate ace-cli: %s" % offenders


# ── §23 / §19: SessionStart presence check; a missing CLI NEVER disables ACE ────────────

def test_sessionstart_plugin_local_ok_silent(tmp_path):
    b = Box3d(tmp_path, local=True)
    p = b.session_start()
    assert p.returncode == 0, p.stderr
    assert "ace-cli" not in system_message(p) and b.flags() == []


def test_sessionstart_global_ok_silent_and_logged_as_global(tmp_path):
    b = Box3d(tmp_path, global_version="4.4.2")
    p = b.session_start()
    assert "ace-cli" not in system_message(p) and b.flags() == []
    assert any(r.get("cli_source") == "global" for r in b.relevance()), b.relevance()


def test_sessionstart_global_newer_than_pin_is_accepted(tmp_path):
    b = Box3d(tmp_path, global_version="5.0.0")
    assert b.session_start().returncode == 0
    assert b.flags() == [] and b.resolve()[1] == "global"


def test_sessionstart_no_cli_one_message_naming_repair_command_no_flag(tmp_path):
    b = Box3d(tmp_path)
    p = b.session_start()
    assert p.returncode == 0, p.stderr
    msg = system_message(p)
    assert "/ace:ace-install-cli" in msg, msg
    assert "npm install -g" not in msg and "DISABLED" not in msg
    assert b.flags() == [], "a missing CLI must never write disabled.flag (§23)"


def test_sessionstart_global_below_pin_message_no_flag_and_not_used(tmp_path):
    b = Box3d(tmp_path, global_version="4.0.0")
    msg = system_message(b.session_start())
    assert "/ace:ace-install-cli" in msg and "npm install -g" not in msg, msg
    assert b.flags() == []
    assert b.ups().returncode == 0
    assert b.cli_calls("search") == [], "a global below the pin floor is resolution step 3 (none)"


def test_floor_is_read_from_package_json(tmp_path):
    """§23: no MIN_VERSION constant survives; the pin in package.json is the single source."""
    b = Box3d(tmp_path, pin="9.9.9", global_version="4.4.2")
    assert "/ace:ace-install-cli" in system_message(b.session_start())


def test_ace_activates_by_itself_once_the_cli_appears(tmp_path):
    b = Box3d(tmp_path)
    b.session_start()
    assert b.ups().returncode == 0 and b.cli_calls("search") == []
    b.install_local()
    assert b.ups().returncode == 0
    assert len(b.cli_calls("search")) == 1, "no restart, no flag to clear"


def test_ups_with_no_cli_exits_zero_without_install_hint(tmp_path):
    b = Box3d(tmp_path)
    p = b.ups()
    assert p.returncode == 0 and "npm install -g" not in p.stdout + p.stderr


def test_cli_not_found_error_names_the_repair_command(tmp_path):
    b = Box3d(tmp_path)
    res = b.py("import ace_cli; print(json.dumps(ace_cli.run_search('q')[0]))")
    assert res["error"] == "cli_not_found"
    assert "/ace:ace-install-cli" in res["message"] and "npm install" not in res["message"]


# ── §23 / §20.1: no npm on hook paths ───────────────────────────────────────────────────

def test_update_check_machinery_is_gone():
    src = (PLUGIN / "shared-hooks" / "ace_install_cli.py").read_text()
    for gone in ("def update_check", "def update_notice", "update-check.json", '"show"', "Update available"):
        assert gone not in src, gone


def test_only_npm_spawn_in_production_is_the_sqlite_rebuild():
    spawns = []
    for p in PROD:
        for m in re.finditer(r"\[\s*['\"]npm['\"][^\]]*\]", p.read_text()):
            spawns.append((p.name, re.sub(r"\s+", " ", m.group(0))))
    assert spawns, "the §23 rebuild must exist"
    assert all("rebuild" in s and "better-sqlite3" in s for _, s in spawns), spawns


def test_sync_sessionstart_never_touches_npm(tmp_path):
    for src in ("startup", "clear"):
        b = Box3d(tmp_path / src, local=True)
        b.session_start(source=src)
        assert b.npm_calls() == []


def test_async_row_with_no_cli_makes_no_npm_call_and_writes_no_update_cache(tmp_path):
    """Global path: §23 removes the daily npm check entirely, not only for plugin-local."""
    b = Box3d(tmp_path, global_version="4.4.2")
    p = b.session_start_async()
    assert p.returncode == 0 and p.stdout == ""
    assert b.npm_calls() == []
    assert not (b.data / "update-check.json").exists()


# ── §23 / §17: async once-per-plugin-version sqlite rebuild ─────────────────────────────

def _rebuilds(b):
    return [c for c in b.npm_calls() if c["argv"][:2] == ["rebuild", "better-sqlite3"]]


def test_rebuild_runs_in_plugin_root_and_prints_nothing(tmp_path):
    b = Box3d(tmp_path, local=True)
    p = b.session_start_async()
    assert p.returncode == 0, p.stderr
    assert p.stdout == "", "async hooks print nothing"
    rb = _rebuilds(b)
    assert len(rb) == 1, b.npm_calls()
    assert Path(rb[0]["cwd"]).resolve() == b.root.resolve()
    assert all(c["argv"][:1] == ["rebuild"] for c in b.npm_calls())


def test_rebuild_verifies_the_binary_by_constructing_a_database(tmp_path):
    """better-sqlite3 loads the addon lazily: `require` exits 0 with no binary (measured). The -e code must
    construct a Database; fake node cannot tell, so assert the code itself."""
    b = Box3d(tmp_path, local=True)
    b.session_start_async()
    codes = [c["argv"][1] for c in b.node_evals()]
    assert codes and all("new (require('better-sqlite3'))(':memory:')" in c for c in codes), codes


def test_binary_that_loads_is_not_rebuilt_again(tmp_path):
    b = Box3d(tmp_path, local=True)
    b.session_start_async(sid="a")
    b.session_start_async(sid="b")
    assert len(_rebuilds(b)) == 1
    assert len(b.node_evals()) == 3, "probe, verify after the rebuild, probe again: one cheap node spawn per startup"


def test_binary_is_probed_on_every_startup_not_trusted_from_a_marker(tmp_path):
    """Node switch (nvm/volta/brew) or a reinstall at the same plugin version: the old marker said 'done'."""
    b = Box3d(tmp_path, local=True)
    b.session_start_async(sid="a")
    b.session_start_async(sid="b", FAKE_NODE_REQUIRE_RC=1)  # new Node ABI: the binary no longer loads
    assert len(_rebuilds(b)) == 2
    (b.tmp / "sqlite-built").unlink()  # reinstall wiped the build dir
    b.session_start_async(sid="c")
    assert len(_rebuilds(b)) == 3
    assert not list(b.data.glob("sqlite-rebuilt*")), "no version marker any more"


def test_no_rebuild_forever_marker_when_require_fails(tmp_path):
    b = Box3d(tmp_path, local=True)
    b.session_start_async(sid="a", FAKE_NODE_REQUIRE_RC=1)
    b.session_start_async(sid="b", FAKE_NODE_REQUIRE_RC=1)
    assert len(_rebuilds(b)) == 2, "a binary node cannot load must not be marked done"


def test_no_marker_when_rebuild_fails(tmp_path):
    b = Box3d(tmp_path, local=True)
    p = b.session_start_async(sid="a", FAKE_NPM_RC=1)
    assert p.returncode == 0 and p.stdout == ""
    b.session_start_async(sid="b", FAKE_NPM_RC=1)
    assert len(_rebuilds(b)) == 2


def test_rebuild_overrides_ignore_scripts_from_env_or_npmrc(tmp_path):
    """`npm_config_ignore_scripts=true` makes `npm rebuild` exit 0 and build nothing (measured)."""
    b = Box3d(tmp_path, local=True)
    b.session_start_async(npm_config_ignore_scripts="true")
    (rb,) = _rebuilds(b)
    assert rb["ignore_scripts"] == "false"


def test_successful_rebuild_clears_the_pin_backoff(tmp_path):
    """The first prompt can race the async rebuild and start the 30 min pin backoff; the rebuild ends it."""
    b = Box3d(tmp_path, local=True)
    bo = b.data / "pin-backoff"
    bo.write_text("")
    b.session_start_async(sid="a", FAKE_NODE_REQUIRE_RC=1)
    assert bo.exists(), "a rebuild that still does not load keeps the backoff"
    (b.tmp / "sqlite-built").unlink()
    b.session_start_async(sid="b", FAKE_NODE_REQUIRE_RC=None)
    assert not bo.exists()


def test_rebuild_skipped_under_disable_nonessential_traffic(tmp_path):
    b = Box3d(tmp_path, local=True)
    b.session_start_async(CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1)
    assert b.npm_calls() == []


def test_rebuild_skipped_without_plugin_local_deps(tmp_path):
    b = Box3d(tmp_path, global_version="4.4.2")
    b.session_start_async()
    assert b.npm_calls() == []


def test_rebuild_without_npm_on_path_is_silent(tmp_path):
    b = Box3d(tmp_path, local=True, npm=False)
    p = b.session_start_async()
    assert p.returncode == 0 and p.stdout == "" and p.stderr == ""


# ── §23 / §20.2: ace-cli's own stderr notifier ──────────────────────────────────────────

def test_hook_never_surfaces_the_notifier(tmp_path):
    b = Box3d(tmp_path, local=True)
    p = b.ups(FAKE_CLI_NOTIFY=1)
    assert p.returncode == 0
    assert "npm install -g" not in p.stdout + p.stderr and "Update available" not in p.stdout + p.stderr


def test_error_rows_filter_the_notifier_and_keep_the_real_error(tmp_path):
    b = Box3d(tmp_path, local=True)
    b.py("import ace_cli; print(json.dumps(ace_cli.run_search('q', org='o', project='p')[0]))",
         FAKE_CLI_NOTIFY=1, FAKE_CLI_RC=1, FAKE_CLI_STDERR="boom-real-error")
    rows = [r for r in b.relevance() if r.get("location") == "ace_cli_nonzero_exit"]
    assert rows, b.relevance()
    assert "boom-real-error" in rows[-1]["stderr_sample"], rows[-1]["stderr_sample"]
    assert "npm install -g" not in rows[-1]["stderr_sample"]


def _wrapper(b, *args, **env):
    return subprocess.run([BASH, str(b.root / "scripts" / "ace-cli")] + list(args), capture_output=True, text=True,
                          cwd=str(b.proj), env=b.env(**env), timeout=30)


def test_command_wrapper_is_plugin_local_first(tmp_path):
    b = Box3d(tmp_path, local=True, global_version="4.4.2")
    p = _wrapper(b, "search", "--json", "q")
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout)["retrieval_id"] == "r-r3d"
    assert [c["source"] for c in b.cli_calls()] == ["plugin-local"]


def test_command_wrapper_falls_back_to_global(tmp_path):
    b = Box3d(tmp_path, global_version="4.4.2")
    assert _wrapper(b, "--version").stdout.strip() == "4.4.2"
    assert [c["source"] for c in b.cli_calls()] == ["global"]


def test_command_wrapper_none_names_the_repair_command(tmp_path):
    p = _wrapper(Box3d(tmp_path), "search", "q")
    assert p.returncode != 0 and "/ace:ace-install-cli" in p.stderr
    assert "npm install -g" not in p.stderr


def test_command_wrapper_filters_notifier_keeps_stderr_stdout_and_rc(tmp_path):
    b = Box3d(tmp_path, local=True)
    p = _wrapper(b, "whoami", FAKE_CLI_NOTIFY=1, FAKE_CLI_STDERR="real-diagnostic", FAKE_CLI_RC=3)
    assert p.returncode == 3, "exit code survives the filter"
    assert "real-diagnostic" in p.stderr
    assert "Update available" not in p.stderr and "npm install -g" not in p.stderr
    q = _wrapper(b, "whoami", FAKE_CLI_NOTIFY=1)
    assert q.returncode == 0 and json.loads(q.stdout)["authenticated"] is True
    assert NOTIFIER.strip() not in q.stdout


# Bare `ace-cli` at a command position inside a bash block (prose and comments are fine).
_BARE = re.compile(r"(?:^|[\s;&|(`$])(?<![/\w-])ace-cli(?:\s|$)")
_FENCE = re.compile(r"```(?:bash|sh|shell)\n(.*?)```", re.S)
_FILES = sorted(p for p in (PLUGIN / "commands").glob("*.md") if "ace-cli" in p.read_text())


def _bare_lines(text):
    out = []
    for block in _FENCE.findall(text):
        for line in block.splitlines():
            code = line.split(" #")[0]
            if code.lstrip().startswith("#") or 'scripts/ace-cli' in code:
                continue
            if _BARE.search(code):
                out.append(line.strip())
    return out


@pytest.mark.parametrize("path", _FILES, ids=lambda p: p.name)
def test_command_bash_blocks_use_the_wrapper(path):
    """§17/§23: plugin-local first, notifier filtered. /ace:ace-install-cli may name the global fallback."""
    bare = _bare_lines(path.read_text())
    if path.name == "ace-install-cli.md":
        bare = [l for l in bare if "npm " not in l]
    assert bare == [], "%s: %s" % (path.name, bare[:5])


@pytest.mark.parametrize("path", [p for p in _FILES if _FENCE.search(p.read_text())], ids=lambda p: p.name)
def test_command_allows_the_wrapper(path):
    """`Bash(ace-cli:*)` does not match a path: without this every run prompts in default mode."""
    head = path.read_text().split("---", 2)[1]
    assert "scripts/ace-cli" in head, path.name


# ── the plugin root is where the code lives, not what the shared env file says ─────────────────

def test_foreign_plugin_root_does_not_hide_the_local_cli_or_the_floor(tmp_path):
    """§16 P5: other plugins export THEIR CLAUDE_PLUGIN_ROOT into the shared env file."""
    b = Box3d(tmp_path, local=True, global_version="4.4.2")
    foreign = tmp_path / "other-plugin"
    foreign.mkdir()
    assert b.resolve(CLAUDE_PLUGIN_ROOT=foreign)[1] == "plugin-local"
    assert b.py("import ace_cli; print(json.dumps(ace_cli._pin()))", CLAUDE_PLUGIN_ROOT=foreign) == b.pin
    p = subprocess.run([BASH, str(b.root / "scripts" / "ace-cli"), "--version"], capture_output=True, text=True,
                       cwd=str(b.proj), env=b.env(CLAUDE_PLUGIN_ROOT=foreign), timeout=30)
    assert p.returncode == 0 and [c["source"] for c in b.cli_calls()] == ["plugin-local"], p.stderr


def test_no_plugin_root_env_still_finds_the_local_cli(tmp_path):
    b = Box3d(tmp_path, local=True)
    assert b.resolve(CLAUDE_PLUGIN_ROOT=None)[1] == "plugin-local"
