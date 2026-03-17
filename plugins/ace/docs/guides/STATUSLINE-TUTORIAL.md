# Getting Started with the ACE Statusline

**Audience**: ACE is already installed. You want to add the live statusline to your Claude Code setup.

**Time**: ~5 minutes

---

## 1. What is the ACE Statusline?

The ACE statusline is a live status bar that appears inside Claude Code after each assistant response. It shows ACE effectiveness metrics for your current session: how focused Claude is being, how well its patterns matched your work, and how actively your playbook is learning.

The display adapts to your terminal width across four responsive modes:

| Mode | Width | What you see |
|---|---|---|
| nano | < 40 cols | QPT score only |
| micro | 40–59 cols | QPT + Focus + Confidence |
| mini | 60–99 cols | QPT + all metrics + playbook health |
| normal | 100+ cols | Full dashboard with sparkline activity charts |

A terminal width of 100 columns or more is recommended to see the full dashboard.

---

## 2. Prerequisites

Before setup, confirm you have:

**jq** — required at runtime by the statusline script:
```bash
# macOS
brew install jq

# Debian / Ubuntu
sudo apt install jq

# Verify
jq --version
```

**ace-cli** — installed and authenticated. If you haven't done this yet, follow the [Installation Guide](INSTALL.md) first.

```bash
ace-cli --version
# Should show: >= 3.10.3
```

---

## 3. Install

Run this slash command from inside Claude Code in your project:

```
/ace-statusline-setup
```

That's it. The command does three things automatically:

1. Locates `ace-statusline.sh` in your plugin installation.
2. Creates `.claude/statusline-command.sh` — a thin wrapper that Claude Code calls after each response.
3. Adds the `statusLine` key to `.claude/settings.local.json` pointing at that wrapper.

After it completes, **restart Claude Code** for the statusline to appear.

> The command is idempotent — safe to run again if something changes or needs re-wiring.

---

## 4. First Run

After restarting Claude Code and opening your project, you may briefly see one of two placeholder states before any prompts are submitted:

**`ACE: awaiting session`** — Claude Code has not yet provided a session ID. This is a normal state during startup; it resolves within a second or two as the session initializes.

**`ACE: no data`** — The session ID is present, but the file `.claude/data/logs/ace-relevance.jsonl` does not exist yet. This means no ACE hooks have fired yet in this project. After your first prompt completes, the file is created and the statusline switches to showing real data.

On your very first prompt after setup, all metrics will show zeros. This is expected — see the next section for why.

---

## 5. Reading the Output

In **normal** mode (terminal width >= 100 cols) the statusline renders as a multi-line dashboard. Here is what each component means:

### QPT — Quality Per Task

```
◉ QPT: 72  Focus: 85%  Conf: 60%  Inj: 40%  Terrain: familiar
```

**QPT** (Quality Per Task) is a composite score from 0–100 representing how effectively ACE helped Claude during this session. It is a weighted blend of Focus, Confidence, learning rate, and task success rate.

Color interpretation:
- Green (>= 70) — ACE is contributing well; patterns are being found and used.
- Yellow (40–69) — partial contribution; some patterns matched but usage is moderate.
- Red (< 40) — low contribution; playbook may lack patterns for this domain.

**Focus** — the percentage of Claude's tool calls that were state-changing (writes, edits, creates) versus reads. Higher focus generally means Claude is executing rather than exploring.

**Conf** — average confidence of pattern matches returned by the ACE search on the most recent UserPromptSubmit. A value of 0% on the first prompt is expected (see Section 6).

**Inj** — the percentage of injected patterns that Claude actually used (referenced in tool calls). Higher injection utilization means patterns are relevant and actionable.

**Terrain** — how well the current session's domains overlap with your playbook's strongest domains:
- `familiar` (green) — >= 70% overlap; you are working in well-covered territory.
- `exploring` (yellow) — 30–69% overlap; some patterns exist but coverage is partial.
- `blind spot` (red) — < 30% overlap; ACE has few patterns for this domain yet.

### PLAYBOOK line

```
♦ PLAYBOOK: 148 pts  Ratio: 91% healthy  Domains: 12
```

Shows the total number of patterns in your playbook, the percentage rated helpful versus harmful, and how many distinct domains are covered. These values come from `ace-cli status` and are cached for 60 seconds (see Section 7).

### USAGE bar

```
▪ USAGE:    ⛁⛁⛁⛁⛁⛁⛁⛁⛁⛁⛁⛁⛁⛁⛁ 47%  (70/150)
```

The USAGE bar shows your plan's pattern consumption. It only appears when your account has a pattern limit (i.e., a paid plan with a cap). If you are on an unlimited plan or the limit is not set, this line is hidden.

### LEARNING sparklines

```
✿ LEARNING:  15m: 3 │ 60m: 8 │ 1d: 22 │ 1w: 97
├─ 15m: ▁▂▃▄▅
├─ 60m: ▂▃▄▅▃▂▁▂▃▄▅▃
├── 1d: ▃▄▅▄▃▂▁▂▃▄▅▄▃▂▁▃▄▅▄▃▄▄▅
└── 1w: ▂▄▅▄▃
```

Each row is a sparkline showing ACE hook event density over time. The height and color of each bar encodes relative activity: tall green bars mean high activity, short red bars mean low activity relative to the window's peak.

The counts above the sparklines (15m, 60m, 1d, 1w) are the total number of events in each window.

### CC section

