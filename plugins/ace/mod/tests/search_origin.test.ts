// ACE mod suite, 8.2.3: interactive / human_prompt_count on the engine search stdin (POST /patterns/search body).
// Same source and rules as the 8.2.2 trace fields: each only when known, never defaulted. Harness: ./helpers.ts.
import { expect, test } from 'claude-code/testing'
import S8 from './fixtures/search_8.ts'
import { CWD, HUMAN, PDIR, PLACEHOLDER, PROOT, REAL, SDIR, SID, cliOf, done, host, mainTask, spawn, submit } from './helpers.ts'

const ENGINE = { [`${PROOT}/engine/search.js`]: '' }
const start = ($: any, isInteractive: boolean) => $.session.start({ cwd: CWD, surface: null, isInteractive } as any)
const engineHost = (on: any, got: any[], extra: any = {}) =>
  host(on, { ...extra, files: { ...ENGINE, ...(extra.files ?? {}) }, engine: (stdin?: string) => { got.push(JSON.parse(stdin!)); return { stdout: S8 } } })

test('8.2.3: headless (-p): interactive=false and human_prompt_count=0 survive the engine payload', async ($, on) => {
  const got: any[] = []
  engineHost(on, got)
  await start($, false)
  await submit($, HUMAN, 'sdk')
  expect(got.length).toBe(1)
  expect(got[0].interactive).toBe(false)
  expect(got[0].human_prompt_count).toBe(0)
})

test('8.2.3: interactive: true and the count; the main search count INCLUDES the current prompt', async ($, on) => {
  const got: any[] = []
  engineHost(on, got)
  await start($, true)
  await submit($)
  await submit($, HUMAN, 'bridge')
  expect(got.map(g => [g.interactive, g.human_prompt_count])).toEqual([[true, 1], [true, 2]])
})

test('8.2.3: unknown -> both omitted (no session.start, no origin file), never defaulted', async ($, on) => {
  const got: any[] = []
  engineHost(on, got, { beforeWrite: async (p: string) => { if (p.endsWith('/prompt-origin.json')) throw new Error('disk full') } })
  await submit($)
  expect(got.length).toBe(1)
  expect('interactive' in got[0]).toBe(false)
  expect('human_prompt_count' in got[0]).toBe(false)
})

test('8.2.3: readOrigin failure -> human_prompt_count omitted (not 0); a known interactive still goes', async ($, on) => {
  const got: any[] = []
  engineHost(on, got, { beforeWrite: async (p: string) => { if (p.endsWith('/prompt-origin.json')) throw new Error('disk full') } })
  await start($, false)
  await submit($)
  expect(got[0].interactive).toBe(false)
  expect('human_prompt_count' in got[0]).toBe(false)
})

test('8.2.3: a stored count from before a reload is read (per conversation, on disk)', async ($, on) => {
  const got: any[] = []
  engineHost(on, got, { files: { [`${SDIR}/prompt-origin.json`]: JSON.stringify({ origin: 'sdk', humanPrompts: 5 }) } })
  await submit($)
  expect(got[0].human_prompt_count).toBe(6)
})

test('8.2.3: the subagent-start search carries the parent conversation\'s values', async ($, on) => {
  const got: any[] = []
  engineHost(on, got)
  await start($, true)
  await submit($)
  await spawn($, 'review the domain shift python port for parity bugs')
  expect(got.length).toBe(2)
  expect([got[1].interactive, got[1].human_prompt_count]).toEqual([true, 1])
})

test('8.2.3: the domain-shift search carries the values (headless false/0 kept)', async ($, on) => {
  const got: any[] = []
  engineHost(on, got)
  await start($, false)
  await submit($, HUMAN, 'sdk')
  await $.tool.call({ tool: 'Read', file_path: '/proj/ace-cli/notes.md' } as any)
  const ds = got.find(g => g.top_k === 8)!
  expect([ds.interactive, ds.human_prompt_count]).toEqual([false, 0])
})

test('8.2.3: the ace-cli fallback cannot carry them (deliberate limit): its argv is unchanged', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }) })
  await start($, false)
  await submit($, HUMAN, 'sdk')
  const argv = cliOf(h.searches()[0]!.argv)!
  expect(argv.some(a => /interactive|human/i.test(a))).toBe(false)
})

// ---------- server-team contract cases (spy = the engine stdin = what engine/search.js puts in the body) ----------
const pair = (g: any) => [g.interactive, g.human_prompt_count]
const noOriginWrite = async (p: string) => { if (p.endsWith('/prompt-origin.json')) throw new Error('disk full') }

// origin.kind 'sdk' is what a real `claude -p` delivers (observed 2026-11-11, -p and -p -c, scratch plugin copy + stub engine)
test('contract 1: claude -p / SDK: false and 0 on every search, also after several turns', async ($, on) => {
  const got: any[] = []
  engineHost(on, got)
  await start($, false)
  for (let i = 0; i < 4; i++) await submit($, HUMAN, 'sdk')
  expect(got.map(pair)).toEqual([[false, 0], [false, 0], [false, 0], [false, 0]])
})

test('contract 2: interactive with 1, 2, n prompts: true and count = prompts so far, current included', async ($, on) => {
  const got: any[] = []
  engineHost(on, got)
  await start($, true)
  for (let i = 0; i < 5; i++) await submit($)
  expect(got.map(pair)).toEqual([[true, 1], [true, 2], [true, 3], [true, 4], [true, 5]])
})

