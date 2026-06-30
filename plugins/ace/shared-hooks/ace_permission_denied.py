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

# ---------------------------------------------------------------------------
# Classifier infra-abort detection
# ---------------------------------------------------------------------------

# Exact lowercase phrases that appear ONLY in classifier infrastructure failures
# (not in genuine policy denies).  Long enough to never false-match real denials.
# FIX 1: removed the redundant + over-broad "auto mode cannot determine the safety of"
# (substring of marker 1, short enough to risk false-matches).
_INFRA_MARKERS: tuple[str, ...] = (
    "is temporarily unavailable, so auto mode cannot determine the safety",
    "could not evaluate this action and is blocking it for safety",
    "classifier transcript exceeded context window",
)

# Marker that names the specific tool in the text: "…the safety of <TOOL> right now".
# Requires tool-name correlation (FIX 3).
_TOOL_NAMING_MARKER = "is temporarily unavailable, so auto mode cannot determine the safety"


_TAIL_BYTES = 32768  # FIX 2: seek-based read; never loads full transcript into memory


def _read_transcript_tail(path, max_entries: int = 12) -> list:
    """Best-effort: return the last *max_entries* parsed JSON objects from a JSONL file.

    FIX 2: Uses a seek-based read of the last _TAIL_BYTES bytes so that multi-MB
    transcripts are never loaded into memory in full.  A partial first line (when
    we didn't start at byte 0) is dropped before parsing.

    Returns [] on any error (falsy path, missing file, unreadable, …).
    Malformed lines are skipped silently.
    """
    if not path:
        return []
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            start = max(0, size - _TAIL_BYTES)
            f.seek(start)
            chunk = f.read()
        text = chunk.decode("utf-8", errors="replace")
        lines = text.splitlines()
        # Drop a possibly-partial first line when we didn't read from byte 0
        if start > 0 and lines:
            lines = lines[1:]
    except (OSError, ValueError):
        return []
    candidate_lines = lines[-max_entries:] if len(lines) > max_entries else lines
    result = []
    for line in candidate_lines:
        line = line.strip()
        if not line:
            continue
        try:
            result.append(json.loads(line))
        except (json.JSONDecodeError, ValueError):
            pass
    return result


def _extract_tool_result_texts(entry: dict) -> list[str]:
    """Extract all candidate text strings from a single JSONL entry.

    Handles:
    - message.content as list of blocks with type=="tool_result" whose
      "content" field is either a str or a list of {type,text} sub-blocks.
    - message.content as a plain str (entire message text).
    - entry-level "toolUseResult" as a str.
    """
    texts: list[str] = []
    try:
        msg = entry.get("message") or {}
        content = msg.get("content") if isinstance(msg, dict) else None

        if isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") != "tool_result":
                    continue
                blk_content = block.get("content")
                if isinstance(blk_content, str):
                    texts.append(blk_content)
                elif isinstance(blk_content, list):
                    # list of {type:text, text:...} sub-blocks
                    for sub in blk_content:
                        if isinstance(sub, dict) and sub.get("type") == "text":
                            t = sub.get("text")
                            if isinstance(t, str):
                                texts.append(t)
        elif isinstance(content, str):
            texts.append(content)

        # Also check entry-level toolUseResult (a str in real transcripts)
        tor = entry.get("toolUseResult")
        if isinstance(tor, str):
            texts.append(tor)
    except Exception:
        pass
    return texts


def _is_classifier_infra_denial(event) -> bool:
    """Return True iff the PermissionDenied was caused by a classifier infra abort.

    FIX 3: scans the tail NEWEST→OLDEST and takes the FIRST entry that has
    tool_result text (= the current denial's result).  Only THAT text is checked —
    older tool_results are ignored to prevent cross-event contamination.

    Correlation guard for _TOOL_NAMING_MARKER: the temporarily-unavailable marker
    includes the tool name ("…the safety of <TOOL> right now").  When the event
    provides a non-empty tool_name, require it to appear in the text; if it doesn't,
    the marker belongs to a different tool's denial → return False.

    The other two markers do not name a specific tool → accept on marker presence
    alone regardless of tool_name.

    Best-effort — any exception returns False.
    """
    try:
        if not isinstance(event, dict):
            return False
        transcript_path = event.get("transcript_path")
        if not transcript_path:
            return False
        entries = _read_transcript_tail(transcript_path, max_entries=12)
        tool_name = (event.get("tool_name") or "").strip()

        # Scan newest → oldest; stop at the first entry that has tool_result text.
        for entry in reversed(entries):
            texts = _extract_tool_result_texts(entry)
            if not texts:
                continue
            # Found the current denial's entry — check ONLY these texts.
            for text in texts:
                lowered = text.lower()
                for marker in _INFRA_MARKERS:
                    if marker not in lowered:
                        continue
                    # Tool-name correlation for the marker that names the tool.
                    if marker == _TOOL_NAMING_MARKER and tool_name:
                        if tool_name.lower() not in lowered:
                            # Marker names a different tool — not our denial.
                            return False
                    return True
            # First entry with tool_result found but no marker — genuine deny.
            return False
    except Exception:
        pass
    return False


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

    # FIX 4: debounce check runs BEFORE the transcript read so that bursts of
    # genuine denies for the same tool do NOT re-read (potentially large) transcripts.
    if _is_debounced(tool_name, session_id):
        return 0

    # Guard: classifier infra-abort (e.g. LLM overloaded) fires PermissionDenied
    # with NO denial reason in the event itself, but leaves a marker in the
    # transcript.  Do NOT learn these — they are infrastructure noise, not
    # genuine permission-boundary verdicts.  Infra path returns WITHOUT recording
    # debounce (infra aborts are not genuine boundary signals).
    if _is_classifier_infra_denial(event):
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
