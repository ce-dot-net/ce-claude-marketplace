// ACE mod suite, layout (a) render arm: cohort vectors, server share (render_layout_a_pct), default off, every path, trace field. Harness: ./helpers.ts.
import { expect } from 'claude-code/testing'
import { test } from './t.ts'
import S8 from './fixtures/search_8.ts'
import G from './fixtures/golden.ts'
import V from './fixtures/layout_a_vectors.ts'
import { pyLoads } from '../lib/pyjson.ts'
import { LAYOUT_A_DEFAULT_PCT, layoutAPct, RENDER_LAYOUT_A_PCT_FILE, layoutA, layoutAMember, renderCohort, serverLayoutAPct, sha256Hex, storedLayoutAPct } from '../lib/cohort.ts'
import { LAYOUT_A_FIELDS, renderLayoutBudget } from '../lib/render.ts'
import { mergeState } from '../lib/state.ts'
import { FULL_PCT, HUMAN, PDIR, ROOT, SDIR, done, execRow, host, mainTask, spawn, submit } from './helpers.ts'

const LAYOUT_PCT = `${ROOT}/${RENDER_LAYOUT_A_PCT_FILE}`
const NOW = 1_800_000_000_000  // the host clock
const fresh = (pct: number, ageDays = 0) => JSON.stringify({ pct, at: Math.floor(NOW / 1000) - ageDays * 86400 })
const cfgEnv = (c: any, l?: string) => ({ ACE_AB_CONTROL_PCT: String(c.C), ACE_AB_COMPACT_PCT: String(c.K), ACE_RENDER_FULL_PCT: String(c.F), ...(l ? { ACE_RENDER_LAYOUT_A_PCT: l } : {}) })
const bucket = (salt: string, id: string) => parseInt(sha256Hex(salt + id).slice(0, 8), 16) % 100
const withLayoutPct = (pct: unknown) => { const o = JSON.parse(S8); o.render_layout_a_pct = pct; return JSON.stringify(o) }

// ---------- the server's cohort vectors (plugins/ace/tests-fixtures/layout-a/cohort_vectors.json) ----------
test('cohort vectors: buckets, arms of both configs and layout_a, exactly (control and compact never get layout_a)', async () => {
  const v: any = V
  expect(v.cases.length >= 14).toBe(true)
  for (const c of v.cases) {
    if (c.id) expect([bucket('render:', c.id), bucket('layout:', c.id)]).toEqual([c.render_bucket, c.layout_bucket])
    const sid = c.id || undefined
    expect([c.id, renderCohort(sid, cfgEnv(v.configs.c0))]).toEqual([c.id, c.arm_c0])
    expect([c.id, renderCohort(sid, cfgEnv(v.configs.c10))]).toEqual([c.id, c.arm_c10])
    expect([c.id, layoutA(sid, cfgEnv(v.configs[v.layout_config], String(v.L)))]).toEqual([c.id, c.layout_a])
  }
  const byId = (id: string) => v.cases.find((c: any) => c.id === id)
  expect(byId('tv-02').arm_c10).toBe('compact'); expect(byId('tv-05').arm_c10).toBe('control')
  // the layout bucket alone would say yes there: the arm gate is what says no
  const env = cfgEnv(v.configs.c10, '100')
  expect([layoutAMember('tv-02', env), layoutA('tv-02', env), layoutAMember('tv-05', env), layoutA('tv-05', env)]).toEqual([true, false, true, false])
})

// ---------- server share render_layout_a_pct: env > file (< 7 days) > LAYOUT_A_DEFAULT_PCT (0) ----------
test('render_layout_a_pct: only a top-level integer 0-100 counts; the stored value expires after 7 days', async () => {
  for (const v of [0, 50, 100]) expect(serverLayoutAPct({ render_layout_a_pct: v })).toBe(v)
  for (const v of [-1, 101, '0', 12.5, true, null, [0]]) expect(serverLayoutAPct({ render_layout_a_pct: v })).toBe(undefined)
  expect(serverLayoutAPct(pyLoads('{"render_layout_a_pct": 50.0}'))).toBe(undefined)
  expect(serverLayoutAPct(null)).toBe(undefined)
  expect(storedLayoutAPct(fresh(30, 6), NOW)).toBe(30)
  expect(storedLayoutAPct(fresh(30, 8), NOW)).toBe(undefined)
  for (const t of [undefined, 'x', '[]', '{"pct": 200, "at": 1800000000}', '{"pct": 5}']) expect(storedLayoutAPct(t, NOW)).toBe(undefined)
})

