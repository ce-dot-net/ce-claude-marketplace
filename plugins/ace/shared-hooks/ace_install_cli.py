#!/usr/bin/env python3
"""ACE SessionStart (v8, DESIGN §3/§23): slim presence check. Sync row (startup|clear|resume): no whoami, no
network, no npm. The CLI is the one pinned in package.json and installed by Claude Code itself
(plugin-local); a global ace-cli >= the pin is the fallback; neither = one message naming
/ace:ace-install-cli (never disabled.flag). The async row (flag kept: `--update-check`) runs the
orphan sweep and the `npm rebuild better-sqlite3` when the binary does not load.

Caches under CLAUDE_PLUGIN_DATA: python_path (read by every shim) and cli_version.json
{path, mtime, version} of a GLOBAL ace-cli so `--version` (~1.2 s CPU) runs only when it changes.
Output: at most ONE JSON object (cc_hooks_reference.md: JSON alone on stdout). Always exit 0.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "utils"))

CC_FLOOR = "2.1.311"  # §16 P6 (SubagentStop double-fire fix)
_VER = re.compile(r"\d+\.\d+\.\d+")


def _tup(v):
    return tuple(int(x) for x in v.split("."))


def _cli_version(cli):
    """Version of the ace-cli binary, cached by (realpath, mtime)."""
    from plugin_data_dir import cli_version_file
    real = os.path.realpath(cli)
    mtime = os.stat(real).st_mtime
    f = cli_version_file()
    try:
        c = json.loads(f.read_text())
        if c.get("path") == real and c.get("mtime") == mtime and c.get("version"):
            return c["version"]
    except Exception:
        pass
    try:
        out = subprocess.run([cli, "--version"], capture_output=True, text=True, timeout=15).stdout
    except Exception:
        out = ""
    m = _VER.search(out)
    ver = m.group(0) if m else None  # None = unknown (cold probe timed out): never disable on it
    if m:  # never cache a failed probe
        try:
            _atomic_write(f, json.dumps({"path": real, "mtime": mtime, "version": ver}))
        except OSError:
            pass
    return ver


def _atomic_write(path, text):
    """tempfile + os.replace: the sync and async rows may write the same file concurrently."""
    import tempfile
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".")
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(text)
        os.replace(tmp, str(path))
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _write_if_changed(path, text):
    try:
        if not path.exists() or path.read_text() != text:
            path.write_text(text)
    except OSError:
        pass


def sweep_orphans(current_sid):
    """P-13: remove <root>/projects/*/sessions/<dir> untouched for 7 days (crashed / locked-out SessionEnd).
    Local, bounded, best-effort; never the current session, never non-dirs."""
    from plugin_data_dir import data_root
    cutoff, n = time.time() - 7 * 86400, 0
    try:
        for d in (data_root() / "projects").glob("*/sessions/*"):
            if n >= 200:
                break
            try:
                if d.is_dir() and d.name != current_sid and d.stat().st_mtime < cutoff:
                    shutil.rmtree(str(d), ignore_errors=True)
                    n += 1
            except OSError:
                pass
    except OSError:
        pass


# better-sqlite3 loads its native addon lazily (in the constructor), so `require` alone proves nothing.
# First line out = the Node ABI, so the check also names a binary built for another Node.
_SQLITE_PROBE = "console.log(process.versions.modules);new (require('better-sqlite3'))(':memory:').close()"


def _sqlite_loads(root):
    try:
        return subprocess.run(["node", "-e", _SQLITE_PROBE], cwd=root, capture_output=True, timeout=30).returncode == 0
    except Exception:
        return False


def rebuild_sqlite():
    """Async, every startup: CC installs deps with --ignore-scripts, so better-sqlite3 has no binary and
    ace-cli runs RAM-only (no pins, empty graph cache) until it is rebuilt (0.5 s, prebuilt). The only
    state is the binary itself: if it loads (new Database) in the CURRENT node, nothing to do; otherwise
    rebuild (scripts forced on, user .npmrc/env may say ignore-scripts) and verify the same way. That also
    covers a Node switch (nvm/volta) and a reinstall at the same plugin version. Best-effort, silent."""
    root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if os.environ.get("CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC") or not root or not (Path(root) / "node_modules" / "better-sqlite3").is_dir():
        return
    try:
        if _sqlite_loads(root):
            return
        env = dict(os.environ, npm_config_ignore_scripts="false")
        if subprocess.run(["npm", "rebuild", "better-sqlite3"], cwd=root, capture_output=True, timeout=120, env=env).returncode:
            return
        if _sqlite_loads(root):  # the early pin failure's backoff (first prompt raced this rebuild) is stale now
            from plugin_data_dir import pin_backoff_file
            try:
                pin_backoff_file().unlink()
            except OSError:
                pass
    except Exception:
        pass


def _cc_below_floor():
    """Running Claude Code version if it is parseable and below CC_FLOOR, else None (unknown never disables)."""
    v = os.environ.get("CLAUDE_CODE_VERSION", "")
    return v if _VER.fullmatch(v) and _tup(v) < _tup(CC_FLOOR) else None


def startup(ev, sid, pid, cli=None):
    """`cli`: a global ace-cli path to probe (default: the one on PATH)."""
    from ace_env import client_id
    from plugin_data_dir import disabled_flag, python_path_file
    flag = disabled_flag(pid, sid)

    def disable(reason):
        try:
            flag.write_text(reason)
        except OSError:
            pass

    try:
        flag.unlink()
    except OSError:
        pass
    _write_if_changed(python_path_file(), sys.executable)
    try:
        from ace_relevance_logger import archive_relevance_log
        archive_relevance_log()
    except Exception:
        pass

    try:  # auto-sync the installed statusline copy on plugin update
        dst, src = Path.home() / ".claude" / "ace_statusline.sh", Path(__file__).resolve().parent.parent / "scripts" / "ace_statusline.sh"
        if dst.is_file() and src.is_file() and dst.read_bytes() != src.read_bytes():
            shutil.copyfile(str(src), str(dst))
            dst.chmod(0o755)
    except OSError:
        pass
    old_cc = _cc_below_floor()
    if old_cc:  # §15: one message, every other hook exits silently on the flag
        disable("Claude Code %s < %s" % (old_cc, CC_FLOOR))
        return ["⛔ [ACE] ACE 8.0 needs Claude Code >= %s (you run %s). Update Claude Code; ACE hooks are paused."
                % (CC_FLOOR, old_cc)]
    import ace_cli
    g = cli or ace_cli.global_cli()
    cur = None
    if g and ace_cli.cli_source() != "plugin-local":
        cur = _cli_version(g)  # caches {path, mtime, version}: ace_cli.cli_argv() reads it without a spawn
        if cur is None:
            from plugin_data_dir import append_error
            append_error("%s version_unknown cli=%s (probe timed out/unparseable; ACE stays enabled)"
                         % (time.strftime("%Y-%m-%dT%H:%M:%S"), g))
    source = ace_cli.cli_source()
    try:
        from ace_relevance_logger import log_event
        log_event("cli_source", hook="SessionStart", session_id=sid, cli_source=source, cli_version=cur)
    except Exception:
        pass
    notice = []
    if not source:  # §23: never disable for this - ACE activates by itself once a CLI appears
        pin = ace_cli._pin()
        why = ("ace-cli v%s is older than the v%s this plugin was tested with" % (cur, pin)) if (g and cur) else "ace-cli not found"
        notice = ["⚠️ [ACE] %s. Run /ace:ace-install-cli. ACE learns once it is installed." % why]

    msgs = list(notice)
    old, new = Path.home() / ".ace" / "config.json", Path.home() / ".config" / "ace" / "config.json"
    try:
        if old.is_file() and '"apiToken"' in old.read_text():
            msgs.append("⚠️ [ACE] Deprecated config at ~/.ace/config.json. Run /ace-login to migrate.")
        if new.is_file():
            t = new.read_text()
            if '"apiToken"' in t and '"auth"' not in t:
                msgs.append("⚠️ [ACE] Old config format detected. Run /ace-login to migrate to device code auth.")
    except OSError:
        pass

    for stale in ("ace-review-result.json", "ace-eval-request.json"):  # previous session's self-eval state
        try:
            Path(".claude/data/logs", stale).unlink()
        except OSError:
            pass
    env_file = os.environ.get("CLAUDE_ENV_FILE")
    if env_file and not os.environ.get("ACE_CLIENT_ID"):  # DESIGN §8: same id as _ace_env.sh
        try:
            with open(env_file, "a") as f:
                f.write('export ACE_CLIENT_ID="%s"\n' % client_id())
        except OSError:
            pass
    return msgs


def main():
    from ace_env import read_event, resolve_ids
    ev = read_event()
    sid, pid = resolve_ids(ev)
    if "--update-check" in sys.argv[1:]:  # async row (name kept for hooks.json): sweep + sqlite rebuild
        try:
            sweep_orphans(ev.get("session_id"))
            rebuild_sqlite()
        except Exception:
            pass
        msgs = []
    else:
        msgs = startup(ev, sid, pid)
    if msgs:
        print(json.dumps({"systemMessage": "\n".join(msgs)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        main()
    except Exception as _e:
        try:
            from ace_relevance_logger import log_error
            log_error('SessionStart', 'ace_install_cli.main', error=_e)
        except Exception:
            pass
    sys.exit(0)
