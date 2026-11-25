#!/usr/bin/env python3
"""Full steps (Python chain): ONE hard safety cap for a trace, the same rule as the mod's capTrace (mod/lib/trace.ts).

Nothing is cut below the cap: no per-tool_response limit, no 'last 50 steps', no 2 MiB target (the server sets its own budgets).
- ACE_TRACE_HARD_CAP_BYTES (default 4 MiB, under ace_trace_queue MAX_FILE 5 MiB), measured as json.dumps bytes (= mod pyDumps).
  Over it: 1. the longest step payloads (tool_response / tool_input) become '<truncated: N bytes>', longest first;
  2. then the OLDEST steps that did not fail are dropped (failed steps always stay; the Reflector needs every failure);
  3. last resort task / summary (the mod's shrink: 2048 / 4096).
  A `_truncation_marker` (counters) leads the trajectory and metadata.trace_truncated is set, ONLY when the cap bites.
- ACE_TEXT_HARD_CAP_CHARS (default 200000) for task and result.summary: head + '<truncated: N chars>' (mod capText; ace_after_task
  cap_text applies it at build time already, this keeps the module self-contained).
Python steps stay summaries (action / result); their format is not touched.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

TRACE_HARD_CAP_BYTES = 4 * 1024 * 1024
TEXT_HARD_CAP_CHARS = 200_000


def _env_int(name: str, default: int) -> int:
    try:
        n = int(os.environ.get(name, "").strip())
    except ValueError:
        return default
    return n if n > 0 else default


TRACE_HARD_CAP_MAX = 5 * 1024 * 1024 - 256 * 1024  # round 8 I3: = mod TRACE_HARD_CAP_MAX, below ace_trace_queue.MAX_FILE


def hard_cap_bytes() -> int:
    return min(_env_int("ACE_TRACE_HARD_CAP_BYTES", TRACE_HARD_CAP_BYTES), TRACE_HARD_CAP_MAX)


def text_cap_chars() -> int:
    return _env_int("ACE_TEXT_HARD_CAP_CHARS", TEXT_HARD_CAP_CHARS)


def _size(v: Any) -> int:
    return len(json.dumps(v, default=str))


def _step_is_failed(step: dict) -> bool:
    """Heuristic: a step is failed if its result indicates non-zero exit or contains 'error'."""
    result = step.get("result")
    if isinstance(result, dict):
        if result.get("exit_code") not in (None, 0, "0"):
            return True
        if result.get("success") is False:
            return True
        if "error" in result and result["error"]:
            return True
    if isinstance(result, str) and ("error" in result.lower() or "failed" in result.lower()):
        return True
    return False


_CAPPED = re.compile(r"<truncated: \d+ chars>\Z")


def _cap_text(text: Any, cap: int) -> Any:
    # idempotent: a text ace_after_task.cap_text already capped (head + marker) is left as it is
    if not isinstance(text, str) or len(text) <= cap or (_CAPPED.search(text) and len(text) - len(_CAPPED.search(text).group(0)) <= cap):
        return text
    return text[:cap] + "<truncated: %d chars>" % len(text)


def _shrink(s: Any, mx: int, what: str) -> Any:
    return "<truncated: %d bytes — %s>" % (len(s), what) if isinstance(s, str) and len(s) > mx else s


def cap_trace(trace: dict) -> tuple[dict, dict | None]:
    """(trace, hit): hit = {bytes_before, bytes_after, steps} when the byte cap bit, else None. Mutates trace in place."""
    tcap = text_cap_chars()
    if isinstance(trace.get("task"), str):  # the request body is capped, not the 'User request: ' prefix (mod capText, ace_after_task cap_text)
        pre = "User request: " if trace["task"].startswith("User request: ") else ""
        trace["task"] = pre + _cap_text(trace["task"][len(pre):], tcap)
    res = trace.get("result")
    if isinstance(res, dict) and isinstance(res.get("summary"), str):
        res["summary"] = _cap_text(res["summary"], tcap)

    cap = hard_cap_bytes()
    size = _size(trace)
    if size <= cap:
        return trace, None
    before = size
    tr = trace.get("trajectory") if isinstance(trace.get("trajectory"), list) else []
    n = len(tr)
    pay = []
    for i, st in enumerate(tr):
        if isinstance(st, dict):
            for f in ("tool_response", "tool_input"):
                if f in st:
                    pay.append((i, f, _size(st[f])))
    pay.sort(key=lambda x: (-x[2], x[0]))
    outputs = 0
    for i, f, ln in pay:
        if size <= cap:
            break
        m = "<truncated: %d bytes>" % ln
        if _size(m) >= ln:
            continue
        tr[i][f] = m
        size -= ln - _size(m)
        outputs += 1
    keep = [True] * n

    def build() -> int:
        k = [i for i in range(n) if keep[i]]
        trace["trajectory"] = [{"_truncation_marker": True, "original_length": n, "kept": len(k), "kept_indices": k,
                                "outputs_truncated": outputs, "steps_dropped": n - len(k)}] + [tr[i] for i in k]
        meta = trace.get("metadata")
        trace["metadata"] = dict(meta, trace_truncated=True) if isinstance(meta, dict) else {"trace_truncated": True}
        return _size(trace)

    size = build()
    # ponytail: one exact re-measure per dropped step only near the cap; the estimate (step bytes + ', ') does the bulk
    for i in range(n):
        if size <= cap:
            break
        if isinstance(tr[i], dict) and _step_is_failed(tr[i]):
            continue
        keep[i] = False
        size -= _size(tr[i]) + 2
        if size <= cap + 64:
            size = build()
    size = build()
    if size > cap:
        trace["task"] = _shrink(trace.get("task"), 2048, "task")
        if isinstance(res, dict):
            res["summary"] = _shrink(res.get("summary"), 4096, "summary")
        size = _size(trace)
    return trace, {"bytes_before": before, "bytes_after": size, "steps": n}


def truncate_trace(trace: dict) -> dict:
    """Compatible entry point: the trace, capped (see cap_trace)."""
    return cap_trace(trace)[0]

# ---- full steps OFF (ACE_TRACE_FULL_STEPS=0/false/off/no or the server's full_steps:false): the 8.3.0 truncate_trace,
# word for word (renamed legacy_truncate_trace; _step_is_failed above is the same function). Mod twin: lib/trace.ts legacyTruncate.
MAX_TOOL_RESPONSE_BYTES = 10_240          # 10KB per individual tool response
MAX_TRAJECTORY_RECENT_STEPS = 50          # keep last N steps (failed steps kept regardless)
MAX_TOTAL_TRACE_BYTES = 2_097_152         # 2MB total
BASE64_MIN_LEN = 100                      # treshold for base64 blob detection
_BASE64_RE = re.compile(r"^[A-Za-z0-9+/]{100,}={0,2}$")


def _is_base64_blob(s: str) -> bool:
    if not isinstance(s, str) or len(s) < BASE64_MIN_LEN:
        return False
    return bool(_BASE64_RE.match(s))


def _truncate_string(s: str, max_bytes: int, marker: str) -> str:
    encoded = s.encode("utf-8")
    if len(encoded) <= max_bytes:
        return s
    return f"<truncated: {len(encoded)} bytes — {marker}>"


def _truncate_step(step: dict) -> tuple[dict, bool]:
    """Mutate-in-place a single trajectory step. Returns (step, changed_flag)."""
    changed = False
    # tool_response is the heaviest field typically
    if "tool_response" in step:
        resp = step["tool_response"]
        if isinstance(resp, str):
            if _is_base64_blob(resp):
                step["tool_response"] = "<truncated: base64 blob>"
                changed = True
            elif len(resp.encode("utf-8")) > MAX_TOOL_RESPONSE_BYTES:
                step["tool_response"] = _truncate_string(resp, MAX_TOOL_RESPONSE_BYTES, "tool_response")
                changed = True
        elif isinstance(resp, dict):
            for key in list(resp.keys()):
                val = resp[key]
                if isinstance(val, str):
                    if _is_base64_blob(val):
                        resp[key] = "<truncated: base64 blob>"
                        changed = True
                    elif len(val.encode("utf-8")) > MAX_TOOL_RESPONSE_BYTES:
                        resp[key] = _truncate_string(val, MAX_TOOL_RESPONSE_BYTES, f"tool_response.{key}")
                        changed = True
    return step, changed


def legacy_truncate_trace(trace: dict) -> dict:
    """Mutate trace in-place; set metadata.trace_truncated when truncation applied."""
    truncated = False

    trajectory = trace.get("trajectory", [])
    if isinstance(trajectory, list) and len(trajectory) > MAX_TRAJECTORY_RECENT_STEPS:
        # Keep all failed steps + last N steps; deduplicate by id() so we don't
        # double-count steps that are both failed AND in the tail window.
        failed_indices = {i for i, st in enumerate(trajectory) if isinstance(st, dict) and _step_is_failed(st)}
        tail_indices = set(range(len(trajectory) - MAX_TRAJECTORY_RECENT_STEPS, len(trajectory)))
        keep_indices = sorted(failed_indices | tail_indices)
        new_trajectory = [trajectory[i] for i in keep_indices]
        # Marker so reader knows steps were dropped
        new_trajectory.insert(0, {
            "_truncation_marker": True,
            "original_length": len(trajectory),
            "kept": len(new_trajectory),
            "kept_indices": keep_indices,
        })
        trace["trajectory"] = new_trajectory
        truncated = True

    # Step-level payload truncation (always run, even if no trajectory-level truncation)
    for step in trace.get("trajectory", []):
        if isinstance(step, dict) and not step.get("_truncation_marker"):
            _, changed = _truncate_step(step)
            if changed:
                truncated = True

    # Final size check — if still too big, truncate task/summary strings
    serialized = json.dumps(trace, default=str)
    if len(serialized.encode("utf-8")) > MAX_TOTAL_TRACE_BYTES:
        task = trace.get("task", "")
        if isinstance(task, str):
            trace["task"] = _truncate_string(task, 2048, "task")
            truncated = True
        summary = trace.get("summary") or trace.get("result", {}).get("summary")
        if isinstance(summary, str):
            trunc_summary = _truncate_string(summary, 4096, "summary")
            if "summary" in trace:
                trace["summary"] = trunc_summary
            elif isinstance(trace.get("result"), dict):
                trace["result"]["summary"] = trunc_summary
            truncated = True

    if truncated:
        meta = trace.setdefault("metadata", {})
        if not isinstance(meta, dict):
            # Defensive: if metadata wasn't a dict, wrap it
            trace["metadata"] = {"original_metadata": meta, "trace_truncated": True}
        else:
            meta["trace_truncated"] = True

    return trace
