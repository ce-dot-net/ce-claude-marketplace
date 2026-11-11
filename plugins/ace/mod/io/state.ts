// Session state through `$`: Sess resolution, per-load state (Load), the mod-active/mod-classic markers, the
// patterns-used / mod-tools / pending / deferral files (queued read-merge-write), cohort env and server switches.
import type { EventName, Hook } from 'claude-code'
import { readJson, readText, rm, writePrivate } from './fs.ts'
import { BACKFILL_FLAG_FILE, serverBackfill, CLIENT_POLICY_FILE, FEEDBACK_DOWNVOTE_FILE, RENDER_FULL_PCT_FILE, serverDownvote, serverFullPct, storedDownvote, storedFullPct, validClientPolicy } from '../lib/cohort.ts'
import { relLog } from './log.ts'
import { REJECTION_PREV_MAX_AGE_S, type ToolRec } from '../lib/evidence.ts'
import { num, pyDumps } from '../lib/pyjson.ts'
import { type StateUpdate, dataRootFromPluginRoot, mergeState, safeComponent as safe } from '../lib/state.ts'
import { type Ctx, type Env, type State, exportEnv, readEnv, resolveContext } from '../context/index.ts'
import { cliRun } from './cli.ts'

export const MARKER_REFRESH_MS = 60_000           // between handoffs; plugin_data_dir.MOD_AFTER_TOOL_S is 120 s, MOD_HANDOFF_S 15 s
export const MAX_TOOL_RECS = 1000                 // ponytail: the trace keeps the last 50 + failures anyway; older steps are lost past this
export type Sess = { sessionId: string; cwd: string; project: string; org?: string; root: string; pdir: string; sdir: string;
  logs: string; logRoot: string; minChars: number; extraPrefixes: string[]; clientId: string }
