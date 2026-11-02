// Pure ACE logic of the v8 mod: no `$`, no I/O, so node (tests/e2e/mod_parity_node.mjs) and the mod share it.
// Every function names the shared-hooks Python it mirrors.

// ---------- Python-compatible JSON (json.loads / json.dumps defaults) ----------
// Python keeps int vs float apart ("1.0" stays 1.0); JS does not. Floats are boxed on parse.
export class PyFloat { v: number; constructor(v: number) { this.v = v } }
export const num = (x: unknown): number | undefined =>
  x instanceof PyFloat ? x.v : typeof x === 'number' ? x : undefined

export function pyLoads(src: string): any {
  let i = 0
  const ws = () => { while (i < src.length && ' \t\n\r'.includes(src[i])) i++ }
  const val = (): any => {
    ws()
    const c = src[i]
    if (c === '{') {
      i++; const o: any = {}; ws()
      if (src[i] === '}') { i++; return o }
      for (;;) {
        ws(); const k = str(); ws()
        if (src[i++] !== ':') throw new SyntaxError('expected : at ' + i)
        o[k] = val(); ws()
        const d = src[i++]
        if (d === '}') return o
        if (d !== ',') throw new SyntaxError('expected , at ' + i)
      }
    }
    if (c === '[') {
      i++; const a: any[] = []; ws()
      if (src[i] === ']') { i++; return a }
      for (;;) {
        a.push(val()); ws()
        const d = src[i++]
        if (d === ']') return a
        if (d !== ',') throw new SyntaxError('expected , at ' + i)
      }
    }
    if (c === '"') return str()
    if (src.startsWith('true', i)) { i += 4; return true }
    if (src.startsWith('false', i)) { i += 5; return false }
    if (src.startsWith('null', i)) { i += 4; return null }
    const m = /^-?\d+(\.\d+)?([eE][+-]?\d+)?/.exec(src.slice(i, i + 40))
    if (!m) throw new SyntaxError('bad JSON at ' + i)
    i += m[0].length
    return m[1] || m[2] ? new PyFloat(Number(m[0])) : Number(m[0]) // ponytail: ints > 2^53 lose precision; none in ACE payloads
  }
  const str = (): string => {
    if (src[i] !== '"') throw new SyntaxError('expected string at ' + i)
    const start = i; i++
    while (i < src.length && src[i] !== '"') i += src[i] === '\\' ? 2 : 1
    if (i >= src.length) throw new SyntaxError('unterminated string at ' + start)
    i++
    return JSON.parse(src.slice(start, i))
  }
  const v = val(); ws()
  if (i !== src.length) throw new SyntaxError('trailing data')
  return v
}

// repr(float) (Python 'r' format): fixed for 1e-4 <= |x| < 1e16, else scientific with >= 2 exponent digits.
export function pyFloatRepr(x: number): string {
  if (Number.isNaN(x)) return 'NaN'
  if (!Number.isFinite(x)) return x > 0 ? 'Infinity' : '-Infinity'
  if (x === 0) return Object.is(x, -0) ? '-0.0' : '0.0'
  const [mant, e] = x.toExponential().split('e')
  const exp = Number(e)
  const neg = mant.startsWith('-')
  const digits = mant.replace('-', '').replace('.', '')
  let out: string
  if (exp >= -5 + 1 && exp < 16) { // Python: -4 <= exp < 16
    if (exp >= 0) {
      const intPart = digits.slice(0, exp + 1).padEnd(exp + 1, '0')
      const frac = digits.slice(exp + 1)
      out = intPart + '.' + (frac || '0')
    } else {
      out = '0.' + '0'.repeat(-exp - 1) + digits
    }
  } else {
    const m = digits.length > 1 ? digits[0] + '.' + digits.slice(1) : digits
    out = m + 'e' + (exp < 0 ? '-' : '+') + String(Math.abs(exp)).padStart(2, '0')
  }
  return (neg ? '-' : '') + out
}

function pyStr(s: string): string {
  let out = '"'
  for (let k = 0; k < s.length; k++) {
    const ch = s[k], c = s.charCodeAt(k)
    if (ch === '"') out += '\\"'
    else if (ch === '\\') out += '\\\\'
    else if (ch === '\n') out += '\\n'
    else if (ch === '\r') out += '\\r'
    else if (ch === '\t') out += '\\t'
    else if (ch === '\b') out += '\\b'
    else if (ch === '\f') out += '\\f'
    else if (c < 0x20 || c > 0x7e) out += '\\u' + c.toString(16).padStart(4, '0')
    else out += ch
  }
  return out + '"'
}

// json.dumps(v[, sort_keys=True]) byte-for-byte (ensure_ascii, ", " / ": ").
export function pyDumps(v: any, sortKeys = false): string {
  if (v === null || v === undefined) return 'null'
  if (v === true) return 'true'
  if (v === false) return 'false'
  if (v instanceof PyFloat) return pyFloatRepr(v.v)
  if (typeof v === 'number') return Number.isInteger(v) ? String(v) : pyFloatRepr(v)
  if (typeof v === 'string') return pyStr(v)
  if (Array.isArray(v)) return '[' + v.map(x => pyDumps(x, sortKeys)).join(', ') + ']'
  const keys = Object.keys(v).filter(k => v[k] !== undefined)
  if (sortKeys) keys.sort()
  return '{' + keys.map(k => pyStr(k) + ': ' + pyDumps(v[k], sortKeys)).join(', ') + '}'
}

