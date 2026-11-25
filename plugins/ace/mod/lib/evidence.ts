// F-080 evidence: self-eval prompt + review parse, used-pattern ids (H1/H2), applied log ids, eval stats/injection,
// user-rejection match (ace_feedback). Pure: no `$`, no I/O.
import { num } from './pyjson'
import { cps, cpSlice, normWs } from './text'

export type ToolRec = { tool: string; action: string; result: string; failed: boolean; start_ms: number; end_ms: number; commit?: string
  hay?: string  // hay: the call's toolHaystack (item H2 used check), never sent in the trace
  key?: string; dec?: boolean; intr?: true  // 8.1.3 outcome: recovery key, decisive step, interrupted (lib/trace.ts taskOutcome)
  input?: unknown; output?: unknown }  // full steps: the redacted tool input / output, sent as the step's tool_input / tool_response

// ace_after_task.parse_ace_review
export function parseAceReview(msg: string): { quality_pct: number; time_saved: string } | null {
  const m = /ACE_REVIEW:\s*(\d+)/.exec(msg || '')
  if (!m) return null
  const t = /\d+m\d*s? saved|\d+s saved|\d+ ?min/.exec(msg)
  return { quality_pct: Number(m[1]), time_saved: t ? t[0].replace(' saved', '') : '' }
}

// patterns_used_state.eval_stats: mean confidence of the INJECTED x100 (truncated, 0..100; non-number 0), distinct RETURNED domains
export function evalStats(injected: any[], returned: any[]): { avg_relevance: number; domains: number } {
  const conf = (injected ?? []).map(p => { const c = num(p?.confidence); return c !== undefined && Number.isFinite(c) ? c : 0 })
  const rel = conf.length ? Math.trunc(conf.reduce((x, y) => x + y, 0) / conf.length * 100) : 0
  const doms = new Set((returned ?? []).filter(p => p && p.domain).map(p => String(p.domain)))
  return { avg_relevance: Math.max(0, Math.min(100, rel)), domains: doms.size }
}

