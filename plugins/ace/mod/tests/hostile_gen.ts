// Per-rule hostile inputs, derived from the rule tables (lib/redact_rules.ts) so that a NEW rule gets a hostile test without anyone
// remembering it. Registry: tests-fixtures/secret-filter/hostile_rules.json (fixtures/hostile_rules.ts): every rule is listed there
// (its inputs are derived), with extra hand-picked units, or marked 'linear' with a reason. Python twin: tests/hostile_gen.py.
import { ENTROPY_RUN, ENV_LINE, FORMAT_RULES, NV_RULES, PII_RULES, PREFIX_RULES, SECRET_RULES, SPAN_RULES, URL_CRED } from '../lib/redact_rules.ts'
import { HOSTILE } from './fixtures/hostile_rules.ts'

export type Rule = { id: string, sources: string[] }
export const tableRules = (): Rule[] => [
  ...SPAN_RULES.map(([n, r]) => ({ id: `span:${n}`, sources: (Array.isArray(r) ? r : [r]).map(x => x.source) })),
  ...SECRET_RULES.map(([n, r]) => ({ id: `secret:${n}`, sources: [r.source] })),
  ...PREFIX_RULES.map(([n, r]) => ({ id: `prefix:${n}`, sources: [r.source] })),
  ...FORMAT_RULES.map(([n, r]) => ({ id: `format:${n}`, sources: [r.source] })),
  ...NV_RULES.map(([n, r]) => ({ id: `nv:${n}`, sources: [r.source] })),
  ...PII_RULES.map(([n, , , r]) => ({ id: `pii:${n}`, sources: [r.source] })),
  { id: 'env-line', sources: [ENV_LINE.source] }, { id: 'url-cred', sources: [URL_CRED.source] }, { id: 'entropy-run', sources: [ENTROPY_RUN.source] },
]

/** Units from a regex source: the longest literal words (outside classes, escapes skipped) and a class filler char; repeated by the caller. */
export function deriveUnits(sources: string[]): string[] {
  const words = new Set<string>(), fillers: string[] = []
  const addFiller = (c: string) => { if (!fillers.includes(c)) fillers.push(c) }
  for (const src of sources) {
    let cls = false, cur = ''
    const flush = () => { if (cur.length >= 3 && /[A-Za-z]/.test(cur)) words.add(cur); cur = '' }
    for (let i = 0; i < src.length; i++) {
      const c = src[i]
      if (c === '\\') { flush(); const n = src[++i]; if (n === 'd') addFiller('1'); else if (n === 's') addFiller(' '); else if (n === 'w') addFiller('a'); continue }
      if (cls) { if (c === ']') cls = false; continue }
      if (c === '[') {
        flush(); cls = true
        const n = src[i + 1]
        if (n !== '^' && n !== '\\' && n !== ']' && n >= ' ' && n <= '~') addFiller(n)
        continue
      }
      if (/[A-Za-z0-9_-]/.test(c)) cur += c; else flush()
    }
    flush()
  }
  addFiller('a')
  const ws = [...words].sort((a, b) => b.length - a.length || (a < b ? -1 : 1)).slice(0, 2)
  const F = (fillers.find(x => x !== 'a' && x !== ' ') ?? 'a').repeat(8)
  return ws.length ? [ws[0] + ' ', ws[0] + F + ' ', (ws[1] ?? ws[0]) + ':'] : [F, F + '@', F + ' ']
}

/** [rule id, unit] pairs to measure; a rule marked linear yields none. */
export function hostileCases(): [string, string][] {
  const out: [string, string][] = []
  for (const r of tableRules()) {
    const d = HOSTILE.rules[r.id]
    if (d && d.linear) continue
    for (const u of new Set([...deriveUnits(r.sources), ...(d?.units ?? [])])) out.push([r.id, u])
  }
  for (const id of Object.keys(HOSTILE.rules)) if (id.startsWith('engine:')) for (const u of HOSTILE.rules[id].units ?? []) out.push([id, u])
  return out
}

/** The unit repeated to about `size` chars, then a tail that stops a match at the very end. */
export const build = (unit: string, size: number) => unit.repeat(Math.max(1, Math.ceil(size / unit.length))) + '\u0001'
