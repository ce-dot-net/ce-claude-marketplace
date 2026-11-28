// Render cohort (salted sha256 bucket), trace variant label, server switches (render_full_pct, feedback_downvote).
// Pure: no `$`, no I/O.

// ---------- render_cohort (salt "render:", same bucket as ace_pattern_render) ----------
export function sha256Hex(text: string): string {
  const bytes: number[] = []
  for (const ch of text) { // UTF-8
    const c = ch.codePointAt(0)!
    if (c < 0x80) bytes.push(c)
    else if (c < 0x800) bytes.push(0xc0 | c >> 6, 0x80 | c & 63)
    else if (c < 0x10000) bytes.push(0xe0 | c >> 12, 0x80 | c >> 6 & 63, 0x80 | c & 63)
    else bytes.push(0xf0 | c >> 18, 0x80 | c >> 12 & 63, 0x80 | c >> 6 & 63, 0x80 | c & 63)
  }
  const K: number[] = [], H: number[] = []
  const frac = (x: number) => ((x - Math.floor(x)) * 2 ** 32) | 0
  for (let p = 2, n = 0; n < 64; p++) {
    let prime = true
    for (let d = 2; d * d <= p; d++) if (p % d === 0) { prime = false; break }
    if (!prime) continue
    if (n < 8) H.push(frac(Math.sqrt(p)))
    K.push(frac(Math.cbrt(p))); n++
  }
  const len = bytes.length
  bytes.push(0x80)
  while (bytes.length % 64 !== 56) bytes.push(0)
  for (let i = 7; i >= 0; i--) bytes.push(i >= 4 ? 0 : (len * 8) >>> (i * 8) & 255)
  const rr = (x: number, n: number) => (x >>> n) | (x << (32 - n))
  for (let o = 0; o < bytes.length; o += 64) {
    const w: number[] = []
    for (let i = 0; i < 64; i++) {
      if (i < 16) w[i] = bytes[o + 4 * i]! << 24 | bytes[o + 4 * i + 1]! << 16 | bytes[o + 4 * i + 2]! << 8 | bytes[o + 4 * i + 3]!
      else {
        const a = w[i - 15]!, b = w[i - 2]!
        w[i] = (w[i - 16]! + (rr(a, 7) ^ rr(a, 18) ^ a >>> 3) + w[i - 7]! + (rr(b, 17) ^ rr(b, 19) ^ b >>> 10)) | 0
      }
    }
    let [a, b, c, d, e, f, g, h] = H as [number, number, number, number, number, number, number, number]
    for (let i = 0; i < 64; i++) {
      const t1 = (h + (rr(e, 6) ^ rr(e, 11) ^ rr(e, 25)) + ((e & f) ^ (~e & g)) + K[i]! + w[i]!) | 0
      const t2 = ((rr(a, 2) ^ rr(a, 13) ^ rr(a, 22)) + ((a & b) ^ (a & c) ^ (b & c))) | 0
      h = g; g = f; f = e; e = (d + t1) | 0; d = c; c = b; b = a; a = (t1 + t2) | 0
    }
    ;[a, b, c, d, e, f, g, h].forEach((v, i) => { H[i] = (H[i]! + v) | 0 })
  }
  return H.map(v => (v >>> 0).toString(16).padStart(8, '0')).join('')
}

const pyInt = (v: string | undefined, dflt: number): number | null => {
  if (v === undefined) return dflt
  return /^\s*[+-]?\d+\s*$/.test(v) ? parseInt(v, 10) : null
}
export type Cohort = 'control' | 'compact' | 'full' | 'budget'
// §31: the trace label is 'budget' | 'full' | 'control' (stripped, lowercase); anything else is unknown -> undefined (OMIT).
export const normalizeVariant = (v: unknown): 'budget' | 'full' | 'control' | undefined => {
  const t = typeof v === 'string' ? v.trim().toLowerCase() : ''
  return t === 'budget' || t === 'full' || t === 'control' ? t : undefined
}
// §31: the variant stored at render time, normalized; never recomputed, never defaulted (a missing label = unknown).
// a stored label wins; without one (no search before this trace) the conversation's arm (server request 2026-11-02)
export const traceVariant = (stored: unknown, conversationId?: string, env: Record<string, string | undefined> = {}): string | undefined =>
  normalizeVariant(stored) ?? (conversationId ? normalizeVariant(renderCohort(conversationId, env)) : undefined)