export const uuid = (): string => {
  const c: any = (globalThis as any).crypto
  if (c?.randomUUID) return c.randomUUID()
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, ch => {
    const r = Math.random() * 16 | 0; return (ch === 'x' ? r : (r & 3) | 8).toString(16)
  })
}
export async function dataRoot($: any) {
  return dataRootFromPluginRoot(await $.env.get('HOME') ?? '', $.plugin.root, $.plugin.name, await $.env.get('CLAUDE_CONFIG_DIR'))
}
// 8.1.0: the binding comes from the one core (context/), resolved once per load from the env as the session started
// (before the mod exported its own ids). Unbound, refused or invalid: no Sess, every hook steps aside.
export async function resolveContextOnce($: any, L: Load, cwd: string): Promise<Ctx> {
  if (L.ctx && L.ctxCwd === cwd) return L.ctx
  L.env0 ??= await readEnv($)
  L.ctx = await resolveContext($, cwd, L.env0, { dataRoot: await dataRoot($), cli: (argv, o) => cliRun($, null, argv, o) })
  L.ctxCwd = cwd
  return L.ctx
}
export async function resolveSession($: any, cwd: string, L?: Load): Promise<Sess | null> {
  const c: any = L ? await resolveContextOnce($, L, cwd) : await resolveContext($, cwd, await readEnv($), { dataRoot: await dataRoot($) })
  if (!c.bound) return null
  const project: string = c.projectId, org: string = c.orgId
  const root = await dataRoot($)
  const sessionId = await $.session.id()
  const pdir = `${root}/projects/${safe(project)}`
  const minRaw = Number(await $.env.get('ACE_MIN_PROMPT_CHARS'))
  const extra = String(await $.env.get('ACE_MACHINE_PROMPT_PREFIXES') ?? '').split(',').map(x => x.trim().toLowerCase()).filter(Boolean)
  const manifest = await readJson($, `${$.plugin.root}/.claude-plugin/plugin.json`)
  return { sessionId, cwd, project, org, root, pdir, sdir: `${pdir}/sessions/${safe(sessionId)}`, logs: `${c.root}/.claude/data/logs`, logRoot: c.root,
    minChars: Number.isFinite(minRaw) && minRaw > 0 ? minRaw : 12, extraPrefixes: extra,
    clientId: `claude-code-plugin/${manifest?.version ?? '0.0.0'}` }
}
// Per-load state, created in register (a reload starts over). What a learn needs is on disk: the F-080 state, the tool
// records, a mid-turn prompt. Lost on a reload: the Stop effort, title, in-flight claims, pending late searches.
export type Load = {
  sess: Sess | null
  env0: Env | undefined                         // the env as the session started (the core's input; never our own export)
  ctx: Ctx | undefined                          // the core's binding for ctxCwd
  ctxCwd: string | undefined
  ctxState: State | null | undefined            // verify's state; undefined = not checked yet
  ctxLogged: boolean                            // the one `context` row of this load
  verifying: Promise<unknown> | undefined
  pendingMain: string | null | undefined        // set by prompt.submit, bound to the next main turn.start
  pendingTitle: string | undefined              // classic.UserPromptSubmit answers it
  stopEffort: string | undefined                // classic.Stop's effort for the turn.complete learn
  domains: string[] | null
  turnAnchor: Map<string, string | null>        // main turnId -> tsid (null = machine turn)
  tools: Map<string, ToolRec[]>                 // write-through cache of mod-tools-<key>.json; key: 'main' or agentId
  spawnPrompts: Map<string, string>             // workflow agentId -> the prompt agent.spawn saw
  placeholders: Set<string>                     // spawn prompts proven to be a workflow's placeholder: no search for them
  late: Map<string, string>                     // agentId -> query: a run whose prompt no hook can rewrite gets its patterns at its first tool call
  agentTypes: Map<string, string>               // agents this load saw spawn (a turn.start of one without state is a wake)
  earlyStart: Map<string, string>               // agentId -> turn.start text, heard before its agent.spawn settled
  agentEffort: Map<string, string>              // classic.SubagentStop's effort for that agent's turn.complete
  lastClaim: Map<string, string>                // key -> newest claimed domain: only that one writes domain-last
  markerAt: number
  reuseUsed: Set<string>                         // §32: `${entry}\0${agent}` already served to that agent
  mainSeen: number                              // item 4: main tool.call events of the current task (diagnostic: tools_mismatch)
  compacted: boolean                             // item A: a main compaction ran; prompt.compose re-adds the patterns
  stopDefer: string[] | null                    // classic.Stop: background task types while delegated work runs (§16 P2)
  deferred: string | undefined                  // tsid of the main task whose learn waits for its delegated work
  handback: Map<string, string>                 // agentId -> last SubagentHandback message (§16 P1)
  claims: Set<string>                           // ponytail: in-process; the marker silences the Python hook, so no second process races this one
  queues: Map<string, Promise<unknown>>         // per state file: parallel hooks read-merge-write in turn
  interactive: boolean | undefined              // item 1a: session.start isInteractive (false: -p / SDK, no Haiku wait); undefined = unknown
  pendingLearns: Set<{ ctl: AbortController; flush: () => Promise<boolean> }>  // item 1b: self-evals session.end must not lose
}
export async function ensure($: any, L: Load): Promise<Sess | null> {
  if (L.sess && L.sess.sessionId === await $.session.id()) return L.sess
  L.sess = await resolveSession($, await $.session.root(), L)  // the session cwd can move to a subdir; the project cannot
  return L.sess
}
// 8.2.2: the conversation's origin fields, on disk under the CC session dir (never the task pin): a reload or resume
// keeps them, a /clear (new session id) starts over. Removed with the session dir at session.end.
export const originFile = (s: Sess) => `${s.sdir}/prompt-origin.json`
export async function notePrompt($: any, s: Sess, kind: string | undefined) {
  try {
    const o = await readJson($, originFile(s))
    const origin = typeof o?.origin === 'string' ? o.origin : kind || 'unclassified'  // the first ever seen, never overwritten
    const human = (num(o?.humanPrompts) ?? 0) + (kind === 'composer' || kind === 'bridge' ? 1 : 0)
    await writePrivate($, originFile(s), JSON.stringify({ origin, humanPrompts: human }))
  } catch { /* never break the prompt */ }
}
export async function readOrigin($: any, s: Sess): Promise<{ promptOrigin?: string; humanPromptCount?: number }> {
  const o = await readJson($, originFile(s))
  return typeof o?.origin === 'string' ? { promptOrigin: o.origin, humanPromptCount: num(o.humanPrompts) ?? 0 } : {}
}
// 8.2.3: the same two signals for the POST /patterns/search body (server: headless = interactive===false AND count 0/null).
// Each only when known, never defaulted: a failed origin read leaves the count out, it never turns into 0.
export type SearchOrigin = { interactive?: boolean; human_prompt_count?: number }
export async function searchOrigin($: any, L: Load, s: Sess): Promise<SearchOrigin> {
  const o: SearchOrigin = {}
  if (typeof L.interactive === 'boolean') o.interactive = L.interactive
  const n = (await readOrigin($, s).catch(() => ({} as { humanPromptCount?: number }))).humanPromptCount
  if (n !== undefined) o.human_prompt_count = n
  return o
}
export const stateFile = (s: Sess, key: string) => `${s.sdir}/patterns-used-${safe(key)}.json`
export async function disabled($: any, s: Sess) {
  return await $.fs.exists(`${s.sdir}/disabled.flag`) || await $.fs.exists(`${s.pdir}/disabled.flag`)
}
export function touchMarker($: any, L: Load, s: Sess, now: number) { L.markerAt = now; return $.fs.write(`${s.sdir}/mod-active`, String(now)) }
// classic.* hooks of a user mod do not run on seats where the built-in managed-settings guard (sec-default@builtin)
// is loaded (Team/Enterprise, managed settings): the mod still runs. Each classic.* event touches mod-classic; the
// Python Stop/SubagentStop step aside only while it is fresh (plugin_data_dir.mod_owns_learn), and the mod's turn.complete
// learns only then, so exactly one chain learns and the Python Stop keeps the background_tasks deferral + effort.
export async function touchClassic($: any, L: Load) {
  try {
    const s = await ensure($, L)
    if (s) await $.fs.write(`${s.sdir}/mod-classic`, String(await $.clock.now()))
  } catch { /* the Python Stop then learns itself */ }
}
export async function classicFresh($: any, s: Sess): Promise<boolean> {
  try {
    const st = await $.fs.stat(`${s.sdir}/mod-classic`)
    return (await $.clock.now()) - st.mtimeMs < 600_000
  } catch { return false }
}
// Between prompts: a long task must not wake the Python chain beside the mod. Never throws.
export async function refreshMarker($: any, L: Load, force = false) {
  try {
    const now = await $.clock.now()
    if (!force && now - L.markerAt < MARKER_REFRESH_MS) return
    L.markerAt = now  // first: no project means no marker, and no settings read per tool call either
    const s = await ensure($, L)
    if (s) await touchMarker($, L, s, now)
    if (L.ctx?.bound) await exportEnv($, L.ctx, now)  // keeps ACE_CONTEXT fresh for the Python chain
  } catch { /* the Python chain may wake; nothing is lost */ }
}
export function readState($: any, s: Sess, key: string) { return readJson($, stateFile(s, key)) }
export function enqueue<T>(L: Load, path: string, fn: () => Promise<T>): Promise<T> {
  const job = (L.queues.get(path) ?? Promise.resolve()).then(fn)
  L.queues.set(path, job.catch(() => undefined))
  return job
}
export function updateState($: any, L: Load, s: Sess, key: string, u: StateUpdate, reset = false) {
  const path = stateFile(s, key)
  return enqueue(L, path, async () => {
    const state = mergeState(reset ? undefined : await readJson($, path), u)
    await writePrivate($, path, pyDumps(state))
    return state
  })
}
export const toolsFile = (s: Sess, key: string) => `${s.sdir}/mod-tools-${safe(key)}.json`
export const pendingFile = (s: Sess) => `${s.sdir}/mod-pending-main.json`
export async function loadTools($: any, L: Load, s: Sess, key: string): Promise<ToolRec[]> {
  const cached = L.tools.get(key)
  if (cached) return cached
  try { return JSON.parse(await $.fs.read(toolsFile(s, key)) as string) } catch { return [] }
}
export function recordTool($: any, L: Load, s: Sess, key: string, rec: ToolRec) {
  return enqueue(L, toolsFile(s, key), async () => {
    const list = [...await loadTools($, L, s, key), rec].slice(-MAX_TOOL_RECS)
    L.tools.set(key, list)
    await writePrivate($, toolsFile(s, key), JSON.stringify(list))
  })
}
export function takeTools($: any, L: Load, s: Sess, key: string): Promise<ToolRec[]> {
  return enqueue(L, toolsFile(s, key), () => loadTools($, L, s, key))
}
export function clearTools($: any, L: Load, s: Sess, key: string) {
  return enqueue(L, toolsFile(s, key), async () => {
    L.tools.delete(key)
    if (await $.fs.exists(toolsFile(s, key))) await rm($, toolsFile(s, key))
  })
}
// Full share precedence (ace_pattern_render.full_pct_source): env if set > the server's render_full_pct (< 7 days) > 50.
export async function cohortEnv($: any, s: Sess) {
  let full: string | undefined = await $.env.get('ACE_RENDER_FULL_PCT')
  if (full === undefined) {
    const server = storedFullPct(await readText($, `${s.root}/${RENDER_FULL_PCT_FILE}`), await $.clock.now())
    if (server !== undefined) full = String(server)
  }
  return { ACE_AB_CONTROL_PCT: await $.env.get('ACE_AB_CONTROL_PCT'), ACE_AB_COMPACT_PCT: await $.env.get('ACE_AB_COMPACT_PCT'), ACE_RENDER_FULL_PCT: full }
}
// Every real search persists the valid server switches (latest wins; missing/invalid keeps the stored value):
// render_full_pct and feedback_downvote. A reuse-cache hit is older and never does.
export async function storeFullPct($: any, s: Sess, resp: any) {
  const pct = serverFullPct(resp), down = serverDownvote(resp), at = Math.floor(await $.clock.now() / 1000)
  try { if (pct !== undefined) await writePrivate($, `${s.root}/${RENDER_FULL_PCT_FILE}`, JSON.stringify({ pct, at })) } catch { /* keep the old value */ }
  try { if (down !== undefined) await writePrivate($, `${s.root}/${FEEDBACK_DOWNVOTE_FILE}`, JSON.stringify({ on: down, at })) } catch { /* keep the old value */ }
  const bf = serverBackfill(resp)
  try { if (bf !== undefined) await writePrivate($, `${s.root}/${BACKFILL_FLAG_FILE}`, JSON.stringify({ on: bf, at })) } catch { /* keep the old value */ }
  if (resp && typeof resp === 'object' && 'client_policy' in resp) {  // 8.1.4 (dormant): invalid -> dropped, reason logged
    const v = validClientPolicy(resp.client_policy)
    try {
      if ('policy' in v) await writePrivate($, `${s.root}/${CLIENT_POLICY_FILE}`, JSON.stringify({ policy: v.policy, at }))
      else await relLog($, s, { timestamp: new Date(at * 1000).toISOString(), event: 'client_policy_invalid', reason: v.why, source: 'mod' })
    } catch { /* keep the old value */ }
  }
}
export async function downvoteEnabled($: any, s: Sess): Promise<boolean> {
  const env = await $.env.get('ACE_FEEDBACK_DOWNVOTE')
  if (env === '1' || env === '0') return env === '1'
  return storedDownvote(await readText($, `${s.root}/${FEEDBACK_DOWNVOTE_FILE}`), await $.clock.now())
}
// At the next main trace: the pending downvote's ids, consumed once.
export async function takeDownvote($: any, s: Sess): Promise<number[] | undefined> {
  const f = `${s.sdir}/pending-downvote.json`, d = await readJson($, f)
  if (d === undefined) return undefined
  await rm($, f)
  const dAt = num(d?.at)
  return Array.isArray(d?.applied_log_ids) && d.applied_log_ids.length && dAt !== undefined && await $.clock.now() / 1000 - dAt < REJECTION_PREV_MAX_AGE_S ? d.applied_log_ids : undefined
}
// §16 P2: the deferral survives a mod reload on disk (tsid only).
export const deferFile = (s: Sess) => `${s.sdir}/learn-deferred`
export async function deferredAnchor($: any, L: Load, s: Sess): Promise<string | null> {
  const tsid = L.deferred ?? (await readText($, deferFile(s)))?.trim()
  return tsid && (await readState($, s, 'main'))?.task_session_id === tsid ? tsid : null
}
export async function clearDeferred($: any, L: Load, s: Sess) {
  L.deferred = undefined
  if (await $.fs.exists(deferFile(s))) await rm($, deferFile(s))
}

export type HookArgs<E extends EventName> = Parameters<Hook<E>>
// Per-load state, fresh in each register (a reload starts over).
export function newLoad(): Load {
  return { sess: null, env0: undefined, ctx: undefined, ctxCwd: undefined, ctxState: undefined, ctxLogged: false, verifying: undefined, pendingMain: undefined, pendingTitle: undefined, stopEffort: undefined, domains: null,
    turnAnchor: new Map(), tools: new Map(), spawnPrompts: new Map(), placeholders: new Set(), late: new Map(), agentTypes: new Map(),
    earlyStart: new Map(), agentEffort: new Map(), lastClaim: new Map(), markerAt: 0, claims: new Set(), queues: new Map(),
    stopDefer: null, deferred: undefined, handback: new Map(), reuseUsed: new Set(), compacted: false, mainSeen: 0,
    interactive: undefined, pendingLearns: new Set() }
}
