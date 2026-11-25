// A hostile input per redaction rule, derived from the rule tables (hostile_gen.ts): the scaling exponent of redact() on it must stay
// linear (timing.ts: fitted log-log slope, load-proof). A rule without a registry entry fails the first test.
import { expect } from 'claude-code/testing'
import { test } from './t.ts'
import { redact } from '../lib/redact.ts'
import { HOSTILE } from './fixtures/hostile_rules.ts'
import { build, hostileCases, tableRules } from './hostile_gen.ts'
import { expectLinear } from './timing.ts'

const FULL = 256 * 1024

test('every rule in the tables has a hostile-registry entry (derived, extra units, or linear with a reason), and no entry is stale', () => {
  const ids = tableRules().map(r => r.id), reg = Object.keys(HOSTILE.rules)
  expect(ids.filter(i => !(i in HOSTILE.rules))).toEqual([])
  expect(reg.filter(i => !ids.includes(i) && !i.startsWith('engine:'))).toEqual([])
  for (const [id, d] of Object.entries<any>(HOSTILE.rules)) if (d.linear) expect([id, typeof d.linear]).toEqual([id, 'string'])
})

const byRule = new Map<string, string[]>()
for (const [id, u] of hostileCases()) byRule.set(id, [...(byRule.get(id) ?? []), u])
for (const [id, units] of byRule)
  test(`hostile input for ${id}: redact() scales linearly (${units.length} inputs)`, { timeoutMs: 120_000 }, () => {
    for (const u of units) expectLinear(f => build(u, Math.floor(FULL * f)), redact, `${id} ${JSON.stringify(u.slice(0, 20))}`)
  })
