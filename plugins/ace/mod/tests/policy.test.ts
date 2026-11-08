// ACE mod suite, 8.1.4: client_policy (dormant until the server sends it) and the /ace:ace-doctor delivery line.
// Cases: ../../tests-fixtures/client-policy/cases.json via ./fixtures/client_policy_cases.ts (shared with
// tests/test_client_policy.py). Harness: ./helpers.ts.
import { expect, test } from 'claude-code/testing'
import { CASES } from './fixtures/client_policy_cases.ts'
import S8 from './fixtures/search_8.ts'
import { CLIENT_POLICY_FILE, clientPolicyBand, clientPolicyState, validClientPolicy } from '../lib/cohort.ts'
import { CWD, PROOT, REL, ROOT, host, submit } from './helpers.ts'

const DAY = 86_400_000
const MANIFEST = { [`${PROOT}/.claude-plugin/plugin.json`]: '{"name": "ace", "version": "8.1.4"}' }
const BAND = { plugin: 'ace', component: 'AbovePrompt', surface: 'terminal', props: { hasSurvey: false, isWorking: false, bodyRows: 10, bodyColumns: 120 } } as any
const start = ($: any) => $.session.start({ cwd: CWD, surface: null, isInteractive: false } as any)
const tick = async () => { for (let i = 0; i < 20; i++) await new Promise(r => setTimeout(r, 2)) }
const run = async ($: any, name: string) => (await $.command.run({ command: `ace:ace-${name}`, args: '' })).text as string
const withPolicy = (policy: any) => JSON.stringify({ ...JSON.parse(S8), client_policy: policy })

for (const c of CASES) {
  test(`client_policy: ${c.name}`, async () => {
    const now = 1_800_000_000_000
    let text: string | undefined
    if ('policy' in c) {
      const v = validClientPolicy(c.policy)
      expect('policy' in v).toBe(c.expect_valid === true)
      if ('policy' in v) text = JSON.stringify({ policy: v.policy, at: (now - c.age_days * DAY) / 1000 })
    }
    expect(clientPolicyState(text, c.version, now) ?? null).toBe(c.expect_state)
  })
}

test('a search response stores a valid client_policy privately (known keys only)', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: withPolicy({ min_plugin_version: '9.0.0', future: 1 }) }) })
  await submit($)
  expect(JSON.parse(h.files.get(`${ROOT}/${CLIENT_POLICY_FILE}`)!).policy).toEqual({ min_plugin_version: '9.0.0' })
})

test('an invalid client_policy is dropped and logged (reason only)', async ($, on) => {
  const h2 = host(on, { search: () => ({ stdout: withPolicy({ url: 'javascript:alert(1)' }) }) })
  await submit($)
  expect(h2.files.has(`${ROOT}/${CLIENT_POLICY_FILE}`)).toBe(false)
  const bad = h2.rows().filter((r: any) => r.event === 'client_policy_invalid')
  expect(bad.length).toBe(1)
  expect(bad[0].reason).toBe('bad_url')
  expect(JSON.stringify(bad[0]).includes('javascript')).toBe(false)
})

test('below min: ONE band line with one action; ACE keeps searching and learning', async ($, on) => {
  const h = host(on, { files: { ...MANIFEST, [`${ROOT}/${CLIENT_POLICY_FILE}`]: JSON.stringify({ policy: { min_plugin_version: '8.1.5' }, at: 1_800_000_000 }) } })
  await start($)
  await tick()
  const ui = await $.ui.mount(BAND)
  expect((await ui.find({ type: 'Text', text: /ist zu alt/ }))?.text).toContain('ACE 8.1.4 ist zu alt, bitte /plugin update ausführen')
  expect((await ui.findAll({ type: 'Button' })).length).toBe(1)
  await ui.unmount()
  await submit($)
  expect(h.searches().length).toBe(1)
})

test('below recommended: no band, one doctor line', async ($, on) => {
  const text = JSON.stringify({ policy: { recommended_plugin_version: '8.2.0', message: 'fixes trace loss', url: 'https://example.com/r' }, at: 1_800_000_000 })
  host(on, { files: { ...MANIFEST, [`${ROOT}/${CLIENT_POLICY_FILE}`]: text } })
  expect(clientPolicyBand(text, '8.1.4', 1_800_000_000_000)).toBeUndefined()  // the band steps aside (next)
  await start($)
  expect(await run($, 'doctor')).toContain('update   ACE 8.1.4 · empfohlen 8.2.0: fixes trace loss · https://example.com/r')
})

test('doctor: delivery queue depth, oldest age, replayed/dead/expired of the last 7 days', async ($, on) => {
  const T = 1_800_000_000  // the host clock (s)
  const e = (id: string, ageS: number) => JSON.stringify({ v: 1, id, created_at: T - ageS, next_at: T, attempts: 1, meta: {}, trace: {} })
  const iso = (ageS: number) => new Date((T - ageS) * 1000).toISOString()
  host(on, { files: {
    [`${ROOT}/trace-queue/a.json`]: e('a', 7200), [`${ROOT}/trace-queue/b.json`]: e('b', 60),
    [`${ROOT}/trace-queue/dead/c.json`]: e('c', 10),
    [REL]: [{ event: 'learn_replayed', timestamp: iso(100) }, { event: 'learn_replayed', timestamp: iso(8 * 86400) },
      { event: 'learn_expired', timestamp: iso(100) }].map(r => JSON.stringify(r)).join('\n') + '\n' } })
  await start($)
  expect(await run($, 'doctor')).toContain('delivery queue 2 · oldest 2h · 7d replayed 1 · dead 1 · expired 1')
})