test('contract 3: subagent of an interactive session inherits true + the parent count at start AND at lateInject', async ($, on) => {
  const got: any[] = []
  engineHost(on, got)
  await start($, true)
  await submit($)
  await submit($, HUMAN, 'bridge')
  await spawn($, 'review the domain shift python port for parity bugs')
  await spawn($, PLACEHOLDER, { workflow: { runId: 'wf_x', agentIndex: 2 } })
  await $.turn.start({ text: REAL, turnId: 'w1', agentId: 'agent-2' } as any)
  await $.tool.call({ tool: 'Bash', command: 'ls', agentId: 'agent-2' } as any)
  expect(got.find(g => g.query === REAL)).toBeDefined()  // the lateInject search ran
  expect(got.slice(2).map(pair)).toEqual([[true, 2], [true, 2], [true, 2]])  // spawn, placeholder spawn, late
})

test('contract 4: subagent of a headless run inherits false and 0', async ($, on) => {
  const got: any[] = []
  engineHost(on, got)
  await start($, false)
  await submit($, HUMAN, 'sdk')
  await spawn($, 'review the domain shift python port for parity bugs')
  expect(got.map(pair)).toEqual([[false, 0], [false, 0]])
})

test('contract 5: the domain-shift search sends the same values as the main search of the session', async ($, on) => {
  const got: any[] = []
  engineHost(on, got)
  await start($, true)
  await submit($)
  await $.tool.call({ tool: 'Read', file_path: '/proj/ace-cli/notes.md' } as any)
  const ds = got.find(g => g.top_k === 8)!
  expect(pair(ds)).toEqual(pair(got[0]))
  expect(pair(ds)).toEqual([true, 1])
})

test('contract 6: prompt-origin.json unreadable (garbage, not rewritable) -> count absent, interactive still set', async ($, on) => {
  const got: any[] = []
  engineHost(on, got, { files: { [`${SDIR}/prompt-origin.json`]: '{not json' }, beforeWrite: noOriginWrite })
  await start($, true)
  await submit($)
  expect(got[0].interactive).toBe(true)
  expect('human_prompt_count' in got[0]).toBe(false)
})

// ponytail: one load stands in for two processes, so only the per-session FILE is exercised (L.interactive is per process)
test('contract 7: two sessions in one project keep separate counters (file per Claude Code session id)', async ($, on) => {
  let sid = SID
  const got: any[] = []
  const h = engineHost(on, got, { sid: () => sid, files: { [`${PDIR}/sessions/sess-2/mod-classic`]: '1800000000000' } })
  await submit($)
  await submit($)
  sid = 'sess-2'
  await submit($, HUMAN, 'sdk')
  await submit($, HUMAN, 'sdk')
  sid = SID
  await submit($)
  expect(got.map(g => g.human_prompt_count)).toEqual([1, 2, 0, 0, 3])
  expect(JSON.parse(h.files.get(`${SDIR}/prompt-origin.json`)!).humanPrompts).toBe(3)
  expect(JSON.parse(h.files.get(`${PDIR}/sessions/sess-2/prompt-origin.json`)!).humanPrompts).toBe(0)
})

test('contract 8: ace-cli fallback (engine gate fails): neither field on the CLI argv or stdin', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }), files: ENGINE, engine: () => ({ exitCode: 3, stderr: 'gate: core_missing' }) })
  await start($, false)
  await submit($, HUMAN, 'sdk')
  const s = h.searches()[0]!
  expect(cliOf(s.argv)!.some(a => /interactive|human/i.test(a))).toBe(false)
  expect(/interactive|human_prompt/.test(String(s.stdin))).toBe(false)
})

for (const [interactive, kind, want] of [[true, 'composer', [true, 1]], [false, 'sdk', [false, 0]]] as const) {
  test(`contract 9: trace and search of the same task carry the same interactive/count (${kind})`, async ($, on) => {
    const got: any[] = []
    const h = engineHost(on, got)
    await start($, interactive)
    await submit($, HUMAN, kind)
    await $.turn.start({ text: HUMAN, turnId: 't1' } as any)
    await $.tool.call({ tool: 'Edit', file_path: '/proj/x.py', old_string: 'a', new_string: 'b' } as any)
    await $.tool.call({ tool: 'Bash', command: 'pytest -q' } as any)
    await done($, 'all done')
    const t = h.trace(h.learns()[0]!)
    expect(pair(got[0])).toEqual([...want])
    expect([t.interactive, t.human_prompt_count]).toEqual(pair(got[0]))
  })
}

test('contract 9b: the one allowed difference: the trace count is read at turn end, the search count at search time', async ($, on) => {
  const got: any[] = []
  const h = engineHost(on, got)
  await start($, true)
  await mainTask($, h)
  await $.prompt.submit({ text: SECOND_PROMPT, wait: true, origin: { kind: 'composer' }, turnId: 't1' } as any)  // a human prompt into the running turn
  await done($, 'all done')
  const t = h.trace(h.learns()[0]!)
  expect(got[0].human_prompt_count).toBe(1)
  expect(t.human_prompt_count).toBe(2)
  expect(t.interactive).toBe(got[0].interactive)
})
const SECOND_PROMPT = 'and also make the second change to the trace builder please'
