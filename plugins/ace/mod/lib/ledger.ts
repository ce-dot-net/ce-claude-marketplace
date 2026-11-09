// 8.2.0 backfill ledger (pure, unwired, network-free): remembers which `bootstrap:<32 hex>` task keys were already sent, so a
// rerun sends nothing twice and an aborted run resumes. Strings in, strings out: the caller does the I/O and owns the secret
// (the per-install random key, same idea as ace_trace_queue's queue.key: one local HMAC key, never in the repo or the file).
// Line format: v1 TAB key TAB status TAB atMs TAB attempts TAB hmac. A line with a bad/missing signature is dropped and counted.
import { sha256Hex } from './cohort.ts'

export type Status = 'sent' | 'failed' | 'skipped' | 'skipped-failed'
export type Entry = { status: Status, atMs: number, attempts: number }
export type Ledger = { entries: Map<string, Entry>, dropped: number }

export const MAX_KEYS = 50000
export const MAX_ATTEMPTS = 3
const MAX_LINES = MAX_KEYS * 2   // bound on lines examined per parse, duplicates included
const MAX_LINE = 300
const KEY_RE = /^bootstrap:[0-9a-f]{32}$/
const STATUSES = new Set(['sent', 'failed', 'skipped', 'skipped-failed'])
const TERMINAL = new Set(['sent', 'skipped', 'skipped-failed'])

export const emptyLedger = (): Ledger => ({ entries: new Map(), dropped: 0 })
export const has = (l: Ledger, key: string) => l.entries.has(key)
export const statusOf = (l: Ledger, key: string): Status | undefined => l.entries.get(key)?.status

// HMAC-SHA256 on top of the string-only sha256Hex. The mod's sha takes text (UTF-8), not raw bytes, so the pads and the inner
// digest are fed as hex text: the standard nested HMAC shape, not byte-identical to RFC 2104 (nothing else verifies this file).
const hex = (c: number) => c.toString(16).padStart(2, '0')
function hmac(secret: string, msg: string): string {
  const k = sha256Hex(secret).padEnd(128, '0') // 64 hex chars -> 64 chars; always one block of key material
  const pad = (x: number) => Array.from(k.slice(0, 64), ch => hex(ch.charCodeAt(0) ^ x)).join('')
  return sha256Hex(pad(0x5c) + sha256Hex(pad(0x36) + msg))
}
function sameSig(a: string, b: string): boolean { // constant time over equal-length text
  if (a.length !== b.length) return false
  let d = 0
  for (let i = 0; i < a.length; i++) d |= a.charCodeAt(i) ^ b.charCodeAt(i)
  return d === 0
}

const validAt = (n: unknown): n is number => typeof n === 'number' && Number.isSafeInteger(n) && n >= 0

// sent is never downgraded; otherwise the later write wins. Returns false when refused (full ledger: new keys only).
function put(l: Ledger, key: string, e: Entry): boolean {
  const cur = l.entries.get(key)
  if (!cur && l.entries.size >= MAX_KEYS) return false
  if (cur?.status === 'sent') return e.status === 'sent' ? (l.entries.set(key, e), true) : true
  l.entries.set(key, e)
  return true
}

// Mutates and returns false on a bad key/status/time or a full ledger (fail-closed), true otherwise. failed counts attempts;
// the MAX_ATTEMPTS-th failure becomes skipped-failed.
export function add(l: Ledger, key: string, status: 'sent' | 'failed' | 'skipped', atMs: number): boolean {
  if (typeof key !== 'string' || !KEY_RE.test(key) || !validAt(atMs)) return false
  if (status !== 'sent' && status !== 'failed' && status !== 'skipped') return false
  const prev = l.entries.get(key)
  if (status !== 'failed') return put(l, key, { status, atMs, attempts: prev?.attempts ?? 0 })
  const attempts = Math.min((prev?.attempts ?? 0) + 1, MAX_ATTEMPTS)
  return put(l, key, { status: attempts >= MAX_ATTEMPTS ? 'skipped-failed' : 'failed', atMs, attempts })
}

export const pending = (l: Ledger, keys: string[]): string[] =>
  keys.filter(k => typeof k === 'string' && KEY_RE.test(k) && !TERMINAL.has(l.entries.get(k)?.status ?? ''))

const body = (key: string, e: Entry) => `v1\t${key}\t${e.status}\t${e.atMs}\t${e.attempts}`

export function serialize(l: Ledger, secret: string): string {
  let out = ''
  for (const [k, e] of l.entries) out += `${body(k, e)}\t${hmac(secret, body(k, e))}\n`
  return out
}

// Never throws. Bad/unsigned/garbage lines are counted in `dropped`; a ledger that would pass MAX_KEYS stops growing.
export function parse(text: string, secret: string): Ledger {
  const l = emptyLedger()
  if (typeof text !== 'string') return l
  let seen = 0, pos = 0
  while (pos < text.length) {
    let nl = text.indexOf('\n', pos)
    if (nl < 0) nl = text.length
    const line = text.slice(pos, Math.min(nl, pos + MAX_LINE + 1)), over = nl - pos > MAX_LINE
    pos = nl + 1
    if (line.trim() === '') continue
    if (++seen > MAX_LINES) { l.dropped++; break }
    const f = line.split('\t')
    if (over || f.length !== 6 || f[0] !== 'v1' || !KEY_RE.test(f[1]) || !STATUSES.has(f[2]) || !/^\d{1,15}$/.test(f[3]) || !/^[0-3]$/.test(f[4])) { l.dropped++; continue }
    const e: Entry = { status: f[2] as Status, atMs: Number(f[3]), attempts: Number(f[4]) }
    if (!sameSig(f[5], hmac(secret, body(f[1], e)))) { l.dropped++; continue }
    if (!put(l, f[1], e)) l.dropped++
  }
  return l
}
