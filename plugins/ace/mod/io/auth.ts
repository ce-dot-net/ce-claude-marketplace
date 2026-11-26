// The auth guard (8.4.0; 8.4.1: a leaf module, so handlers/context.ts and io/spawn.ts both import it without a cycle).
// After an auth failure no engine / ace-cli call (search, learn, bootstrap, backfill) until the global token file changes,
// AUTH_HOLD_MS pass, the session-start status says ok or a search answers. <root>/auth-rejected = sha256 of that file
// (never the token); released = 'ok' (the file stays: its mtime is the barrier for older dead/ entries). Python twin:
// ace_cli._auth_held / _hold_auth (no time bound and no release there: the Python chain stays held until the token file changes).
import { sha256Hex } from '../lib/cohort'
import { run, writePrivate } from './fs'

export const AUTH_HOLD_MS = 30 * 60_000  // self-heal: a wrongly rejected token is retried once after this (a new 401 holds again)
export const RELOGIN_MARGIN_MS = 60_000  // a dead/ auth entry within this of a token-file write may be the OLD token's learn child
export const DEAD_HEAD_BYTES = 1024      // last_error is the 5th key of a queue entry: the head of the file is enough
// stderr only, never stdout (pattern text may say anything); 401 as a whole number only (not a UUID or 0.7401)
export const isAuthFailure = (stderr: string) => /unauthorized|\b401\b|not logged in|no api token|token_expired|session expired|log in again|ace-cli login/i.test(stderr)
type Root = { root: string }
async function cfgPath($: any): Promise<string> {
  const x = await $.env.get('XDG_CONFIG_HOME')
  return await $.env.get('ACE_CONFIG_PATH') || `${x || `${await $.env.get('HOME') ?? ''}/.config`}/ace/config.json`
}
async function authFp($: any): Promise<string> {
  try { return sha256Hex(String(await $.fs.read(await cfgPath($)))) } catch { return 'none' }
}
async function mtimeOf($: any, p: string): Promise<number | undefined> {
  try { return (await $.fs.stat(p))?.mtimeMs } catch { return undefined }
}
// the hold's mtime while held, else undefined (prompt.ts keys its once-per-hold notice to it)
export async function heldSince($: any, s: Root): Promise<number | undefined> {
  try {
    const m = `${s.root}/auth-rejected`
    if (String(await $.fs.read(m)).trim() !== await authFp($)) return undefined
    const at = await mtimeOf($, m), now = await $.clock.now()
    return at !== undefined && at <= now && now - at < AUTH_HOLD_MS ? at : undefined  // no stat / a future mtime: expired
  } catch { return undefined }
}
export async function authHeld($: any, s: Root): Promise<boolean> { return (await heldSince($, s)) !== undefined }
export async function holdAuth($: any, s: Root) { try { await writePrivate($, `${s.root}/auth-rejected`, await authFp($)) } catch { /* the guard is an optimisation */ } }
// a working token (status ok, a search answered): release, only when a hold marker is there (one read per call otherwise)
export async function releaseAuth($: any, s: Root) {
  try {
    const m = `${s.root}/auth-rejected`
    if (String(await $.fs.read(m)).trim() !== 'ok') await writePrivate($, m, 'ok')
  } catch { /* no marker: nothing held */ }
}

// 8.4.1: the detached learn child classifies a 401 as a dead/ queue entry with last_error 'auth' (ace_trace_queue.py). An entry
// newer than the token file + RELOGIN_MARGIN_MS and newer than the marker (each entry holds at most once) holds the token.
// seen.deadSeen = the newest entry mtime already looked at in this load: nothing is read twice. ponytail: the 20 newest of the
// last AUTH_HOLD_MS, DEAD_HEAD_BYTES each (a 5 MB entry is never read whole).
export async function noteDeadAuth($: any, s: Root, seen: { deadSeen?: number }): Promise<void> {
  try {
    const dir = `${s.root}/trace-queue/dead`, now = await $.clock.now()
    const cfg = await mtimeOf($, await cfgPath($)), mark = await mtimeOf($, `${s.root}/auth-rejected`)
    const after = Math.max(cfg === undefined ? 0 : cfg + RELOGIN_MARGIN_MS, mark === undefined ? 0 : mark + 1, (seen.deadSeen ?? -1) + 1)
    const list: any[] = await $.fs.list(dir).catch(() => [])
    const recent = list.filter(f => String(f.name).endsWith('.json') && !f.isLink && f.mtimeMs >= after && now - f.mtimeMs < AUTH_HOLD_MS)
      .sort((a, b) => b.mtimeMs - a.mtimeMs).slice(0, 20)
    let auth = false
    for (const f of recent) {
      const r = await run($, ['head', '-c', String(DEAD_HEAD_BYTES), `${dir}/${f.name}`], { timeoutMs: 2000 })
      if (r && r.exitCode === 0 && /"last_error"\s*:\s*"auth"/.test(String(r.stdout ?? ''))) { auth = true; break }
    }
    if (auth) await holdAuth($, s)
    // 8.4.2: moved only after the reads (and the hold): a concurrent learn scanning meanwhile reads the same entries, never skips them
    if (recent.length) seen.deadSeen = Math.max(seen.deadSeen ?? 0, recent[0].mtimeMs)
  } catch { /* the guard is an optimisation */ }
}
