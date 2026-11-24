// Round 4 (C102) I/O: run the fixed update command through $.process behind the gates of lib/update.ts. Automatic only in a
// non-interactive session (session.start isInteractive === false); interactive sessions get the band action (ui/band.ts).
// Output: one text-free `auto_update` row (never the server's message or url, never the command output).
import { readJson, readText, rm, run, writePrivate } from './fs'
import { nowIso, relLog } from './log'
import { type Load, type Sess, ensure } from './state'
import { CLIENT_POLICY_FILE } from '../lib/cohort'
import { switchOff } from '../lib/switches'
import { IS_EXEC_SH, UPDATE_LOCK_SH } from '../lib/sh'
import { UPDATE_ARGS, UPDATE_LAUNCHER, UPDATE_LOCK, UPDATE_LOCK_STALE_MS, UPDATE_MS, UPDATE_STATE_FILE, updateBinaryCandidates, updateGate } from '../lib/update'

const inflight = new Set<Promise<unknown>>()  // ponytail: module-level (a reload drops them); the tests wait on it
export const flushUpdates = () => Promise.all([...inflight]).then(() => undefined)
function track<T>(p: Promise<T>): Promise<T> { inflight.add(p); p.catch(() => undefined).finally(() => inflight.delete(p)); return p }

// atomic mkdir; a lock older than UPDATE_LOCK_STALE_MS (a dead session) is removed and taken once
async function takeLock($: any, path: string): Promise<boolean> {
  const r = await run($, ['/bin/sh', '-c', UPDATE_LOCK_SH, 'sh', path], { timeoutMs: 5000 })
  if (r?.exitCode === 0) return true
  const st = await $.fs.stat(path).catch(() => null)
  if (!st || await $.clock.now() - st.mtimeMs <= UPDATE_LOCK_STALE_MS) return false
  await rm($, path)
  return (await run($, ['/bin/sh', '-c', UPDATE_LOCK_SH, 'sh', path], { timeoutMs: 5000 }))?.exitCode === 0
}

// 4b: the first candidate that exists, is no directory and is executable (stat + `test -x`: $.fs.stat has no mode bits); null = none
export async function resolveClaude($: any): Promise<string | null> {
  const env = { CLAUDE_CODE_EXECPATH: await $.env.get('CLAUDE_CODE_EXECPATH'), HOME: await $.env.get('HOME'), PATH: await $.env.get('PATH') }
  const exec = env.CLAUDE_CODE_EXECPATH?.trim()
  for (const p of updateBinaryCandidates(env)) {
    const st = await $.fs.stat(p).catch(() => null)
    if (!st || st.kind === 'dir' || st.kind === 'directory') continue
    if ((await run($, ['/bin/sh', '-c', IS_EXEC_SH, 'sh', p], { timeoutMs: 5000 }))?.exitCode !== 0) continue
    // round 5 F12: CLAUDE_CODE_EXECPATH may be node or another runtime: basename 'claude', or `<path> --version` names Claude Code
    if (p === exec && p.slice(p.lastIndexOf('/') + 1) !== 'claude') {
      const v = await run($, [p, '--version'], { timeoutMs: 5000 })
      if (!v || v.exitCode !== 0 || !/\(Claude Code\)/.test(String(v.stdout ?? ''))) continue
    }
    return p
  }
  return null
}