test('layoutAMember: default 0 = off, env not an integer -> 0, negative -> 0, clamped to 100, no id -> no', async () => {
  expect(LAYOUT_A_DEFAULT_PCT).toBe(0)
  const ids = Array.from({ length: 300 }, (_, i) => `c-${i}`)
  expect(ids.some(i => layoutAMember(i, {}))).toBe(false)
  for (const bad of ['abc', '-5', '', '1.5', '0']) expect(ids.some(i => layoutAMember(i, { ACE_RENDER_LAYOUT_A_PCT: bad }))).toBe(false)
  expect(ids.every(i => layoutAMember(i, { ACE_RENDER_LAYOUT_A_PCT: '999' }))).toBe(true)
  expect(layoutAMember(undefined, { ACE_RENDER_LAYOUT_A_PCT: '100' })).toBe(false)
})

// ---------- the arm through every path, and OFF by default ----------
test('default (no env, no file): the render is byte-identical to today, no render_layout anywhere', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }) })
  const r: any = await submit($)
  expect(r.context[0]).toBe(G.full_main_8)
  expect('render_layout' in h.state()!).toBe(false)
  expect(h.rows().find((x: any) => x.event === 'search')!.render_cohort).toBe('full')
  await $.tool.call({ tool: 'Read', file_path: '/proj/ace-cli/notes.md' } as any)
  const sp: any = await spawn($, 'review the domain shift python port for parity bugs')
  expect(sp.seenPrompt).toBe('review the domain shift python port for parity bugs\n\n' + G.full_sub_8)
})

test('env 100: main (full arm), subagent and domain shift render layout (a); state, log and trace carry it; render_variant stays', async ($, on) => {
  const h = host(on, { env: { ACE_RENDER_LAYOUT_A_PCT: '100' }, search: () => ({ stdout: S8 }) })
  const r: any = await submit($)
  expect(r.context[0]).toBe(G.layout_a_full_8)
  expect(r.context[0].split('\n').length).toBe(2 + 1 + 8)
  const st = h.state()!
  expect([st.render_variant, st.render_layout]).toEqual(['full', 'a'])
  expect(h.rows().find((x: any) => x.event === 'search')!.render_cohort).toBe('full+layout_a')
  const ds: any = await $.tool.call({ tool: 'Read', file_path: '/proj/ace-cli/notes.md' } as any)
  expect(ds.context[ds.context.length - 1]).toBe(G.layout_a_domain_shift_8)
  const p1 = 'review the domain shift python port for parity bugs'
  const sp: any = await spawn($, p1)
  expect(sp.seenPrompt).toBe(p1 + '\n\n' + G.layout_a_sub_8)
  await $.turn.start({ text: HUMAN, turnId: 't1' } as any)
  await $.tool.call({ tool: 'Edit', file_path: '/proj/x.py', old_string: 'a', new_string: 'b' } as any)
  await $.tool.call({ tool: 'Bash', command: 'pytest -q' } as any)
  await done($, 'finished the change')
  for (let i = 0; i < 200 && h.learns().length < 1; i++) await new Promise(r => setTimeout(r, 5))
  const t = h.trace(h.learns()[0]!)
  expect([t.render_variant, t.render_path, t.render_layout]).toEqual(['full', 'mod', 'a'])
})

test('budget arm (full share 0) renders layout (a) too: the layout_a_main_8 golden', async ($, on) => {
  host(on, { defaultArm: true, env: { ACE_RENDER_FULL_PCT: '0', ACE_RENDER_LAYOUT_A_PCT: '100' }, search: () => ({ stdout: S8 }) })
  const r: any = await submit($)
  expect(r.context[0]).toBe(G.layout_a_main_8)
})

test('control and compact arms never get layout (a), whatever the layout share', async ($, on) => {
  const h = host(on, { env: { ACE_AB_CONTROL_PCT: '100', ACE_RENDER_LAYOUT_A_PCT: '100' }, search: () => ({ stdout: S8 }) })
  const r: any = await submit($)
  expect(r.context === undefined || r.context.length === 0).toBe(true)
  expect('render_layout' in h.state()!).toBe(false)
})
test('compact arm: one-liners as today, no layout (a)', async ($, on) => {
  const h = host(on, { env: { ACE_AB_COMPACT_PCT: '100', ACE_RENDER_LAYOUT_A_PCT: '100' }, search: () => ({ stdout: S8 }) })
  const r: any = await submit($)
  expect(r.context[0].includes('mode="compact"')).toBe(true)
  expect(r.context[0].includes('"fields"')).toBe(false)
  expect('render_layout' in h.state()!).toBe(false)
})

