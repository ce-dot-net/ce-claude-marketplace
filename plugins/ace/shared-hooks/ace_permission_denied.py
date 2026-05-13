#!/usr/bin/env python3
"""ACE PermissionDenied → boundary-signal trace (v6.5.0 Item #15).

Per ACE-SDK-team guidance (Q2 answers):
- agent_type: "permission_gate" (filterable in searchPatterns + listTraces, requires ace-cli >= 2.16)
- domain: "permission-boundary" (client-side tag, NOT anti-pattern)
- result.success: false (boundary signal, no explicit harmful_delta — Curator decides)
- Client-side debounce: max 1 trace per (tool_name) per 60s

Why this exists:
- CC auto-mode classifier denies tool calls (e.g., dangerous bash). ACE captures
  these as "user-boundary" patterns so the Curator can learn org-specific limits.
- NOT a learning-from-mistake signal — the agent didn't choose poorly, the
  permission system blocked execution. Treat as configuration intent.

Best-effort: any failure is swallowed silently. Hook MUST NOT block CC turns.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from datetime import datetime


DEBOUNCE_SECONDS = 60


def _read_event() -> dict:
    try:
        return json.loads(sys.stdin.read() or "{}")
    except (json.JSONDecodeError, OSError):
        return {}


def _debounce_dir(session_id: str) -> Path:
    """Per-session subdir for debounce timestamps. Uses /tmp until #2 migration completes."""
    # Phase 1 placeholder; Phase 4 will migrate to ${CLAUDE_PLUGIN_DATA}/projects/<id>/sessions/<sid>/
    base = Path(f"/tmp/ace-denials-{session_id or 'default'}")
    try:
        base.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return base


def _is_debounced(tool_name: str, session_id: str) -> bool:
    """Return True if we've sent a denial for this tool within DEBOUNCE_SECONDS."""
    if not tool_name:
        return False
    stamp = _debounce_dir(session_id) / f"{tool_name}.ts"
    if not stamp.exists():
        return False
    try:
        age = time.time() - stamp.stat().st_mtime
        return age < DEBOUNCE_SECONDS
    except OSError:
        return False


def _record_debounce(tool_name: str, session_id: str) -> None:
    if not tool_name:
        return
    dbg_dir = _debounce_dir(session_id)
    stamp = dbg_dir / f"{tool_name}.ts"
    try:
        stamp.touch()
    except OSError:
        pass

    # PR-review I5: opportunistic cleanup of siblings older than 10× TTL.
    # /tmp/ace-denials-<sid>/ would otherwise grow unbounded on long-running
    # CC sessions that never restart (web/Linear variants).
    try:
        cutoff = time.time() - (DEBOUNCE_SECONDS * 10)
        for sibling in dbg_dir.iterdir():
            try:
                if sibling.stat().st_mtime < cutoff:
                    sibling.unlink()
            except OSError:
                pass
    except OSError:
        pass


def _structural_fingerprint(tool_name: str, tool_input) -> str:
    """Redacted fingerprint of tool_input.

    The user explicitly did NOT approve this call — we must never ship the
    payload off-box (could contain credentials, API keys, sensitive code).
    Send only structural info: tool verb (Bash) or input key shape (Edit/Write).
    """
    if not isinstance(tool_input, dict):
        return "input=non-dict"

    if tool_name == "Bash":
        # Leading verb only — strips arguments which may contain secrets
        cmd = str(tool_input.get("command", ""))
        verb = cmd.split(None, 1)[0] if cmd else ""
        return f"verb={verb!r}"

    # For Edit/Write/etc., expose only the *keys* present (file_path, new_string, …)
    keys = sorted(k for k in tool_input.keys() if isinstance(k, str))
    return f"input_keys={keys}"


def _build_trace(event: dict) -> dict:
    """Build ExecutionTrace shape per SDK-team guidance."""
    tool_name = event.get("tool_name", "unknown")
    tool_input = event.get("tool_input", {})
    reason = event.get("reason") or event.get("denial_reason") or "auto-mode classifier denial"
    session_id = event.get("session_id", "")

    # Compact task line — server filters trivial tasks (<learningMinTokens=100),
    # so this becomes telemetry-only. Acceptable per Q2.
    task = f"PermissionDenied: {tool_name}"

    # SECURITY: never ship raw tool_input. The user just denied this call,
    # which means by definition we should not exfiltrate its payload.
    # Use a structural fingerprint instead (PR-review B1).
    trajectory = [{
        "step": 1,
        "tool": tool_name,
        "action": f"Attempt {tool_name} ({_structural_fingerprint(tool_name, tool_input)})",
        "result": f"denied: {reason}",
    }]

    return {
        "task": task,
        "trajectory": trajectory,
        "result": {
            "success": False,
            "output": f"denied: {reason}",
        },
        "playbook_used": [],
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "agent_type": "permission_gate",
        "session_id": session_id,
        # Domain tag — client-side classification; server respects this for searchPatterns
        "domains": ["permission-boundary"],
    }


def _send_to_cli(trace: dict) -> bool:
    """Pipe trace JSON to `ace-cli learn --stdin`. Returns success."""
    try:
        proc = subprocess.Popen(
            ["ace-cli", "learn", "--stdin", "--quiet"],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        proc.communicate(input=json.dumps(trace).encode("utf-8"), timeout=10)
        return proc.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


def main() -> int:
    event = _read_event()
    if not event:
        return 0

    tool_name = event.get("tool_name", "")
    session_id = event.get("session_id", "")

    if _is_debounced(tool_name, session_id):
        return 0

    trace = _build_trace(event)
    _send_to_cli(trace)  # silently fire-and-forget on any error
    _record_debounce(tool_name, session_id)
    return 0


if __name__ == "__main__":
    # Always exit 0 — hook must never block CC operation.
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
