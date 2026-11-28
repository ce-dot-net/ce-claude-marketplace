// prompt.submit: the main search -> cohort render -> inject, the patterns-used state, the rejection downvote,
// the status line and session title.
import { python } from '../commands/py'
import { readJson, readText, rm, writePrivate } from '../io/fs'
import { nowIso, relLog, searchRow } from '../io/log'
import { SEARCH_MS, search } from '../io/spawn'
import { heldSince, noteDeadAuth } from '../io/auth'
import { type Load, type Sess, clearDeferred, dataRoot, clearTools, cohortEnv, deferredAnchor, disabled, downvoteEnabled, ensure, followupMode, followupTargetFile, pendingFollowupFile, notePrompt, pendingFile, pendingFile830, pendingHead, pendingVoteFile, readState, searchOrigin, touchMarker, unresolvedEnabled, updateState, upvoteEnabled, uuid, type HookArgs, refreshMarker } from '../io/state'
import { type Cohort, appliedControlPct, layoutA, layoutLabel, layoutValue, renderCohort } from '../lib/cohort'
import { REJECTION_PREV_MAX_AGE_S, evalStats, injectedContents, rejectionProbe, upvoteProbe } from '../lib/evidence'
import { num, pyDumps } from '../lib/pyjson'
import { type ModelVerdict, classifyRejection, rejectionCacheKey, rejectionMinConf } from '../lib/rejection'
import { domainsSummary, renderBudget, renderCompact, renderFull, renderLayoutBudget, renderLayoutFull, renderPatternsDict } from '../lib/render'
import { type StateUpdate, mergeState } from '../lib/state'
import { MACHINE_ORIGINS, domainNames, expandAbbreviations, isNoTaskCommand, skipReason } from '../lib/text'
import { searchErrorLine, searchSummary, sessionTitle, statusLine, topDomains } from '../ui/status'
import { humanPart } from '../lib/humanpart'
import { isUuid } from '../lib/trace'
import type { FollowupMode } from '../lib/cohort'

