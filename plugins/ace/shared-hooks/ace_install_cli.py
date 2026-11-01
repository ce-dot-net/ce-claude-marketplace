#!/usr/bin/env python3
"""ACE SessionStart (v8, DESIGN §3): slim CLI check. Sync row (startup|clear) has NO whoami and NO
network; the async `--update-check` row does the daily npm lookup.

Caches under CLAUDE_PLUGIN_DATA: python_path (read by every shim) and cli_version.json
{path, mtime, version} so `ace-cli --version` (~1.2 s CPU) runs only when the binary changes.
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

MIN_VERSION = "4.1.2"
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
    ver = m.group(0) if m else "0.0.0"
    if m:  # never cache a failed probe
        try:
            f.write_text(json.dumps({"path": real, "mtime": mtime, "version": ver}))
        except OSError:
            pass
    return ver


def _write_if_changed(path, text):
    try:
        if not path.exists() or path.read_text() != text:
            path.write_text(text)
    except OSError:
        pass


def update_check(cli):
    """Async daily npm check (cc_hooks_reference.md async: output reaches the next turn)."""
    if os.environ.get("CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC") or not cli:
        return None
    from plugin_data_dir import data_root
    cache = data_root() / "update-check.json"
    today = time.strftime("%Y%m%d")
    latest = ""
    try:
        c = json.loads(cache.read_text())
        if c.get("date") == today:
            latest = c.get("latest", "")
        else:
            c = None
    except Exception:
        c = None
    if c is None:
        try:
            latest = subprocess.run(["npm", "show", "@ace-sdk/cli", "version"], capture_output=True,
                                    text=True, timeout=20).stdout.strip()
        except Exception:
            latest = ""
        try:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps({"date": today, "latest": latest}))
        except OSError:
            pass
    cur = _cli_version(cli)
    if _VER.fullmatch(latest or "") and _tup(latest) > _tup(cur):
        return "💡 [ACE] Update available: v%s → v%s. Run: npm install -g @ace-sdk/cli" % (cur, latest)
    return None


def startup(ev, sid, pid, cli):
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

    if not cli:
        disable("CLI not installed")
        return ["⛔ [ACE] ace-cli not found. Install: npm install -g @ace-sdk/cli. ACE hooks DISABLED."]
    cur = _cli_version(cli)
    if _tup(cur) < _tup(MIN_VERSION):
        disable("CLI version %s < %s" % (cur, MIN_VERSION))
        return ["⛔ [ACE] Outdated CLI: v%s (requires >= v%s). Upgrade: npm install -g @ace-sdk/cli. "
                "ACE hooks DISABLED." % (cur, MIN_VERSION)]

    msgs = []
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
    try:  # auto-sync the installed statusline copy on plugin update
        dst, src = Path.home() / ".claude" / "ace_statusline.sh", Path(__file__).resolve().parent.parent / "scripts" / "ace_statusline.sh"
        if dst.is_file() and src.is_file() and dst.read_bytes() != src.read_bytes():
            shutil.copyfile(str(src), str(dst))
            dst.chmod(0o755)
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
    cli = shutil.which("ace-cli")
    if "--update-check" in sys.argv[1:]:
        msgs = [m for m in [update_check(cli)] if m]
    else:
        msgs = startup(ev, sid, pid, cli)
    if msgs:
        print(json.dumps({"systemMessage": "\n".join(msgs)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