// ace_before_task.sanitize_response: a lone surrogate -> 3 x U+FFFD (utf-8 surrogatepass -> replace).
const LONE = /[\ud800-\udbff](?![\udc00-\udfff])|(?<![\ud800-\udbff])[\udc00-\udfff]/g
export function sanitize(v: any): any {
  if (typeof v === 'string') return v.replace(LONE, '���')
  if (Array.isArray(v)) return v.map(sanitize)
  if (v && typeof v === 'object' && !(v instanceof PyFloat)) {
    const o: any = {}; for (const k of Object.keys(v)) o[k] = sanitize(v[k]); return o
  }
  return v
}

// ---------- utils/validation.is_valid_pattern_id ----------
export const isValidPatternId = (id: unknown): boolean =>
  typeof id === 'string' && (/^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/.test(id)
    || /^ctx-[a-z0-9]+(-[a-z0-9]+)*$/.test(id))

// ---------- utils/ace_pattern_render.render_patterns_dict ----------
const KEEP = ['id', 'domain', 'content', 'section', 'evidence', 'root_cause', 'error_context',
  'cumulative_v15_reward', 'n_hot_pos', 'n_hot_neg', 'isAtRisk', 'confidence', 'helpful', 'harmful']
const DROP_TOP = new Set(['domains_summary', 'expanded', 'threshold'])
const truthy = (v: any) => !(v === null || v === undefined || v === false || v === 0 || v === ''
  || (Array.isArray(v) && v.length === 0) || (v instanceof PyFloat && v.v === 0)
  || (typeof v === 'object' && !Array.isArray(v) && !(v instanceof PyFloat) && Object.keys(v).length === 0))

export function hoistAndStrip(p: any): any {
  const mf = p.match_factors && typeof p.match_factors === 'object' ? p.match_factors : {}
  const r: any = {}
  for (const k of KEEP) {
    if (k === 'evidence') { if (truthy(p.evidence)) r.evidence = p.evidence.slice(0, 2) }
    else if (k === 'root_cause' || k === 'error_context') { if (truthy(p[k])) r[k] = p[k] }
    else if (k in p) r[k] = p[k]
  }
  if (mf.bandit_rank !== undefined && mf.bandit_rank !== null) r.bandit_rank = mf.bandit_rank
  if (mf.semantic_score !== undefined && mf.semantic_score !== null) r.semantic_score = mf.semantic_score
  return r
}

const isPyInt = (x: any) => typeof x === 'number' && Number.isInteger(x) // bool/PyFloat excluded by type

export function renderPatternsDict(resp: any): { dict: any; ids: string[]; rlog: Record<string, number> } {
  const pats: any[] = resp.similar_patterns || []
  const rank = (p: any) => { const mf = p.match_factors; return mf && typeof mf === 'object' ? num(mf.bandit_rank) ?? null : null }
  const sorted = pats.map((p, idx) => ({ p, idx })).sort((a, b) => {
    const ra = rank(a.p), rb = rank(b.p)
    if (ra === null || rb === null) return ra === null && rb === null ? a.idx - b.idx : ra === null ? 1 : -1
    return ra - rb || a.idx - b.idx
  }).map(x => x.p)
  const rlog: Record<string, number> = {}
  for (const p of sorted) {
    const rl = p.match_factors && typeof p.match_factors === 'object' ? p.match_factors.retrieval_log_id : undefined
    if (truthy(p.id) && isPyInt(rl)) rlog[p.id] = rl
  }
  const processed = sorted.map(hoistAndStrip)
  const ids = processed.filter(p => truthy(p.id) && isValidPatternId(p.id)).map(p => p.id)
  const dict: any = {}
  for (const k of Object.keys(resp)) if (!DROP_TOP.has(k) && k !== 'similar_patterns') dict[k] = resp[k]
  dict.similar_patterns = processed
  dict.count = processed.length
  return { dict, ids, rlog }
}

// ace_before_task: domains.json = domains_summary when non-empty, else per-domain counts.
export function domainsSummary(resp: any): Record<string, any> {
  const ds = resp.domains_summary
  if (ds && typeof ds === 'object' && Object.keys(ds).length) return ds
  const out: Record<string, number> = {}
  for (const p of resp.similar_patterns || []) if (p.domain) out[p.domain] = (out[p.domain] || 0) + 1
  return out
}

// ---------- utils/machine_prompts + ace_before_task._skip_reason ----------
export const MACHINE_PROMPT_PREFIXES = ['<task-notification', '<agent-message', '<cross-session-message',
  '[system notification', '<local-command', '<command-name>', '<bash-input>', '<bash-stdout>', '<bash-stderr>',
  '<system-reminder>']
const LEADING_REMINDER = /^(?:\s*<system-reminder>[\s\S]*?<\/system-reminder>)+\s*/i
export const isMachinePrompt = (t: string, extra: string[] = []) =>
  [...MACHINE_PROMPT_PREFIXES, ...extra].some(p => (t || '').toLowerCase().trimStart().startsWith(p))

// Python str.strip() strips Unicode whitespace; JS trim() is close enough (both cover \s + NBSP etc.).
export function skipReason(prompt: string, minChars = 12, extra: string[] = []): string | null {
  const raw = prompt.trim()
  const stripped = raw.replace(LEADING_REMINDER, '').trim()
  if (!stripped && raw) return 'machine_prompt'
  if (isMachinePrompt(stripped, extra)) return 'machine_prompt'
  if ([...stripped].length < minChars) return 'prompt_too_short'
  const low = stripped.toLowerCase()
  if (low.startsWith('/ace-') || low.startsWith('/ace:')) return 'ace_command'
  return null
}