test('server share: file on -> arm on; stale file, env 0 -> off; the search response stores its own file, never render-full-pct.json', async ($, on) => {
  const on100 = host(on, { files: { [LAYOUT_PCT]: fresh(100) }, search: () => ({ stdout: S8 }) })
  expect(((await submit($)) as any).context[0]).toBe(G.layout_a_full_8)
  expect(on100.state()!.render_layout).toBe('a')
})
test('server share: a stale (> 7 days) file is the default (off)', async ($, on) => {
  const h = host(on, { files: { [LAYOUT_PCT]: fresh(100, 8) }, search: () => ({ stdout: S8 }) })
  expect(((await submit($)) as any).context[0]).toBe(G.full_main_8)
  expect(h.files.get(LAYOUT_PCT)).toBe(fresh(100, 8))
})
test('server share: env 0 beats a fresh file, env 100 beats a file of 0', async ($, on) => {
  host(on, { env: { ACE_RENDER_LAYOUT_A_PCT: '0' }, files: { [LAYOUT_PCT]: fresh(100) }, search: () => ({ stdout: S8 }) })
  expect(((await submit($)) as any).context[0]).toBe(G.full_main_8)
})
test('server share: a search response render_layout_a_pct is persisted in its own file; invalid values and a missing field keep it', async ($, on) => {
  let pct: unknown = 40
  const h = host(on, { search: () => ({ stdout: withLayoutPct(pct) }) })
  await submit($)
  expect(JSON.parse(h.files.get(LAYOUT_PCT)!)).toEqual({ pct: 40, at: Math.floor(h.now() / 1000) })
  expect(h.files.has(FULL_PCT)).toBe(false)  // render-full-pct.json is not touched
  for (const bad of ['off', -1, 101, true, 12.5]) { pct = bad; await submit($, HUMAN + ' again'); expect(JSON.parse(h.files.get(LAYOUT_PCT)!).pct).toBe(40) }
  pct = undefined; await submit($, HUMAN + ' once more'); expect(JSON.parse(h.files.get(LAYOUT_PCT)!).pct).toBe(40)
  pct = 0; await submit($, HUMAN + ' and zero'); expect(JSON.parse(h.files.get(LAYOUT_PCT)!).pct).toBe(0)
})
test('server share: render_full_pct in the response writes only the full file', async ($, on) => {
  const o = JSON.parse(S8); o.render_full_pct = 70
  const h = host(on, { search: () => ({ stdout: JSON.stringify(o) }) })
  await submit($)
  expect(h.files.has(FULL_PCT)).toBe(true)
  expect(h.files.has(LAYOUT_PCT)).toBe(false)
})

// ---------- format: head + one line per pattern ----------
test('layout (a) text: header names the fields once, one compact array per pattern, null for missing, hint only on request', async () => {
  const resp = JSON.parse(S8)
  const plain = renderLayoutBudget(resp, 'ace-patterns', 'agent-type="main"').context as string
  const lines = plain.split('\n')
  const head = JSON.parse(lines[1]!)
  expect(head.fields).toEqual(LAYOUT_A_FIELDS)
  expect(Object.keys(head)).toEqual(['retrieval_id', 'count', 'fields'])
  for (const l of lines.slice(2, -1)) expect(JSON.parse(l).length).toBe(LAYOUT_A_FIELDS.length)
  expect(plain.length <= 9500).toBe(true)
  const hinted = renderLayoutBudget(resp, 'ace-patterns', 'agent-type="main"', true).context as string
  expect(hinted.split('\n')[1]!.startsWith('Format:')).toBe(true)
  expect(hinted.length <= 9500).toBe(true)
})

