# ACE Statusline Component Reference

**Version**: v5.4.27
**Script**: `plugins/ace/scripts/ace-statusline.sh`

---

## At a Glance

All metrics, their ranges, color thresholds, and what a reading means — in one place.

| Metric | Range | Green | Yellow | Red | One-line meaning |
|--------|-------|-------|--------|-----|-----------------|
| **QPT** | 0–100 | ≥70 | 40–69 | <40 | Overall session effectiveness score |
| **Focus** | 0–100% | ≥60% | 30–59% | <30% | Tool budget spent on writes vs. reads |
| **Conf** | 0–100% | ≥70% | 40–69% | <40% | How well-validated the retrieved patterns are |
| **Inj** | 0–100%+ | ≥70% | 40–69% | <40% | Fraction of injected patterns actually used |
| **Terrain** | label | `familiar` | `exploring` | `blind spot` / `unknown` | Playbook coverage of current domains |
| **PLAYBOOK ratio** | 0–100% | ≥80% | 60–79% | <60% | Helpful patterns as a share of all rated patterns |

---

## Overview

The ACE statusline is a shell script that renders a live session dashboard in Claude Code's status bar. It surfaces ACE session effectiveness metrics sourced from `ace-relevance.jsonl`.

Output is responsive: the script detects terminal width and selects one of four display modes, from a single score to a full multi-line dashboard.

**Data sources:**

| Source | Latency | Contents |
|--------|---------|----------|
| `.claude/data/logs/ace-relevance.jsonl` | <10 ms (local read) | Session events: searches, executions, learning outcomes |
| `ace-cli status --json` | Network (60 s cached) | Playbook health, usage limits, org/project info |

### Data Flow

```
ace-relevance.jsonl  ──▶  aggregate_session()  ──▶  Focus, Conf, Inj, LearnRate, SuccessRate
                                                      └──▶  compute_qpt()  ──▶  QPT

ace-cli status --json  ──▶  fetch_playbook_data()  ──▶  PLAYBOOK, USAGE bar
                             (60s cache)

session_domains + top_domains  ──▶  compute_terrain()  ──▶  Terrain
```

QPT is a *derived* metric — it rolls up Focus, Conf, LearnRate, and SuccessRate into a single score. The four contributing components are what to inspect when QPT drops.

---

## Responsive Display Modes

The script detects terminal width using a four-tier fallback (Kitty IPC → `stty` → `tput` → `$COLUMNS`) and maps it to a mode.

| Mode | Min width | Max width | Components shown | What disappears vs. previous mode |
|------|-----------|-----------|------------------|------------------------------------|
| `nano` | 0 | 39 cols | QPT only | — |
| `micro` | 40 | 59 cols | QPT, Focus, Conf | — |
| `mini` | 60 | 99 cols | QPT, Focus, Conf, Inj, playbook health ratio | — |
| `normal` | 100 | — | Full dashboard: all metrics + playbook + usage bar + sparklines | None — this is the full view |

When your terminal narrows below 100 columns, Inj, Terrain, the USAGE bar, and sparklines are all suppressed. QPT, Focus, and Conf are the last metrics standing at narrow widths because they carry the most diagnostic signal per character.

---

## ACE Section Components

### QPT — Quality Per Task

A single 0–100 composite score. If one number summarises whether the session is going well, this is it.