// ace_pattern_render.render_arm (§31): arms in bucket order control, compact, full (ACE_RENDER_FULL_PCT, default 50,
// invalid -> 0; register.cohortEnv fills it from the server file when the env is unset), rest budget. No conversation id -> budget.
// control + compact over 100 (or either invalid/negative) -> both 0; the control share applied, 0 = off (trace render_control_pct)
function abPcts(env: Record<string, string | undefined>): [number, number] {
  const ctrl = pyInt(env.ACE_AB_CONTROL_PCT, 0), comp = pyInt(env.ACE_AB_COMPACT_PCT, 0)
  if (ctrl === null || comp === null || ctrl < 0 || comp < 0 || Math.min(ctrl, 100) + Math.min(comp, 100) > 100) return [0, 0]
  return [Math.min(ctrl, 100), Math.min(comp, 100)]
}
export const appliedControlPct = (env: Record<string, string | undefined>): number => abPcts(env)[0]
export function renderCohort(sid: string | undefined, env: Record<string, string | undefined>): Cohort {
  const [ctrl, comp] = abPcts(env)
  let full = pyInt(env.ACE_RENDER_FULL_PCT, 50)
  if (full === null || full < 0) full = 0
  full = Math.min(full, 100 - ctrl - comp)
  if (!sid) return 'budget'
  const b = parseInt(sha256Hex('render:' + sid).slice(0, 8), 16) % 100
  return b < ctrl ? 'control' : b < ctrl + comp ? 'compact' : b < ctrl + comp + full ? 'full' : 'budget'
}

// Server control share (search response render_control_pct, int 0-100), persisted like render_full_pct but in its OWN file; < 7 days.
export const RENDER_CONTROL_PCT_FILE = 'render-control-pct.json'
export const serverControlPct = (resp: any): number | undefined => validPct(resp?.render_control_pct) ? resp.render_control_pct : undefined
export const storedControlPct = (text: string | undefined, nowMs: number): number | undefined => storedFullPct(text, nowMs)

// Layout (a) arm (ace_pattern_render.layout_a_*): own salt "layout:" (orthogonal to "render:"), env ACE_RENDER_LAYOUT_A_PCT
// (not an integer / negative -> 0, clamped to 100), unset -> LAYOUT_A_DEFAULT_PCT, the ONE default (0 = off). No id -> not a member.
export const LAYOUT_A_DEFAULT_PCT = 0  // THE one default (0 = off until the server sends render_layout_a_pct > 0); mirror of ace_pattern_render.LAYOUT_A_DEFAULT_PCT
// Server share (search response render_layout_a_pct, int 0-100), persisted like render_full_pct but in its OWN file; < 7 days.
export const RENDER_LAYOUT_A_PCT_FILE = 'render-layout-a-pct.json'
export const serverLayoutAPct = (resp: any): number | undefined => validPct(resp?.render_layout_a_pct) ? resp.render_layout_a_pct : undefined
export const storedLayoutAPct = (text: string | undefined, nowMs: number): number | undefined => storedFullPct(text, nowMs)
// Strict like ace_pattern_render.layout_a_pct: ASCII digits, optional sign, outer blanks only ('5_0', '50.0', '1e1', fullwidth digits -> 0).
export function layoutAPct(env: Record<string, string | undefined>): number {
  const raw = env.ACE_RENDER_LAYOUT_A_PCT
  if (raw === undefined) return LAYOUT_A_DEFAULT_PCT
  return /^[ \t\n\r]*[+-]?[0-9]+[ \t\n\r]*$/.test(raw) ? Math.min(Math.max(parseInt(raw, 10), 0), 100) : 0
}
export function layoutAMember(sid: string | undefined, env: Record<string, string | undefined>): boolean {
  return !!sid && parseInt(sha256Hex('layout:' + sid).slice(0, 8), 16) % 100 < layoutAPct(env)
}
// render_layout values (state, trace, log label): 'a' without, 'a+hint' with the format hint; '' = none
export const LAYOUT_A_VALUES = ['a', 'a+hint']
export const layoutValue = (env: Record<string, string | undefined>): 'a' | 'a+hint' => env.ACE_RENDER_LAYOUT_A_HINT === '1' ? 'a+hint' : 'a'
export const layoutLabel = (v: unknown): string => typeof v === 'string' && LAYOUT_A_VALUES.includes(v) ? '+layout_' + v : ''