// mod-only: slash commands that carry no task of their own (ACE's, and session built-ins whose arguments are not work).
const NO_TASK_COMMANDS = new Set(['compact', 'clear', 'model', 'config', 'help', 'status', 'memory', 'resume', 'mcp', 'hooks',
  'cost', 'context', 'login', 'logout', 'exit', 'quit', 'plugin', 'reload-plugins', 'effort', 'permissions', 'agents', 'rename'])
export const isNoTaskCommand = (name: string) => /^ace([:-]|$)/i.test(name) || NO_TASK_COMMANDS.has(name)

// mod-only: origins that are never a human task (PromptOrigin kinds), checked before the text.
export const MACHINE_ORIGINS = new Set(['task-notification', 'scheduled-trigger', 'peer', 'peer-send-message',
  'observer', 'observer-activity', 'projects-relay', 'coordinator'])

// ace_before_task.expand_abbreviations
export function expandAbbreviations(prompt: string): string {
  const rep: [string, string][] = [[' JWT ', ' JSON Web Token '], [' API ', ' REST API '], [' DB ', ' database '],
    [' env ', ' environment '], [' auth ', ' authentication '], [' config ', ' configuration '],
    [' deps ', ' dependencies '], [' repo ', ' repository ']]
  let r = ` ${prompt} `
  for (const [a, b] of rep) r = r.split(a).join(b)
  return r.trim()
}

// ---------- ace_domain_shift.match_domain_to_path ----------
export function matchDomainToPath(domain: string, path: string): boolean {
  const words = domain.toLowerCase().split(/[-\s]+/).filter(w => w.length >= 3)
  for (const seg of path.toLowerCase().split(/[/._\-\s]+/)) {
    if (seg.length < 3) continue
    for (const w of words) {
      let n = 0; while (n < w.length && n < seg.length && w[n] === seg[n]) n++
      if (seg === w || n >= 4) return true
    }
  }
  return false
}
export const domainNames = (domains: Record<string, unknown>) =>
  [...new Set(Object.keys(domains).map(k => k.split(':')[0].toLowerCase()))].sort()
export const basenameQuery = (p: string) => (p.replace(/\/+$/, '').split('/').pop() || '').replace(/\.[^.]*$/, '')

// ---------- ace_after_task ----------
const TRIVIAL = [/<command-message>ace[:\-]/i, /ace:ace-/i, /(?:^|\s)\/ace-[\w:-]*(?:\s|$)/i, /ace-status/i, /ace-patterns/i, /ace-search/i,
  /ace-learn/i, /ace-configure/i, /ace-bootstrap/i, /ace-clear/i, /ace-doctor/i, /ace-export/i, /ace-import/i, /ace-top/i,
  /^(what|how|why|where|when|can you|could you|would you)\s.*\?$/i, /^(list|show|display|print|view|see)\s/i,
  /^(check|status|version|help|info)\s*$/i, /git\s+(status|log|diff|branch|show)\s*$/i, /^ls\s/i, /^cat\s/i,
  /^head\s/i, /^tail\s/i, /^(hi|hello|hey|thanks|thank you|ok|okay|yes|no|sure)\s*$/i,
  /caveat:.*messages below were generated/i, /^plugin\s*$/i, /(?:^|\s)\/plugin(?:\s|$)/i]
// Python re.search without MULTILINE/DOTALL: '.' stops at newlines, '^'/'$' anchor the whole string.
export const isTrivialTask = (t: string, extra: string[] = []) =>
  isMachinePrompt(t.toLowerCase(), extra) || TRIVIAL.some(r => r.test(t.toLowerCase()))

const STATE_CHANGING = ['Edit', 'Write', 'Bash', 'mcp__', 'NotebookEdit']
export const hasSubstantialWork = (tools: ToolRec[]) => tools.some(t => STATE_CHANGING.some(s => t.tool.includes(s)))

// One trajectory step, summarized when the call settles (results can be huge; Python keeps them in sqlite).
export type ToolRec = { tool: string; action: string; result: string; failed: boolean; start_ms: number; end_ms: number; commit?: string }
const base = (p: any) => String(p ?? 'unknown file').replace(/\/+$/, '').split('/').pop()
const cut = (s: string, n: number) => s.length > n ? s.slice(0, n) + '...' : s

export function summarizeAction(tool: string, i: any): string {
  i = i || {}
  if (tool === 'Edit') return `Edited ${base(i.file_path)}`
  if (tool === 'Write') return `Wrote ${base(i.file_path)}`
  if (tool === 'Read') return `Read ${base(i.file_path)}`
  if (tool === 'Bash') return `Ran: ${cut(i.command ?? i.description ?? '', 60)}`
  if (tool === 'Grep') return `Searched for: ${i.pattern ?? ''}`
  if (tool === 'Glob') return `Found files matching: ${i.pattern ?? ''}`
  if (tool === 'Task' || tool === 'Agent') return `Spawned task: ${cut(i.description ?? i.prompt ?? '', 60)}` // Python names only 'Task'
  if (tool === 'TodoWrite') return 'Updated todo list'
  if (tool.startsWith('mcp__')) return `Called MCP: ${tool}`
  return tool
}

