#!/usr/bin/env python3
"""ACE PreToolUse `Agent` hook (DESIGN §9 G1): stash the spawn prompt for SubagentStart.

SubagentStart input carries no prompt (cc_hooks_reference.md:2553-2566); the Agent tool
input does (:1905-1912). Writes <session>/agent-prompts/<prompt_id>-<subagent_type>.json
({prompt, subagent_type, description}, <= 8 KB). No ace-cli, no stdout (a PreToolUse
stdout could be read as a decision), always exit 0.
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / 'utils'))
sys.path.insert(0, str(Path(__file__).parent.parent / 'utils'))

_MAX = 8192


def main() -> None:
    try:
        event = json.load(sys.stdin)
        if not isinstance(event, dict) or event.get('tool_name') != 'Agent' or not event.get('prompt_id'):
            return
        ti = event.get('tool_input') or {}
        cwd = event.get('cwd')
        if cwd and os.path.isdir(cwd):
            os.chdir(cwd)
        import plugin_data_dir
        from ace_project_context import get_context
        ctx = get_context()
        if not ctx:
            return
        sid = plugin_data_dir.resolve_session_id(event)
        if plugin_data_dir.is_disabled(ctx['project'], sid) or plugin_data_dir.is_mod_active(ctx['project'], sid, plugin_data_dir.MOD_HANDOFF_S):
            return
        stype = str(ti.get('subagent_type') or 'general-purpose')
        data = {"prompt": str(ti.get('prompt') or ''), "subagent_type": stype,
                "description": str(ti.get('description') or '')[:500]}
        # ponytail: shrink the prompt by halves until the JSON fits 8 KB (multi-byte safe).
        while len(json.dumps(data).encode('utf-8')) > _MAX and data["prompt"]:
            data["prompt"] = data["prompt"][:len(data["prompt"]) * 3 // 4 - 1]
        f = plugin_data_dir.agent_prompt_file(ctx['project'], sid, event['prompt_id'], stype)
        try:  # O_EXCL: of parallel same-type siblings only the first wins; the rest tombstone
            fd = os.open(str(f), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:  # key is ambiguous -> reader falls back to the transcript
            f.write_text(json.dumps({"ambiguous": True, "subagent_type": stype}))
        else:
            with os.fdopen(fd, 'w') as fh:
                fh.write(json.dumps(data))
    except Exception as e:
        try:
            from ace_relevance_logger import log_error
            log_error('PreToolUse', 'ace_agent_prompt_stash.main', error=e)
        except Exception:
            pass


if __name__ == '__main__':
    main()
