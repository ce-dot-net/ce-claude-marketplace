#!/usr/bin/env python3
"""Item #16 — Client-side smart trace truncation.

ACE plugin sends ExecutionTrace to ace-cli learn. Subagent transcripts can grow
to 50+MB which causes server-side Reflector context-window overflow + heap pressure.

SDK-team confirmed: target <2MB per trace. This module truncates strategically:
- Drop tool_response payloads > 10KB (replace with marker)
- Drop base64 blobs
- Keep: task, success/error indicators, ALL failed steps, summary, last 50 steps
- Set trace.metadata.trace_truncated=True when applied

Wichtig: NEVER alter the failed-step semantic — Reflector needs all failures
for accurate boundary learning.
"""

from __future__ import annotations

import json
import re
from typing import Any


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


def _step_is_failed(step: dict) -> bool:
    """Heuristic: a step is failed if its result indicates non-zero exit or contains 'error'."""
    result = step.get("result")
    if isinstance(result, dict):
        # exit_code != 0, success: false, or 'error' key
        if result.get("exit_code") not in (None, 0, "0"):
            return True
        if result.get("success") is False:
            return True
        if "error" in result and result["error"]:
            return True
    if isinstance(result, str) and ("error" in result.lower() or "failed" in result.lower()):
        return True
    return False


def truncate_trace(trace: dict) -> dict:
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
