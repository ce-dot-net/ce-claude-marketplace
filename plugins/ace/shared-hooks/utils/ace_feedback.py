"""User rejection as a downvote on the NEXT main task's trace (server-team spec; mod: lib/evidence.ts REJECTION_PHRASES).

A human main prompt <= 300 chars with a REJECTION_PHRASES phrase (whole word, not right after "nicht"/"not") rejects
the previous main task. Its evidenced applied_log_ids (last-main-applied.json, < 6 h) become a pending downvote that
the next main trace carries as feedback {kind: downvote, applied_log_ids}, only while the server gate is on.
"""
import json
import os
import time

import plugin_data_dir

# One list for the Python chain; the mod's copy is lib/evidence.ts REJECTION_PHRASES (parity test).
REJECTION_PHRASES = (
    "falsch", "stimmt nicht", "geht nicht", "funktioniert nicht", "klappt nicht", "rückgängig", "mach das rückgängig",
    "immer noch kaputt", "immer noch nicht", "nicht das was ich wollte", "das war nicht gemeint", "doch nicht",
    "das ist falsch", "kaputt gemacht", "arbeit umsonst", "alles umsonst", "war umsonst", "das war mist", "scheisse aus", "scheiße aus",
    "wrong", "that's wrong", "doesn't work", "does not work", "not working", "still broken", "still not",
    "not what i asked", "that broke", "you broke",
)
MAX_CHARS = 300
PREV_MAX_AGE = 6 * 3600
# A hit is blocked after a negation, after "oder"/"or" ("richtig oder falsch") and when it closes a rhetorical question
# about the user ("sehe ich das falsch", "liege ich falsch"). Mod parity: lib/evidence.ts rejectionProbe.
_BLOCKERS = ("nicht", "not", "nichts", "kein", "keine", "keinen", "keiner", "nie", "never", "oder", "or")


def _word(c: str) -> bool:
    return c.isalnum() or c == "_"


def rejection_probe(text):
    """{matched: the longest unblocked whole-word phrase (ties: list order), blocked: the longest guarded one, too_long}."""
    low = (text or "").strip().lower().replace("’", "'").replace("‘", "'")
    if len(low) > MAX_CHARS:
        return {"matched": None, "blocked": None, "too_long": True}
    best = blocked = None
    for phrase in REJECTION_PHRASES:
        i = low.find(phrase)
        while i >= 0:
            j = i + len(phrase)
            if (i == 0 or not _word(low[i - 1])) and (j == len(low) or not _word(low[j])):
                before = low[:i]
                words = before.split()
                last = words[-1] if words else None
                prev = words[-2] if len(words) > 1 else None
                rhetorical = phrase in ("falsch", "wrong")  # "sehe ich das falsch"; "das wollte ich doch nicht" stays a rejection
                guard = bool(words) and before != before.rstrip() and (
                    last in _BLOCKERS or (rhetorical and (last == "ich" or (prev == "ich" and last in ("das", "es")))))
                if guard:
                    if blocked is None or len(phrase) > len(blocked):
                        blocked = phrase
                else:
                    if best is None or len(phrase) > len(best):
                        best = phrase
                    break
            i = low.find(phrase, i + 1)
    return {"matched": best, "blocked": blocked if best is None else None, "too_long": False}


def rejection_match(text):
    """The matched phrase (the longest non-blocked whole-word hit; ties: list order), else None."""
    return rejection_probe(text)["matched"]


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
    """UserPromptSubmit (human main prompt): detect a rejection, remember a pending downvote, log the rows. Never raises.

    8.2.9: every call logs one text-free row `rejection_check` {matched, blocked, chars, failed, prev_age_s, prev_ids}; `failed`
    is the first failing condition in the cheap-first order too_long, prev_stale, empty_ids, switch_off, no_phrase (None = queued).
    """
    try:
        probe = rejection_probe(prompt)
        matched = probe["matched"]
        last, pending = _files(project, session_id)
        prev = {}
        if not probe["too_long"]:
            try:
                prev = json.loads(last.read_text())
            except Exception:
                prev = {}
        ids = prev.get("applied_log_ids") if isinstance(prev, dict) else None
        at = prev.get("at") if isinstance(prev, dict) else None
        age = time.time() - at if isinstance(at, (int, float)) and not isinstance(at, bool) else None
        fresh = age is not None and age < PREV_MAX_AGE
        ids = [x for x in ids if isinstance(x, int) and not isinstance(x, bool)] if isinstance(ids, list) and fresh else []
        on = False if probe["too_long"] else downvote_enabled()
        failed = ("too_long" if probe["too_long"] else "prev_stale" if not fresh else "empty_ids" if not ids
                  else "switch_off" if not on else "no_phrase" if not matched else None)
        sent = failed is None
        if sent:
            plugin_data_dir.private_write(pending, json.dumps({"applied_log_ids": ids, "at": time.time()}))
        from ace_relevance_logger import log_event
        log_event("rejection_check", matched=matched, blocked=probe["blocked"], chars=len((prompt or "")), failed=failed,
                  prev_age_s=None if age is None else round(age), prev_ids=len(ids), session_id=session_id, source="python")
        if matched:
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
