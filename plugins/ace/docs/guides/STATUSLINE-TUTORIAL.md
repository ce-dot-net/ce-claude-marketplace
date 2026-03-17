# Getting Started with the ACE Statusline

**Audience**: ACE is already installed. You want to add the live statusline to your Claude Code setup.

**Time**: ~5 minutes

---

## 🎯 What is the ACE Statusline?

Without the statusline, ACE is a black box. Patterns get retrieved, tasks get executed, learning gets captured — but you have no visibility into whether any of it is actually working for you. Is ACE finding relevant patterns, or returning noise? Is Claude using what it found, or ignoring it? Is your playbook growing?

The statusline answers those questions after every single response. It appears inside Claude Code as a live dashboard showing ACE effectiveness metrics for your current session: how focused Claude is being, how confidently patterns matched your work, and whether your playbook is accumulating knowledge in the domains you actually use.

The display adapts to your terminal width across four responsive modes:

| Mode | Width | What you see |
|---|---|---|
| nano | < 40 cols | QPT score only |
| micro | 40–59 cols | QPT + Focus + Confidence |
| mini | 60–99 cols | QPT + all metrics + playbook health |
| normal | 100+ cols | Full dashboard with sparkline activity charts |

A terminal width of 100 columns or more is recommended to see the full dashboard. The rest of this tutorial assumes normal mode.

---

## 📋 Prerequisites

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

## 🚀 Install

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

## 🔍 First Run

After restarting Claude Code and opening your project, you may briefly see one of two placeholder states before any prompts are submitted:

**`ACE: awaiting session`** — Claude Code has not yet provided a session ID. This is a normal startup state; it resolves within a second or two as the session initializes.

**`ACE: no data`** — The session ID is present, but `.claude/data/logs/ace-relevance.jsonl` does not exist yet. This means no ACE hooks have fired in this project. After your first prompt completes, the file is created and the statusline switches to showing real data.

On your very first prompt after setup, all metrics will show zeros. This is expected — Section 6 explains exactly what is happening and why it resolves on its own.

---

## 📊 Reading the Output

In **normal** mode (terminal width >= 100 cols) the statusline renders as a multi-line dashboard. Here is a complete example of what you will see after a productive session:

```
◉ QPT: 72  Focus: 85%  Conf: 60%  Inj: 40%  Terrain: familiar
♦ PLAYBOOK: 148 pts  Ratio: 91% healthy  Domains: 12
▪ USAGE:    ⛁⛁⛁⛁⛁⛁⛁⛁⛁⛁⛁⛁⛁⛁⛁ 47%  (70/150)
✿ LEARNING:  15m: 3 │ 60m: 8 │ 1d: 22 │ 1w: 97
├─ 15m: ▁▂▃▄▅
├─ 60m: ▂▃▄▅▃▂▁▂▃▄▅▃
├── 1d: ▃▄▅▄▃▂▁▂▃▄▅▄▃▂▁▃▄▅▄▃▄▄▅
└── 1w: ▂▄▅▄▃
```

Let's walk through each line.

### ◉ QPT — Quality Per Task

```
◉ QPT: 72  Focus: 85%  Conf: 60%  Inj: 40%  Terrain: familiar
```

**QPT** (Quality Per Task) is a composite score from 0–100 representing how effectively ACE helped Claude during this session. It is a weighted blend of Focus, Confidence, learning rate, and task success rate. Think of it as a single health number for the session: above 70 means ACE is pulling its weight, below 40 means your playbook probably lacks patterns for the domains you are working in.

Color interpretation:
- ✅ Green (>= 70) — ACE is contributing well; patterns are being found and used.
- 🟡 Yellow (40–69) — partial contribution; some patterns matched but usage is moderate.
- 🔴 Red (< 40) — low contribution; playbook may lack patterns for this domain.

**Focus** — the percentage of Claude's tool calls that were state-changing (writes, edits, creates) versus reads. Higher focus generally means Claude is executing rather than exploring. A low Focus score on a simple implementation task can signal that Claude is spending more time reading the codebase than making changes — worth noticing if it's a pattern.

**Conf** — average confidence of pattern matches returned by the ACE search on the most recent `UserPromptSubmit`. This tells you how well your playbook's patterns aligned with the prompt semantically. High Conf means ACE found strong matches; low Conf means the domain may be undercovered. A value of 0% on the first prompt is expected (see Section 6).

