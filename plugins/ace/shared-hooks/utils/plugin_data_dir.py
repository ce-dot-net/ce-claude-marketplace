#!/usr/bin/env python3
"""v8 state layout (DESIGN §4, contract C3, §10 P-19) — the ONLY way to compute state paths.

Project ids are the server `prj_...` ids from ace_project_context (single scheme).
Root = $CLAUDE_PLUGIN_DATA (exported to hook processes) else the real CC data dir.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

# ═══════════════════════════════════════════════════════════════════════════
# v8 state layout (DESIGN §4, contract C3) — the ONLY way to compute state paths.
# Root = $CLAUDE_PLUGIN_DATA (exported to hook processes, cc_hooks_reference.md:480)
# else ~/.claude/plugins/data/ace (cc_plugins_reference.md:559).
# Helpers never raise: a mkdir failure just leaves the path uncreated and the
# caller's own write fails (and is swallowed there).
# ═══════════════════════════════════════════════════════════════════════════
import re as _re

_SAFE_COMPONENT = _re.compile(r"[^A-Za-z0-9._-]")


def _safe(component: Optional[str]) -> str:
    """Hook-supplied ids are untrusted: never let them leave the data root."""
    s = _SAFE_COMPONENT.sub("_", str(component or ""))
    if s in ("", ".", ".."):
        return "default" if not s else "_"
    return s


def _mk(path: Path, private: bool = False) -> Path:
    try:
        path.mkdir(parents=True, exist_ok=True)
        if private:  # §24: holds prompts / traces
            os.chmod(path, 0o700)
    except OSError:
        pass
    return path


def private_dir(path: Path) -> Path:
    return _mk(Path(path), private=True)


def private_write(path, text: str) -> None:
    """Atomic create+rename, mode 0600 (mkstemp), dir 0700 (§24: traces and state hold user prompts)."""
    import tempfile
    path = Path(path)
    private_dir(path.parent)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".w-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def project_log_unsafe(path, base=None) -> bool:
    """§24: <cwd>/.claude/data/logs is repo-controlled. True when writing `path` could leave the project: a symlinked
    component of a relative path (or the target), or a resolved dir outside cwd. An absolute dir (an explicit
    log_dir) only must not itself be, or hold the target as, a symlink."""
    path = Path(path)
    if path.is_symlink():
        return True
    if path.is_absolute() and base:  # 8.1.0: logs keyed to the repo root: the same walk, from that root
        try:
            path = path.relative_to(base)
        except ValueError:
            return True
    elif path.is_absolute():
        return path.parent.is_symlink()
    base = Path(base or os.getcwd())
    cur = base
    for part in path.parent.parts:
        cur = cur / part
        if cur.is_symlink():
            return True
    try:
        (base / path).parent.resolve().relative_to(base.resolve())
    except (ValueError, OSError):
        return True
    return False


def open_project_log(path, append: bool = True, base=None):
    """Open a <cwd>/.claude/data/logs file for writing without following a symlinked target (O_NOFOLLOW),
    or None when project_log_unsafe. Creates the dir."""
    path = Path(path)
    if project_log_unsafe(path, base):
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    if project_log_unsafe(path, base):  # re-check after mkdir: nothing may have been swapped in
        return None
    flags = os.O_WRONLY | os.O_CREAT | (os.O_APPEND if append else os.O_TRUNC) | getattr(os, "O_NOFOLLOW", 0)
    return os.fdopen(os.open(str(path), flags, 0o600), "a" if append else "w")  # 0600: rows carry prompts


def data_root() -> Path:
    explicit = os.environ.get("CLAUDE_PLUGIN_DATA")
    # §16 P5: other plugins export THEIR CLAUDE_PLUGIN_DATA into the shared CLAUDE_ENV_FILE; ours is ace-*.
    if explicit and Path(explicit).name.startswith("ace"):
        return Path(explicit)
    return _fallback_root()


def _fallback_root() -> Path:
    """Non-hook consumers have no CLAUDE_PLUGIN_DATA. Order (P-19): CC's real dir
    ~/.claude/plugins/data/<plugin>-<marketplace> (derived from CLAUDE_PLUGIN_ROOT
    .../cache/<marketplace>/<plugin>/<ver>, else ace-ce-dot-net-marketplace) when it
    exists, else $XDG_DATA_HOME/ace, else the real dir."""
    base = Path.home() / ".claude" / "plugins" / "data"
    real = base / "ace-ce-dot-net-marketplace"
    root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if root:
        parts = Path(root).parts
        if "cache" in parts:
            i = len(parts) - 1 - parts[::-1].index("cache")
            if len(parts) > i + 2:
                real = base / ("%s-%s" % (parts[i + 2], parts[i + 1]))
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg and not real.is_dir():
        return Path(xdg) / "ace"
    return real


def project_dir(project_id: Optional[str], create: bool = True) -> Path:
    p = data_root() / "projects" / _safe(project_id)
    return _mk(p) if create else p


def session_dir(project_id: Optional[str], session_id: Optional[str], create: bool = True) -> Path:
    p = project_dir(project_id, create=False) / "sessions" / _safe(session_id)
    return _mk(p, private=True) if create else p


def _file(path: Path) -> Path:
    _mk(path.parent)
    return path


def python_path_file() -> Path:
    return _file(data_root() / "python_path")


def cli_version_file() -> Path:
    return _file(data_root() / "cli_version.json")


def errors_log() -> Path:
    return _file(data_root() / "logs" / "ace-hook-errors.log")


def search_cache_dir() -> Path:
    return _mk(data_root() / "cache" / "search")


def domains_file(project_id: Optional[str]) -> Path:
    return _file(project_dir(project_id, create=False) / "domains.json")


RENDER_FULL_PCT_MAX_AGE = 7 * 86400


def render_full_pct_file() -> Path:
    """The server's §31 full share (search response `render_full_pct`), {"pct": N, "at": <epoch>}."""
    return data_root() / "render-full-pct.json"


