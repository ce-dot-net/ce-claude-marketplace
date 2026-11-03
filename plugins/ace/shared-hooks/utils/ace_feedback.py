"""User rejection as a downvote on the NEXT main task's trace (server-team spec; mod: core.ts REJECTION_PHRASES).

A human main prompt <= 300 chars with a REJECTION_PHRASES phrase (whole word, not right after "nicht"/"not") rejects
the previous main task. Its evidenced applied_log_ids (last-main-applied.json, < 6 h) become a pending downvote that
the next main trace carries as feedback {kind: downvote, applied_log_ids}, only while the server gate is on.
"""
import json
import os
import time

import plugin_data_dir

# One list for the Python chain; the mod's copy is core.ts REJECTION_PHRASES (parity test).
REJECTION_PHRASES = (
    "falsch", "stimmt nicht", "geht nicht", "funktioniert nicht", "klappt nicht", "rückgängig", "mach das rückgängig",
    "immer noch kaputt", "immer noch nicht", "nicht das was ich wollte", "das war nicht gemeint", "doch nicht",
    "das ist falsch", "kaputt gemacht",
    "wrong", "that's wrong", "doesn't work", "does not work", "not working", "still broken", "still not",
    "not what i asked", "that broke", "you broke",
)
MAX_CHARS = 300
PREV_MAX_AGE = 6 * 3600
_NEGATIONS = ("nicht", "not")


def _word(c: str) -> bool:
    return c.isalnum() or c == "_"


def rejection_match(text):
    """The matched phrase (the longest non-negated whole-word hit; ties: list order), else None."""
    low = (text or "").strip().lower().replace("’", "'").replace("‘", "'")
    if len(low) > MAX_CHARS:
        return None
    best = None
    for phrase in REJECTION_PHRASES:
        i = low.find(phrase)
        while i >= 0:
            j = i + len(phrase)
            if (i == 0 or not _word(low[i - 1])) and (j == len(low) or not _word(low[j])):
                before = low[:i]
                words = before.split()
                if not (words and before != before.rstrip() and words[-1] in _NEGATIONS):
                    if best is None or len(phrase) > len(best):
                        best = phrase
                    break
            i = low.find(phrase, i + 1)
    return best


def downvote_enabled() -> bool:
    env = os.environ.get("ACE_FEEDBACK_DOWNVOTE")
    if env in ("1", "0"):
        return env == "1"
    return plugin_data_dir.stored_feedback_downvote()


def _files(project, session_id):
    d = plugin_data_dir.session_dir(project, session_id, create=False)
    return d / "last-main-applied.json", d / "pending-downvote.json"


def record_main_applied(project, session_id, task_session_id, applied_log_ids) -> None:
    """At every main learn: this task's evidenced ids (overwrites; [] too, so a rejection of it sends nothing)."""
    try:
        last, _ = _files(project, session_id)
        plugin_data_dir.private_write(last, json.dumps({"task_session_id": task_session_id,
                                                        "applied_log_ids": list(applied_log_ids or []), "at": time.time()}))
    except Exception:
        pass


def on_human_prompt(project, session_id, prompt) -> None:
    """UserPromptSubmit (human main prompt): detect a rejection, remember a pending downvote, log the row. Never raises."""
    try:
        matched = rejection_match(prompt)
        if not matched:
            return
        last, pending = _files(project, session_id)
        try:
            prev = json.loads(last.read_text())
        except Exception:
            prev = {}
        ids = prev.get("applied_log_ids") if isinstance(prev, dict) else None
        at = prev.get("at") if isinstance(prev, dict) else None
        fresh = isinstance(at, (int, float)) and time.time() - at < PREV_MAX_AGE
        ids = [x for x in ids if isinstance(x, int) and not isinstance(x, bool)] if isinstance(ids, list) and fresh else []
        sent = bool(ids) and downvote_enabled()
        if sent:
            plugin_data_dir.private_write(pending, json.dumps({"applied_log_ids": ids, "at": time.time()}))
        from ace_relevance_logger import log_event
        log_event("rejection_detected", matched=matched, downvote_sent=sent,
                  prev_task=str(prev.get("task_session_id") or "")[:8] or None, session_id=session_id)
    except Exception:
        pass


def take_pending_downvote(project, session_id):
    """At the next main trace: the pending downvote's ids (consumed once), else None."""
    try:
        _, pending = _files(project, session_id)
        d = json.loads(pending.read_text())
        pending.unlink()
        ids = d.get("applied_log_ids")
        if isinstance(ids, list) and ids and time.time() - d.get("at", 0) < PREV_MAX_AGE:
            return ids
    except Exception:
        pass
    return None
