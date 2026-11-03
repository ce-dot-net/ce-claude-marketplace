// The visible notices: per-prompt status line, search summary/error lines, session title, end-of-task learn line.
// Pure strings; the handlers show them through $.ui.log.
import { num } from '../lib/pyjson.ts'

// item 2: the ONE end-of-task line (v7.1.14 "✅ [ACE] N% quality | ~Xm saved | Learning in background"), unknown parts
// left out. Same text as the Python Stop systemMessage (ace_after_task.learn_line).
export function learnLine(review: { quality_pct?: unknown; time_saved?: unknown } | null | undefined): string {
  let line = 'ACE · learning sent'
  const pct = num(review?.quality_pct)
  if (pct !== undefined && Number.isFinite(pct)) line += ` · ${pct}%`
  const m = /(\d+)\s*m/.exec(String(review?.time_saved ?? ''))
  if (m && Number(m[1]) > 0) line += ` · ~${Number(m[1])}m saved`
  return line
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

// the UPS notice, shown through $.ui.log: ONE line ($.ui.log renders a newline as a replacement glyph)
export function searchSummary(patterns: any[]): string {
  const n = patterns.length
  if (!n) return 'ℹ️  [ACE] No patterns found for this query'
  const domains = [...new Set(patterns.map(p => String(p.domain ?? 'general')))]
  const shown = domains.slice(0, 3).join(', ') + (domains.length > 3 ? ` (+${domains.length - 3} more)` : '')
  return `✅ [ACE] Found ${n} relevant bullets · ${shown}`
}
// the per-prompt notice, ONE transcript line right after the prompt ($.ui.log draws a newline as a glyph): what the
// MODEL got, not what the server found. Same text as the Python chain's systemMessage (status_line).
export function statusLine(o: { injected: number, returned: number, cohort: string, domains: string[] }): string {
  if (!o.returned) return 'ACE · no patterns for this prompt'
  const arm = o.cohort === 'full' ? 'full' : 'budget'
  const noun = o.returned === 1 ? 'pattern' : 'patterns'
  const what = o.injected === o.returned ? `${o.injected} ${noun}` : `${o.injected} of ${o.returned} ${noun}`
  const d = o.domains.slice(0, 2).join(', ') + (o.domains.length > 2 ? ` +${o.domains.length - 2}` : '')
  return `ACE · ${what} · ${arm}` + (d ? ` · ${d}` : '')
}
// domains of the injected patterns, most frequent first
export function topDomains(patterns: any[]): string[] {
  const c = new Map<string, number>()
  for (const p of patterns) if (p?.domain) c.set(String(p.domain), (c.get(String(p.domain)) ?? 0) + 1)
  return [...c.entries()].sort((a, b) => b[1] - a[1]).map(([d]) => d)
}
export function searchErrorLine(error: string | undefined): string {
  if (error === 'not_authenticated') return '⚠️ [ACE] Not authenticated. Run /ace:ace-login'
  if (error === 'timeout') return '⏱️ [ACE] Search timed out. Check your connection.'
  if (error === 'cli_not_found') return '❌ [ACE] ace-cli not found. Run /ace:ace-install-cli'
  return '❌ [ACE] Search failed or returned no results'
}
