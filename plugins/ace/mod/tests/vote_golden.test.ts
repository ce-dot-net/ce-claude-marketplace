// 8.4.3 golden: the live vote decisions are byte-identical to 8.4.2 while followup_judging and feedback_unresolved are off: absent,
// stored off / stale / malformed, or a search answer carrying a value other than exactly 'shadow' / true (followup_judging) or exactly
// true (feedback_unresolved). The fixture was captured on the
// 8.4.2 code (4c8fb1b). last-main-applied.json is compared without its new retrieval_id field (8.4.3 adds it; nothing reads it without the capability).
import { expect } from 'claude-code/testing'
import { test } from './t.ts'
import GOLDEN from './fixtures/vote_golden_842.ts'
import { SCENARIOS, SWITCHES, snapshot } from './vote_scenarios.ts'

for (const [name, sc] of Object.entries(SCENARIOS))
  for (const [sw, files] of Object.entries(SWITCHES))
    test(`golden 8.4.2: ${name} (switches ${sw}) -> identical vote rows, files, feedback, model calls`, async ($, on) => {
      const { snap } = await snapshot($, on, sc, files)
      if (!(name in GOLDEN)) console.log('GOLDEN ' + JSON.stringify({ [name]: snap }))
      expect(snap).toEqual((GOLDEN as any)[name])
    })
// the server answer itself carries an invalid / off value (every real answer is stored, so this is what the client then sees)
const RESP_OFF: Record<string, Record<string, unknown>> = {
  unresolved_false: { feedback_unresolved: false }, unresolved_string: { feedback_unresolved: 'true' }, unresolved_one: { feedback_unresolved: 1 },
  followup_false: { followup_judging: false }, followup_string: { followup_judging: 'true' }, both_null: { feedback_unresolved: null, followup_judging: null },
}
for (const [name, sc] of Object.entries(SCENARIOS))
  for (const [sw, extra] of Object.entries(RESP_OFF))
    test(`golden 8.4.2: ${name} (answer ${sw}) -> identical vote rows, files, feedback, model calls`, async ($, on) => {
      const { snap } = await snapshot($, on, sc, {}, {}, (o: any) => Object.assign(o, extra))
      expect(snap).toEqual((GOLDEN as any)[name])
    })
