#!/usr/bin/env python3
"""The ONE installer of the plugin-local pinned ace-cli (8.1.1). Callers: SessionStart (both chains: `ensure`),
the mod's band button, the mod's /ace:ace-install-cli confirm and the markdown fallback (`--run`).

Reads only this plugin's own package.json (the exact pin) and package-lock.json. `npm ci --ignore-scripts` from
the lockfile, then `npm rebuild better-sqlite3`; never `npm install`, never touches the lock, cwd = the plugin root
(never the user's project), registry = whatever the lockfile's resolved URLs say (replace-registry-host=never).
State under CLAUDE_PLUGIN_DATA: cli-install.lock (one installer at a time) and cli-install.json (last result).

CLI (always exit 0, one JSON line on stdout {"state": ...}):
  --ensure   decide; start a detached background `--run --auto` when due        (SessionStart)
  --wait     --ensure, then block (<= 400 s) until no installer holds the lock   (the mod's quiet window)
  --run      install now in the foreground; add --auto for the throttled/opt-out rules (the detached child)
  --status   what --ensure would see, no side effects                            (doctor)
states: ok | started | running | failed | off | unavailable
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

RETRY_S = 3600           # after a failure: one attempt per plugin version per hour
STEP_TIMEOUT_S = 240     # per npm step
LOCK_STALE_S = 900       # a live lock older than this is a hung installer's (ci 240 + rebuild 240 + margin)
WAIT_S = 400
_SEMVER = re.compile(r"\d+\.\d+\.\d+")


def _ace_cli():
    import ace_cli
    return ace_cli


def _pdd():
    import plugin_data_dir
    return plugin_data_dir


def root():
    return _ace_cli()._plugin_root()


def pin(r=None):
    try:
        v = json.loads(((r or root()) / "package.json").read_text())["dependencies"]["@ace-sdk/cli"]
        return v if _SEMVER.fullmatch(v) else None
    except Exception:
        return None


def installed_version(r=None):
    """Version of the plugin-local CLI if its entry point exists, else None."""
    r = r or root()
    try:
        base = r / "node_modules" / "@ace-sdk" / "cli"
        if not (base / "dist" / "cli.js").is_file():
            return None
        return json.loads((base / "package.json").read_text()).get("version")
    except Exception:
        return None


def _key(r):
    return "%s:%s" % (r.name, pin(r))  # <cache dir = plugin version>:<pin>


def _read(path):
    try:
        d = json.loads(Path(path).read_text())
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _alive(pid):
    try:
        os.kill(int(pid), 0)
        return True
    except ProcessLookupError:
        return False
    except Exception:
        return True  # PermissionError etc.: it exists


def lock_held(now=None):
    now = time.time() if now is None else now
    d = _read(_pdd().cli_install_lock())
    return bool(d) and now - float(d.get("at", 0)) < LOCK_STALE_S and _alive(d.get("pid", 0))


def _acquire():
    path = _pdd().cli_install_lock()
    for _ in range(2):
        try:
            fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        except FileExistsError:
            if lock_held():
                return False
            try:
                path.unlink()
            except OSError:
                return False
            continue
        except OSError:
            return False
        with os.fdopen(fd, "w") as f:
            f.write(json.dumps({"pid": os.getpid(), "at": time.time()}))
        return True
    return False


def _release():
    try:
        _pdd().cli_install_lock().unlink()
    except OSError:
        pass


def _log(line):
    _pdd().append_error("%s cli_auto_install %s" % (time.strftime("%Y-%m-%dT%H:%M:%S"), line))


def _unsafe_node_modules(r):
    """node_modules a symlink that leaves the plugin dir: never install through it."""
    nm = r / "node_modules"
    if not nm.is_symlink():
        return False
    real, base = os.path.realpath(str(nm)), os.path.realpath(str(r))
    return os.path.commonpath([real, base]) != base


def _bad_lock(r):
    """No lockfile, or a resolved URL that is not https: refuse (the registry is what the lock says)."""
    try:
        pk = json.loads((r / "package-lock.json").read_text()).get("packages", {})
    except Exception:
        return True
    return any(isinstance(v, dict) and v.get("resolved") and not str(v["resolved"]).startswith("https://") for v in pk.values())


def decide(auto=True, now=None, env=None):
    """(state, detail). `auto` = the SessionStart rules (opt-out, managed, throttle); manual skips those three."""
    env = os.environ if env is None else env
    now = time.time() if now is None else now
    r = root()
    p = pin(r)
    if not p:
        return "unavailable", "no exact pin in package.json"
    if installed_version(r) == p:
        return "ok", p
    if auto and env.get("ACE_AUTO_INSTALL") == "0":
        return "off", "ACE_AUTO_INSTALL=0"
    if auto and env.get("CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"):
        return "unavailable", "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC is set"
    if not shutil.which("npm") or not shutil.which("node"):
        return "unavailable", "npm or node not on PATH"
    if _unsafe_node_modules(r):
        return "unavailable", "node_modules is a symlink leaving the plugin dir"
    if _bad_lock(r):
        return "unavailable", "package-lock.json missing or not https-only"
    if not os.access(str(r), os.W_OK):
        return "unavailable", "plugin dir is read-only"
    if lock_held(now):
        return "running", ""
    st = _read(_pdd().cli_install_state())
    if auto and st.get("key") == _key(r) and not st.get("ok") and now - float(st.get("at", 0)) < RETRY_S:
        return "failed", str(st.get("error", ""))
    return "start", ""


def _spawn():
    subprocess.Popen([sys.executable, os.path.abspath(__file__), "--run", "--auto"], cwd=str(root()),
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


def ensure(now=None):
    """SessionStart / the mod: start the background install when due. Never blocks, never raises."""
    try:
        s, d = decide(True, now)
        if s == "start":
            try:
                _spawn()
                return {"state": "started"}
            except OSError as e:
                return {"state": "failed", "detail": "spawn: %s" % e}
        return {"state": s, "detail": d}
    except Exception as e:
        return {"state": "unavailable", "detail": str(e)[:120]}


def _npm(args, cwd, ignore_scripts):
    env = dict(os.environ, npm_config_ignore_scripts="true" if ignore_scripts else "false",
               npm_config_replace_registry_host="never", npm_config_audit="false", npm_config_fund="false",
               npm_config_update_notifier="false")
    p = subprocess.run(["npm"] + args, cwd=str(cwd), env=env, capture_output=True, text=True, timeout=STEP_TIMEOUT_S)
    return p.returncode, (p.stderr or p.stdout or "").strip()


def run(auto=False):
    """Install now. Returns {"state": ok|running|failed|off|unavailable, "detail"}; records the result."""
    s, d = decide(auto)
    if s in ("off", "unavailable", "failed"):
        return {"state": s, "detail": d}
    if s == "ok":
        return {"state": "ok", "detail": d}
    if not _acquire():
        return {"state": "running", "detail": ""}
    r, t0, err, rebuild = root(), time.time(), "", ""
    try:
        if _unsafe_node_modules(r):  # re-check under the lock
            raise RuntimeError("node_modules is a symlink leaving the plugin dir")
        rc, out = _npm(["ci", "--ignore-scripts", "--no-audit", "--no-fund"], r, True)
        if rc:
            raise RuntimeError("npm ci exit %s: %s" % (rc, out[-300:]))
        rc, out = _npm(["rebuild", "better-sqlite3"], r, False)
        rebuild = "" if not rc else " (npm rebuild exit %s: ACE runs RAM-only until SessionStart's rebuild works)" % rc
        if installed_version(r) != pin(r):
            raise RuntimeError("installed %s, expected %s" % (installed_version(r), pin(r)))
    except subprocess.TimeoutExpired:
        err = "timeout after %ss" % STEP_TIMEOUT_S
    except Exception as e:
        err = str(e)[:400]
    finally:
        _release()
    ok = not err
    try:
        _pdd().private_write(_pdd().cli_install_state(), json.dumps({"key": _key(r), "ok": ok, "at": time.time(), "error": err}))
    except Exception:
        pass
    _log("%s plugin=%s pin=%s secs=%d%s" % ("ok" if ok else "FAILED", r.name, pin(r), time.time() - t0,
                                                 (rebuild if ok else " " + err.replace("\n", " "))))
    if ok:  # the early pin failure's backoff (first prompt raced this install) is stale now
        try:
            _pdd().pin_backoff_file().unlink()
        except OSError:
            pass
    return {"state": "ok", "detail": pin(r)} if ok else {"state": "failed", "detail": err}


def status(now=None):
    s, d = decide(True, now)
    return {"state": "started" if s == "start" else s, "detail": d}


def wait():
    res = ensure()
    t0 = time.time()
    while res["state"] in ("started", "running") and time.time() - t0 < WAIT_S:
        time.sleep(1)
        if not lock_held():
            time.sleep(0.5)  # the child may not hold the lock yet right after the spawn
            if not lock_held():
                break
    s, d = decide(True)
    return {"state": "ok" if s == "ok" else s if s in ("failed", "off", "unavailable") else "failed", "detail": d}


def main(argv):
    try:
        if "--run" in argv:
            out = run("--auto" in argv)
        elif "--wait" in argv:
            out = wait()
        elif "--status" in argv:
            out = status()
        else:
            out = ensure()
    except Exception as e:
        out = {"state": "unavailable", "detail": str(e)[:120]}
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