// Server kill switch (plugin_data_dir.store_render_full_pct): a search response MAY carry a top-level integer
// render_full_pct 0-100, persisted to <root>/render-full-pct.json {pct, at (epoch s)}; used while < 7 days old.
export const RENDER_FULL_PCT_FILE = 'render-full-pct.json'
const RENDER_FULL_PCT_MAX_AGE_S = 7 * 86400
const validPct = (v: unknown): v is number => typeof v === 'number' && Number.isInteger(v) && v >= 0 && v <= 100
export const serverFullPct = (resp: any): number | undefined => validPct(resp?.render_full_pct) ? resp.render_full_pct : undefined
export function storedFullPct(text: string | undefined, nowMs: number): number | undefined {
  try {
    const d = JSON.parse(text as string)
    return validPct(d?.pct) && typeof d.at === 'number' && nowMs / 1000 - d.at < RENDER_FULL_PCT_MAX_AGE_S ? d.pct : undefined
  } catch { return undefined }
}

// User rejection as a downvote on the NEXT main task's trace (ace_feedback.py, same list: parity test). A human main
// Server gate for the downvote: search response feedback_downvote (bool), persisted {on, at}; < 7 days; default off.
export const FEEDBACK_DOWNVOTE_FILE = 'feedback-downvote.json'
export const serverDownvote = (resp: any): boolean | undefined => typeof resp?.feedback_downvote === 'boolean' ? resp.feedback_downvote : undefined
export function storedDownvote(text: string | undefined, nowMs: number): boolean {
  try { const d = JSON.parse(text as string); return d?.on === true && typeof d.at === 'number' && nowMs / 1000 - d.at < RENDER_FULL_PCT_MAX_AGE_S } catch { return false }
}
// 8.4.3 server-side follow-up judging. Search response followup_judging: exactly "shadow" -> 'shadow' (send trace.followup AND keep
// the client vote), exactly true -> 'live' (trace.followup, no client vote), any other present value -> 'off', absent -> undefined
// (a real server answer without the key withdraws it: io/state.ts stores 'off'). Stored {mode, at, org, project}; only 'shadow' / 'live'
// for THIS org/project, younger than 7 days and not from the future (5 min skew) count; anything else is off. No env knob.
// 8.4.3 (review 2): ONE file per org/project (a short hash of org + NUL + project, no plain names), so a search of project B can never
// switch project A. The pre-hash global files (followup-judging.json, feedback-unresolved.json) are never read: they count as off.
const bindingHash = (org: string | null | undefined, project: string) => sha256Hex(`${org ?? ''}\0${project}`).slice(0, 16)
export const followupFileFor = (org: string | null | undefined, project: string) => `followup-judging-${bindingHash(org, project)}.json`
export const unresolvedFileFor = (org: string | null | undefined, project: string) => `feedback-unresolved-${bindingHash(org, project)}.json`
export type FollowupMode = 'off' | 'shadow' | 'live'
export const serverFollowup = (resp: any): FollowupMode | undefined => !resp || typeof resp !== 'object' || !('followup_judging' in resp) ? undefined
  : resp.followup_judging === 'shadow' ? 'shadow' : resp.followup_judging === true ? 'live' : 'off'