**Inj** — the percentage of injected patterns that Claude actually used (referenced in tool calls). This is the signal for pattern *quality*, not just retrieval. If Conf is high but Inj is near zero, ACE is finding patterns but they are too generic to be actionable — run `/ace-patterns` to inspect what's being injected.

**Terrain** — how well the current session's domains overlap with your playbook's strongest domains:
- `familiar` (green) — >= 70% overlap; you are working in well-covered territory.
- `exploring` (yellow) — 30–69% overlap; some patterns exist but coverage is partial.
- `blind spot` (red) — < 30% overlap; ACE has few patterns for this domain yet.

If you see `blind spot`, don't panic — it just means ACE hasn't learned this domain yet. Your next Stop hook will start building that coverage automatically.

### ♦ PLAYBOOK line

```
♦ PLAYBOOK: 148 pts  Ratio: 91% healthy  Domains: 12
```

The total number of patterns in your playbook, the percentage rated helpful versus harmful, and how many distinct domains are covered. These values come from `ace-cli status` and are cached for 60 seconds (see Section 7 for why). A healthy ratio above 85% and growing domain count is a good sign that your playbook is maturing.

### ▪ USAGE bar

```
▪ USAGE:    ⛁⛁⛁⛁⛁⛁⛁⛁⛁⛁⛁⛁⛁⛁⛁ 47%  (70/150)
```

Your plan's pattern consumption against its cap. This line only appears when your account has a pattern limit (i.e., a paid plan with a cap). If you are on an unlimited plan or the limit is not set, this line is hidden.

### ✿ LEARNING sparklines

```
✿ LEARNING:  15m: 3 │ 60m: 8 │ 1d: 22 │ 1w: 97
├─ 15m: ▁▂▃▄▅
├─ 60m: ▂▃▄▅▃▂▁▂▃▄▅▃
├── 1d: ▃▄▅▄▃▂▁▂▃▄▅▄▃▂▁▃▄▅▄▃▄▄▅
└── 1w: ▂▄▅▄▃
```

Each row is a sparkline showing ACE hook event density over time. The height and color of each bar encodes relative activity: tall green bars mean high activity, short red bars mean low activity relative to the window's peak. The counts above (15m, 60m, 1d, 1w) are the total number of events in each window. A flat or empty 1w sparkline on a project you've been using for days is a signal to check whether your Stop hook is firing — that's where learning events originate.

---

## 🤔 Why All Zeros? (Common Confusion)

You just ran a task. Claude responded. The statusline updated. Everything is zero.

Here is exactly what happened — and why it resolves on its own.

### What the statusline is actually reading

The statusline reads `.claude/data/logs/ace-relevance.jsonl`, a log file that ACE hooks write to during your session. Every metric on the dashboard is derived from events in that file. No events yet means all zeros, every time.

Two hooks write to that file:

- **`UserPromptSubmit`** fires when you submit a prompt. It searches the playbook and writes a `search` event containing the confidence score of each match.
- **`Stop`** fires when Claude finishes responding. It writes an `execution` event containing what tool calls were made, which patterns were used, and what domains were active.

The statusline updates after `Stop` — so both events need to exist before you see meaningful numbers.

### All metrics are scoped to the current session

ACE metrics accumulate within a single Claude Code session and reset when you restart. The statusline aggregates only the events from your current session — it does not pull history from previous sessions. On session start, the slate is clean.

### The first-prompt sequence

Here is the exact sequence on your very first prompt:

1. You submit a prompt → `UserPromptSubmit` fires, searches the playbook, writes a `search` event.
2. Claude responds → `Stop` fires, writes an `execution` event.
3. Statusline updates → now it has both events and can calculate metrics.

So after your first prompt completes, Conf will be populated and QPT will have data. The zeros you see immediately after submitting are correct — the Stop hook hasn't fired yet.

### "ACE: no data" means hooks haven't run at all

If the statusline shows `ACE: no data` even after a prompt completes, the log file was never created, which means the ACE hooks are not running. Run `/ace-test` to check your hook configuration and verify the hooks are wired correctly.

### What to do

Submit a prompt that does real work — something like "explain this codebase" or "implement X". Wait for Claude to finish responding completely. The next statusline update will show populated metrics.

---

## ⏱️ Update Timing

Knowing when each piece of the dashboard refreshes helps you trust what you are reading.