export type UpdateResult = { result: 'ok' | 'failed' | 'timeout' | 'skipped'; reason?: string; target?: string; exit?: number | null }
export async function runUpdate($: any, s: Sess, mode: 'auto' | 'click'): Promise<UpdateResult> {
  const version = s.clientId.slice(s.clientId.lastIndexOf('/') + 1), now = await $.clock.now()
  const g = updateGate({ optOut: switchOff(await $.env.get('ACE_AUTO_UPDATE')), policyText: await readText($, `${s.root}/${CLIENT_POLICY_FILE}`),
    version, nowMs: now, state: await readJson($, `${s.root}/${UPDATE_STATE_FILE}`), mode })
  const row = async (x: Record<string, unknown>) => relLog($, s, { timestamp: await nowIso($), event: 'auto_update', mode, installed: version, session_id: s.sessionId, ...x, source: 'mod' })
  if (!g.go) {
    if (g.why !== 'not_min') await row({ result: 'skipped', reason: g.why, target: g.target ?? null })
    return { result: 'skipped', reason: g.why, target: g.target }
  }
  const lock = `${s.root}/${UPDATE_LOCK}`
  if (!(await takeLock($, lock))) { await row({ result: 'skipped', reason: 'locked', target: g.target }); return { result: 'skipped', reason: 'locked', target: g.target } }
  // round 8 L1: the gate again, now under the lock (another session may have tried this target in between)
  const g2 = updateGate({ optOut: switchOff(await $.env.get('ACE_AUTO_UPDATE')), policyText: await readText($, `${s.root}/${CLIENT_POLICY_FILE}`),
    version, nowMs: now, state: await readJson($, `${s.root}/${UPDATE_STATE_FILE}`), mode })
  if (!g2.go) {
    await rm($, lock).catch(() => undefined)
    await row({ result: 'skipped', reason: g2.why, target: g2.target ?? g.target })
    return { result: 'skipped', reason: g2.why, target: g2.target ?? g.target }
  }
  // round 5 F10: our nonce in the lock, re-read right before the spawn (a stale takeover by another session replaces it)
  const owner = `${lock}/owner`, nonce = `${s.sessionId}:${now}:${Math.random().toString(36).slice(2)}`
  let mine = true
  try {
    await writePrivate($, owner, nonce)
    // the attempt counts BEFORE it runs: a crash or a kill mid-update never leads to a second try for this target
    await writePrivate($, `${s.root}/${UPDATE_STATE_FILE}`, JSON.stringify({ target: g.target, at: Math.floor(now / 1000), mode }))
    const bin = await resolveClaude($)
    if (!bin) {  // no retry: the attempt above already counts for this target
      await row({ result: 'failed', reason: 'no_binary', target: g.target, exit_code: null })
      return { result: 'failed', reason: 'no_binary', target: g.target, exit: null }
    }
    if ((await readText($, owner))?.trim() !== nonce) {  // ponytail: narrows the takeover race, a lock server would close it
      mine = false
      await row({ result: 'skipped', reason: 'lock_lost', target: g.target })
      return { result: 'skipped', reason: 'lock_lost', target: g.target }
    }
    const dir = bin.slice(0, bin.lastIndexOf('/')), path = String(await $.env.get('PATH') ?? '')
    const envPath = path ? `${dir}:${path}` : `${dir}:/usr/bin:/bin`
    if (mode === 'auto') {  // round 6: detached, never waited for (see UPDATE_LAUNCHER)
      const py = (await readText($, `${s.root}/python_path`))?.trim() || 'python3'
      const base = JSON.stringify({ event: 'auto_update_result', mode, installed: version, target: g.target, session_id: s.sessionId, source: 'mod' })
      const r = await run($, [py, '-I', '-c', UPDATE_LAUNCHER, envPath, `${s.logs}/ace-relevance.jsonl`, base, lock, nonce, String(UPDATE_MS / 1000),
        bin, ...UPDATE_ARGS], { timeoutMs: 5000 })
      const result = r?.exitCode === 0 ? 'started' : 'failed'
      if (result === 'started') mine = false  // round 8 L1: the watchdog holds the lock now and removes it when done
      await row({ result, target: g.target, ...(result === 'failed' ? { reason: 'launch_failed' } : {}) })
      return { result: result === 'started' ? 'ok' : 'failed', target: g.target, exit: null }
    }
    const t0 = await $.clock.now()
    // io/spawn.ts convention: a throw is the timeout kill, unless the binary is missing (ENOENT / not found)
    let r: any = null, thrown: 'timeout' | 'spawn_failed' | null = null
    // PATH carries the binary's folder first: the CLI may start node or helpers next to it
    try { r = await $.process.run([bin, ...UPDATE_ARGS], { timeoutMs: UPDATE_MS, env: { PATH: envPath } }) }
    catch (e) { thrown = /ENOENT|not found/i.test(String(e)) ? 'spawn_failed' : 'timeout' }
    const result = thrown === 'timeout' ? 'timeout' : thrown === null && r?.exitCode === 0 ? 'ok' : 'failed'
    await row({ result, target: g.target, exit_code: r?.exitCode ?? null, ms: Math.round(await $.clock.now() - t0), ...(thrown === 'spawn_failed' ? { reason: 'spawn_failed' } : {}) })
    return { result, target: g.target, exit: r?.exitCode ?? null }
  } finally { if (mine) await rm($, lock).catch(() => undefined) }  // a lost lock belongs to the other session now
}
// session.start: non-interactive only (claude -p, CI, SDK); never blocks the start.
export function autoUpdate($: any, L: Load) {
  if (L.interactive !== false || !L.sess) return
  void track(runUpdate($, L.sess, 'auto').catch(() => undefined))
}
// The band's 'Aktualisieren' press: the same command and gates (minus the daily / per-target limits: the press is the consent).
export async function clickUpdate($: any, L: Load) {
  const s = await ensure($, L)
  if (!s) return
  const r = await track(runUpdate($, s, 'click'))
  const msg = r.result === 'ok' ? `ACE auf ${r.target} aktualisiert; gilt ab dem nächsten Start (oder jetzt /reload-plugins)`
    : r.result === 'timeout' ? 'ACE-Update fehlgeschlagen (Zeitüberschreitung)'
    : r.result === 'failed' ? `ACE-Update fehlgeschlagen (exit ${r.exit ?? '?'})`
    : r.reason === 'locked' ? 'ACE-Update läuft bereits in einer anderen Session' : `ACE-Update nicht ausgeführt (${r.reason})`
  $.ui.toast(msg)
}