**What it measures:** QPT aggregates four orthogonal signals — how efficiently Claude is executing, how well-validated the retrieved patterns are, how often learning propagates back to the server, and the overall task success rate. It is a *derived* metric computed from [Focus](#focus--focus), [Conf](#conf--confidence), LearnRate, and SuccessRate.

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

**When to act:**

- **QPT < 40**: Check [Conf](#conf--confidence) first — low pattern quality drags QPT most. Then check [Focus](#focus--focus) for exploratory execution. If both are fine, low LearnRate or SuccessRate is the cause.
- **QPT 40–69 and not rising**: If the session is past initial exploration, this signals a playbook calibration issue. Run `/ace-search` to see what was retrieved; run `/ace-patterns` to review playbook quality.
- **QPT ≥ 70**: No action needed. A score that stays this high across many sessions means patterns are well-matched to the project.

**Notes:** QPT is 0 before the first `UserPromptSubmit` event fires (no events to aggregate yet). A single-task session with one search and one execution event will produce a meaningful but provisional score — interpret it as directional, not definitive.

---

### Focus

The ratio of work done to exploration. In a well-executing session, this rises as tasks progress.

**What it measures:** The fraction of tool calls in the session that change state (writes, edits, creates) versus the total tool calls fired. High focus means Claude is spending its tool budget on productive work rather than reads and explorations.

**Formula:**

```
Focus = (sum of state_changing_tools across execution events) /
        (sum of tools_executed across execution events) × 100
```

**Source:** `execution` events in `ace-relevance.jsonl`, fields `state_changing_tools` and `tools_executed`.

**Range:** 0–100%

**When to act:**

- **< 30%**: Session is heavily exploratory. Expected at the start of a task; a concern if it persists through implementation. Check whether injected patterns are actually relevant to the work being done.
- **30–59%**: Moderate exploration mixed with execution. Normal for tasks involving significant codebase navigation.
- **≥ 60%**: Efficient task execution. Claude is spending the majority of its tool budget on actual changes.

**Notes:** Focus is only meaningful once execution events exist in the log. It reflects the *cumulative* session ratio — a burst of exploration followed by heavy execution will average out. Monitor the trend over multiple tasks rather than reacting to a single reading.

---

### Conf — Confidence

A quality signal for the playbook itself. Low Conf means ACE found patterns, but those patterns have not yet earned trust through real-world usage.

**What it measures:** How confident the ACE server is in the patterns it retrieved for the most recent search. Confidence reflects accumulated community signal: patterns that have received many "helpful" votes and few "harmful" votes score higher.

**Formula:**

```
Conf (%) = avg_confidence from the last search event × 100
```

The raw `avg_confidence` field on search events is a float in [0.0, 1.0]. The statusline multiplies by 100 and rounds to display as a percentage.

**Source:** `search` events in `ace-relevance.jsonl`, field `avg_confidence`. Only the **last** search event in the session is used, reflecting the most recent retrieval context.

**Range:** 0–100%

**When to act:**

- **< 40%**: The playbook is either new and under-voted, the search did not match well-validated patterns, or the current domain is a blind spot. Run `/ace-search` to inspect what was retrieved. If the patterns look relevant but unvoted, they will grow in confidence over time as the team uses ACE.
- **40–69%**: Patterns have some validation. Reasonable for a project in active growth.
- **≥ 70%**: Patterns have strong historical validation. High Conf combined with low [Inj](#inj--injection-rate) indicates retrieval is working but pattern-task alignment is off.

**Notes:** Conf is always 0 before the first `UserPromptSubmit` of a session — no search event exists yet. Conf and [Inj](#inj--injection-rate) provide complementary signals: Conf measures pattern *quality*, Inj measures pattern *relevance to the actual task*. Both low together is the strongest signal of a calibration problem.

---

### Inj — Injection Rate

Measures whether the right patterns were retrieved. High Inj means patterns were not just injected but actually drawn upon.

**What it measures:** The fraction of injected patterns that Claude actually referenced during task execution. High injection rate means the patterns were relevant and Claude drew on them.

**Formula:**

```
Inj (%) = (sum of patterns_used_count across execution events) /
           (sum of patterns_injected across search events) × 100
```

**Source:** `ace-relevance.jsonl` — field `patterns_injected` on `search` events, field `patterns_used_count` on `execution` events.

**Range:** 0–100% (see note below)

**When to act:**

- **< 40%**: Patterns were injected but went largely unused. Either retrieval is over-broad (query did not match actual work), or the task diverged significantly from the search query. Review what was retrieved with `/ace-search`.
- **40–69%**: Moderate utilisation. Acceptable, especially for exploratory tasks.
- **≥ 70%**: Retrieved patterns matched the task well. Combined with high [Conf](#conf--confidence), this is the ideal signal.

**Notes:** Inj can exceed 100% when patterns injected in one search event are reused across multiple subsequent execution events. This is expected behaviour and a positive signal — it means a single retrieval is providing value across multiple tool calls. Inj should be read alongside [Conf](#conf--confidence): Conf measures whether patterns are high-quality, Inj measures whether they were the *right* patterns for the work at hand.

---

### Terrain

Tells you whether ACE has useful knowledge for the current work — before you see a low QPT and wonder why.

**What it measures:** The overlap between the domains encountered in the current session and the top five domains in the playbook. It answers: "does ACE have strong coverage for what Claude is doing right now?"

**Computation:**

1. Collect unique domains from all `search` events in the session (`domains[]` array).
2. Compare against the top five domains by pattern count from `ace-cli domains`.
3. Compute `overlap_count / session_domain_count × 100`.

**Values:**

| Value | Overlap | Color | Meaning |
|-------|---------|-------|---------|
| `familiar` | ≥70% | Green | ACE has strong coverage of current domains |
| `exploring` | 30–69% | Yellow | Partial coverage; some domains are new territory |
| `blind spot` | <30% | Red | ACE has little knowledge of the current domain |
| `unknown` | no data | Red | No domain data available yet for this session |

**When to act:**

- **`blind spot`**: Not necessarily a problem — it means the playbook has not yet been trained on this domain. Complete the work, then run `/ace-bootstrap` or `/ace-learn` to bring the domain into coverage. Expect [Conf](#conf--confidence) and [Inj](#inj--injection-rate) to be low in the same session.
- **`exploring`**: Normal for projects expanding into new areas. Coverage will grow naturally as sessions in those domains produce learning events.
- **`familiar`**: Optimal. Cross-reference with [Conf](#conf--confidence) to confirm that familiar domains also have well-validated patterns.

**Notes:** `unknown` is the initial state of every session before any search event fires. Terrain is complementary to [Conf](#conf--confidence) and [Inj](#inj--injection-rate): Terrain tells you whether the *domain* is covered, Conf tells you whether retrieved *patterns* are high quality, and Inj tells you whether those patterns matched the *specific task*.

---

### PLAYBOOK

Playbook health at a glance: how many patterns exist, how trustworthy they are, and how broadly they cover the project.

**What it measures:** A snapshot of the health and size of the project's pattern playbook, fetched from `ace-cli status --json`.

**Fields displayed (normal mode):**

| Field | Source | Description |
|-------|--------|-------------|
| `N pts` | `playbook.total_patterns` | Total number of patterns in the playbook |
| Ratio | `helpful_total / (helpful_total + harmful_total) × 100` | Percentage of patterns rated as helpful vs harmful |
| Domains | `playbook.by_domain \| length` | Number of distinct domains with at least one pattern |

**Caching:** Playbook data is cached in `/tmp/ace-statusline-cache[+project-id].json` for 60 seconds. When the cache is stale the script serves the previous value immediately and refreshes in the background, so the statusline never blocks on a network call.

**When to act:**

- **Ratio < 60%**: Accumulated harmful patterns are degrading retrieval quality. Run `/ace-patterns` to review and prune. Expect [Conf](#conf--confidence) and [QPT](#qpt--quality-per-task) to be suppressed until harmful patterns are removed.
- **Ratio 60–79%**: Moderate health. Normal for a growing playbook where some early patterns have been marked harmful.
- **Ratio ≥ 80%**: Healthy playbook. The bulk of patterns are validated as useful.

**Notes:** PLAYBOOK shows `--` on first render if the 60-second cache has not yet been populated. This clears after the first background refresh completes. The display requires `USAGE_PATTERNS_LIMIT > 0` for the USAGE bar (see below) but the health ratio and counts render regardless of plan type.

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

Activity density over time. Useful for orienting yourself in a long session or confirming that ACE is actively running.

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

**Interpretation:** A dense 15m sparkline with sparse 1w bars indicates a project in active development. A flat 15m sparkline with dense 1d bars may indicate a context that is continuing work from earlier in the day.

**Performance note:** For short windows (bucket size ≤60 s) the script pre-filters to the last 200 lines of the relevance file to avoid parsing the entire log. Longer windows use progressively higher line limits (500, 2000) before falling back to a full scan.

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