// Mirrors summarize_tool_response on the PostToolUse tool_response shape; the mod sees the tool's
// structured result plus isError/deny, so failed and denied calls (which Python only sees via
// PostToolUseFailure / not at all) are recorded too.
export function summarizeResult(tool: string, res: any, isError = false, denied?: string): string {
  if (denied) return `Error: ${denied.slice(0, 100)}`
  if (isError) return `Error: ${String(typeof res === 'string' ? res : JSON.stringify(res)).slice(0, 100)}`
  if (res === null || res === undefined || typeof res !== 'object' || Array.isArray(res))
    return cut(typeof res === 'string' ? res : JSON.stringify(res ?? ''), 100)
  if (res.error) return `Error: ${String(res.error).slice(0, 100)}`
  if (res.stderr) return `Stderr: ${String(res.stderr).slice(0, 100)}`
  if (tool === 'Edit' || tool === 'Write') return 'Success'
  if (tool === 'Read') { const c = res.file?.content ?? res.content ?? ''; return `Read ${c ? c.split('\n').length : 0} lines` }
  if (tool === 'Bash') { const first = String(res.stdout || '').split('\n')[0]; return res.stdout ? (cut(first, 60) || 'Success') : 'Success' }
  if (tool === 'Grep' || tool === 'Glob') { const f = res.filenames ?? res.files; return Array.isArray(f) ? `Found ${f.length} files` : cut(JSON.stringify(res), 100) }
  if (tool === 'Task' || tool === 'Agent') return 'Task completed'
  return cut(JSON.stringify(res), 100)
}

export function toolRec(tool: string, input: any, res: any, isError: boolean, denied: string | undefined, t0: number, t1: number): ToolRec {
  const failed = isError || !!denied || !!(res && typeof res === 'object' && !Array.isArray(res) && (res.error || res.stderr))
  const rec: ToolRec = { tool, action: summarizeAction(tool, input), result: summarizeResult(tool, res, isError, denied), failed, start_ms: t0, end_ms: t1 }
  if (tool === 'Bash' && String(input?.command ?? '').includes('git commit')) { // git_utils.detect_commits_in_session
    const m = /\[[\w\-/]+\s+([a-f0-9]{7,40})\]/.exec(String(res?.stdout ?? ''))
    if (m) rec.commit = m[1]
  }
  return rec
}

// ace_after_task.parse_ace_review
export function parseAceReview(msg: string): { quality_pct: number; time_saved: string } | null {
  const m = /ACE_REVIEW:\s*(\d+)/.exec(msg || '')
  if (!m) return null
  const t = /\d+m\d*s? saved|\d+s saved|\d+ ?min/.exec(msg)
  return { quality_pct: Number(m[1]), time_saved: t ? t[0].replace(' saved', '') : '' }
}

// ace_before_task.check_eval_request_and_review text
export function evalInjection(d: any): string {
  const g = (k: string) => { const v = d?.[k]; return v instanceof PyFloat ? pyFloatRepr(v.v) : String(v ?? 0) }
  return `<!-- ACE Self-Eval Request: Previous task used ${g('patterns_injected')} patterns ` +
    `(${g('avg_relevance')}% relevance, ${g('domains')} domains, ${g('tools_executed')} tools). ` +
    `As a human developer, how much time did these patterns save? ` +
    `Without ACE, a developer would search docs, explore codebases, ask colleagues, or trial-and-error. ` +
    `Rate from a HUMAN DEVELOPER perspective, not AI perspective. ` +
    `Include in your response: ACE_REVIEW: N% | Xm saved | one-line reason -->`
}

// ---------- renderers (ace_pattern_render; per-pattern keys SORTED: Python's own order comes from a
// frozenset and changes with PYTHONHASHSEED, so it has no stable byte form to copy) ----------
const cps = (s: string) => Array.from(s)
const cpLen = (s: string) => { let n = 0; for (const _ of s) n++; return n }
const cpSlice = (s: string, n: number) => cps(s).slice(0, n).join('')
export const FULL_CAP = 95000, BUDGET = 9500, STATE_CAP = 10000, DOMAIN_CAP = 10000

const dumpSorted = (pats: any[]) => pats.map(p => pyDumps(p, true))
const baseOf = (dict: any) => Object.keys(dict).filter(k => k !== 'similar_patterns' && k !== 'count')
function envelope(dict: any, items: string[], count: number) {
  return '{' + [...baseOf(dict).map(k => pyDumps(k) + ': ' + pyDumps(dict[k])),
    '"similar_patterns": [' + items.join(', ') + ']', '"count": ' + count].join(', ') + '}'
}
const openTag = (tag: string, shown: number, total: number, attrs: string, extra = '') =>
  `<${tag} shown="${shown}" of="${total}"${extra}${attrs ? ' ' + attrs : ''}>`
function credit(pats: any[], rlog: Record<string, number>) {
  const ids = pats.filter(p => truthy(p.id) && isValidPatternId(p.id)).map(p => p.id as string)
  const keep = new Set(ids), out: Record<string, number> = {}
  for (const k of Object.keys(rlog)) if (keep.has(k)) out[k] = rlog[k]
  return { ids, rlog: out }
}

// The mod's default arm: ALL patterns (user ruling 1), whole tail patterns dropped until <= cap (§13.1 100K guard).
export function renderFull(resp: any, tag: string, attrs: string, cap = FULL_CAP) {
  const { dict, rlog } = renderPatternsDict(resp)
  const total: number = dict.count
  let pats: any[] = dict.similar_patterns
  const items = dumpSorted(pats)
  let n = pats.length, context = ''
  for (;;) {
    context = `${openTag(tag, n, total, attrs)}\n${envelope(dict, items.slice(0, n), n)}\n</${tag}>`
    if (context.length <= cap || n === 0) break
    n--
  }
  pats = pats.slice(0, n)
  return { context, ...credit(pats, rlog), patterns: pats, shown: n, total }
}