// ---------- review fixes ----------
const DS = { tool: 'Read', file_path: '/proj/ace-cli/notes.md' } as any
const DOMAINS = { [`${PDIR}/domains.json`]: JSON.stringify({ 'ace-cli': 3 }) }  // known domains, no prompt before the domain shift
test('W1: a domain shift alone marks the state (render_layout a)', async ($, on) => {
  const h = host(on, { env: { ACE_RENDER_LAYOUT_A_PCT: '100' }, files: DOMAINS, search: () => ({ stdout: S8 }) })
  await $.tool.call(DS)  // no prompt before it: the domain shift is the only render of this task
  expect(h.state()!.render_layout).toBe('a')
})
test('W1: a domain shift alone with the hint env marks a+hint', async ($, on) => {
  const h = host(on, { env: { ACE_RENDER_LAYOUT_A_PCT: '100', ACE_RENDER_LAYOUT_A_HINT: '1' }, files: DOMAINS, search: () => ({ stdout: S8 }) })
  await $.tool.call(DS)
  expect(h.state()!.render_layout).toBe('a+hint')
})
test('W1: domain shift without layout cohort sets no render_layout', async ($, on) => {
  const h = host(on, { files: DOMAINS, search: () => ({ stdout: S8 }) })
  await $.tool.call(DS)
  expect('render_layout' in (h.state() ?? {})).toBe(false)
})
test('W1: domain shift in the control arm sets no render_layout', async ($, on) => {
  const h = host(on, { env: { ACE_RENDER_LAYOUT_A_PCT: '100', ACE_AB_CONTROL_PCT: '100' }, files: DOMAINS, search: () => ({ stdout: S8 }) })
  await $.tool.call(DS)
  expect('render_layout' in (h.state() ?? {})).toBe(false)
})
test('W1: domain shift in the compact arm sets no render_layout', async ($, on) => {
  const h = host(on, { env: { ACE_RENDER_LAYOUT_A_PCT: '100', ACE_AB_COMPACT_PCT: '100' }, files: DOMAINS, search: () => ({ stdout: S8 }) })
  await $.tool.call(DS)
  expect('render_layout' in (h.state() ?? {})).toBe(false)
})
test('W2: a render without layout removes an earlier render_layout (not sticky)', async ($, on) => {
  const h = host(on, { files: { [LAYOUT_PCT]: fresh(100) }, search: () => ({ stdout: S8 }) })
  await submit($)
  expect(h.state()!.render_layout).toBe('a')
  h.files.set(LAYOUT_PCT, fresh(0))  // the server share drops to 0: the next task renders today's layout
  await submit($, HUMAN + ' second')
  expect('render_layout' in h.state()!).toBe(false)
})
test('I8: the hint env makes the value a+hint in state, log label and trace; a hint-free render stays a', async ($, on) => {
  const h = host(on, { env: { ACE_RENDER_LAYOUT_A_PCT: '100', ACE_RENDER_LAYOUT_A_HINT: '1' }, search: () => ({ stdout: S8 }) })
  const r: any = await submit($)
  expect(r.context[0].split('\n')[1]!.startsWith('Format:')).toBe(true)
  expect(h.state()!.render_layout).toBe('a+hint')
  expect(h.rows().find((x: any) => x.event === 'search')!.render_cohort).toBe('full+layout_a+hint')
  await $.turn.start({ text: HUMAN, turnId: 't1' } as any)
  await $.tool.call({ tool: 'Edit', file_path: '/proj/x.py', old_string: 'a', new_string: 'b' } as any)
  await $.tool.call({ tool: 'Bash', command: 'pytest -q' } as any)
  await done($, 'finished the change')
  for (let i = 0; i < 200 && h.learns().length < 1; i++) await new Promise(r => setTimeout(r, 5))
  expect(h.trace(h.learns()[0]!).render_layout).toBe('a+hint')
  expect(execRow(h).render_cohort).toBe('full+layout_a+hint')
})
test('I2: ACE_RENDER_LAYOUT_A_PCT parses like Python (ASCII digits, sign, outer blanks only)', async () => {
  const vals = ['5_0', ' 50 ', '+50', '50.0', '0x10', '', '1e1', '-5', '\uff15\uff10', '50\n', '007', '100', '101', '-0', '5 0']
  expect(vals.map(v => layoutAPct({ ACE_RENDER_LAYOUT_A_PCT: v }))).toEqual([0, 50, 50, 0, 0, 0, 0, 0, 0, 50, 7, 100, 100, 0, 0])
})
test('W2: mergeState — a render without layout (null) clears render_layout, nothing rendered (undefined) keeps it, only a / a+hint are stored', async () => {
  const prior = { pattern_ids: [], render_layout: 'a' }
  expect(mergeState(prior, { renderLayout: null }).render_layout).toBe(undefined)
  expect(mergeState(prior, {}).render_layout).toBe('a')
  expect(mergeState(prior, { renderLayout: 'a+hint' }).render_layout).toBe('a+hint')
  expect(mergeState({}, { renderLayout: 'a+hint' }).render_layout).toBe('a+hint')
  expect(mergeState({}, { renderLayout: 'b' }).render_layout).toBe(undefined)
  expect(mergeState({ render_layout: 'x' }, {}).render_layout).toBe(undefined)
})
test('domain shift with one oversize pattern renders nothing and stamps nothing (same as Python)', async ($, on) => {
  const o = JSON.parse(S8); o.similar_patterns = [{ ...o.similar_patterns[0], content: 'x'.repeat(12000) }]
  const h = host(on, { env: { ACE_RENDER_LAYOUT_A_PCT: '100' }, files: DOMAINS, search: () => ({ stdout: JSON.stringify(o) }) })
  const r: any = await $.tool.call(DS)
  expect(r.context === undefined || r.context.length === 0).toBe(true)
  expect('render_layout' in (h.state() ?? {})).toBe(false)
})
