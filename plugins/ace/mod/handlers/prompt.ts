// prompt.submit: the main search -> cohort render -> inject, the patterns-used state, the rejection downvote,
// the status line and session title.
import { readJson, readText, rm, writePrivate } from '../io/fs'
import { nowIso, relLog, searchRow } from '../io/log'
import { SEARCH_MS, search } from '../io/spawn'
import { type Load, type Sess, clearDeferred, clearTools, cohortEnv, deferredAnchor, disabled, downvoteEnabled, ensure, notePrompt, pendingFile, readState, searchOrigin, touchMarker, updateState, uuid, type HookArgs, refreshMarker } from '../io/state'
import { type Cohort, renderCohort } from '../lib/cohort'
import { REJECTION_PREV_MAX_AGE_S, evalStats, injectedContents, rejectionProbe } from '../lib/evidence'
import { num, pyDumps } from '../lib/pyjson'
import { type ModelVerdict, classifyRejection, rejectionCacheKey, rejectionMinConf } from '../lib/rejection'
import { domainsSummary, renderBudget, renderCompact, renderFull, renderPatternsDict } from '../lib/render'
import { type StateUpdate, mergeState } from '../lib/state'
import { MACHINE_ORIGINS, domainNames, expandAbbreviations, isNoTaskCommand, skipReason } from '../lib/text'
import { searchErrorLine, searchSummary, sessionTitle, statusLine, topDomains } from '../ui/status'

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
export async function onRejection($: any, s: Sess, text: string, L?: Load) {
  const { matched, blocked, tooLong } = rejectionProbe(text)
  const prev = tooLong ? undefined : await readJson($, `${s.sdir}/last-main-applied.json`)
  const prevAt = num(prev?.at)  // a seconds float reads back as a PyFloat: compare its value
  const ageS = prevAt !== undefined ? await $.clock.now() / 1000 - prevAt : undefined
  const fresh = ageS !== undefined && ageS < REJECTION_PREV_MAX_AGE_S
  const ids: number[] = fresh && Array.isArray(prev.applied_log_ids) ? prev.applied_log_ids.filter((x: unknown) => Number.isInteger(x)) : []
  const on = tooLong ? undefined : await downvoteEnabled($, s)
  const gate = tooLong ? 'too_long' : !fresh ? 'prev_stale' : !ids.length ? 'empty_ids' : !on ? 'switch_off' : null
  // S4: headless (-p / SDK, interactive === false) skips the model like the self-eval does; the phrase path is unchanged. Empty text: nothing to classify.
  const useModel = gate === null && !matched && String(text ?? '').trim() !== '' && L?.interactive !== false && (await $.env.get('ACE_REJECTION_MODEL')) !== '0'
  const row = (failed: string | null, extra: Record<string, unknown>, nowIsoStr: string) => ({ timestamp: nowIsoStr, event: 'rejection_check', matched, blocked,
    chars: [...String(text ?? '')].length, failed, prev_age_s: ageS === undefined ? null : Math.round(ageS), prev_ids: ids.length, session_id: s.sessionId,
    detect_source: matched ? 'phrase' : useModel ? 'model' : null, model_reject: null, model_conf: null, model_ms: null, model_label: null, ...extra, source: 'mod' })
  const tsid: string | null = typeof prev?.task_session_id === 'string' && prev.task_session_id ? prev.task_session_id : null
  const doneFile = `${s.sdir}/last-downvoted-task`
  // S7: one downvote per task, and never into a session dir that is gone (session.end removed it while the model was answering).
  // null = written, else why it was skipped.
  const write = async (meta: { detect_source: 'phrase' | 'model'; model_conf?: number }): Promise<'session_gone' | 'task_downvoted' | null> => {
    if (!(await $.fs.exists(s.sdir))) return 'session_gone'
    if (tsid && (await readText($, doneFile))?.trim() === tsid) return 'task_downvoted'
    await writePrivate($, `${s.sdir}/pending-downvote.json`, JSON.stringify({ applied_log_ids: ids, at: await $.clock.now() / 1000, task_session_id: tsid, ...meta }))
    if (tsid) await writePrivate($, doneFile, tsid).catch(() => {})
    return null
  }
  if (useModel) {
    // $.clock.after: the native way to run work after the hook returned (the call is no part of this dispatch, so an
    // abandoned dispatch cannot abort it); bounded by REJECTION_MODEL_MS, fails safe. A downvote written after the next
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
      if (failed === null) failed = await write({ detect_source: 'model', model_conf: Math.round(v.conf! * 100) / 100 })
      await relLog($, s, row(failed, { model_reject: v.reject, model_conf: v.conf, model_ms: ms, model_label: v.label ?? null }, await nowIso($)))
      if (v.reject === true && v.conf !== null && v.conf >= minConf)
        await relLog($, s, { timestamp: await nowIso($), event: 'rejection_detected', matched: null, downvote_sent: failed === null, detect_source: 'model',
          prev_task: String(prev?.task_session_id ?? '').slice(0, 8) || null, session_id: s.sessionId, source: 'mod' })
    }
    try { $.clock.after(1, () => { const p: Promise<void> = work().catch(() => {}).finally(() => { inflight.delete(p) }); inflight.add(p) }) }
    catch { await relLog($, s, row('model_error', {}, await nowIso($))) }
    return
  }
  const failed = gate ?? (!matched ? 'no_phrase' : null)
  const skipped = failed === null ? await write({ detect_source: 'phrase' }) : failed
  const sent = skipped === null
  await relLog($, s, row(skipped, {}, await nowIso($)))
  if (!matched) return
  await relLog($, s, { timestamp: await nowIso($), event: 'rejection_detected', matched, downvote_sent: sent,
    prev_task: String(prev?.task_session_id ?? '').slice(0, 8) || null, session_id: s.sessionId, source: 'mod' })
}
// §13.1 cohort arms; `rendered` = the ≤ 10K re-inject copy (C1). control: search + anchor, nothing injected.
// §28: bucket on the STABLE CC session id (one arm per conversation; subagents share it), never the per-task pin.
// §31 dedupe (main prompts only): under full, ids already injected in this conversation since the last compaction
// (`seen`) are left out; nothing new -> nothing injected.
export async function renderArm($: any, resp: any, tag: string, attrs: string, s: Sess, seen?: Set<string>) {
  const cohort: Cohort = renderCohort(s.sessionId, await cohortEnv($, s))
  // item 3: the full arm's re-inject copy is the budget render (<= 9,500) of the WHOLE response, never the deduped subset
  const reinject = cohort === 'full' ? renderBudget(resp, tag, attrs).context as string : ''
  if (cohort === 'full' && seen?.size) {
    resp = { ...resp, similar_patterns: (resp.similar_patterns || []).filter((p: any) => !seen.has(p?.id)) }
    if (!resp.similar_patterns.length) return { cohort, context: null as string | null, ids: [] as string[], rlog: {} as Record<string, number>, patterns: [] as any[], rendered: reinject, truncated: false }
  }
  if (cohort === 'control') return { cohort, context: null as string | null, ids: [] as string[], rlog: {} as Record<string, number>, patterns: [] as any[], rendered: '', truncated: false }
  const r = cohort === 'compact' ? renderCompact(resp, tag, attrs) : cohort === 'budget' ? renderBudget(resp, tag, attrs) : renderFull(resp, tag, attrs)
  const rendered = cohort === 'full' ? reinject : r.context
  return { cohort, context: r.context as string | null, ids: r.ids, rlog: r.rlog, patterns: r.patterns, rendered, truncated: cohort === 'full' && r.shown < r.total }
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
  const tsid = uuid()
  // A running task keeps its anchor, tools and state. The new prompt waits on disk: if a turn starts with its text it
  // is its own task (turn.start). If it was delivered into the running turn its work lands in that task's learn, its
  // search goes uncredited (no way to tell the two apart here, and a false credit is worse than none).
  const mainState = midTurn ? await readState($, s, 'main') : undefined
  const running = !midTurn ? undefined : L.turnAnchor.has(e.turnId) ? L.turnAnchor.get(e.turnId) : mainState?.task_session_id
  const defer = !!running && mainState?.task_session_id === running
  const save = (u: StateUpdate) => defer
    ? writePrivate($, pendingFile(s), JSON.stringify({ text, state: pyDumps(mergeState(undefined, u)) })) // ponytail: one slot; of two queued prompts the first is not learned
    : updateState($, L, s, 'main', u, true)
  if (!defer) {
    L.pendingMain = tsid
    L.mainSeen = 0
    await clearDeferred($, L, s)  // accepted edge (CHANGELOG): a new human prompt before the notification drops the deferred learn
    await clearTools($, L, s, 'main')
    if (await $.fs.exists(pendingFile(s))) await rm($, pendingFile(s))
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
    renderVariant: r.cohort, contents: injectedContents(r.patterns, r.ids), evalStats: evalStats(r.patterns, sr.resp.similar_patterns || []) })
  const ds = domainsSummary(sr.resp)
  if (Object.keys(ds).length) {
    L.domains = domainNames(ds)
    await $.fs.write(`${s.pdir}/domains.json`, pyDumps(ds))
  }
  const returned = sr.resp.similar_patterns || []
  await relLog($, s, searchRow({ hook: 'UserPromptSubmit', sessionId: s.sessionId, userPrompt: e.text, query, returned, injected: r.patterns,
    projectId: s.project, orgId: s.org, agentType: 'main', cohort: r.cohort, hookMs: await $.clock.now() - t0, nowIso: await nowIso($),
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