// render_patterns: top-N verbatim until the whole string fits the budget; count stays the total.
export function renderBudget(resp: any, tag: string, attrs: string, budget = BUDGET) {
  const { dict, rlog } = renderPatternsDict(resp)
  const total: number = dict.count, close = `</${tag}>`
  const available = budget - (openTag(tag, total, total, attrs).length + 1 + envelope(dict, [], total).length + 1 + close.length)
  const picked: any[] = []
  let chars = 2
  for (const p of dict.similar_patterns as any[]) {
    const cost = pyDumps(p, true).length + (picked.length ? 2 : 0)
    if (chars + cost <= available) { picked.push(p); chars += cost; continue }
    if (!picked.length) { // even top-1 alone is too big: no evidence, content cut to fit; never empty
      const c: any = { ...p }; delete c.evidence
      const size = () => pyDumps(c, true).length
      if (chars + size() > available) {
        const content = String(c.content ?? '')
        const excess = chars + size() - available
        c.content = cpSlice(content, Math.max(1, Math.max(4, pyDumps(content).length - excess - 1) - 2))
        while (chars + size() > available && cpLen(c.content) > 1) c.content = cps(c.content).slice(0, -10).join('')
        if (chars + size() > available) c.content = cpSlice(content, 1)
      }
      picked.push(c)
    }
    break
  }
  let context = ''
  for (;;) {
    context = `${openTag(tag, picked.length, total, attrs)}\n${envelope(dict, dumpSorted(picked), total)}\n${close}`
    if (context.length <= budget || !picked.length) break
    picked.pop()
  }
  return { context, ...credit(picked, rlog), patterns: picked, shown: picked.length, total }
}

// f"{x:.1f}": toFixed picks the larger digit on an exact tie (x*4 odd), Python the even one.
function fmt1(v: any): string {
  const x = num(v) ?? 0
  if (Object.is(x, -0)) return '-0.0'
  if (Number.isInteger(x * 4) && (x * 4) % 2 !== 0) {
    let n = Math.floor(Math.abs(x) * 10); n += n % 2
    return (x < 0 ? '-' : '') + (n / 10).toFixed(1)
  }
  return x.toFixed(1)
}

// render_compact_all: every pattern a one-liner, snippet length sized to the budget.
export function renderCompact(resp: any, tag: string, attrs: string, budget = BUDGET) {
  const { dict, rlog } = renderPatternsDict(resp)
  const all: any[] = dict.similar_patterns, total: number = dict.count, close = `</${tag}>`
  const open = (n: number) => openTag(tag, n, total, attrs, ' mode="compact"')
  if (!all.length) return { context: `${open(0)}\n${close}`, ids: [] as string[], rlog: {} as Record<string, number>, patterns: all, shown: 0, total }
  const head = (p: any) => {
    const r = p.bandit_rank
    return `#${r === undefined ? '?' : r instanceof PyFloat ? pyFloatRepr(r.v) : r} [${p.domain ?? ''}] r=${fmt1(p.cumulative_v15_reward)} `
  }
  const fixed = open(total).length + 1 + close.length + all.reduce((a, p) => a + cpLen(head(p)), 0) + all.length
  const snip = Math.max(0, Math.floor((budget - fixed) / all.length))
  const build = (ps: any[]) => `${open(ps.length)}\n${ps.map(p => head(p) + cpSlice(String(p.content ?? ''), snip)).join('\n')}\n${close}`
  let pats = all, context = build(pats)
  while (pats.length && cpLen(context) > budget) { pats = pats.slice(0, -1); context = build(pats) }
  return { context, ...credit(pats, rlog), patterns: pats, shown: pats.length, total }
}

// ace_domain_shift._context, trailing patterns dropped until <= 10,000 chars (count follows).
export function renderDomainShift(resp: any, domain: string) {
  const { dict, rlog } = renderPatternsDict(resp)
  const attr = domain.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#x27;')
  const pats: any[] = dict.similar_patterns
  const items = dumpSorted(pats)
  let n = pats.length, context = ''
  for (;;) {
    const body = '{' + Object.keys(dict).map(k => pyDumps(k) + ': ' + (k === 'similar_patterns' ? '[' + items.slice(0, n).join(', ') + ']'
      : k === 'count' ? String(n) : pyDumps(dict[k]))).join(', ') + '}'
    context = `<ace-patterns-domain-shift domain="${attr}">${body}</ace-patterns-domain-shift>`
    if (context.length <= DOMAIN_CAP || n === 0) break
    n--
  }
  return { context, ...credit(pats.slice(0, n), rlog), shown: n }
}