def _valid_pct(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 100


def feedback_downvote_file() -> Path:
    """The server's rejection-downvote gate (search response `feedback_downvote`), {"on": bool, "at": <epoch>}."""
    return data_root() / "feedback-downvote.json"


CLIENT_POLICY_KEYS = ("min_plugin_version", "recommended_plugin_version", "message", "url")
_VERSION_RE = r"\d{1,4}\.\d{1,4}\.\d{1,4}"
_POLICY_TEXT_MAX = 200


def client_policy_file() -> Path:
    """8.1.4 (dormant until the server sends it): the search response's `client_policy`, {"policy": {...}, "at": <epoch>}."""
    return data_root() / "client-policy.json"


def valid_client_policy(v):
    """(policy, None) with only the known keys, or (None, reason). Same rules as mod lib/cohort.ts validClientPolicy."""
    import re
    if not isinstance(v, dict):
        return None, "not_an_object"
    out = {}
    for k in CLIENT_POLICY_KEYS:
        if k not in v:
            continue
        x = v[k]
        if not isinstance(x, str) or len(x) > _POLICY_TEXT_MAX:
            return None, "bad_" + k
        if re.search(r"[\x00-\x1f\x7f-\x9f\u200e\u200f\u202a-\u202e\u2066-\u2069]", x):
            return None, "bad_" + k
        if k.endswith("_version") and not re.fullmatch(_VERSION_RE, x):
            return None, "bad_" + k
        if k == "url" and (not x.startswith("https://") or re.search(r"[\s\"'<>\\`]", x)):
            return None, "bad_" + k
        out[k] = x
    return out, None


def _ver(v):
    import re
    return tuple(int(x) for x in v.split(".")) if isinstance(v, str) and re.fullmatch(_VERSION_RE, v) else None


def stored_client_policy(now=None):
    """The stored policy when valid and younger than 7 days, else None."""
    try:
        import json, time
        d = json.loads(client_policy_file().read_text())
        at = d.get("at")
        pol, _ = valid_client_policy(d.get("policy"))
        if pol is not None and isinstance(at, (int, float)) and (time.time() if now is None else now) - at < RENDER_FULL_PCT_MAX_AGE:
            return pol
    except Exception:
        pass
    return None


def client_policy_state(version, now=None):
    """None (quiet) | "recommended" | "min" for the running plugin version; unknown version forms stay quiet."""
    pol, mine = stored_client_policy(now), _ver(version)
    if not pol or mine is None:
        return None
    mn, rec = _ver(pol.get("min_plugin_version")), _ver(pol.get("recommended_plugin_version"))
    if mn and mine < mn:
        return "min"
    if rec and mine < rec:
        return "recommended"
    return None


def client_policy_band(version):
    """The ONE line below min (mod band, Python SessionStart message). ACE stays on and keeps learning."""
    return "ACE %s ist zu alt, bitte /plugin update ausführen" % version if client_policy_state(version) == "min" else None


def client_policy_line(version):
    """The /ace:ace-doctor line, or None."""
    st = client_policy_state(version)
    if not st:
        return None
    pol = stored_client_policy() or {}
    if st == "min":
        return "update   ACE %s ist zu alt (min %s), bitte /plugin update ausführen" % (version, pol["min_plugin_version"])
    line = "update   ACE %s · empfohlen %s" % (version, pol["recommended_plugin_version"])
    if pol.get("message"):
        line += ": " + pol["message"]
    if pol.get("url"):
        line += " · " + pol["url"]
    return line


def store_server_switches(resp) -> None:
    """Persist the valid top-level server switches of a search response (latest wins; a missing or invalid field keeps
    the stored value): `render_full_pct` (int 0-100), `feedback_downvote` (bool), 8.1.4 `client_policy` (object; an
    invalid one is dropped and logged as client_policy_invalid with the reason only). Never raises."""
    import json, time
    r = resp if isinstance(resp, dict) else {}
    if "client_policy" in r:
        try:
            pol, why = valid_client_policy(r["client_policy"])
            if pol is not None:
                private_write(client_policy_file(), json.dumps({"policy": pol, "at": int(time.time())}))
            else:
                from ace_relevance_logger import log_event
                log_event("client_policy_invalid", reason=why)
        except Exception:
            pass
    try:
        if _valid_pct(r.get("render_full_pct")):
            private_write(render_full_pct_file(), json.dumps({"pct": r["render_full_pct"], "at": int(time.time())}))
    except Exception:
        pass
    try:
        if isinstance(r.get("feedback_downvote"), bool):
            private_write(feedback_downvote_file(), json.dumps({"on": r["feedback_downvote"], "at": int(time.time())}))
    except Exception:
        pass


def stored_feedback_downvote() -> bool:
    """The stored server gate when younger than 7 days, else False (default off)."""
    try:
        import json, time
        d = json.loads(feedback_downvote_file().read_text())
        at = d.get("at")
        return d.get("on") is True and isinstance(at, (int, float)) and time.time() - at < RENDER_FULL_PCT_MAX_AGE
    except Exception:
        return False


def stored_render_full_pct() -> Optional[int]:
    """The stored server share when valid and younger than 7 days, else None."""
    try:
        import json, time
        d = json.loads(render_full_pct_file().read_text())
        at = d.get("at")
        if _valid_pct(d.get("pct")) and isinstance(at, (int, float)) and time.time() - at < RENDER_FULL_PCT_MAX_AGE:
            return d["pct"]
    except Exception:
        pass
    return None


def disabled_flag(project_id: Optional[str], session_id: Optional[str]) -> Path:
    return _file(session_dir(project_id, session_id, create=False) / "disabled.flag")


def cli_install_lock() -> Path:
    return _file(data_root() / "cli-install.lock")


def cli_install_state() -> Path:
    return _file(data_root() / "cli-install.json")


def sqlite_probe_file() -> Path:
    return _file(data_root() / "sqlite-probe.json")


def pin_backoff_file() -> Path:
    return _file(data_root() / "pin-backoff")


def agent_prompts_dir(project_id, session_id) -> Path:
    return _mk(session_dir(project_id, session_id, create=False) / "agent-prompts")


def agent_prompt_file(project_id, session_id, prompt_id, agent_type) -> Path:
    name = "%s-%s.json" % (_safe(prompt_id), _safe(agent_type))
    return agent_prompts_dir(project_id, session_id) / name


def project_disabled_flag(project_id: Optional[str]) -> Path:
    return _file(project_dir(project_id, create=False) / "disabled.flag")


def is_disabled(project_id: Optional[str], session_id: Optional[str]) -> bool:
    """P-26: session flag OR project flag. Never creates directories."""
    try:
        return (project_dir(project_id, create=False) / "disabled.flag").exists() or \
            (session_dir(project_id, session_id, create=False) / "disabled.flag").exists()
    except OSError:
        return False


def mod_active_marker(project_id: Optional[str], session_id: Optional[str]) -> Path:
    """§13.1: the mod touches this at session.start / every prompt.submit. Never creates dirs."""
    return session_dir(project_id, session_id, create=False) / "mod-active"


# The mod rewrites mod-active right before every event whose Python hook must step aside (prompt.submit before the
# UPS, agent.spawn, tool.call, classic.Stop/SubagentStop). A crashed or unloaded mod (Claude Code unloads user mods
# after 3 worker crashes) stops writing, so the Python chain takes over within seconds instead of 10 minutes.
MOD_HANDOFF_S = 15      # hooks that run right after a mod write: UPS, PreToolUse(Agent), SubagentStart, Stop, SubagentStop
MOD_AFTER_TOOL_S = 120  # hooks after a tool ran (domain shift, tool accumulation): the tool's own time sits in between


def is_mod_active(project_id: Optional[str], session_id: Optional[str], max_age: float = MOD_AFTER_TOOL_S) -> bool:
    """True when the mod-active marker is younger than max_age -> the Python hook early-exits."""
    try:
        import time
        return time.time() - mod_active_marker(project_id, session_id).stat().st_mtime < max_age
    except OSError:
        return False


def mod_owns_learn(project_id: Optional[str], session_id: Optional[str], max_age: float = MOD_AFTER_TOOL_S) -> bool:
    """True when the mod is active AND its classic.* hooks run (mod-classic fresh). On seats where the managed-settings
    guard filters them, the mod's turn.complete does not learn, so the Python Stop/SubagentStop must."""
    try:
        import time
        return is_mod_active(project_id, session_id, max_age) and time.time() - (
            session_dir(project_id, session_id, create=False) / "mod-classic").stat().st_mtime < max_age
    except OSError:
        return False


MOD_COMPACT_S = 300  # item A: mod-compact is written as the compaction starts; SessionStart(compact) follows its summary


def mod_handled_compact(project_id: Optional[str], session_id: Optional[str], max_age: float = MOD_COMPACT_S) -> bool:
    """True when the mod's session.compact hook handled this compaction (its prompt.compose re-adds the patterns):
    the Python SessionStart(compact) re-inject steps aside. Guarded seats never run session.compact."""
    try:
        import time
        return time.time() - (session_dir(project_id, session_id, create=False) / "mod-compact").stat().st_mtime < max_age
    except OSError:
        return False


def learn_lock(project_id: Optional[str], session_id: Optional[str], agent: Optional[str]) -> Path:
    name = "learn-inflight-%s.lock" % _safe(agent or "main")
    return _file(session_dir(project_id, session_id, create=False) / name)


def domain_last_file(project_id, session_id, agent) -> Path:
    name = "domain-last-%s.txt" % _safe(agent or "main")
    return _file(session_dir(project_id, session_id, create=False) / name)


def tools_db(project_id, session_id) -> Path:
    return _file(session_dir(project_id, session_id, create=False) / "tools.db")


def patterns_used_file(project_id, session_id, agent) -> Path:
    name = "patterns-used-%s.json" % _safe(agent or "main")
    return _file(session_dir(project_id, session_id, create=False) / name)


ERRORS_LOG_MAX = 5 * 1024 * 1024


def append_error(line: str) -> None:
    """Append one line to logs/ace-hook-errors.log; rotate (1 backup) at 5 MB. Never raises."""
    try:
        p = errors_log()
        if p.exists() and p.stat().st_size > ERRORS_LOG_MAX:
            os.replace(p, str(p) + ".1")
        with open(p, "a") as f:
            f.write(line.rstrip("\n") + "\n")
    except Exception:
        pass


def resolve_session_id(event: Optional[dict]) -> str:
    """Hook JSON session_id, then CLAUDE_CODE_SESSION_ID, then 'default'."""
    sid = event.get("session_id") if isinstance(event, dict) else None
    return sid or os.environ.get("CLAUDE_CODE_SESSION_ID") or "default"
