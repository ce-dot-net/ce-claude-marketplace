#!/usr/bin/env python3
"""ACE SessionStart hook (v8). Only mode: --compact.

SessionStart source == "compact" (cc_hooks_reference.md:1256-1262): re-inject the
`rendered_context` UPS saved in the MAIN agent's state (DESIGN §5 C1) as
hookSpecificOutput.additionalContext (:1295-1312), capped at the 10,000-char hook
output limit. Local state only: no ace-cli call, no /tmp, never blocks.
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / 'utils'))
sys.path.insert(0, str(Path(__file__).parent.parent / 'utils'))

import plugin_data_dir                         # noqa: E402
from ace_context import get_context            # noqa: E402
from ace_relevance_logger import log_error     # noqa: E402
from patterns_used_state import load_rendered_context     # noqa: E402

_CAP = 10000


def main() -> None:
    try:
        event = json.load(sys.stdin)
        if '--compact' not in sys.argv or event.get('source') != 'compact':
            return
        cwd = event.get('cwd')
        if cwd and os.path.isdir(cwd):
            os.chdir(cwd)  # v8 shims never cd (DESIGN §3.1)
        ctx = get_context()
        if not ctx:
            return
        sid = plugin_data_dir.resolve_session_id(event)
        if plugin_data_dir.is_disabled(ctx['project'], sid):
            return
        try:  # §31: the mod's per-conversation full dedupe starts over after a compaction
            (plugin_data_dir.session_dir(ctx['project'], sid, create=False) / 'full-injected.json').unlink()
        except OSError:
            pass
        rendered = load_rendered_context(sid, project_id=ctx['project'])
        if rendered and isinstance(rendered, str):
            print(json.dumps({"hookSpecificOutput": {
                "hookEventName": "SessionStart", "additionalContext": rendered[:_CAP]}}))
    except Exception as e:
        log_error('SessionStart', 'ace_session_start.main', error=e)  # DESIGN §3.1; exit 0, no stdout


if __name__ == '__main__':
    main()