// ---------- render_cohort (salt "render:", same bucket as ace_pattern_render) ----------
function sha256Hex(text: string): string {
  const bytes: number[] = []
  for (const ch of text) { // UTF-8
    const c = ch.codePointAt(0)!
    if (c < 0x80) bytes.push(c)
    else if (c < 0x800) bytes.push(0xc0 | c >> 6, 0x80 | c & 63)
    else if (c < 0x10000) bytes.push(0xe0 | c >> 12, 0x80 | c >> 6 & 63, 0x80 | c & 63)
    else bytes.push(0xf0 | c >> 18, 0x80 | c >> 12 & 63, 0x80 | c >> 6 & 63, 0x80 | c & 63)
  }
  const K: number[] = [], H: number[] = []
  const frac = (x: number) => ((x - Math.floor(x)) * 2 ** 32) | 0
  for (let p = 2, n = 0; n < 64; p++) {
    let prime = true
    for (let d = 2; d * d <= p; d++) if (p % d === 0) { prime = false; break }
    if (!prime) continue
    if (n < 8) H.push(frac(Math.sqrt(p)))
    K.push(frac(Math.cbrt(p))); n++
  }
  const len = bytes.length
  bytes.push(0x80)
  while (bytes.length % 64 !== 56) bytes.push(0)
  for (let i = 7; i >= 0; i--) bytes.push(i >= 4 ? 0 : (len * 8) >>> (i * 8) & 255)
  const rr = (x: number, n: number) => (x >>> n) | (x << (32 - n))
  for (let o = 0; o < bytes.length; o += 64) {
    const w: number[] = []
    for (let i = 0; i < 64; i++) {
      if (i < 16) w[i] = bytes[o + 4 * i] << 24 | bytes[o + 4 * i + 1] << 16 | bytes[o + 4 * i + 2] << 8 | bytes[o + 4 * i + 3]
      else {
        const a = w[i - 15], b = w[i - 2]
        w[i] = (w[i - 16] + (rr(a, 7) ^ rr(a, 18) ^ a >>> 3) + w[i - 7] + (rr(b, 17) ^ rr(b, 19) ^ b >>> 10)) | 0
      }
    }
    let [a, b, c, d, e, f, g, h] = H
    for (let i = 0; i < 64; i++) {
      const t1 = (h + (rr(e, 6) ^ rr(e, 11) ^ rr(e, 25)) + ((e & f) ^ (~e & g)) + K[i] + w[i]) | 0
      const t2 = ((rr(a, 2) ^ rr(a, 13) ^ rr(a, 22)) + ((a & b) ^ (a & c) ^ (b & c))) | 0
      h = g; g = f; f = e; e = (d + t1) | 0; d = c; c = b; b = a; a = (t1 + t2) | 0
    }
    ;[a, b, c, d, e, f, g, h].forEach((v, i) => { H[i] = (H[i] + v) | 0 })
  }
  return H.map(v => (v >>> 0).toString(16).padStart(8, '0')).join('')
}

const pyInt = (v: string | undefined, dflt: number): number | null => {
  if (v === undefined) return dflt
  return /^\s*[+-]?\d+\s*$/.test(v) ? parseInt(v, 10) : null
}
export type Cohort = 'control' | 'compact' | 'full' | 'budget'
// ace_pattern_render._read_ab_pcts + ACE_RENDER_FULL_PCT (default 100). Arms in bucket order:
// control, compact, full, budget. No anchor -> full (never experiment without one).
export function renderCohort(sid: string | undefined, env: Record<string, string | undefined>): Cohort {
  let ctrl = pyInt(env.ACE_AB_CONTROL_PCT, 0), comp = pyInt(env.ACE_AB_COMPACT_PCT, 0)
  if (ctrl === null || comp === null || ctrl < 0 || comp < 0 || Math.min(ctrl, 100) + Math.min(comp, 100) > 100) { ctrl = 0; comp = 0 }
  ctrl = Math.min(ctrl, 100); comp = Math.min(comp, 100)
  let full = pyInt(env.ACE_RENDER_FULL_PCT, 100)
  if (full === null || full < 0) full = 100
  full = Math.min(full, 100 - ctrl - comp)
  if (!sid) return 'full'
  const b = parseInt(sha256Hex('render:' + sid).slice(0, 8), 16) % 100
  return b < ctrl ? 'control' : b < ctrl + comp ? 'compact' : b < ctrl + comp + full ? 'full' : 'budget'
}

// ---------- plugin_data_dir ----------
export const safeComponent = (c: string | undefined | null): string => {
  const s = String(c ?? '').replace(/[^A-Za-z0-9_.-]/g, '_')
  return s === '' ? 'default' : s === '.' || s === '..' ? '_' : s
}
// F1: a mod reads the HOST env, so the plugin-data variable there may name another plugin. Derive CC's own dir name:
// <config>/plugins/cache/<marketplace>/<name>/<ver> -> <config>/plugins/data/<name>-<marketplace>; else <name>-inline.
export function dataRootFromPluginRoot(home: string, root: string, name: string, configDir?: string): string {
  const m = /^(.*)\/plugins\/cache\/([^/]+)\/([^/]+)\/[^/]+\/?$/.exec(root)
  if (m) return `${m[1]}/plugins/data/${m[3]}-${m[2]}`
  return `${configDir || home + '/.claude'}/plugins/data/${name}-inline`
}

// ---------- patterns_used_state.append_patterns_used: same merge, same key order, same bytes ----------
export type StateUpdate = { ids?: string[]; retrievalId?: string | null; rlog?: Record<string, number>; tsid?: string | null
  userPrompt?: string; rendered?: string; hook?: string; parentTaskId?: string; agentType?: string }
export function mergeState(prior: any, u: StateUpdate): any {
  const p = prior && typeof prior === 'object' && !Array.isArray(prior) ? prior : {}
  const ids: string[] = Array.isArray(p.pattern_ids) ? [...p.pattern_ids] : Array.isArray(prior) ? [...prior] : []
  for (const id of u.ids ?? []) if (isValidPatternId(id) && !ids.includes(id)) ids.push(id)
  const state: any = {
    pattern_ids: ids,
    retrieval_id: u.retrievalId ?? p.retrieval_id ?? null,
    retrieval_log_ids: { ...(p.retrieval_log_ids ?? {}), ...(u.rlog ?? {}) },
    task_session_id: u.tsid ?? p.task_session_id ?? null,
  }
  const up = u.userPrompt ?? p.user_prompt
  if (up) state.user_prompt = cpSlice(up, 4000)
  const rc = u.rendered ?? p.rendered_context
  if (rc !== undefined && rc !== null) state.rendered_context = cpSlice(rc, STATE_CAP)
  const he = u.hook ?? p.hook_event_name
  if (he) state.hook_event_name = he
  const pt = u.parentTaskId ?? p.parent_task_id
  if (pt) state.parent_task_id = pt
  const at = u.agentType ?? p.agent_type // mod-only: its turn.complete carries no agent type; Python ignores the key
  if (at) state.agent_type = at
  return state
}

