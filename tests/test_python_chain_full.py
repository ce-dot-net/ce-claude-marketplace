"""Python chain, round 4: trace.chain = 'python' (never omitted), the hard trace cap logged as trace_cap_hit only when it bites,
and a non-interactive run (subprocess, no TTY, like `claude -p`) sends the same uncut trace: the chain never reads interactivity."""
import json
import re
from pathlib import Path

from test_stop_v8 import ORG_ID, PROJECT_ID, WORK, box  # noqa: F401
from test_r3d_hook_behavior import _handback_transcript

AFTER = Path(__file__).resolve().parent.parent / "plugins" / "ace" / "shared-hooks" / "ace_after_task.py"


def _run(box, aid, last="done", handback=None, **env):
    sid = "s-" + aid
    box.write_state(sid, aid, task_session_id="own-uuid", user_prompt="refactor the parser module")
    box.seed_tools(sid, WORK, agent_id=aid)
    ev = box.subagent_event(sid, aid, agent_type="Explore", last_assistant_message=last)
    if handback is not None:
        ev["agent_transcript_path"] = _handback_transcript(box, aid, handback)()
    p = box.run_after_task(ev, ACE_PROJECT_ID=PROJECT_ID, ACE_ORG_ID=ORG_ID, **env)
    assert p.returncode == 0, p.stderr
    (learn,) = box.cli_calls("learn")
    return learn["trace"]


def test_trace_carries_chain_python(box):
    assert _run(box, "c1")["chain"] == "python"


def test_no_cap_hit_by_default_no_metadata_no_row(box):
    t = _run(box, "c2")
    assert "metadata" not in t and not any(s.get("_truncation_marker") for s in t["trajectory"])
    assert box.relevance_rows("trace_cap_hit") == []


def test_cap_hit_is_logged_text_free_and_marked(box):
    t = _run(box, "c3", last="z" * 5000, ACE_TRACE_HARD_CAP_BYTES="600")  # unreachable: the last resort (summary > 4096) bites
    assert t["metadata"]["trace_truncated"] is True and t["trajectory"][0]["_truncation_marker"] is True
    (row,) = box.relevance_rows("trace_cap_hit")
    assert row["bytes_before"] > row["bytes_after"] and row["steps"] >= 1 and row["source"] == "python"
    assert "zzzz" not in json.dumps(row)


def test_non_interactive_run_sends_the_whole_text_and_chain(box):
    # box.run_after_task is a subprocess with piped stdin: no TTY, exactly the `claude -p` / CI situation
    report = "## Findings\n" + "r" * 30000
    t = _run(box, "c4", handback=report)
    assert (t["chain"], t["result"]["summary"]) == ("python", report)


def test_the_python_chain_never_branches_on_interactivity():
    src = AFTER.read_text()
    assert not re.search(r"isatty|isInteractive|is_interactive|interactive", src)
