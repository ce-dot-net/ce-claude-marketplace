---
disable-model-invocation: true
model: claude-haiku-4-5
description: Show top patterns + last session summary on return to a session
argument-hint: "[--hours N]"
allowed-tools: Bash(${CLAUDE_PLUGIN_ROOT}/scripts/ace-cli:*), Bash(python3:*), Read
---

# ACE Recap

Quick recap when you return to a Claude Code session: top patterns used recently +
last task summary. Reads local ACE telemetry (`ace-relevance.jsonl`); no server roundtrip.

Complements Claude Code's built-in `/recap` with ACE-specific pattern context.

## Steps

1. **The log** is the repo root's `.claude/data/logs/ace-relevance.jsonl` (the main checkout of a worktree; the
   analyzer finds it through the plugin core, `scripts/ace-context --logs`). Nothing to resolve here.

2. **Build recap.** Invoke the local analyzer with `--mode recap`:
   ```bash
   ANALYZER="${CLAUDE_PLUGIN_ROOT}/shared-hooks/utils/ace_insights_analyzer.py"
   python3 "$ANALYZER" --mode text --hours "${HOURS:-12}"
   ```

3. **Output structure** (rendered by the analyzer):
   - **Last task** — its prompt, `used N/M` (evidenced use), outcome, whether the learn was sent
   - **Evidenced use per arm** (budget / full), **learn health** (unsent learns, 0 applied ids, retries, engine lib/cli),
     **skips, rejections, binding states, domain-shift cache hits**. The same text as `/ace:ace-insights` Step 1 and the
     mod's model-free answer.

4. **Be terse.** This is a returning-user view. No analysis, no recommendations.
   If `--hours` produced 0 events, say so in one sentence and stop.

## Notes

- This command does NOT call `ace-cli` — it's a pure local read.
- If `ace_insights_analyzer.py` lacks `--mode recap`, fall back to `--mode text` and
  print only the first ~20 lines.
- Use `--hours 12` as default; user can override via argument.