```
◉ CTX: ⛁⛁⛁⛁⛁⛁⛁⛁⛁⛁⛁ 28%
▸ Model: claude-sonnet-4-5  Cost: $0.12  Time: 3m42s  CC-Lines: +127/-34
```

The CC section is Claude Code's own session information. It is separate from ACE metrics and is always shown regardless of ACE data availability.

- **CTX bar** — context window usage (green = plenty of room, red = approaching limit).
- **Model** — the model that responded.
- **Cost** — cumulative API cost for the session.
- **Time** — total wall time since session start.
- **CC-Lines** — lines added/removed by Claude Code across the session.

---

## 6. Why All Zeros? (Common Confusion)

If you run a prompt and the statusline still shows zeros, here is why and what to do.

### Session scope

All ACE metrics accumulate within a single Claude Code session and reset when you restart. The statusline aggregates events from the current session only — it does not pull history from previous sessions.

### Per-prompt scope

Each time you submit a prompt, the `UserPromptSubmit` hook fires, searches the playbook, and writes one `search` event to `ace-relevance.jsonl`. When the task completes, the `Stop` hook fires and writes one `execution` event. The statusline reads and aggregates all events for the current session.

### First prompt: Conf shows 0

`Conf` is the average confidence from the most recent search event. On the very first prompt of a fresh session, the search runs as part of `UserPromptSubmit` — but the statusline updates after `Stop`, which is at the end of the response. So after your first prompt completes, Conf will be populated and visible on the statusline. It is only 0 before any prompt has been submitted.

### "ACE: no data" — hooks have not fired yet

If the statusline shows `ACE: no data` after you submit a prompt, it means `.claude/data/logs/ace-relevance.jsonl` still does not exist. This means the ACE hooks are not running. Run `/ace-test` to verify your hook configuration and check that the hooks are wired correctly.

### What to do to see real data

1. Submit a prompt that does some work (e.g., "explain this codebase" or "implement X").
2. Wait for Claude to finish responding — the Stop hook fires at the end.
3. The next statusline update will show populated metrics.

---

## 7. Update Timing

Understanding when the statusline refreshes helps set expectations:

**Session metrics (QPT, Focus, Conf, Inj, Terrain)** — refresh after every assistant response. The `Stop` hook writes a new execution event, and the statusline reads `ace-relevance.jsonl` fresh each time (no in-process caching). Expect a brief delay between Claude's final message and the statusline updating.

**Playbook health (PLAYBOOK line)** — uses a 60-second background cache stored at `/tmp/ace-statusline-cache-*.json`. This is intentional: fetching playbook stats requires a network call to the ACE server, which would add visible latency on every response. Instead, the statusline renders from the cache immediately and refreshes the cache in the background when it is stale. Values are always within 60 seconds of the latest server state.

**First-time playbook fetch** — on a fresh session with no cache file, the PLAYBOOK line shows `--` until the background refresh completes (typically under 5 seconds). Subsequent updates use the cached file.

---

## 8. Troubleshooting

### Statusline not appearing after restart

Check that `settings.local.json` has the `statusLine` key:

```bash
cat .claude/settings.local.json | jq '.statusLine'
```

Expected output:
```json
{
  "command": ".claude/statusline-command.sh"
}
```

If the key is missing or the file does not exist, run `/ace-statusline-setup` again.

Also verify the wrapper script is executable:
```bash
ls -la .claude/statusline-command.sh
```

It should have execute permission (`-rwxr-xr-x`). If not:
```bash
chmod +x .claude/statusline-command.sh
```

### All zeros after multiple prompts

Check that the relevance log file exists:
```bash
ls .claude/data/logs/ace-relevance.jsonl
```

If the file is missing, ACE hooks have not written any data. Run `/ace-test` to verify hooks are wiring up correctly.

If the file exists but metrics stay at zero, inspect the content:
```bash
tail -5 .claude/data/logs/ace-relevance.jsonl | jq '.'
```

You should see objects with `event: "search"` and `event: "execution"` entries that have your current `session_id`.

### Statusline shows "ACE: no data"

This means `ace-relevance.jsonl` does not exist in the current project directory. The most common cause is that the ACE hooks have not run yet. Steps to verify:

1. Run `/ace-test` — this will check that hooks are firing.
2. Submit a real prompt and wait for it to complete.
3. Check that the file was created: `ls .claude/data/logs/ace-relevance.jsonl`.

### Slow startup / PLAYBOOK shows "--"

The `--` value on the PLAYBOOK line means the cache is empty and the background fetch is in progress. This is normal on the first statusline render of a session. Wait a few seconds and submit another prompt — the next render will use the populated cache.

If the PLAYBOOK line never populates, verify `ace-cli` can reach the server:
```bash
ace-cli status --json
```

---

## Next Steps

Once the statusline is running, use it to understand how ACE is performing in your project:

- **Low QPT / red score** — your playbook may not yet have patterns for the domains you are working in. Run `/ace-bootstrap` to generate initial patterns from your codebase.
- **Terrain shows "blind spot"** — submit a few tasks and let the Stop hook capture learnings. Playbook coverage grows automatically as you work.
- **Inj% near zero but Conf% is high** — patterns are being found but not referenced. Check if the patterns are specific enough to your codebase with `/ace-patterns`.

For more on the ACE plugin:
- [Installation Guide](INSTALL.md)
- [Configuration Guide](CONFIGURATION.md)
- [Troubleshooting Guide](TROUBLESHOOTING.md)