// ---------- ace_before_task ----------
// build_session_title (main agent; subagents set no title). `review` = parsed ace-review-result.json.
export function sessionTitle(patterns: any[], review?: any): string | undefined {
  const n = patterns.length
  if (!n) return undefined
  const helpful: Record<string, number> = {}
  let conf = 0
  for (const p of patterns) {
    if (p.domain) helpful[p.domain] = (helpful[p.domain] ?? 0) + (num(p.helpful) ?? 0)
    conf += num(p.confidence) ?? 0
  }
  conf /= n
  const top = Object.entries(helpful).sort((a, b) => b[1] - a[1])[0]
  const short = top ? top[0].split('-')[0] : ''
  const m = /(\d+)\s*m/.exec(String(review?.time_saved ?? '').trim())
  const roi = m && Number(m[1]) > 0 ? ` · +${m[1]}m` : ''
  const reliable = patterns.some(p => { const r = num(p.cumulative_v15_reward); return r !== undefined && !p.isAtRisk && r >= 0 }) || (top ? top[1] : 0) >= 20
  if (conf < 0.5) return `ACE low · ${n}`
  if (n >= 5 && conf >= 0.7 && reliable) return (short ? `ACE ready · ${short}` : `ACE ready · ${n}`) + roi
  return (short ? `ACE · ${n} · ${short}` : `ACE · ${n}`) + roi
}

// the UPS systemMessage text, shown through $.ui.log
export function searchSummary(patterns: any[]): string {
  const n = patterns.length
  if (!n) return 'ℹ️  [ACE] No patterns found for this query'
  const lines = [`✅ [ACE] Found ${n} relevant bullets`]
  for (const p of patterns.slice(0, 3)) {
    const c = String(p.content ?? '')
    lines.push(`   • [${p.domain ?? 'general'}] ${c.length > 80 ? c.slice(0, 77) + '...' : c}`)
  }
  if (n > 3) lines.push(`   ... and ${n - 3} more bullets`)
  return lines.join('\n')
}
export function searchErrorLine(error: string | undefined): string {
  if (error === 'not_authenticated') return '⚠️ [ACE] Not authenticated. Run /ace:ace-login'
  if (error === 'timeout') return '⏱️ [ACE] Search timed out. Check your connection.'
  if (error === 'cli_not_found') return '❌ [ACE] ace-cli not found. Run: npm install -g @ace-sdk/cli'
  return '❌ [ACE] Search failed or returned no results'
}

// relevance log 'search' row (ace_relevance_logger.log_search_metrics)
export function searchRow(a: { hook: string; sessionId: string; userPrompt: string; query: string; returned: any[];
  injected: any[]; projectId: string; orgId?: string; agentType: string; cohort: string; hookMs: number; nowIso: string; extra?: any }) {
  const conf = a.injected.map(p => num(p.confidence) ?? 0)
  const row: any = {
    timestamp: a.nowIso, event: 'search', hook: a.hook, session_id: a.sessionId, project_id: a.projectId,
    org_id: a.orgId ?? null, agent_type: a.agentType || 'main', user_prompt: a.userPrompt.slice(0, 200),
    search_query: a.query.slice(0, 100), patterns_returned: a.returned.length, patterns_injected: a.injected.length,
    patterns_filtered: a.returned.length - a.injected.length,
    avg_confidence: conf.length ? Math.round(conf.reduce((x, y) => x + y, 0) / conf.length * 1000) / 1000 : 0,
    domains: [...new Set(a.returned.map(p => p.domain).filter(Boolean))].slice(0, 10),
    top_patterns: a.injected.slice(0, 5).map(p => ({ id: p.id ?? 'unknown', confidence: p.confidence ?? 0, helpful: p.helpful ?? 0,
      harmful: p.harmful ?? 0, domain: p.domain ?? 'unknown', section: p.section ?? 'unknown',
      content: String(p.content ?? '').slice(0, 100) + (String(p.content ?? '').length > 100 ? '...' : ''),
      cumulative_v15_reward: p.cumulative_v15_reward ?? null, isAtRisk: p.isAtRisk ?? null,
      n_hot_pos: p.n_hot_pos ?? null, n_hot_neg: p.n_hot_neg ?? null })),
    render_cohort: a.cohort, hook_ms: a.hookMs,
  }
  return Object.assign(row, a.extra || {})
}

// ---------- ace_subagent_start ----------
// Workflow agents get a fixed harness preamble ending in this marker; it would make every query identical.
const WORKFLOW_MARKER = 'The computed task text follows:'
export function subagentQuery(prompt: string): string {
  const i = prompt.indexOf(WORKFLOW_MARKER)
  return cpSlice((i >= 0 ? prompt.slice(i + WORKFLOW_MARKER.length) : prompt).trim(), 500)
}

// ---------- ace_after_task + trace_truncate ----------
const EFFORT_WEIGHT: Record<string, number> = { auto: 1, low: 1, normal: 1, high: 1.5, xhigh: 2, max: 2 }
export const effortWeight = (level: string) => EFFORT_WEIGHT[level] ?? 1

const stepFailed = (st: any) => typeof st.result === 'string' && /error|failed/i.test(st.result)
const MAX_RECENT_STEPS = 50, MAX_TRACE_BYTES = 2_097_152
const shrink = (s: string, max: number, what: string) => s.length > max ? `<truncated: ${s.length} bytes — ${what}>` : s

