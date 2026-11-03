// ACE mod suite, tool.call: the domain shift. Harness: ./helpers.ts.
import { expect, test } from 'claude-code/testing'
import S100 from './fixtures/search_100.ts'
import S8 from './fixtures/search_8.ts'
import SEDGE from './fixtures/search_edge.ts'
import G from './fixtures/golden.ts'
import USED_CASES from './fixtures/used_cases.ts'
import REJECTION_CASES from './fixtures/rejection_cases.ts'
import { pyLoads } from '../lib/pyjson.ts'
import { renderPatternsDict } from '../lib/render.ts'
import { traceVariant, renderCohort, serverFullPct, storedFullPct } from '../lib/cohort.ts'
import { hasSubstantialWork, toolRec } from '../lib/trace.ts'
import { rejectionMatch, evalStats, evalInjection, usedPatternIds, toolHaystack } from '../lib/evidence.ts'
import { PRIVATE_WRITE_SH } from '../lib/sh.ts'
import { statusLine, learnLine } from '../ui/status.ts'
import { CWD, EVAL_REQ, FULL_PCT, HOME, HUMAN, LOCAL_CLI, LOCKED, MALFORMED, MIN, PDIR, PLACEHOLDER, PRJ, PROOT, REAL, REL, ROOT, SDIR, SECOND, SID, UUID4, bodyOf, cliOf, cmd, done, dsSearches, execRow, host, mainTask, ranked, rejectFlow, settle, shownOf, spawn, st8a, submit, withPct } from './helpers.ts'
import type { Opts, Run, SearchAnswer } from './helpers.ts'

// ---------- tool.call Read: domain shift ----------


test('domain shift: Read in a known domain → one --top-k 8 search, NO pin (§16 P8), context attached, once per domain', async ($, on) => {
  const h = host(on)
  await submit($)
  const main = h.pin(h.searches()[0]!)!
  const r1: any = await $.tool.call({ tool: 'Read', file_path: '/proj/ace-cli/notes.md' } as any)
  const r2: any = await $.tool.call({ tool: 'Read', file_path: '/proj/ace-cli/other.md' } as any)
  const ds = h.searches().filter(s => s.argv.includes('--top-k'))
  expect(ds.length).toBe(1)
  expect(h.flag(ds[0]!.argv, '--top-k')).toBe('8')
  expect(h.pin(ds[0]!)).toBeUndefined()  // §16 P8: the server never credits domain-shift rows; the sqlite pin is the lock source
  expect(h.flag(ds[0]!.argv, '--session-id')).toBe(main)  // cli 4.3.1: unpinned session stamp
  expect(h.state()!.task_session_id).toBe(main)
  expect(ds[0]!.stdin).toBe('notes')
  expect(ds[0]!.timeoutMs! <= 17000).toBe(true)
  expect(r1.context[r1.context.length - 1]).toBe(G.domain_shift_8)
  expect(r2.context === undefined || r2.context.length === 0).toBe(true)
  expect(h.files.get(`${SDIR}/domain-last-main.txt`)!.trim()).toBe('ace-cli')
  const st = h.state()!
  expect(st.retrieval_id).toBe(JSON.parse(S100).retrieval_id)
  for (const p of JSON.parse(S8).similar_patterns) if (/^[0-9a-f-]{36}$/.test(p.id ?? '')) expect(st.pattern_ids).toContain(p.id)
  expect(h.rows().some((x: any) => x.event === 'domain_shift' && x.to_domain === 'ace-cli')).toBe(true)
})

test('domain-shift claim: two parallel Reads in the same new domain → exactly one search', async ($, on) => {
  const h = host(on)
  await submit($)
  await Promise.all([
    $.tool.call({ tool: 'Read', file_path: '/proj/ace-cli/a.md' } as any),
    $.tool.call({ tool: 'Read', file_path: '/proj/ace-cli/b.md' } as any),
  ])
  expect(h.searches().filter(s => s.argv.includes('--top-k')).length).toBe(1)
})

test('domain-shift claim is per agent+domain: a Read of domain B while A is in flight still searches; last-domain is the newest claim', async ($, on) => {
  const h = host(on)
  await submit($)
  await Promise.all([
    $.tool.call({ tool: 'Read', file_path: '/proj/ace-cli/a.md' } as any),
    $.tool.call({ tool: 'Read', file_path: '/proj/system-validation/b.md' } as any),
  ])
  expect(h.searches().filter(s => s.argv.includes('--top-k')).length).toBe(2)
  expect(h.files.get(`${SDIR}/domain-last-main.txt`)!.trim()).toBe('system-validation-and-testing')
})

test('domain shift inside a subagent: no pin (§16 P8), merges into the SUBAGENT state, its id kept', async ($, on) => {
  const h = host(on)
  await submit($)
  await spawn($, 'review the domain shift python port for parity bugs')
  const sub = h.state('agent-1')!.task_session_id
  await $.tool.call({ tool: 'Read', file_path: '/proj/ace-cli/notes.md', agentId: 'agent-1' } as any)
  const ds = h.searches().filter(s => s.argv.includes('--top-k'))
  expect(ds.length).toBe(1)
  expect(h.pin(ds[0]!)).toBeUndefined()
  expect(h.files.get(`${SDIR}/domain-last-agent-1.txt`)!.trim()).toBe('ace-cli')
  expect(h.state('agent-1')!.task_session_id).toBe(sub)
})