const FOLLOWUP_SKEW_S = 300
// 8.4.3 unresolved votes: search response feedback_unresolved, exactly true = on; any other present value = false; absent = undefined
// (io/state.ts then stores false: a real answer without the key is off). Stored {on, at, org, project}, same rules as followup_judging.
export const serverUnresolved = (resp: any): boolean | undefined => !resp || typeof resp !== 'object' || !('feedback_unresolved' in resp) ? undefined : resp.feedback_unresolved === true
export function storedUnresolved(text: string | undefined, nowMs: number, org: string | null, project: string): boolean {
  try {
    const d = JSON.parse(text as string), age = typeof d?.at === 'number' ? nowMs / 1000 - d.at : NaN
    return d?.on === true && age < RENDER_FULL_PCT_MAX_AGE_S && age > -FOLLOWUP_SKEW_S && d.org === org && d.project === project
  } catch { return false }
}
export function storedFollowup(text: string | undefined, nowMs: number, org: string | null, project: string): FollowupMode {
  try {
    const d = JSON.parse(text as string), age = typeof d?.at === 'number' ? nowMs / 1000 - d.at : NaN
    return (d?.mode === 'shadow' || d?.mode === 'live') && age < RENDER_FULL_PCT_MAX_AGE_S && age > -FOLLOWUP_SKEW_S && d.org === org && d.project === project ? d.mode : 'off'
  } catch { return 'off' }
}
// Round 5 kill switch: search response full_steps (bool), persisted {on, at}, < 7 days. The server can only switch full steps
// OFF: a missing, broken, stale or non-bool file keeps them on (plugin_data_dir.stored_full_steps, same rule).
export const FULL_STEPS_FILE = 'full-steps.json'
export const serverFullSteps = (resp: any): boolean | 'invalid' | undefined =>
  !resp || typeof resp !== 'object' || !('full_steps' in resp) ? undefined : typeof resp.full_steps === 'boolean' ? resp.full_steps : 'invalid'
export function storedFullSteps(text: string | undefined, nowMs: number): boolean {
  try { const d = JSON.parse(text as string); return !(d?.on === false && typeof d.at === 'number' && nowMs / 1000 - d.at < RENDER_FULL_PCT_MAX_AGE_S) } catch { return true }
}
// Upvote gate: search response feedback_upvote (bool) when the server sends one, persisted {on, at}, < 7 days. undefined = the
// server never sent it (or it is stale): no switch of its own, the upvote then follows the downvote gate (io/state.ts upvoteEnabled).
export const FEEDBACK_UPVOTE_FILE = 'feedback-upvote.json'
export const serverUpvote = (resp: any): boolean | undefined => typeof resp?.feedback_upvote === 'boolean' ? resp.feedback_upvote : undefined
export function storedUpvote(text: string | undefined, nowMs: number): boolean | undefined {
  try { const d = JSON.parse(text as string); return typeof d?.on === 'boolean' && typeof d.at === 'number' && nowMs / 1000 - d.at < RENDER_FULL_PCT_MAX_AGE_S ? d.on : undefined } catch { return undefined }
}

