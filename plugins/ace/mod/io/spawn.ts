// Engine and ace-cli runner through `$`: search with pin/backoff/budgets, the §32 local reuse cache, git context.
import { run, writePrivate } from './fs.ts'
import { type Load, type Sess, storeFullPct } from './state.ts'
import { pyDumps, pyLoads, sanitize } from '../lib/pyjson.ts'
import { REUSE_TTL_MS, reuseEnabled, reuseKey } from '../lib/state.ts'
import { parseDiffStat } from '../lib/trace.ts'

export const SEARCH_MS = 25000, DOMAIN_MS = 17000 // §11 A2: blocking budget per search, retry included
export const PIN_SHARE = 0.6                      // of a search budget, for the pinned attempt
export const LAUNCHER_MS = 15_000                 // a loaded machine must not get a live learn's lock and trace removed
export function aceEnv(s: Sess): Record<string, string> {
  const env: Record<string, string> = { ACE_PROJECT_ID: s.project, ACE_CLIENT_ID: s.clientId }
  if (s.org) env.ACE_ORG_ID = s.org
  return env
}
// 8.1.0: --org/--project on every CLI spawn, after the subcommand: the CLI never picks its own binding (4.3.4 reads settings.json).
export const ids = (s: Sess): string[] => [...(s.org ? ['--org', s.org] : []), '--project', s.project]
export const isAuthFailure = (t: string) => /unauthorized|401|not logged in|no api token|token_expired/i.test(t)
// §17/§23: the same order as ace_cli.cli_argv: the plugin-local pinned CLI, else the global `ace-cli` on PATH.
export async function cliHead($: any): Promise<string[]> {
  const js = `${$.plugin.root}/node_modules/@ace-sdk/cli/dist/cli.js`
  return await $.fs.exists(js).catch(() => false) ? ['node', js] : ['ace-cli']
}
// §14: the in-process engine (shared with ace_engine.py); its own gate exits 3 when the core is unusable. ACE_ENGINE=cli opts out.
export async function engineScript($: any, name: string): Promise<string | null> {
  if (String(await $.env.get('ACE_ENGINE') ?? '').toLowerCase() === 'cli') return null
  const p = `${$.plugin.root}/engine/${name}`
  return await $.fs.exists(p).catch(() => false) ? p : null
}
// One engine search: { resp } or { why } (fall back to ace-cli), or { timeout } (no fallback, as ace_cli._search_lib).
export async function engineSearch($: any, s: Sess, script: string, query: string, sid: string | undefined, topK: number | undefined, budgetMs: number) {
  const payload: any = { query, org: s.org, project: s.project, session_id: sid, top_k: topK }
  for (const k of Object.keys(payload)) if (!payload[k]) delete payload[k]
  let r: any
  try { r = await $.process.run(['node', script], { stdin: JSON.stringify(payload), env: aceEnv(s), timeoutMs: budgetMs }) }
  catch (err) { return /ENOENT|not found/i.test(String(err)) ? { why: 'spawn failed: ' + String(err).slice(0, 200) } : { timeout: true } }
  if (r.exitCode === 0) {
    const out = String(r.stdout ?? '').trim()
    for (const text of [out, out.split('\n').pop() ?? '']) {  // a core log line before the JSON (8.1.0 audit): the last line
      try { const resp = sanitize(pyLoads(text)); if (resp && Array.isArray(resp.similar_patterns)) return { resp } } catch { /* next */ }
    }
    return { why: 'unexpected output (no similar_patterns list)' }
  }
  return { why: `exit ${r.exitCode}: ${String(r.stderr).trim().slice(0, 200)}` }
}
// ace_cli.run_search + §11 A1: while pin-backoff is young no pin at all; a locked/empty pinned search is re-run ONCE
// without the pin, only within what is left of the blocking budget. Every CLI spawn carries --session-id <task session>
// (cli >= 4.3.1: request field, no sessions.db; capped at 512): `sid` defaults to the pin, domain shift passes it unpinned;
// the engine stdin carries the same `sid` as session_id.
export async function search($: any, s: Sess, query: string, pin: string | undefined, topK: number | undefined, budgetMs: number, sid: string | undefined = pin) {
  const t0 = await $.clock.now()
  let engineWhy: string | undefined = 'no engine'
  const eng = await engineScript($, 'search.js')
  if (eng) {
    const e = await engineSearch($, s, eng, query, sid, topK, budgetMs)  // engine never pins: session_id is the task stamp
    const ms = await $.clock.now() - t0
    if ('resp' in e) await storeFullPct($, s, e.resp)
    if ('resp' in e) return { resp: e.resp, error: undefined, ms, pinFailed: false, pinSkipped: undefined, pinMs: undefined, stderr: '', engine: 'lib', engineWhy: 'ok' }
    if ('timeout' in e) return { resp: null, error: 'timeout', ms, pinFailed: false, pinSkipped: undefined, pinMs: undefined, stderr: '', engine: 'lib', engineWhy: 'timeout' }
    engineWhy = 'lib failed: ' + e.why
    budgetMs -= ms
    if (budgetMs < 2000) return { resp: null, error: 'timeout', ms, pinFailed: false, pinSkipped: undefined, pinMs: undefined, stderr: e.why.slice(0, 300), engine: 'lib', engineWhy }
  }
  const t1 = await $.clock.now()
  const head = await cliHead($)
  const backoffPath = `${s.root}/pin-backoff`
  let usePin = pin, pinSkipped: string | undefined, pinFailed = false
  if (usePin) {
    const min = Number(await $.env.get('ACE_PIN_BACKOFF_MIN'))
    const age = await $.fs.stat(backoffPath).then((st: any) => t1 - st.mtimeMs, () => Infinity)
    if (age < (Number.isFinite(min) && min > 0 ? min : 5) * 60_000) { usePin = undefined; pinSkipped = 'backoff' }  // 5 min since SDK 4.3.0 (sessions.db index); server team agreed
  }
  const spawn = async (p: string | undefined, timeoutMs: number) => {
    const argv = [...head, 'search', '--stdin', '--json', ...(p ? ['--pin-session', p] : []), ...(sid ? ['--session-id', sid.slice(0, 512)] : []), ...(topK ? ['--top-k', String(topK)] : []), ...ids(s)]
    try { return { ...(await $.process.run(argv, { stdin: query, env: aceEnv(s), timeoutMs })), threw: '' } }
    catch (err) { return { exitCode: -1, stdout: '', stderr: String(err), threw: String(err) } }
  }
  // A pin stuck on the sqlite lock hangs until killed (live: > 25 s), so it only gets a share of the budget:
  // the unpinned re-run must still fit. A killed unpinned search has no time left, so no retry.
  let r: any = await spawn(usePin, usePin ? Math.floor(budgetMs * PIN_SHARE) : budgetMs)
  const cliMissing = /ENOENT|not found/i.test(r.threw)
  const killed = !!r.threw && !cliMissing
  const locked = /database is locked/i.test(r.stderr)
  const killedPin = !!usePin && killed
  const pinMs = usePin ? await $.clock.now() - t1 : undefined   // data for PIN_SHARE (live: 11.9 s, p7: 27-37 s under load)
  if (usePin && locked) await $.fs.write(backoffPath, '')   // only the sticky lock suspends pins globally (p2/p6)
  if (usePin && !cliMissing && (locked || killed || (!r.stdout.trim() && !isAuthFailure(r.stderr)))) {
    pinFailed = true
    const left = budgetMs - (await $.clock.now() - t1)
    if (left >= 2000) r = await spawn(undefined, left) // A2: never overrun the hook budget with a floored retry
  }
  let resp: any = null, error: string | undefined
  if (r.threw) error = /ENOENT|not found/i.test(r.threw) ? 'cli_not_found' : 'timeout'
  else if (r.exitCode !== 0) error = isAuthFailure(r.stderr + r.stdout) ? 'not_authenticated' : /timed? ?out/i.test(r.stderr) ? 'timeout' : 'nonzero_exit'
  else { try { resp = sanitize(pyLoads(r.stdout)) } catch { error = 'json_parse_failed' } }
  if (resp && resp.error) { error = String(resp.error); resp = null }
  if (resp) await storeFullPct($, s, resp)
  // A kill alone may be a slow server. Only a re-run that then answers in less time than the pin was given points
  // at the pin. ponytail: server latency varies, so a false 30-min backoff is possible; a lock probe would need the sqlite path.
  if (killedPin && !r.threw && r.exitCode === 0) await $.fs.write(backoffPath, '')
  return { resp, error, ms: await $.clock.now() - t0, pinFailed, pinSkipped, pinMs, stderr: String(r.stderr).slice(0, 300), engine: 'cli', engineWhy }
}
// DESIGN §32: hybrid local reuse of ace_search_cache (domain-shift + SubagentStart only; the main prompt search never reads it).
// A hit = same project, exact normalized query, < 15 min, >= 1 pattern, not yet served to this agent. Server results refresh it.
export const realResp = (r: any) => !!r && !r.error && Array.isArray(r.similar_patterns) && r.similar_patterns.length > 0
export async function reuseGet($: any, L: Load, s: Sess, kind: string, query: string, agent: string): Promise<any | null> {
  try {
    if (!reuseEnabled(await $.env.get('ACE_LOCAL_REUSE'), kind)) return null
    const key = reuseKey(s.project, kind, query), path = `${s.root}/cache/search/${key}.json`
    if (L.reuseUsed.has(`${key}\0${agent}`)) return null
    const st = await $.fs.stat(path)
    if (await $.clock.now() - st.mtimeMs > REUSE_TTL_MS) return null
    const resp = sanitize(pyLoads(await $.fs.read(path) as string))
    if (!realResp(resp)) return null
    L.reuseUsed.add(`${key}\0${agent}`)
    return resp
  } catch { return null }
}
export async function reuseStore($: any, L: Load, s: Sess, kind: string, query: string, agent: string, resp: any) {
  try {
    if (!realResp(resp) || !reuseEnabled(await $.env.get('ACE_LOCAL_REUSE'), kind)) return
    const key = reuseKey(s.project, kind, query)
    await writePrivate($, `${s.root}/cache/search/${key}.json`, pyDumps(resp))
    for (const u of [...L.reuseUsed]) if (u.startsWith(key + '\0')) L.reuseUsed.delete(u)  // a refresh starts a new use-cycle
    L.reuseUsed.add(`${key}\0${agent}`)
  } catch { /* the cache is an optimisation */ }
}
export const hitResult = (resp: any) => ({ resp, error: undefined, ms: 0, pinFailed: false, pinSkipped: undefined, pinMs: undefined, stderr: '', engine: 'cache', engineWhy: 'cache_hit' })
export async function gitContext($: any, cwd: string) {
  const git = async (...a: string[]) => run($, ['git', ...a], { cwd })
  const inside = await git('rev-parse', '--is-inside-work-tree')
  if (!inside || inside.exitCode !== 0) return undefined
  const [hash, msg, name, mail, ts, branch, stat] = await Promise.all([git('rev-parse', 'HEAD'), git('log', '-1', '--format=%s'),
    git('log', '-1', '--format=%an'), git('log', '-1', '--format=%ae'), git('log', '-1', '--format=%aI'),
    git('rev-parse', '--abbrev-ref', 'HEAD'), git('diff', '--stat', 'HEAD~1..HEAD')])
  const out = (r: any) => (r && r.exitCode === 0 ? String(r.stdout).trim() : undefined)
  const commit = out(hash)
  if (!commit) return undefined
  let names = await git('diff', '--name-only', `${commit}~1`, commit)
  if (!names || names.exitCode !== 0) names = await git('show', '--name-only', '--format=', commit)
  const ctx: any = { commit_hash: commit }
  const set = (k: string, v: string | undefined) => { if (v !== undefined) ctx[k] = v }
  set('commit_message', out(msg)); set('author', out(name)); set('author_email', out(mail)); set('timestamp', out(ts)); set('branch', out(branch))
  Object.assign(ctx, parseDiffStat(out(stat) ?? ''))
  ctx.files_changed = (out(names) ?? '').split('\n').filter(Boolean)
  return ctx
}
