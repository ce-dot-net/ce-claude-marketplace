# ACE Statusline Component Reference

**Version**: v5.4.27
**Script**: `plugins/ace/scripts/ace-statusline.sh`

---

## Overview

The ACE statusline is a shell script that renders a live session dashboard in Claude Code's status bar. It has two logical sections:

- **ACE section** — session effectiveness metrics sourced from `ace-relevance.jsonl`
- **CC section** — Claude Code runtime metrics sourced from the input JSON

Output is responsive: the script detects terminal width and selects one of four display modes, from a single score to a full multi-line dashboard.

**Data sources:**

| Source | Latency | Contents |
|--------|---------|----------|
| `.claude/data/logs/ace-relevance.jsonl` | <10 ms (local read) | Session events: searches, executions, learning outcomes |
| `ace-cli status --json` | Network (60 s cached) | Playbook health, usage limits, org/project info |
| Input JSON (stdin) | Immediate | CC model, context usage, cost, duration, line counts |

---

## Responsive Display Modes

The script detects terminal width using a four-tier fallback (Kitty IPC → `stty` → `tput` → `$COLUMNS`) and maps it to a mode.

| Mode | Min width | Max width | ACE components shown | CC components shown |
|------|-----------|-----------|----------------------|---------------------|
| `nano` | 0 | 39 cols | QPT only | Model, context %, cost |
| `micro` | 40 | 59 cols | QPT, Focus, Conf | Context %, model, cost, time |
| `mini` | 60 | 99 cols | QPT, Focus, Conf, Inj, playbook health ratio | Context bar (20), %, model, cost, time |
| `normal` | 100 | — | Full dashboard: all metrics + playbook + usage bar + sparklines | Context bar (40), model, cost, time, CC-Lines |

---

## ACE Section Components

### QPT — Quality Per Task

**What it measures:** A composite score summarising how effective the current session has been at using ACE patterns to deliver value. It aggregates four orthogonal signals into a single 0–100 number.

**Formula:**

```
QPT = (Focus/100 × 0.35  +
       Confidence    × 0.30  +
       LearnRate     × 0.20  +
       SuccessRate/100 × 0.15) × 100
```

All inputs are normalised to [0, 1] before weighting. The result is rounded to the nearest integer.

**Weight rationale:**

| Component | Weight | Rationale |
|-----------|--------|-----------|
| Focus | 35% | Execution efficiency is the strongest signal of productive work |
| Confidence | 30% | Pattern quality directly determines how useful injected context is |
| LearnRate | 20% | Learning propagation is the compounding benefit of ACE |
| SuccessRate | 15% | Broad success signal; lower weight because it varies by task type |

**Source:** Computed from `SESSION_FOCUS_PCT`, `SESSION_CONFIDENCE`, `SESSION_LEARN_SENT/TOTAL`, and `SESSION_SUCCESS_RATE` aggregated from `ace-relevance.jsonl` for the current session.

**Range and interpretation:**

| Range | Color | Interpretation |
|-------|-------|----------------|
| 70–100 | Green | Session is running efficiently with well-matched patterns |
| 40–69 | Yellow | Partial effectiveness; patterns may be mismatched or execution is exploratory |
| 0–39 | Red | Low effectiveness; check Conf and Focus for root cause |

A score of 70+ sustained across multiple tasks indicates ACE patterns are well-calibrated for the project domain.

---

### Focus

**What it measures:** The ratio of state-changing tool calls to total tool calls in the session. High focus means Claude is spending its tool budget on writes, edits, and creates rather than reads and explorations.

**Formula:**

```
Focus = (sum of state_changing_tools across execution events) /
        (sum of tools_executed across execution events) × 100
```

**Source:** `execution` events in `ace-relevance.jsonl`, fields `state_changing_tools` and `tools_executed`.

**Range:** 0–100%

**Interpretation:** A high Focus score (≥60%) indicates efficient task execution. A low Focus score suggests the session is heavily exploratory — which may be appropriate early in a task but should rise as implementation proceeds. Persistently low Focus combined with low QPT often signals that injected patterns are not matching the actual work.

---

### Conf — Confidence

**What it measures:** How confident the ACE server is in the patterns it retrieved for the most recent search. This reflects the quality of the playbook entries: patterns that have accumulated many "helpful" votes and few "harmful" votes produce higher confidence scores.

**Formula:**

```
Conf (%) = avg_confidence from the last search event × 100
```

The raw `avg_confidence` field on search events is a float in [0.0, 1.0]. The statusline multiplies by 100 and rounds to display as a percentage.