// 8.1.4 client_policy (DORMANT until the server sends it): plugin_data_dir.valid_client_policy / client_policy_state,
// same rules (shared cases: tests-fixtures/client-policy). A search response MAY carry a top-level object
// client_policy {min_plugin_version, recommended_plugin_version, message, url}, stored as {policy, at (epoch s)}, < 7 days.
export const CLIENT_POLICY_FILE = 'client-policy.json'
export const CLIENT_POLICY_KEYS = ['min_plugin_version', 'recommended_plugin_version', 'message', 'url'] as const
const VERSION_RE = /^\d{1,4}\.\d{1,4}\.\d{1,4}$/
const POLICY_TEXT_MAX = 200
// Cc, Cf, Zl, Zp (controls, bidi/zero-width/BOM, line/paragraph separators): refused, never stripped
const POLICY_BAD_CHARS = /[\p{Cc}\p{Cf}\p{Zl}\p{Zp}]/u
export function validClientPolicy(v: unknown): { policy: Record<string, string> } | { why: string } {
  if (!v || typeof v !== 'object' || Array.isArray(v)) return { why: 'not_an_object' }
  const out: Record<string, string> = {}
  for (const k of CLIENT_POLICY_KEYS) {
    if (!(k in (v as any))) continue
    const x = (v as any)[k]
    if (typeof x !== 'string' || [...x].length > POLICY_TEXT_MAX || POLICY_BAD_CHARS.test(x)) return { why: 'bad_' + k }  // code points, as Python len
    if (k.endsWith('_version') && !VERSION_RE.test(x)) return { why: 'bad_' + k }
    if (k === 'url' && (!x.startsWith('https://') || /[\s"'<>\\`]/.test(x))) return { why: 'bad_' + k }
    out[k] = x
  }
  return { policy: out }
}
const ver = (v: unknown): number[] | null => typeof v === 'string' && VERSION_RE.test(v) ? v.split('.').map(Number) : null
const below = (a: number[], b: number[]) => { for (let i = 0; i < 3; i++) if (a[i] !== b[i]) return a[i]! < b[i]!; return false }
export function storedClientPolicy(text: string | undefined, nowMs: number): Record<string, string> | undefined {
  try {
    const d = JSON.parse(text as string), v = validClientPolicy(d?.policy)
    return 'policy' in v && typeof d.at === 'number' && nowMs / 1000 - d.at < RENDER_FULL_PCT_MAX_AGE_S ? v.policy : undefined
  } catch { return undefined }
}
export function clientPolicyState(text: string | undefined, version: string, nowMs: number): 'min' | 'recommended' | undefined {
  const pol = storedClientPolicy(text, nowMs), mine = ver(version)
  if (!pol || !mine) return undefined
  const mn = ver(pol.min_plugin_version), rec = ver(pol.recommended_plugin_version)
  if (mn && below(mine, mn)) return 'min'
  if (rec && below(mine, rec)) return 'recommended'
  return undefined
}
export const clientPolicyBand = (text: string | undefined, version: string, nowMs: number): string | undefined =>
  clientPolicyState(text, version, nowMs) === 'min' ? `ACE ${version} ist zu alt, bitte /plugin update ausführen` : undefined
export function clientPolicyLine(text: string | undefined, version: string, nowMs: number): string | undefined {
  const st = clientPolicyState(text, version, nowMs), pol = storedClientPolicy(text, nowMs)
  if (!st || !pol) return undefined
  if (st === 'min') return `update   ACE ${version} ist zu alt (min ${pol.min_plugin_version}), bitte /plugin update ausführen`
  return `update   ACE ${version} · empfohlen ${pol.recommended_plugin_version}${pol.message ? `: ${pol.message}` : ''}${pol.url ? ` · ${pol.url}` : ''}`
}

// 8.2.0 bootstrap backfill capability (DORMANT until the server sends it): a search response with top-level boolean
// `bootstrap_backfill: true` switches the backfill on for the installation (global, the last search wins); stored {on, at (epoch s)}, < 7 days, else off.
export const BACKFILL_FLAG_FILE = 'bootstrap-backfill.json'
export const serverBackfill = (resp: any): boolean | undefined => typeof resp?.bootstrap_backfill === 'boolean' ? resp.bootstrap_backfill : undefined
export function storedBackfill(text: string | undefined, nowMs: number): boolean {
  try { const d = JSON.parse(text as string); return d?.on === true && typeof d.at === 'number' && nowMs / 1000 - d.at < RENDER_FULL_PCT_MAX_AGE_S } catch { return false }
}

// Layout (a) applies only on arms that render patterns verbatim (budget, full); control and compact never get it.
export const layoutA = (sid: string | undefined, env: Record<string, string | undefined>): boolean => {
  const arm = renderCohort(sid, env)
  return (arm === 'budget' || arm === 'full') && layoutAMember(sid, env)
}
