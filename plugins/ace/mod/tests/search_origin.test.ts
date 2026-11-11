// ACE mod suite, 8.2.3: interactive / human_prompt_count on the engine search stdin (POST /patterns/search body).
// Same source and rules as the 8.2.2 trace fields: each only when known, never defaulted. Harness: ./helpers.ts.
import { expect, test } from 'claude-code/testing'
import S8 from './fixtures/search_8.ts'
import { CWD, HUMAN, PROOT, SDIR, cliOf, host, spawn, submit } from './helpers.ts'

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
