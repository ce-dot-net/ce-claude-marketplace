// 8.2.0 bootstrap_backfill capability flag: top-level boolean of a search response, persisted {on, at}, < 7 days, else off.
import { expect, test } from 'claude-code/testing'
import { BACKFILL_FLAG_FILE, serverBackfill, storedBackfill } from '../lib/cohort.ts'

test('serverBackfill: only a real boolean counts; absent / non-boolean = undefined', () => {
  expect(serverBackfill({ bootstrap_backfill: true })).toBe(true)
  expect(serverBackfill({ bootstrap_backfill: false })).toBe(false)
  for (const v of ['true', 1, 0, null, {}, []]) expect(serverBackfill({ bootstrap_backfill: v })).toBe(undefined)
  expect(serverBackfill({})).toBe(undefined)
  expect(serverBackfill(null)).toBe(undefined)
})

test('storedBackfill: on only when {on:true} is younger than 7 days; everything else is off', () => {
  const now = 1_800_000_000_000, at = Math.floor(now / 1000)
  expect(BACKFILL_FLAG_FILE).toBe('bootstrap-backfill.json')
  expect(storedBackfill(JSON.stringify({ on: true, at }), now)).toBe(true)
  expect(storedBackfill(JSON.stringify({ on: true, at: at - 6 * 86400 }), now)).toBe(true)
  expect(storedBackfill(JSON.stringify({ on: true, at: at - 8 * 86400 }), now)).toBe(false)
  expect(storedBackfill(JSON.stringify({ on: false, at }), now)).toBe(false)
  expect(storedBackfill(JSON.stringify({ on: 'true', at }), now)).toBe(false)
  expect(storedBackfill(JSON.stringify({ on: true }), now)).toBe(false)
  expect(storedBackfill('garbage', now)).toBe(false)
  expect(storedBackfill(undefined, now)).toBe(false)
})