**Session metrics (QPT, Focus, Conf, Inj, Terrain)** refresh after every assistant response. The `Stop` hook writes a new execution event, and the statusline reads `ace-relevance.jsonl` fresh each time — no in-process caching. Expect a brief delay between Claude's final message and the statusline updating; that's the Stop hook running.

**Playbook health (PLAYBOOK line)** uses a 60-second background cache stored at `/tmp/ace-statusline-cache-*.json`. This is intentional: fetching playbook stats requires a network call to the ACE server, which would add visible latency on every single response. Instead, the statusline renders from the cache immediately and refreshes it in the background when stale. The values you see are always within 60 seconds of the latest server state.

**First-time playbook fetch** — on a fresh session with no cache file, the PLAYBOOK line shows `--` until the background refresh completes (typically under 5 seconds). Subsequent updates use the cached file.

**Platform behavior** — Claude Code runs the statusline command after every assistant response, when the permission mode changes, and when vim mode toggles. Updates are debounced at 300ms (rapid changes batch into a single run). If a new update triggers while the script is still running, the in-flight execution is cancelled. The statusline does **not** refresh on a time interval while Claude Code is idle — if you want updated playbook counts without sending a message, there is an open feature request for a `refreshIntervalSeconds` option ([issue #5685](https://github.com/anthropics/claude-code/issues/5685)).

---

## 🔧 Troubleshooting

### Statusline not appearing after restart

**Symptom**: You restarted Claude Code after running `/ace-statusline-setup` and see no statusline at all.

**What's happening**: Claude Code won't render a statusline unless the `statusLine` key exists in `settings.local.json` pointing to an executable script. Either the setup didn't complete, or the file isn't executable.

**Fix**: Check that the key is present:

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

---

### All zeros after multiple prompts

**Symptom**: You've submitted several prompts and all metrics remain at zero.

**What's happening**: The statusline script runs fine, but the log file either doesn't exist (hooks never fired) or exists but contains no events for your current session ID.

**Fix**: Check whether the log file exists:
```bash
ls .claude/data/logs/ace-relevance.jsonl
```

If it's missing, ACE hooks have not written any data. Run `/ace-test` to verify hooks are wiring up correctly.

If the file exists but metrics stay at zero, inspect the content:
```bash
tail -5 .claude/data/logs/ace-relevance.jsonl | jq '.'
```

You should see objects with `event: "search"` and `event: "execution"` entries that have your current `session_id`. If entries exist but with a different session ID, you are looking at data from a previous session — this is normal and the current session will accumulate its own events as you work.

---

### Statusline shows "ACE: no data"

**Symptom**: After submitting a prompt, the statusline displays `ACE: no data` rather than metrics.

**What's happening**: The log file `.claude/data/logs/ace-relevance.jsonl` does not exist in the current project directory. The most common cause is that the ACE hooks have not run yet — either because this is a brand-new project or because the hook configuration is broken.

**Fix**:
1. Run `/ace-test` — this checks that hooks are firing.
2. Submit a real prompt and wait for it to complete.
3. Confirm the file was created: `ls .claude/data/logs/ace-relevance.jsonl`.

---

### Slow startup / PLAYBOOK shows "--"

**Symptom**: The PLAYBOOK line shows `--` for the first several seconds of a session.

**What's happening**: There is no cache file yet, so the statusline is waiting for the background `ace-cli status` call to complete and populate it. This is normal — it is not an error.

**Fix**: Wait a few seconds and submit another prompt. The next render will use the populated cache. If the PLAYBOOK line never populates after 10–15 seconds, verify `ace-cli` can reach the server:
```bash
ace-cli status --json
```

---

## 📚 Next Steps

Once the statusline is running, you can use it as a feedback loop to actively improve ACE's effectiveness in your project:

- **Low QPT / red score** — your playbook may not yet have patterns for the domains you are working in. Run `/ace-bootstrap` to generate initial patterns from your codebase.
- **Terrain shows "blind spot"** — submit a few tasks and let the Stop hook capture learnings. Playbook coverage grows automatically as you work; `blind spot` becomes `exploring` becomes `familiar` over time.
- **Inj% near zero but Conf% is high** — patterns are being found but not referenced. This usually means patterns are too generic. Inspect them with `/ace-patterns` and consider whether they contain specific enough code or commands for your project.

For more on the ACE plugin:
- [Installation Guide](INSTALL.md)
- [Configuration Guide](CONFIGURATION.md)
- [Troubleshooting Guide](TROUBLESHOOTING.md)
