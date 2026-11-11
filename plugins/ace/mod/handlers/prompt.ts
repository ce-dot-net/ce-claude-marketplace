// prompt.submit: the main search -> cohort render -> inject, the patterns-used state, the rejection downvote,
// the status line and session title.
import { readJson, rm, writePrivate } from '../io/fs.ts'
import { nowIso, relLog, searchRow } from '../io/log.ts'
import { SEARCH_MS, search } from '../io/spawn.ts'
import { type Load, type Sess, clearDeferred, clearTools, cohortEnv, deferredAnchor, disabled, downvoteEnabled, ensure, pendingFile, readState, touchMarker, updateState, uuid, type HookArgs, refreshMarker } from '../io/state.ts'
import { type Cohort, renderCohort } from '../lib/cohort.ts'
import { REJECTION_PREV_MAX_AGE_S, evalStats, injectedContents, rejectionMatch } from '../lib/evidence.ts'
import { num, pyDumps } from '../lib/pyjson.ts'
import { domainsSummary, renderBudget, renderCompact, renderFull, renderPatternsDict } from '../lib/render.ts'
import { type StateUpdate, mergeState } from '../lib/state.ts'
import { MACHINE_ORIGINS, domainNames, expandAbbreviations, isNoTaskCommand, skipReason } from '../lib/text.ts'
import { searchErrorLine, searchSummary, sessionTitle, statusLine, topDomains } from '../ui/status.ts'

// ace_feedback.on_human_prompt: a rejection of the previous main task -> a pending downvote with its evidenced ids.
export async function onRejection($: any, s: Sess, text: string) {
  const matched = rejectionMatch(text)
  if (!matched) return
  const prev = await readJson($, `${s.sdir}/last-main-applied.json`)
  const prevAt = num(prev?.at)  // a seconds float reads back as a PyFloat: compare its value
  const fresh = prevAt !== undefined && await $.clock.now() / 1000 - prevAt < REJECTION_PREV_MAX_AGE_S
  const ids: number[] = fresh && Array.isArray(prev.applied_log_ids) ? prev.applied_log_ids.filter((x: unknown) => Number.isInteger(x)) : []
  const sent = ids.length > 0 && await downvoteEnabled($, s)
  if (sent) await writePrivate($, `${s.sdir}/pending-downvote.json`, JSON.stringify({ applied_log_ids: ids, at: await $.clock.now() / 1000 }))
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
  if (!midTurn && !e.command && (reason === null || reason === 'prompt_too_short') && !(await disabled($, s)))
    try { await onRejection($, s, text) } catch { /* never break the prompt */ }
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
  const sr = await search($, s, query, tsid, undefined, SEARCH_MS)
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
  const kind: string | undefined = e.origin?.kind
  L.promptOrigin ??= kind || 'unclassified'
  if (kind === 'composer' || kind === 'bridge') L.humanPrompts++
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
