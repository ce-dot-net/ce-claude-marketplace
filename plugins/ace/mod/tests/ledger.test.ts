// 8.2.0 backfill ledger (pure, unwired): which bootstrap task keys were already sent. Strings in, strings out; no I/O.
import { expect, test } from 'claude-code/testing'
import { add, emptyLedger, has, MAX_ATTEMPTS, MAX_KEYS, parse, pending, serialize, statusOf } from '../lib/ledger.ts'

const K = (n: number) => 'bootstrap:' + n.toString(16).padStart(32, '0')
const S = 'per-install-secret'

test('round trip keeps keys, statuses and attempts', () => {
  let l = emptyLedger()
  add(l, K(1), 'sent', 10); add(l, K(2), 'failed', 20); add(l, K(3), 'skipped', 30)
  const p = parse(serialize(l, S), S)
  expect(p.dropped).toBe(0)
  expect(statusOf(p, K(1))).toBe('sent')
  expect(statusOf(p, K(2))).toBe('failed')
  expect(statusOf(p, K(3))).toBe('skipped')
  expect(has(p, K(4))).toBe(false)
  expect(serialize(p, S)).toBe(serialize(l, S))
})

test('a tampered line is dropped and counted, the rest survives', () => {
  let l = emptyLedger()
  add(l, K(1), 'failed', 10); add(l, K(2), 'sent', 20)
  const lines = serialize(l, S).split('\n').filter(Boolean)
  const forged = lines[0].replace('failed', 'sent')
  const p = parse([forged, lines[1]].join('\n') + '\n', S)
  expect(p.dropped).toBe(1)
  expect(has(p, K(1))).toBe(false)
  expect(statusOf(p, K(2))).toBe('sent')
})

test('a missing signature is dropped', () => {
  const p = parse(`v1\t${K(1)}\tsent\t1\t0\n`, S)
  expect(p.dropped).toBe(1)
  expect(has(p, K(1))).toBe(false)
})

test('the wrong secret drops every line', () => {
  let l = emptyLedger()
  for (let i = 0; i < 5; i++) add(l, K(i), 'sent', i)
  const p = parse(serialize(l, S), 'other-secret')
  expect(p.dropped).toBe(5)
  expect(p.entries.size).toBe(0)
})

test('a truncated last line is dropped, earlier lines survive', () => {
  let l = emptyLedger()
  add(l, K(1), 'sent', 1); add(l, K(2), 'sent', 2)
  const t = serialize(l, S)
  const p = parse(t.slice(0, t.length - 12), S)
  expect(statusOf(p, K(1))).toBe('sent')
  expect(has(p, K(2))).toBe(false)
  expect(p.dropped).toBe(1)
})

test('garbage, blank and binary-ish lines never throw', () => {
  const p = parse('\n\n???\n\u0000\u0001\n' + 'x'.repeat(100000) + '\n\t\t\t\t\t\n', S)
  expect(p.entries.size).toBe(0)
  expect(parse(undefined as any, S).entries.size).toBe(0)
  expect(parse('v1\tbootstrap:zz\tsent\t1\t0\tabc', S).dropped).toBe(1)
})

test('duplicate lines: last write wins per key', () => {
  let a = emptyLedger(); add(a, K(1), 'failed', 10)
  let b = emptyLedger(); add(b, K(1), 'skipped', 20)
  const p = parse(serialize(a, S) + serialize(b, S), S)
  expect(p.entries.size).toBe(1)
  expect(statusOf(p, K(1))).toBe('skipped')
})

test('sent is never downgraded, in add or in parse', () => {
  const l = emptyLedger()
  add(l, K(1), 'sent', 10)
  add(l, K(1), 'failed', 20); add(l, K(1), 'skipped', 30)
  expect(statusOf(l, K(1))).toBe('sent')
  let a = emptyLedger(); add(a, K(2), 'sent', 1)
  let b = emptyLedger(); add(b, K(2), 'failed', 2)
  expect(statusOf(parse(serialize(a, S) + serialize(b, S), S), K(2))).toBe('sent')
  expect(statusOf(parse(serialize(b, S) + serialize(a, S), S), K(2))).toBe('sent')
})

test('failed is retried up to the cap, then skipped-failed and no longer pending', () => {
  const l = emptyLedger()
  for (let i = 1; i < MAX_ATTEMPTS; i++) {
    add(l, K(1), 'failed', i)
    expect(statusOf(l, K(1))).toBe('failed')
    expect(pending(l, [K(1)])).toEqual([K(1)])
  }
  add(l, K(1), 'failed', 99)
  expect(statusOf(l, K(1))).toBe('skipped-failed')
  expect(pending(l, [K(1)])).toEqual([])
  expect(statusOf(parse(serialize(l, S), S), K(1))).toBe('skipped-failed')
})

test('bad keys are rejected and never serialized', () => {
  const l = emptyLedger()
  for (const k of ['', 'bootstrap:abc', K(1).toUpperCase(), K(1) + '0', 'x' + K(1), K(1) + '\n', 'bootstrap:' + 'g'.repeat(32), 5 as any, null as any])
    expect(add(l, k, 'sent', 1)).toBe(false)
  expect(l.entries.size).toBe(0)
  expect(add(l, K(1), 'bogus' as any, 1)).toBe(false)
  expect(add(l, K(1), 'sent', NaN)).toBe(false)
  expect(add(l, K(1), 'sent', 1)).toBe(true)
})

test('pending keeps order, drops sent/skipped, keeps unknown and failed, ignores bad keys', () => {
  const l = emptyLedger()
  add(l, K(1), 'sent', 1); add(l, K(2), 'skipped', 1); add(l, K(3), 'failed', 1)
  expect(pending(l, [K(4), K(1), K(3), K(2), 'junk', K(5)])).toEqual([K(4), K(3), K(5)])
  expect(pending(l, [])).toEqual([])
})

test('size cap: new keys beyond it are refused, existing keys still update', () => {
  const l = emptyLedger()
  for (let i = 0; i < MAX_KEYS; i++) l.entries.set(K(i), { status: 'failed', atMs: 1, attempts: 1 })
  expect(add(l, K(MAX_KEYS), 'sent', 1)).toBe(false)
  expect(has(l, K(MAX_KEYS))).toBe(false)
  expect(add(l, K(0), 'sent', 2)).toBe(true)
  expect(l.entries.size).toBe(MAX_KEYS)
})

test('huge input stays bounded and fast', () => {
  const l = emptyLedger()
  for (let i = 0; i < 1000; i++) add(l, K(i), 'sent', i)
  const good = serialize(l, S)
  // far more lines than the line bound allows: parse stops there, never grows without limit; cheap shape checks run before any hash
  const junk = ('v1\t' + K(1) + '\tbogus\t1\t0\tsig\n').repeat(MAX_KEYS * 3)
  const t0 = Date.now()
  const p = parse(good + junk, S)
  expect(p.entries.size).toBe(1000)
  expect(p.entries.size <= MAX_KEYS).toBe(true)
  expect(p.dropped > 0).toBe(true)
  expect(parse('a'.repeat(5_000_000), S).entries.size).toBe(0)
  expect(Date.now() - t0 < 4000).toBe(true)
})