// item D / H1: the Haiku self-eval request (a $.model.complete prompt, never the conversation): the task, its tool
// calls, the injected patterns as `id: content` lines and the final answer, each capped; two lines back.
// 8.2.7: EVERY injected pattern is listed (a 6,000-char cut showed Haiku only the first ~20 of a full arm's ~100, so
// it could never name a later one). The content per pattern shrinks with the count to keep the block near
// SELF_EVAL_PATTERN_CHARS: 8 patterns keep all 600 chars, 100 get ~200 (~24k chars, ~6k tokens; Haiku p50 ~5 s in
// the 8.2.7 probe, inside the 15 s SELF_EVAL_MS), ~300 get ~40, never under 20. The block never passes the budget:
// only when even id + 20 chars per pattern does not fit (~400+ ids) is the list cut, injected order kept.
// A pattern text cannot close the block early: its "</patterns>" is masked.
export const SELF_EVAL_PATTERN_CHARS = 24000
export function selfEvalPrompt(a: { task: string; answer: string; ids: string[]; contents: Record<string, string>; tools: ToolRec[] }): string {
  const per = Math.max(20, Math.min(CONTENT_CAP, Math.floor(SELF_EVAL_PATTERN_CHARS / Math.max(1, a.ids.length)) - 40))
  const lines: string[] = []
  let n = 0
  for (const id of a.ids) {
    const l = `${id}: ${cpSlice(normWs(a.contents?.[id] ?? ''), per).replace(/<\/patterns>/gi, '</ patterns>')}`
    if (n + l.length + 1 > SELF_EVAL_PATTERN_CHARS) break
    lines.push(l); n += l.length + 1
  }
  const tools = cpSlice(a.tools.map(t => `${t.tool}: ${t.action}${t.failed ? ' (failed)' : ''}`).join('\n'), 4000)
  return 'You review one finished coding task for a pattern library. Patterns were injected into the agent before it worked.\n' +
    'The tool calls below already ran in the agent\'s session; their output is left out on purpose. Do not call any tool: judge from this text only. ' +
    'A pattern counts as used when the tool calls or the final answer follow its specific advice, whether or not you can verify the outcome; ' +
    'a generic step any task takes (reading a file, running a linter) is not using a pattern.\n' +
    '<task>\n' + cpSlice(a.task, 2000) + '\n</task>\n<tool_calls>\n' + tools + '\n</tool_calls>\n' +
    '<patterns>\n' + lines.join('\n') + '\n</patterns>\n<final_answer>\n' + cpSlice(a.answer, 4000) + '\n</final_answer>\n' +
    'Answer with exactly two lines and nothing else:\n' +
    'ACE_REVIEW: N% | Xm saved | one-line reason   (N = how much the patterns helped; X = minutes a human developer saved)\n' +
    'ACE_USED: the comma-separated ids of the patterns the task DEMONSTRABLY applied (visible in its tool calls or answer), or none'
}
// ACE_USED ids, whitelisted against the injected set, injected order
export function parseUsedIds(text: string, injected: string[]): string[] {
  const m = /ACE_USED:\s*([^\n]*)/.exec(text || '')
  if (!m) return []
  const named = new Set(m[1]!.split(/[\s,;]+/).map(x => x.replace(/^[`'"<\[(]+|[`'">\]).]+$/g, '')).filter(Boolean))
  return injected.filter(id => named.has(id))
}

// §31 / item H2 "actually used" (patterns_used_state.used_pattern_ids): evidence in what the task DID. Its id in the
// final message / report or the tool inputs, or its evidence tokens as whole tokens in the tool-call inputs: >= 3, or
// >= 2 with one strong (a path / identifier / multi-word span), or one multi-word span whose command is not universal
// (the pattern's own project command). 8.2.7: two plain words or flags were 25% false hits on foreign tasks. A token
// in more than 30% of the injected patterns (and more than one) is too generic. An absolute
// count, never a share of the pattern's tokens: a long pattern does not fire more often than a short one. Injected order.
export const CONTENT_CAP = 600, USED_MESSAGE_CAP = 50000
const TOOL_INPUT_KEYS = ['command', 'file_path', 'path', 'pattern', 'glob', 'notebook_path', 'url']
const TOKEN_STOP = new Set(['and/or', 'e.g.', 'i.e.', 'etc.', 'n/a', 'w/o', 'http://', 'https://', 'true/false', 'yes/no'])
const STRIP = new Set(Array.from("`'\"()[]{}<>,;:!?*"))
// 8.2.7: universal shell vocabulary (POSIX tools, git subcommands, common flags) is in every task's tool calls and says
// nothing about a pattern: a token made only of these words is no evidence. Python parity (_UNIVERSAL).
// ponytail: a fixed list; learn it from a corpus if new noise shows up.
const UNIVERSAL = new Set(('git status diff log add commit checkout push pull show branch stash fetch merge rebase reset grep egrep rg find ls ' +
  'cat head tail sed awk echo printf cd pwd rm cp mv mkdir touch chmod wc sort uniq xargs tee curl jq python python3 ' +
  'pip node npm npx bun pytest bash sh zsh sudo env export source date which true false ps pgrep pkill kill lsof ' +
  '-m -c -q -r -e -n -l -i -v -f -x -la -rf -name -type --stat --oneline --json --help --version --verbose --quiet ' +
  '--force --all 2>/dev/null /dev/null 2>&1 >/dev/null && || | ' +
  'test tests run lint build install start dev format check typecheck rstest cargo make go yarn pnpm tsc eslint prettier ruff mypy docker gh').split(' '))
// tool_haystack: lowercased tool-call inputs (Bash commands, paths, Grep/Glob patterns, Edit targets), never edit bodies
export function toolHaystack(inputs: any[]): string {
  const parts: string[] = []
  for (const ti of inputs ?? []) if (ti && typeof ti === 'object') for (const k of TOOL_INPUT_KEYS) if (typeof ti[k] === 'string' && ti[k]) parts.push(ti[k])
  return parts.join('\n').toLowerCase()
}
const qualifies = (w: string) => {
  if (cps(w).length < 4 || TOKEN_STOP.has(w)) return false
  if (w.includes('/') || w.includes('_') || w.includes('::') || /[a-z][A-Z]/.test(w)) return true
  if (/^--?[A-Za-z][A-Za-z0-9_-]*$/.test(w)) return true
  return /[A-Za-z0-9_]\.[A-Za-z0-9_]/.test(w)
}
// names something specific: a path, an identifier ('_', '::', camelCase) or a dotted name. An ENV_STYLE name is not:
// the same names (ORG_ID, PROJECT_ID, NODE_ENV) sit in many projects' commands, so it only counts as a weak token.
const anchored = (w: string) => !/^[A-Z][A-Z0-9]*(_[A-Z0-9]+)+$/.test(w) && (w.includes('/') || w.includes('_') || w.includes('::') || /[a-z][A-Z]/.test(w) || /[A-Za-z0-9_]\.[A-Za-z0-9_]/.test(w))
// {token: strong}: backticked spans (and their first two words), paths, CLI flags, identifiers; lowercased, length >= 4,
// no universal vocabulary. strong = anchored or a multi-word span; a single plain backticked word or a lone flag is weak.
export function evidenceTokens(content: unknown): Map<string, boolean> {
  const text = cpSlice(String(content ?? ''), CONTENT_CAP), toks = new Map<string, boolean>()
  const add = (t: string, strong: boolean) => {
    const low = t.toLowerCase(), words = low.split(' ')
    if (TOKEN_STOP.has(low) || words.every(w => UNIVERSAL.has(w) || (words.length > 1 && w.startsWith('-')))) return
    toks.set(low, toks.get(low) || strong)
  }
  for (const m of text.matchAll(/`([^`\n]+)`/g)) {
    const span = normWs(m[1]), w = span.split(' ')
    if (cps(span).length >= 4) add(span, w.length > 1 || anchored(span))
    if (w.length >= 2 && cps(w[0] + ' ' + w[1]).length >= 4) add(w[0] + ' ' + w[1], true)
  }
  for (const raw of text.split(/\s+/).filter(Boolean)) {
    let a = Array.from(raw), i = 0, j = a.length
    while (i < j && STRIP.has(a[i]!)) i++
    while (j > i && STRIP.has(a[j - 1]!)) j--
    let w = a.slice(i, j).join('')
    while (w.endsWith('.')) w = w.slice(0, -1)
    if (qualifies(w)) add(w, anchored(w))
  }
  return toks
}
// t in hay as a whole token: a word character at an edge of t must not continue into hay (regex \b)
const isWord = (c: string | undefined) => !!c && /^[A-Za-z0-9_]$/.test(c)
function hasToken(hay: string, t: string): boolean {
  for (let i = hay.indexOf(t); i >= 0; i = hay.indexOf(t, i + 1)) {
    const j = i + t.length
    if (!(isWord(t[0]) && isWord(hay[i - 1])) && !(isWord(t[t.length - 1]) && isWord(hay[j]))) return true
  }
  return false
}
export function usedPatternIds(ids: string[], contents: Record<string, string>, message: string | undefined, haystack = ''): string[] {
  const msg = cpSlice(normWs(message), USED_MESSAGE_CAP)
  const list = (ids ?? []).filter(id => typeof id === 'string' && id)
  const toks = new Map(list.map(id => [id, evidenceTokens(contents?.[id])] as const))
  const df = new Map<string, number>()
  for (const ts of toks.values()) for (const t of ts.keys()) df.set(t, (df.get(t) ?? 0) + 1)
  const generic = new Set([...df].filter(([, n]) => n > 1 && n > 0.3 * list.length).map(([t]) => t))
  return list.filter(id => {
    if (msg.includes(id) || haystack.includes(id.toLowerCase())) return true
    if (!haystack) return false
    const hits = [...toks.get(id)!].filter(([t]) => !generic.has(t) && hasToken(haystack, t))
    return hits.length >= 3 || (hits.length >= 2 && hits.some(([, strong]) => strong)) ||
      hits.some(([t, strong]) => strong && t.includes(' ') && !UNIVERSAL.has(t.split(' ')[0]!))
  })
}
export function injectedContents(patterns: any[], ids: string[]): Record<string, string> {
  const byId = new Map<string, unknown>(), out: Record<string, string> = {}
  for (const p of patterns ?? []) if (p && !byId.has(p.id)) byId.set(p.id, p.content)
  for (const id of ids) { const c = byId.get(id); if (c) out[id] = cpSlice(String(c), CONTENT_CAP) }  // injected order (Python parity)
  return out
}
// §31: applied_log_ids = the USED ids that have a retrieval log id, for every variant. Server 5.15.8: more than 20 in
// one trace count as "all shown" (the trace falls to COLD), so `used` comes ordered by evidence and is cut at 20.
export const APPLIED_LOG_IDS_CAP = 20
export function appliedLogIds(used: string[], rlog: Record<string, number>): { ids: number[]; capped: boolean } {
  const all = used.filter(id => id in rlog).map(id => rlog[id]!)
  return { ids: all.slice(0, APPLIED_LOG_IDS_CAP), capped: all.length > APPLIED_LOG_IDS_CAP }
}

// prompt <= 300 chars with a phrase as a whole word. A hit is blocked when the word before it is a negation
// ("nicht falsch", "nichts falsch", "kein ... falsch", "never wrong") or "oder"/"or" ("richtig oder falsch"), or when it
// closes a rhetorical question about the user ("sehe ich das falsch", "liege ich falsch"). The longest hit wins (ties: list order).
export const REJECTION_PHRASES = ["falsch", "stimmt nicht", "geht nicht", "funktioniert nicht", "klappt nicht", "rückgängig",
  "mach das rückgängig", "immer noch kaputt", "immer noch nicht", "nicht das was ich wollte", "das war nicht gemeint", "doch nicht",
  "das ist falsch", "kaputt gemacht", "arbeit umsonst", "alles umsonst", "war umsonst", "das war mist", "scheisse aus", "scheiße aus",
  "wrong", "that's wrong", "doesn't work", "does not work", "not working", "still broken", "still not", "not what i asked",
  "that broke", "you broke"]
export const REJECTION_MAX_CHARS = 300
export const REJECTION_PREV_MAX_AGE_S = 6 * 3600
const REJECTION_BLOCKERS = ['nicht', 'not', 'nichts', 'kein', 'keine', 'keinen', 'keiner', 'nie', 'never', 'oder', 'or']
const isWordChar = (c: string) => /[\p{L}\p{N}_]/u.test(c)
// {matched: the longest unblocked phrase, blocked: the longest phrase a guard dropped, tooLong: > 300 chars}
export function rejectionProbe(text: string | undefined): { matched: string | null; blocked: string | null; tooLong: boolean } {
  const low = String(text ?? '').trim().toLowerCase().replace(/[\u2018\u2019]/g, "'")
  if ([...low].length > REJECTION_MAX_CHARS) return { matched: null, blocked: null, tooLong: true }
  let best: string | null = null, blocked: string | null = null
  for (const phrase of REJECTION_PHRASES) {
    for (let i = low.indexOf(phrase); i >= 0; i = low.indexOf(phrase, i + 1)) {
      const j = i + phrase.length
      if ((i > 0 && isWordChar(low[i - 1]!)) || (j < low.length && isWordChar(low[j]!))) continue
      const before = low.slice(0, i), words = before.split(/\s+/).filter(Boolean), spaced = before !== before.trimEnd()
      const last = words[words.length - 1], prev = words[words.length - 2]
      const rhetorical = phrase === 'falsch' || phrase === 'wrong'  // "sehe ich das falsch", "liege ich falsch"; "das wollte ich doch nicht" stays a rejection
      const guard = spaced && last !== undefined && (REJECTION_BLOCKERS.includes(last) || (rhetorical && (last === 'ich' || (prev === 'ich' && (last === 'das' || last === 'es')))))
      if (guard) { if (blocked === null || phrase.length > blocked.length) blocked = phrase; continue }
      if (best === null || phrase.length > best.length) best = phrase
      break
    }
  }
  return { matched: best, blocked: best === null ? blocked : null, tooLong: false }
}

// Upvote phrase fast-path (mod-only), PRECISION first: a phrase as a whole word (any of UPVOTE_PHRASES), every phrase hit cut out,
// and what is left must be filler words only (thanks, intensifiers, pronouns): the message is nothing but the approval. Anything
// else (a negation, a '?', a new or additional task, a 'but ...') leaves real words -> blocked, the model decides. Bare
// acknowledgements (ok, ja, weiter, thanks) are never an upvote (bareAck: no phrase, no model upvote).
export const UPVOTE_PHRASES = ['perfekt', 'genau richtig', 'genau so', 'genau das', 'super das klappt', 'das klappt', 'klappt jetzt', 'klappt super',
  'klappt perfekt', 'funktioniert jetzt', 'funktioniert super', 'funktioniert perfekt', 'funktioniert einwandfrei', 'läuft jetzt', 'läuft super',
  'passt perfekt', 'gut gemacht', 'hat geklappt', 'hat funktioniert', 'das hat geholfen', 'perfect', 'works', 'works now', 'that works', 'it works',
  'works great', 'works perfectly', 'that fixed it', 'thanks that fixed it', 'fixed it', 'great job', 'good job', 'well done', 'nice work',
  'exactly right', 'exactly what i wanted', 'spot on', 'nailed it', 'excellent', 'awesome', 'looks good', 'lgtm']
const UPVOTE_FILLER = new Set(['danke', 'dank', 'vielen', 'besten', 'herzlichen', 'dir', 'euch', 'super', 'toll', 'prima', 'klasse', 'wow', 'oh', 'ah',
  'ja', 'jo', 'yes', 'yeah', 'yep', 'ok', 'okay', 'cool', 'nice', 'great', 'good', 'gut', 'sehr', 'echt', 'wirklich', 'really', 'so', 'very', 'much',
  'thanks', 'thank', 'thx', 'ty', 'you', 'du', 'it', 'that', 'this', 'das', 'es', 'ist', 'is', 'now', 'jetzt', 'alles', 'all', 'everything', 'for',
  'me', 'mir', 'uns', 'us', 'again', 'wieder', 'nochmal', 'endlich', 'finally', 'totally', 'absolutely', 'völlig', 'voll', 'einwandfrei', 'richtig',
  'genau', 'just', 'einfach', 'und', 'and', 'haha', 'lol', 'perfectly', 'man', 'mann'])
const UPVOTE_ACK = new Set(['ok', 'okay', 'k', 'ja', 'jo', 'yes', 'yeah', 'yep', 'weiter', 'mach', 'continue', 'go', 'on', 'gut', 'good', 'fine', 'alright',
  'passt', 'danke', 'thanks', 'thank', 'you', 'thx', 'sure', 'klar', 'cool', 'nice', 'super', 'toll', 'prima'])
const UPVOTE_SORTED = [...UPVOTE_PHRASES].sort((a, b) => b.length - a.length)
const words = (t: string) => t.match(/[\p{L}\p{N}_']+/gu) ?? []
// {matched: the longest phrase when the message is only an approval, blocked: a phrase hit with other content, tooLong, bareAck}
export function upvoteProbe(text: string | undefined): { matched: string | null; blocked: string | null; tooLong: boolean; bareAck: boolean } {
  const low = String(text ?? '').trim().toLowerCase().replace(/[‘’]/g, "'")
  if ([...low].length > REJECTION_MAX_CHARS) return { matched: null, blocked: null, tooLong: true, bareAck: false }
  const w = words(low)
  // 3b: emoji / symbol-only replies (no word at all, e.g. a thumbs-up) count as a bare acknowledgement too
  const bareAck = w.length > 0 ? w.every(x => UPVOTE_ACK.has(x)) : low !== ''
  let rest = low, best: string | null = null
  for (const phrase of UPVOTE_SORTED) {
    for (let i = rest.indexOf(phrase); i >= 0; i = rest.indexOf(phrase, i + 1)) {
      const j = i + phrase.length
      if ((i > 0 && isWordChar(rest[i - 1]!)) || (j < rest.length && isWordChar(rest[j]!))) continue
      if (best === null) best = phrase
      rest = rest.slice(0, i) + ' ' + rest.slice(j)
    }
  }
  if (best === null) return { matched: null, blocked: null, tooLong: false, bareAck }
  const clean = !low.includes('?') && words(rest).every(x => UPVOTE_FILLER.has(x))
  return { matched: clean ? best : null, blocked: clean ? null : best, tooLong: false, bareAck }
}