**Source:** `search` events in `ace-relevance.jsonl`, field `avg_confidence`. Only the **last** search event in the session is used, reflecting the most recent retrieval context.

**Range:** 0–100%

**Interpretation:** Higher values mean the patterns returned have strong historical validation from real usage. A low Conf score (below 40%) suggests either the playbook is new and under-voted, the search query did not match well-validated patterns, or the current domain is a blind spot. Use `/ace-search` to inspect what was retrieved.

---

### Inj — Injection Rate

**What it measures:** The fraction of injected patterns that Claude actually referenced during task execution. High injection rate means the patterns were relevant and Claude drew on them.

**Formula:**

```
Inj (%) = (sum of patterns_used_count across execution events) /
           (sum of patterns_injected across search events) × 100
```

**Source:** `ace-relevance.jsonl` — field `patterns_injected` on `search` events, field `patterns_used_count` on `execution` events.

**Range:** 0–100%

**Interpretation:** A high Inj rate (≥70%) indicates retrieved patterns matched the actual task well. A low Inj rate suggests patterns were injected but went unused, which may indicate over-broad retrieval or a mismatch between the query used for retrieval and the work actually performed. Combined with low Conf this can indicate a playbook calibration issue.

---

### Terrain

**What it measures:** The overlap between the domains encountered in the current session and the top five domains in the playbook. It answers: "does ACE have strong coverage for what Claude is doing right now?"

**Computation:**

1. Collect unique domains from all `search` events in the session (`domains[]` array).
2. Compare against the top five domains by pattern count from `ace-cli domains`.
3. Compute `overlap_count / session_domain_count × 100`.

**Values:**

| Value | Overlap | Meaning |
|-------|---------|---------|
| `familiar` | ≥70% | ACE has strong coverage of current domains |
| `exploring` | 30–69% | Partial coverage; some domains are new territory |
| `blind spot` | <30% | ACE has little knowledge of the current domain |
| `unknown` | no data | No domain data available yet for this session |

**Color:** `familiar` renders green, `exploring` yellow, `blind spot` and `unknown` red.

**Interpretation:** `blind spot` is not necessarily a problem — it means the current work is in an area where the playbook has not yet been trained. Running `/ace-bootstrap` or `/ace-learn` after completing work in that domain will bring it into the familiar range over time.

---

### PLAYBOOK

**What it measures:** A snapshot of the health and size of the project's pattern playbook, fetched from `ace-cli status --json`.

**Fields displayed (normal mode):**

| Field | Source | Description |
|-------|--------|-------------|
| `N pts` | `playbook.total_patterns` | Total number of patterns in the playbook |
| Ratio | `helpful_total / (helpful_total + harmful_total) × 100` | Percentage of patterns rated as helpful vs harmful |
| Domains | `playbook.by_domain \| length` | Number of distinct domains with at least one pattern |

**Caching:** Playbook data is cached in `/tmp/ace-statusline-cache[+project-id].json` for 60 seconds. When the cache is stale the script serves the previous value immediately and refreshes in the background, so the statusline never blocks on a network call.

**Interpretation:** A healthy playbook has a ratio above 80% and covers the domains most active in the project. A ratio below 60% indicates accumulated harmful patterns that should be reviewed with `/ace-patterns`.

---

### USAGE Bar

**What it measures:** Patterns consumed against the plan's pattern limit.

**Computation:**

```
USAGE_PATTERNS_PCT = USAGE_PATTERNS_USED / USAGE_PATTERNS_LIMIT × 100
```

The bar is rendered as a row of `⛁` characters. Filled buckets use a continuous color gradient:

| Position | Color |
|----------|-------|
| 0–33% | Green |
| 33–66% | Yellow → Orange |
| 66–100% | Orange → Red |

Empty bucket positions render in a dark neutral tone.

**Visibility:** The USAGE bar is only rendered when `USAGE_PATTERNS_LIMIT > 0`. Plans without a pattern limit omit the bar entirely.

---

### LEARNING Sparklines

**What it measures:** Event density in `ace-relevance.jsonl` over four time windows, visualised as sparkline bar charts. Each sparkline shows how much ACE activity (searches, executions, learning events) has occurred recently.

**Time windows and bucket parameters:**

| Label | Buckets | Bucket size | Total window |
|-------|---------|-------------|--------------|
| 15m | 15 | 60 s | 15 minutes |
| 60m | 12 | 300 s (5 min) | 60 minutes |
| 1d | 24 | 3600 s (1 h) | 24 hours |
| 1w | 7 | 86400 s (1 day) | 7 days |