// ace_feedback.on_human_prompt: a rejection of the previous main task -> a pending downvote with its evidenced ids.
// 8.2.9: every human main prompt also logs one text-free row `rejection_check` for the server team's detection measurement:
// {matched phrase | null, blocked phrase (a guard dropped it) | null, chars, failed: the first failing condition in the cheap-first
// order too_long, prev_stale (no record or >= 6 h), empty_ids, switch_off, no_phrase; null = the downvote was queued}.
// 8.3.0: language-independent. All gates run first (so no model call when the result could never be queued); then a phrase hit
// is the free fast-path (detect_source 'phrase'), else one haiku classification (detect_source 'model', failed model_no /
// model_error / model_timeout, never a downvote on doubt). The model call runs from a $.clock.after timer (the prompt is never delayed; the
// pending downvote is written when it answers; a late one is consumed by the following main learn). ACE_REJECTION_MODEL=0 = phrases only.
// `source` stays 'mod' (the log origin on every row); the detector is `detect_source`.
const inflight = new Set<Promise<void>>()  // ponytail: module-level (a reload drops them); the tests wait on it
export const flushRejections = () => Promise.all([...inflight]).then(() => undefined)
const classified = new Map<string, { reject: boolean; confidence: number; label: string | null }>()  // same prompt twice in a session: one call
// Upvote (mod-only), PHRASE ONLY: the same gates (<= 300 chars, previous task < 6 h with ids), its own switch (upvoteEnabled) and
// evidence.upvoteProbe (the message is nothing but an approval). No model upvote: real haiku found no real approval the phrase missed,
// and a shared prompt cost downvote precision, so the classifier stays the 8.3.0 one. A rejection phrase, a bare acknowledgement
// (also emoji-only) or a phrase hit blocked by other words never upvotes; an upvote phrase hit skips the downvote model
// (rejection_check failed 'upvote_phrase'). last-downvoted-task locks BOTH directions: one feedback per task. One text-free
// `upvote_check` row whenever an upvote phrase was seen.
export async function onRejection($: any, s: Sess, text: string, L?: Load) {
  // 8.4.3 server-side follow-up judging: 'shadow' queues the follow-up and keeps the client vote below unchanged; 'live' queues it and,
  // when its gates held, skips the client vote (no phrase probe, no Haiku); 'off' (the default) changes nothing (golden test).
  // live always returns here (no client vote, also when a follow-up gate failed: headless / ACE_REJECTION_MODEL=0 get no signal).
  const mode = await followupMode($, s)
  if (mode !== 'off') { await queueFollowup($, s, text, L, mode).catch(() => false); if (mode === 'live') return }  // never throws into the vote path
  const { matched, blocked, tooLong } = rejectionProbe(text)
  const up = upvoteProbe(text)
  const prev = tooLong ? undefined : await readJson($, `${s.sdir}/last-main-applied.json`)
  const prevAt = num(prev?.at)  // a seconds float reads back as a PyFloat: compare its value
  const ageS = prevAt !== undefined ? await $.clock.now() / 1000 - prevAt : undefined
  const fresh = ageS !== undefined && ageS < REJECTION_PREV_MAX_AGE_S
  const ids: number[] = fresh && Array.isArray(prev.applied_log_ids) ? prev.applied_log_ids.filter((x: unknown) => Number.isInteger(x)) : []
  const on = tooLong ? undefined : await downvoteEnabled($, s)
  // 8.4.3 unresolved (server capability feedback_unresolved, read only when 8.4.2 would stop at prev_stale / empty_ids): the vote is
  // still detected and goes out without ids, aimed at the record's retrieval_id when it is a UUID (also a stale record's), else no target.
  // too_long and switch_off stay off. Capability off: the 8.4.2 gate order exactly (golden test).
  const unresolved = !tooLong && (!fresh || !ids.length) && await unresolvedEnabled($, s)
  const target: string | null = unresolved && isUuid(prev?.retrieval_id) ? prev.retrieval_id : null
  const gate = tooLong ? 'too_long' : !fresh && !unresolved ? 'prev_stale' : !ids.length && !unresolved ? 'empty_ids' : !on ? 'switch_off' : null
  const upOn = gate === null || gate === 'switch_off' ? await upvoteEnabled($, s) : false
  const upGate = tooLong ? 'too_long' : !fresh && !unresolved ? 'prev_stale' : !ids.length && !unresolved ? 'empty_ids' : !upOn ? 'switch_off' : matched ? 'reject_phrase' : up.bareAck ? 'bare_ack' : null
  const upPhrase = upGate === null && up.matched !== null
  const modelOk = async () => String(text ?? '').trim() !== '' && L?.interactive !== false && (await $.env.get('ACE_REJECTION_MODEL')) !== '0'
  // S4: headless (-p / SDK, interactive === false) skips the model like the self-eval does; the phrase path is unchanged. Empty text: nothing to classify.
  // 8.4.3 (save Haiku): with the capability the model runs only on a record with a valid retrieval_id (so a model vote always
  // has a target); no record / a record without one: the phrase path only (its unresolved vote then has no target)
  const noTarget = unresolved && !target
  // 8.4.3 (prod finding: an untargeted vote books nothing): unresolved rows say whether the vote carries a target and why not. The target
  // is fixed here (the pending file); takeVote only re-checks the UUID, so this is what is sent. 'other' is not reachable from here.
  const targetLog: Record<string, unknown> = !unresolved ? {} : target ? { target: true } : { target: false, no_target_reason: prev === undefined ? 'no_prev_record' : 'no_prev_retrieval' }
  const modelCandidate = gate === null && !matched && !upPhrase && await modelOk()
  const useModel = modelCandidate && !noTarget
  const row = (failed: string | null, extra: Record<string, unknown>, nowIsoStr: string) => ({ timestamp: nowIsoStr, event: 'rejection_check', matched, blocked,
    chars: [...String(text ?? '')].length, failed, prev_age_s: ageS === undefined ? null : Math.round(ageS), prev_ids: ids.length, session_id: s.sessionId,
    detect_source: matched ? 'phrase' : useModel ? 'model' : null, model_reject: null, model_conf: null, model_ms: null, model_label: null, ...(unresolved ? { unresolved: true, ...targetLog } : {}), ...extra, source: 'mod' })
  const upRow = async (failed: string | null, extra: Record<string, unknown> = {}) => relLog($, s, { timestamp: await nowIso($), event: 'upvote_check',
    matched: up.matched, blocked: up.blocked, chars: [...String(text ?? '')].length, failed, prev_age_s: ageS === undefined ? null : Math.round(ageS),
    prev_ids: ids.length, session_id: s.sessionId, detect_source: upPhrase ? 'phrase' : null, ...(unresolved ? { unresolved: true, ...targetLog } : {}), ...extra, source: 'mod' })
  const tsid: string | null = typeof prev?.task_session_id === 'string' && prev.task_session_id ? prev.task_session_id : null
  const doneFile = `${s.sdir}/last-downvoted-task`  // name kept (8.3.0); it now locks up- and downvote alike
  // 8.4.3: an unresolved vote without a task id locks the previous answer by its record time ('none:<at>', 'none:none' without a
  // record), so one untargeted downvote is never followed by an untargeted upvote; a new record opens the next vote. 8.4.2 votes: tsid only.
  const lockKey: string | null = tsid ?? (unresolved ? `none:${prevAt ?? 'none'}` : null)
  // S7: one feedback per task, and never into a session dir that is gone (session.end removed it while the model was answering).
  // null = written, else why it was skipped.
  const write = async (kind: 'downvote' | 'upvote', meta: { detect_source: 'phrase' | 'model'; model_conf?: number }): Promise<'session_gone' | 'task_downvoted' | 'task_voted' | null> => {
    if (!(await $.fs.exists(s.sdir))) return 'session_gone'
    if (lockKey && (await readText($, doneFile))?.trim() === lockKey) return kind === 'downvote' ? 'task_downvoted' : 'task_voted'
    await writePrivate($, pendingVoteFile(s, kind), JSON.stringify({ applied_log_ids: ids, at: await $.clock.now() / 1000, task_session_id: tsid, ...meta,
      ...(unresolved ? { unresolved: true, ...(target ? { target_retrieval_id: target } : {}) } : {}) }))
    if (lockKey) await writePrivate($, doneFile, lockKey).catch(() => {})
    return null
  }
  if (!useModel) {
    const failed = gate ?? (matched ? null : upPhrase ? 'upvote_phrase' : noTarget && modelCandidate ? (prev === undefined ? 'no_prev_record' : 'no_target_record') : 'no_phrase')  // only when the model would have run
    const skipped = failed === null ? await write('downvote', { detect_source: 'phrase' }) : failed
    await relLog($, s, row(skipped, {}, await nowIso($)))
    if (matched) await relLog($, s, { timestamp: await nowIso($), event: 'rejection_detected', matched, downvote_sent: skipped === null,
      prev_task: String(prev?.task_session_id ?? '').slice(0, 8) || null, session_id: s.sessionId, ...targetLog, source: 'mod' })
  }
  if (upPhrase) await upRow(await write('upvote', { detect_source: 'phrase' }))
  else if (up.matched || up.blocked) await upRow(upGate ?? 'no_phrase')
  if (!useModel) return
  // $.clock.after: the native way to run work after the hook returned (the call is no part of this dispatch, so an
  // abandoned dispatch cannot abort it); bounded by REJECTION_MODEL_MS, fails safe. A vote written after the next
  // Stop is not lost: takeDownvote consumes the file at the following main learn (within 6 h).
  const work = async () => {
    const key = rejectionCacheKey(s.sessionId, prev?.task_session_id, text)
    const t0 = await $.clock.now()
    const hit = classified.get(key)
    const minConf = rejectionMinConf(await $.env.get('ACE_REJECTION_MIN_CONF'))
    const v: ModelVerdict = hit ? { failed: hit.reject && hit.confidence >= minConf ? null : 'model_no', reject: hit.reject, conf: hit.confidence, label: hit.label }
      : await classifyRejection($, text, String(prev?.answer_tail ?? ''), minConf)
    if (!hit && v.reject !== null && v.conf !== null) { classified.set(key, { reject: v.reject, confidence: v.conf, label: v.label ?? null }); if (classified.size > 50) classified.delete(classified.keys().next().value!) }
    const ms = hit ? 0 : Math.round(await $.clock.now() - t0)
    let failed: string | null = v.failed
    if (failed === null) failed = await write('downvote', { detect_source: 'model', model_conf: Math.round(v.conf! * 100) / 100 })
    await relLog($, s, row(failed, { model_reject: v.reject, model_conf: v.conf, model_ms: ms, model_label: v.label ?? null }, await nowIso($)))
    if (v.reject === true && v.conf !== null && v.conf >= minConf)
      await relLog($, s, { timestamp: await nowIso($), event: 'rejection_detected', matched: null, downvote_sent: failed === null, detect_source: 'model',
        prev_task: String(prev?.task_session_id ?? '').slice(0, 8) || null, session_id: s.sessionId, ...targetLog, source: 'mod' })
  }
  try { $.clock.after(1, () => { const p: Promise<void> = work().catch(() => {}).finally(() => { inflight.delete(p) }); inflight.add(p) }) }
  catch { await relLog($, s, row('model_error', {}, await nowIso($))) }
}
// 8.4.3: the follow-up of the previous main task, for the server to judge (locked contract v1, lib/trace.ts followupField).
// Gates (nothing written when they fail): interactive (headless sends nothing), ACE_REJECTION_MODEL != '0' (no follow-up text leaves the
// machine), a follow-up target (io/state.ts followupTargetFile: the previous main task's FINAL record) younger than 6 h with a UUID
// retrieval_id. Then: one follow-up per previous task
// (own lock last-followup-task, so the client vote lock is untouched), an empty human part sends nothing. The text is the redacted human
// part (lib/humanpart.ts). One text-free `followup_check` row.
async function queueFollowup($: any, s: Sess, text: string, L: Load | undefined, mode: FollowupMode): Promise<boolean> {
  let ids: number[] = []
  const row = async (failed: string | null, extra: Record<string, unknown> = {}) => relLog($, s, { timestamp: await nowIso($), event: 'followup_check', mode, failed,
    prev_ids: ids.length, session_id: s.sessionId, ...extra, source: 'mod' })
  // 8.4.3 (review S3): a gate that stops it logs why. no_target = no target file (no task yet, or the turn after it was aborted, deferred,
  // task-less or still in its self-eval window: the file is gone or not written yet; those cases cannot be told apart here).
  if (L?.interactive === false) { await row('headless'); return false }
  if ((await $.env.get('ACE_REJECTION_MODEL')) === '0') { await row('model_off'); return false }
  const prev = await readJson($, followupTargetFile(s))
  const prevAt = num(prev?.at), now = await $.clock.now()
  if (prevAt === undefined) { await row('no_target'); return false }
  ids = Array.isArray(prev.applied_log_ids) ? prev.applied_log_ids.filter((x: unknown) => Number.isInteger(x)) : []
  if (now / 1000 - prevAt >= REJECTION_PREV_MAX_AGE_S) { await row('stale_target'); return false }
  if (!isUuid(prev?.target_retrieval_id)) { await row('no_uuid'); return false }
  const tsid: string | null = typeof prev?.task_session_id === 'string' && prev.task_session_id ? prev.task_session_id : null
  const lock = `${s.sdir}/last-followup-task`
  if (!(await $.fs.exists(s.sdir))) { await row('session_gone'); return true }
  if (tsid && (await readText($, lock))?.trim() === tsid) { await row('task_sent'); return true }
  const human = humanPart(text)
  if (!human) { await row('empty_human'); return true }
  try { await writePrivate($, pendingFollowupFile(s), JSON.stringify({ text: human, target_retrieval_id: prev.target_retrieval_id, applied_log_ids: ids, ts: new Date(now).toISOString(), target_at: prevAt })) }
  catch { await row('write_failed').catch(() => {}); return true }  // shadow: the client vote below still runs
  if (tsid) await writePrivate($, lock, tsid).catch(() => {})
  await row(null, { sent_chars: [...human].length })
  return true
}
// 8.4.3: shown once per conversation while the follow-up is on and allowed to leave the machine (marker followup_notified).
export const FOLLOWUP_LINE_LIVE = 'ACE: Follow-up-Text (geschwärzt, rund 600 Zeichen) geht zur Bewertung an den Server; aus mit ACE_REJECTION_MODEL=0.'
export const FOLLOWUP_LINE_SHADOW = 'ACE: Follow-up-Text (geschwärzt, rund 600 Zeichen) geht zur Bewertung an den Server (Vergleichsphase, eigene Bewertung läuft weiter); aus mit ACE_REJECTION_MODEL=0.'
export async function followupNotice($: any, s: Sess, L: Load): Promise<string | null> {
  try {
    const mode = await followupMode($, s)
    if (mode === 'off' || L.interactive === false || (await $.env.get('ACE_REJECTION_MODEL')) === '0') return null
    const marker = `${s.sdir}/followup_notified`
    if (await $.fs.exists(marker)) return null
    await writePrivate($, marker, '1')
    return mode === 'live' ? FOLLOWUP_LINE_LIVE : FOLLOWUP_LINE_SHADOW
  } catch { return null }
}
// §13.1 cohort arms; `rendered` = the ≤ 10K re-inject copy (C1). control: search + anchor, nothing injected.
// §28: bucket on the STABLE CC session id (one arm per conversation; subagents share it), never the per-task pin.
// §31 dedupe (main prompts only): under full, ids already injected in this conversation since the last compaction
// (`seen`) are left out; nothing new -> nothing injected.
export async function renderArm($: any, resp: any, tag: string, attrs: string, s: Sess, seen?: Set<string>) {
  const env = await cohortEnv($, s)
  const cohort: Cohort = renderCohort(s.sessionId, env)
  const controlPct = appliedControlPct(env)  // 8.4.3: frozen into the task state with the variant
  // layout (a): a second, orthogonal arm (own salt) on the budget and full renders; control/compact stay as they are
  const inLayout = layoutA(s.sessionId, env), hint = env.ACE_RENDER_LAYOUT_A_HINT === '1'
  const budgetRender = (r: any) => inLayout ? renderLayoutBudget(r, tag, attrs, hint) : renderBudget(r, tag, attrs)
  // item 3: the full arm's re-inject copy is the budget render (<= 9,500) of the WHOLE response, never the deduped subset
  const reinject = cohort === 'full' ? budgetRender(resp).context as string : ''
  if (cohort === 'full' && seen?.size) {
    resp = { ...resp, similar_patterns: (resp.similar_patterns || []).filter((p: any) => !seen.has(p?.id)) }
    if (!resp.similar_patterns.length) return { cohort, controlPct, layout: undefined as string | null | undefined, context: null as string | null, ids: [] as string[], rlog: {} as Record<string, number>, patterns: [] as any[], rendered: reinject, truncated: false }
  }
  if (cohort === 'control') return { cohort, controlPct, layout: null as string | null | undefined, context: null as string | null, ids: [] as string[], rlog: {} as Record<string, number>, patterns: [] as any[], rendered: '', truncated: false }
  const r = cohort === 'compact' ? renderCompact(resp, tag, attrs) : cohort === 'budget' ? budgetRender(resp)
    : inLayout ? renderLayoutFull(resp, tag, attrs, hint) : renderFull(resp, tag, attrs)
  const rendered = cohort === 'full' ? reinject : r.context
  // layout: the render_layout to store; null = rendered without layout (clears an earlier value), undefined = nothing rendered (keeps it)
  return { cohort, controlPct, layout: (inLayout ? layoutValue(env) : null) as string | null | undefined, context: r.context as string | null, ids: r.ids, rlog: r.rlog, patterns: r.patterns, rendered, truncated: cohort === 'full' && r.shown < r.total }
}
// relevance-log label of a render: the arm, '+layout_a' when the layout arm rendered it (render_variant itself stays budget|full)
export const cohortLabel = (r: { cohort: string; layout?: string | null }) => r.cohort + layoutLabel(r.layout)
// 8.4.0: a rejected token (dead/ entries with last_error 'auth' < 30 min old) is shown ONCE per conversation, from the queue state
// (not the search). The ONE implementation is the Python one (`ace_trace_queue.py --auth-held` prints the line or nothing), so both chains
// say the same words at the same threshold. ponytail: one python spawn per prompt until it has been shown (~30 ms), then none.
// 8.4.1: a held token (io/auth.ts) shows it too, without a count (learns are skipped while held, so dead/ may stay empty); the
// learn child's dead auth entries are turned into the hold first (noteDeadAuth), so this prompt's search already respects it.
export const AUTH_HELD_PREFIX = 'ACE: nicht angemeldet, Traces werden NICHT gesendet'
export const AUTH_HELD_MARKER_LINE = `${AUTH_HELD_PREFIX}. Bitte \`ace-cli login\` ausführen.`
export async function authHeldNotice($: any, s: Sess, L: { deadSeen?: number } = {}): Promise<string | null> {
  try {
    await noteDeadAuth($, s, L)
    const marker = `${s.sdir}/auth_held_notified`
    const since = await heldSince($, s), key = since === undefined ? null : `hold:${since}`
    const seen = (await readText($, marker))?.trim()
    let line: string | null = null
    if (seen === undefined) {  // the queue's counted line, once per conversation; a failing spawn never suppresses the marker line
      try {
        const out = await python($, 'utils/ace_trace_queue.py', ['--auth-held', '--data-root', await dataRoot($)], $.plugin.root, 15_000)
        if (out.startsWith(AUTH_HELD_PREFIX)) line = out.split('\n')[0] ?? null
      } catch { /* the marker line below still counts */ }
    }
    if (!line && key && seen !== key) line = AUTH_HELD_MARKER_LINE  // once per hold (a new hold = a new mtime shows it again)
    if (!line) return null
    await writePrivate($, marker, key ?? '1')
    return line
  } catch { return null }
}
// 8.4.0: ACE_TRACE_SINK set (not blank) = the traces go to a file and NOTHING is sent: shown once per conversation (marker sink_notified).
// Same text as ace_trace_queue.SINK_LINE (tests/test_auth_held_notice.py guards the parity).
export const SINK_LINE = "ACE: Traces gehen in die lokale Senke (ACE_TRACE_SINK), es wird NICHTS gesendet."
export async function sinkNotice($: any, s: Sess): Promise<string | null> {
  try {
    if (!(await $.env.get('ACE_TRACE_SINK'))?.trim()) return null
    const marker = `${s.sdir}/sink_notified`
    if (await $.fs.exists(marker)) return null
    await writePrivate($, marker, '1')
    return SINK_LINE
  } catch { return null }
}
export async function onPrompt($: any, L: Load, e: any): Promise<any> {
  const s = await ensure($, L)
  if (!s) return e
  const t0 = await $.clock.now()
  await touchMarker($, L, s, t0)   // every prompt, machine ones too: this is what keeps the Python hooks quiet
  const text: string = e.command ? e.command.args : e.text
  // Typed over, or delivered into, a running turn: that turn's next turn.start must not be bound to anything here.
  const midTurn = e.turnId !== undefined
  const reason = e.origin && MACHINE_ORIGINS.has(e.origin.kind) ? 'machine_prompt'
    : e.isMeta ? 'machine_prompt' : e.command && isNoTaskCommand(e.command.name) ? 'ace_command'
    : skipReason(text, s.minChars, s.extraPrefixes)
  if (!midTurn && !e.command) L.humanPrompt = reason === null || reason === 'prompt_too_short'  // 8.3.0 (S1): the Stop of this turn moves the rejection record on
  if (!midTurn && !e.command && (reason === null || reason === 'prompt_too_short') && !(await disabled($, s)))
    try { await onRejection($, s, text, L) } catch { /* never break the prompt */ }
  if (reason) {
    // §16 P2: the <task-notification> of a deferred task continues that task (its turn's tools join its learn)
    if (!midTurn) L.pendingMain = reason === 'machine_prompt' ? await deferredAnchor($, L, s) : null
    if (reason !== 'ace_command') await relLog($, s, { timestamp: await nowIso($), event: 'search_skipped', hook: 'UserPromptSubmit', reason, session_id: s.sessionId, project_id: s.project, origin: e.origin?.kind ?? null, source: 'mod' })
    return e
  }
  if (await disabled($, s)) { if (!midTurn) L.pendingMain = null; return e }
  const authHeld = await authHeldNotice($, s, L)
  if (authHeld) $.ui.log(authHeld)
  const sink = await sinkNotice($, s)
  if (sink) $.ui.log(sink)
  const fuLine = await followupNotice($, s, L)
  if (fuLine) $.ui.log(fuLine)
  const tsid = uuid()
  // A running task keeps its anchor, tools and state. The new prompt waits on disk: if a turn starts with its text it
  // is its own task (turn.start). If it was delivered into the running turn its work lands in that task's learn, its
  // search goes uncredited (no way to tell the two apart here, and a false credit is worse than none).
  const mainState = midTurn ? await readState($, s, 'main') : undefined
  const running = !midTurn ? undefined : L.turnAnchor.has(e.turnId) ? L.turnAnchor.get(e.turnId) : mainState?.task_session_id
  const defer = !!running && mainState?.task_session_id === running
  const save = (u: StateUpdate) => defer
    // round 6: a prefix hash, not the prompt (turn.start only compares); ponytail: one slot, of two queued prompts the first is not learned
    ? writePrivate($, pendingFile(s), JSON.stringify(pendingHead(text, pyDumps(mergeState(undefined, u)))))
    : updateState($, L, s, 'main', u, true)
  if (!defer) {
    L.pendingMain = tsid
    L.mainSeen = 0
    await clearDeferred($, L, s)  // accepted edge (CHANGELOG): a new human prompt before the notification drops the deferred learn
    await clearTools($, L, s, 'main')
    for (const f of [pendingFile(s), pendingFile830(s)]) if (await $.fs.exists(f)) await rm($, f)
  }

  // item D: no HTML-comment self-eval request in the conversation while the mod runs (its Haiku self-eval replaces it);
  // a request a Python Stop left (guarded seat, earlier run) is removed, never injected
  const evalFile = `${s.logs}/ace-eval-request.json`
  if (await $.fs.exists(evalFile)) await rm($, evalFile)
  const withEval = (entries: string[]) => {
    const all = [...(e.context ?? []), ...entries]
    return all.length ? { ...e, context: all } : e
  }

  const query = expandAbbreviations(text)
  const sr = await search($, s, query, tsid, undefined, SEARCH_MS, tsid, await searchOrigin($, L, s), L)  // notePrompt ran first: the count includes this prompt
  if (!sr.resp) {
    await save({ tsid, userPrompt: e.text, hook: 'UserPromptSubmit' })  // nothing rendered: no label (§31 omit)
    await relLog($, s, { timestamp: await nowIso($), event: 'error', hook: 'UserPromptSubmit', location: 'mod.search', error: sr.error ?? null, stderr_sample: sr.stderr, pin_failed: sr.pinFailed || undefined, pin_ms: sr.pinMs, session_id: s.sessionId, project_id: s.project, hook_ms: await $.clock.now() - t0, source: 'mod' })
    $.ui.log(searchErrorLine(sr.error))
    return withEval([])
  }
  const seenFile = `${s.sdir}/full-injected.json`  // §31; the SessionStart compact hook removes it
  const seenRaw = await readJson($, seenFile)
  const seen: string[] = Array.isArray(seenRaw) ? seenRaw.filter((x: unknown) => typeof x === 'string') : []
  const r = await renderArm($, sr.resp, 'ace-patterns', 'agent-type="main"', s, new Set(seen))
  if (r.cohort === 'full' && r.ids.length) await writePrivate($, seenFile, JSON.stringify([...new Set([...seen, ...r.ids])]))
  await save({ ids: r.ids, retrievalId: sr.resp.retrieval_id || null, rlog: r.rlog, tsid, userPrompt: e.text, rendered: r.rendered, hook: 'UserPromptSubmit',
    renderVariant: r.cohort, renderControlPct: r.controlPct, renderLayout: r.layout, contents: injectedContents(r.patterns, r.ids), evalStats: evalStats(r.patterns, sr.resp.similar_patterns || []) })
  const ds = domainsSummary(sr.resp)
  if (Object.keys(ds).length) {
    L.domains = domainNames(ds)
    await $.fs.write(`${s.pdir}/domains.json`, pyDumps(ds))
  }
  const returned = sr.resp.similar_patterns || []
  await relLog($, s, searchRow({ hook: 'UserPromptSubmit', sessionId: s.sessionId, userPrompt: e.text, query, returned, injected: r.patterns,
    projectId: s.project, orgId: s.org, agentType: 'main', cohort: cohortLabel(r), hookMs: await $.clock.now() - t0, nowIso: await nowIso($),
    extra: { search_ms: sr.ms, pin_ms: sr.pinMs, pin_failed: sr.pinFailed || undefined, pin_skipped: sr.pinSkipped, truncated_for_cap: r.truncated || undefined,
      context_chars: r.context?.length ?? 0, task_session_id: tsid, mid_turn: defer || undefined, engine: sr.engine, engine_reason: sr.engineWhy, source: 'mod' } }))
  const processed = renderPatternsDict(sr.resp).dict.similar_patterns
  $.ui.log(statusLine({ injected: r.patterns.length, returned: returned.length, cohort: r.cohort, domains: topDomains(r.patterns) }))
  $.ui.log(searchSummary(processed), { to: 'debug' })
  L.pendingTitle = sessionTitle(processed, await readJson($, `${s.logs}/ace-review-result.json`))
  // a managed-settings guard filters classic.UserPromptSubmit: the Python UPS sets this title then (per-duty markers)
  if (L.pendingTitle) await $.fs.write(`${s.sdir}/mod-title`, L.pendingTitle)
  return withEval(r.context ? [r.context] : [])
}

export async function promptSubmit($: HookArgs<'prompt.submit'>[0], L: Load, e: HookArgs<'prompt.submit'>[1], next: HookArgs<'prompt.submit'>[2]) {
  // 8.2.2 trace origin fields: every prompt counts (machine ones too), before any skip or error
  const s0 = await ensure($, L).catch(() => null)
  if (s0) await notePrompt($, s0, e.origin?.kind)
  if (L.compacted) {
    L.compacted = false
    try { if (L.sess && await $.fs.exists(`${L.sess.sdir}/mod-compact`)) await rm($, `${L.sess.sdir}/mod-compact`) } catch { /* stale marker ages out */ }
  }
  let out: any = e
  try { out = await onPrompt($, L, e) } catch (err) {
    if (L.sess) await relLog($, L.sess, { timestamp: await nowIso($), event: 'error', hook: 'UserPromptSubmit', location: 'mod.prompt.submit', error: String(err).slice(0, 300), source: 'mod' })
  }
  await refreshMarker($, L, true)  // handoff: the Python UPS runs inside next(); a crashed mod never writes this (MOD_HANDOFF_S)
  return next(out)
}
