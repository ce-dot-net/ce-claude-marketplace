---
model: claude-haiku-4-5
description: Show top patterns + last session summary on return to a session
argument-hint: "[--hours N]"
allowed-tools: Bash(python3:*), Bash(jq:*), Read
---

# ACE Recap

Quick recap when you return to a Claude Code session: top patterns used recently +
last task summary. Reads local ACE telemetry (`ace-relevance.jsonl`); no server roundtrip.

Complements Claude Code's built-in `/recap` with ACE-specific pattern context.

## Steps

1. **Locate relevance log.** Resolve `${CLAUDE_PLUGIN_DATA}/projects/<id>/ace-relevance.jsonl`,
   falling back to `.claude/data/logs/ace-relevance.jsonl` for backward-compat.

2. **Build recap.** Invoke the local analyzer with `--mode recap`:
   ```bash
   ANALYZER="${CLAUDE_PLUGIN_ROOT}/shared-hooks/utils/ace_insights_analyzer.py"
   python3 "$ANALYZER" --mode recap --hours "${HOURS:-12}"
   ```

3. **Output structure** (rendered by the analyzer):
   - **Last task summary** — task description + outcome from the most recent `execution` event
   - **Top 5 patterns** — by helpful-score from the preceding `search` events
   - **Session-level totals** — patterns injected, average relevance, domains touched

4. **Be terse.** This is a returning-user view. No analysis, no recommendations.
   If `--hours` produced 0 events, say so in one sentence and stop.

## Notes

- This command does NOT call `ace-cli` — it's a pure local read.
- If `ace_insights_analyzer.py` lacks `--mode recap`, fall back to `--mode text` and
  print only the first ~20 lines.
- Use `--hours 12` as default; user can override via argument.