**Bar heights and colors:**

Each bar is a Unicode block character scaled to event count relative to the window maximum.

| Level (1–10) | Character | Color | Meaning |
|-------------|-----------|-------|---------|
| 9–10 | `▅` | Bright green | High activity |
| 7–8 | `▄` | Green | Moderate-high activity |
| 5–6 | `▃` | Blue | Moderate activity |
| 3–4 | `▂` | Yellow | Low activity |
| 1–2 | `▁` | Light red | Minimal activity |
| 0 | ` ` | Dark (empty) | No events |

**Interpretation:** Sparklines reveal patterns in ACE usage over time. A dense 15m sparkline with sparse 1w bars indicates a project in active development. A flat 15m sparkline with dense 1d bars may indicate a context that is continuing work from earlier in the day.

**Performance note:** For short windows (bucket size ≤60 s) the script pre-filters to the last 200 lines of the relevance file to avoid parsing the entire log. Longer windows use progressively higher line limits (500, 2000) before falling back to a full scan.

---

## CC Section Components

The CC section surfaces Claude Code runtime metrics from the JSON payload passed to the script on stdin.

### Context Bar

**What it measures:** Percentage of the active context window consumed.

**Source:** `context_window.used_percentage` from the input JSON.

**Color thresholds:**

| Range | Color |
|-------|-------|
| <40% | Green |
| 40–59% | Yellow |
| 60–79% | Orange |
| ≥80% | Rose |

In `mini` mode the bar renders at 20 characters wide; in `normal` mode at 40 characters. The same green-to-red gradient used for the USAGE bar applies here.

---

### Model

**What it measures:** The display name of the active Claude model.

**Source:** `model.display_name` from the input JSON.

---

### Cost

**What it measures:** Cumulative API cost for the session in USD.

**Source:** `cost.total_cost_usd` from the input JSON.

**Format:** `$X.XX` (always two decimal places).

---

### Time

**What it measures:** Total wall-clock duration of the session.

**Source:** `cost.total_duration_ms` from the input JSON.

**Format:**

| Duration | Format |
|----------|--------|
| <60 s | `Xs` |
| 60 s – 1 h | `Xm Xs` |
| ≥1 h | `Xh Xm` |

---

### CC-Lines

**What it measures:** Net code change in the session, expressed as lines added and removed.

**Source:** `cost.total_lines_added` and `cost.total_lines_removed` from the input JSON.

**Format:** `+<added>/-<removed>`

**Visibility:** Only rendered in `normal` mode.

---

## Data File Reference

### ace-relevance.jsonl

Location: `<project-root>/.claude/data/logs/ace-relevance.jsonl`

Each line is a JSON object. The statusline reads two event types:

**`search` event fields used:**

| Field | Type | Used for |
|-------|------|---------|
| `session_id` | string | Session filtering |
| `event` | `"search"` | Event type selector |
| `avg_confidence` | float [0,1] | Conf metric |
| `patterns_injected` | int | Inj denominator |
| `domains[]` | string array | Terrain computation |
| `timestamp` | ISO 8601 | Sparkline bucketing |

**`execution` event fields used:**

| Field | Type | Used for |
|-------|------|---------|
| `session_id` | string | Session filtering |
| `event` | `"execution"` | Event type selector |
| `state_changing_tools` | int | Focus numerator |
| `tools_executed` | int | Focus denominator |
| `learning_sent` | bool | LearnRate numerator |
| `success` | bool | SuccessRate numerator |
| `patterns_used_count` | int | Inj numerator |
| `timestamp` | ISO 8601 | Sparkline bucketing |

### ace-cli status cache

Location: `/tmp/ace-statusline-cache[+<ACE_PROJECT_ID>].json`

A merged JSON object written by the background refresh process. The cache TTL is 60 seconds. The statusline always reads from the cache and never blocks on a live `ace-cli` call.

---

## Related Documentation

- **Configuration Guide**: [CONFIGURATION.md](./CONFIGURATION.md)
- **Installation Guide**: [INSTALL.md](./INSTALL.md)
- **Troubleshooting**: [TROUBLESHOOTING.md](./TROUBLESHOOTING.md)
- **Architecture**: [../technical/ARCHITECTURE.md](../technical/ARCHITECTURE.md)

---

**Questions?** File an issue on the [marketplace repository](https://github.com/ce-dot-net/ce-claude-marketplace/issues).