// trace_truncate.truncate_trace. Our steps hold summaries (<= 100 chars), so its per-step tool_response cap has nothing to cut.
export function truncateTrace(trace: any): any {
  let truncated = false
  const tr: any[] = trace.trajectory
  if (tr.length > MAX_RECENT_STEPS) {
    const keep = tr.map((_, i) => i).filter(i => i >= tr.length - MAX_RECENT_STEPS || stepFailed(tr[i]))
    trace.trajectory = [{ _truncation_marker: true, original_length: tr.length, kept: keep.length, kept_indices: keep }, ...keep.map(i => tr[i])]
    truncated = true
  }
  if (pyDumps(trace).length > MAX_TRACE_BYTES) {
    trace.task = shrink(trace.task, 2048, 'task')
    if (typeof trace.result.summary === 'string') trace.result.summary = shrink(trace.result.summary, 4096, 'summary')
    truncated = true
  }
  if (truncated) trace.metadata = { ...(trace.metadata ?? {}), trace_truncated: true }
  return trace
}

export function buildTrace(a: {
  userPrompt: string; tools: ToolRec[]; answer: string; playbookUsed: string[]; agentType: string; tsid?: string; agentId?: string
  parentTaskId?: string; retrievalId?: string; appliedLogIds: number[]; nowIso: string; renderVariant: string; effort: string; git?: any
}) {
  const success = !a.tools.some(t => t.failed)
  const trace: any = {
    task: `User request: ${cpSlice(a.userPrompt, 2000)}`,
    trajectory: a.tools.map((t, k) => ({ step: k + 1, tool: t.tool, action: t.action,
      result: t.result, start_ms: t.start_ms, end_ms: t.end_ms, duration_ms: t.end_ms - t.start_ms })),
    result: { success, output: `Executed ${a.tools.length} tool calls`, summary: a.answer ? cpSlice(a.answer, 2000) : null },
    playbook_used: a.playbookUsed,
    timestamp: a.nowIso,
    agent_type: a.agentType,
  }
  if (a.tsid) { trace.session_id = a.tsid; trace.render_variant = a.renderVariant }
  if (a.agentId) trace.agent_id = a.agentId
  if (a.parentTaskId) trace.parent_task_id = a.parentTaskId
  if (a.retrievalId) trace.retrieval_id = a.retrievalId
  if (a.appliedLogIds.length) trace.applied_log_ids = a.appliedLogIds
  trace.effort_level = a.effort
  trace.effort_weight = effortWeight(a.effort)
  if (a.git) trace.git = a.git
  return { trace: truncateTrace(trace), success }
}

// git_utils.parse_diff_stat
export function parseDiffStat(out: string) {
  const last = out.trim().split('\n').pop() ?? ''
  const g = (r: RegExp) => { const m = r.exec(last); return m ? Number(m[1]) : 0 }
  return { insertions: g(/(\d+)\s+insertions?\(\+\)/), deletions: g(/(\d+)\s+deletions?\(-\)/) }
}

// ace_cli.run_learn argv (never --pin-session; --no-stream so server 401/500 surface).
export function learnArgv(traceFile: string, retrievalId?: string, appliedLogIds: number[] = [], verbosity = 'detailed') {
  const a = ['ace-cli', 'learn', '--transcript', traceFile, '--json', '--timeout', '300000', '--verbosity', verbosity, '--no-stream']
  if (retrievalId) a.push('--retrieval-id', retrievalId)
  if (appliedLogIds.length) a.push('--applied-log-ids', appliedLogIds.join(','))
  return a
}

// The launcher starts the child in its own session (setsid) and returns at once, so neither the hook's return nor
// the session group's SIGHUP/SIGKILL at `claude -p` teardown reaches the learn. The child owns the metrics row and
// all cleanup, lock last (session.end keeps the dir while the lock is fresh). Python: already a hard plugin dependency.
const LEARN_CHILD = `import os,subprocess,sys
trace,lock,log,ok,fail,errlog=sys.argv[1:7]
res=trace+'.result'
code=1
try:
    with open(res,'ab') as f:
        code=subprocess.run(sys.argv[7:],stdin=subprocess.DEVNULL,stdout=f,stderr=subprocess.STDOUT,timeout=310).returncode
except Exception as e:
    try:
        with open(res,'a') as f:
            f.write(str(e))
    except OSError:
        pass
try:
    os.makedirs(os.path.dirname(log),exist_ok=True)
    with open(log,'a') as f:
        f.write((ok if code==0 else fail)+chr(10))
except OSError:
    pass
if code!=0 and errlog:
    try:
        os.makedirs(os.path.dirname(errlog),exist_ok=True)
        with open(res,errors='replace') as f, open(errlog,'a') as g:
            g.write('ace-cli learn (mod) exit %d: %s'%(code,f.read()[-500:])+chr(10))
    except OSError:
        pass
for p in (res,trace,lock):
    try:
        os.unlink(p)
    except OSError:
        pass
`
const LEARN_LAUNCHER = `import subprocess,sys
subprocess.Popen([sys.executable,'-I','-c',${JSON.stringify(LEARN_CHILD)}]+sys.argv[1:],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,close_fds=True,start_new_session=True)
`
// ponytail: POSIX-shaped; on Windows the bare `ace-cli` (a .cmd shim) would need a shell. The Python chain covers
// Windows until the mod is proven there (§13.1 m2: Windows untested).
export function detachedLearnArgv(j: { learnArgv: string[]; trace: string; lock: string; log: string; rowOk: string; rowFail: string; errLog?: string; python?: string }): string[] {
  return [j.python || 'python3', '-I', '-c', LEARN_LAUNCHER, j.trace, j.lock, j.log, j.rowOk, j.rowFail, j.errLog ?? '', ...j.learnArgv]
}
