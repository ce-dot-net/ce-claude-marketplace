// ACE v8 production mod (DESIGN §13.1): search -> inject -> domain shift -> subagent inject -> detached learn with
// F-080 credit, in-process. The Python command hooks stay installed as the fallback and step aside while the
// mod-active marker is fresh. ace-cli is consumed as-is via $.process.run; state lives on disk in the Python formats.
import type { Register } from 'claude-code'
import { num, pyLoads, pyDumps, sanitize } from './lib/pyjson.ts'
import { renderFull, renderBudget, renderCompact, renderDomainShift, renderPatternsDict, domainsSummary, STATE_CAP } from './lib/render.ts'
import { renderCohort, traceVariant, serverFullPct, storedFullPct, RENDER_FULL_PCT_FILE, FEEDBACK_DOWNVOTE_FILE, serverDownvote, storedDownvote, type Cohort } from './lib/cohort.ts'
import { dataRootFromPluginRoot, safeComponent as safe, mergeState, reuseKey, reuseEnabled, REUSE_TTL_MS, type StateUpdate } from './lib/state.ts'
import { skipReason, MACHINE_ORIGINS, expandAbbreviations, matchDomainToPath, domainNames, basenameQuery, subagentQuery, isNoTaskCommand } from './lib/text.ts'
import { isTrivialTask, hasSubstantialWork, toolRec, buildTrace, learnArgv, detachedLearnArgv, FALLBACK_ON_3, parseDiffStat, delegatedRunning } from './lib/trace.ts'
import { parseAceReview, evalStats, selfEvalPrompt, parseUsedIds, rejectionMatch, REJECTION_PREV_MAX_AGE_S, appliedLogIds, usedPatternIds, injectedContents, type ToolRec } from './lib/evidence.ts'
import { PRIVATE_WRITE_SH, APPEND_SH } from './lib/sh.ts'
import { learnLine, searchSummary, searchErrorLine, statusLine, topDomains, sessionTitle } from './ui/status.ts'
import { searchRow } from './io/log.ts'
import { readJson, readText, rm, run, writePrivate } from './io/fs.ts'
import { logsSafe, nowIso, relLog } from './io/log.ts'
import { DOMAIN_MS, LAUNCHER_MS, SEARCH_MS, aceEnv, cliHead, engineScript, gitContext, hitResult, reuseGet, reuseStore, search } from './io/spawn.ts'
import { type Load, type Sess, classicFresh, clearDeferred, clearTools, cohortEnv, deferFile, deferredAnchor, disabled, downvoteEnabled, enqueue, ensure, pendingFile, readState, recordTool, refreshMarker, resolveSession, stateFile, takeDownvote, takeTools, touchClassic, touchMarker, updateState, uuid } from './io/state.ts'

const LEARN_LOCK_MS = 600_000              // ace_session_end.py: learn timeout 300 s + margin
// ace_feedback.on_human_prompt: a rejection of the previous main task -> a pending downvote with its evidenced ids.
async function onRejection($: any, s: Sess, text: string) {
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
async function renderArm($: any, resp: any, tag: string, attrs: string, s: Sess, seen?: Set<string>) {
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

// Reap a finished task's state; main keeps rendered-main.txt for the SessionStart compact re-inject (patterns_used_state).
async function reap($: any, L: Load, s: Sess, key: string, state: any) {
  if (key === 'main') L.mainSeen = 0
  if (key === 'main' && state?.rendered_context) await writePrivate($, `${s.sdir}/rendered-main.txt`, state.rendered_context)
  await rm($, stateFile(s, key))
  await clearTools($, L, s, key)
  L.late.delete(key)
}

// true = a learn was dispatched (the detached launcher started); 'later' = it goes out after the self-eval, which logs the line
async function learn($: any, L: Load, s: Sess, key: string, answer: string, hook: 'Stop' | 'SubagentStop', effortEvent: string | undefined, summaryCap = 2000,
  usedText = answer): Promise<boolean | 'later'> {
  const t0 = await $.clock.now()
  const agentId = key === 'main' ? undefined : key
  const recs = await takeTools($, L, s, key)
  if (key === 'main' && !recs.length && L.mainSeen > 0)  // item 4: a seen-once anomaly (Stop learned tools: 0 after Bash calls)
    await relLog($, s, { timestamp: await nowIso($), event: 'tools_mismatch', hook: 'Stop', recorded: 0, seen: L.mainSeen, source: 'mod' })
  const state = await readState($, s, key)
  if (!state) {
    await clearTools($, L, s, key)
    if (hook === 'Stop') await relLog($, s, { timestamp: await nowIso($), event: 'learn_skipped', hook, session_id: s.sessionId, reason: 'no_task_state', source: 'mod' })
    return false
  }
  const prompt: string = state.user_prompt ?? ''
  const agentType: string = agentId ? state.agent_type ?? 'unknown' : 'main'
  const skip = !prompt || isTrivialTask(prompt, s.extraPrefixes) ? 'trivial_task' : !hasSubstantialWork(recs) ? 'no_substantial_work' : null
  if (skip) {
    await reap($, L, s, key, state)
    await relLog($, s, { timestamp: await nowIso($), event: 'learn_skipped', hook, session_id: s.sessionId, reason: skip, tools: recs.length, agent_id: agentId ?? null, source: 'mod' })
    return false
  }
  const playbook: string[] = state.pattern_ids ?? []
  const rlog: Record<string, number> = state.retrieval_log_ids ?? {}
  const variant = traceVariant(state.render_variant, s.sessionId, await cohortEnv($, s))  // §31: stored label, else the conversation arm
  const tokenUsed = usedPatternIds(playbook, state.pattern_contents ?? {}, usedText, recs.map(r => r.hay).filter(Boolean).join('\n'))
  const tsid: string | undefined = state.task_session_id ?? undefined
  const effort = effortEvent || await $.env.get('CLAUDE_EFFORT') || 'normal'
  // Lock BEFORE anything async (session.end keeps the dir); state and tools are captured, so reap now: a new prompt may
  // start while the self-eval runs.
  const lock = `${s.sdir}/learn-inflight-${safe(key)}.lock`
  await $.fs.write(lock, '')
  await reap($, L, s, key, state)

  const dispatch = async (modelUsed: string[] | null): Promise<boolean> => {
    const m = new Set(modelUsed ?? []), tk = new Set(tokenUsed)
    const used = playbook.filter(id => m.has(id) || tk.has(id))  // item H: H1 ∪ H2, injected set, injected order
    const source = m.size && tk.size ? 'both' : m.size ? 'model' : tk.size ? 'tokens' : 'none'
    // item 2: per-source counts (Haiku ids past the whitelist, H2 ids), for the server team
    const bySource = { used_ids_model: playbook.filter(id => m.has(id)).length, used_ids_tokens: playbook.filter(id => tk.has(id)).length }
    // §31: used only (this agent's own tools, report, self-eval); for the 20-cap Haiku ids first, then H2 ids, injected order
    const downvote = key === 'main' ? await takeDownvote($, s) : undefined
    const { ids: applied, capped } = appliedLogIds([...used.filter(id => m.has(id)), ...used.filter(id => !m.has(id))], rlog)
    // the record a later rejection downvotes ([] too: rejecting a task without evidenced ids sends nothing)
    if (key === 'main') await writePrivate($, `${s.sdir}/last-main-applied.json`, JSON.stringify({ task_session_id: tsid ?? null, applied_log_ids: applied, at: await $.clock.now() / 1000 })).catch(() => {})
    let git: any
    try {
      git = await gitContext($, s.cwd)
      const commits = recs.filter(r => r.commit).map(r => r.commit)
      if (git && commits.length) git.session_commits = commits
    } catch { /* git context is optional */ }
    const { trace, success } = buildTrace({ userPrompt: prompt, tools: recs, answer, playbookUsed: playbook, agentType,
      tsid, agentId, parentTaskId: state.parent_task_id, retrievalId: state.retrieval_id ?? undefined, appliedLogIds: applied, usedIds: bySource, downvote,
      nowIso: await nowIso($), renderVariant: variant, conversationId: s.sessionId, effort, git, summaryCap })
    const traceFile = `${s.root}/tmp/ace-trace-${uuid()}.json`
    await writePrivate($, traceFile, pyDumps(trace))
    const row = async (sent: boolean) => ({ timestamp: await nowIso($), event: 'execution', hook, session_id: s.sessionId,
      project_id: s.project, agent_type: agentType, patterns_used_count: playbook.length, pattern_ids: playbook.slice(0, 20),
      tools_executed: recs.length, state_changing_tools: recs.filter(r => ['Edit', 'Write', 'Bash', 'mcp__', 'NotebookEdit'].some(x => r.tool.includes(x))).length,
      success, execution_time_seconds: Math.round((await $.clock.now() - t0) / 10) / 100, learning_sent: sent,
      used_ids_count: used.length, used_source: source, ...bySource, ...(capped ? { used_ids_capped: true } : {}) })
    const log = `${s.logs}/ace-relevance.jsonl`
    const python = (await readText($, `${s.root}/python_path`))?.trim()
    const verbosity = await $.env.get('ACE_VERBOSITY') || 'detailed'
    const cliLearn = learnArgv(traceFile, state.retrieval_id ?? undefined, applied, verbosity, [...await cliHead($), 'learn'])
    const engLearn = await engineScript($, 'learn.js')
    const learnCmd = engLearn  // §14: the engine learns; ace-cli only when it exits 3 (nothing sent)
      ? [...learnArgv(traceFile, state.retrieval_id ?? undefined, applied, verbosity, ['node', engLearn]), FALLBACK_ON_3, ...cliLearn]
      : cliLearn
    const argv = detachedLearnArgv({ learnArgv: learnCmd,
      trace: traceFile, lock, log, rowOk: pyDumps(await row(true)), rowFail: pyDumps(await row(false)), errLog: `${s.root}/logs/ace-hook-errors.log`, python,
      retryRow: pyDumps({ event: 'learn_retry', hook, session_id: s.sessionId, conversation_id: s.sessionId, task_session_id: tsid ?? null,
        agent_id: agentId ?? null, source: 'mod' }), cwd: s.cwd })
    const spawned = await run($, argv, { env: aceEnv(s), timeoutMs: LAUNCHER_MS })
    if (!spawned || spawned.exitCode !== 0) {  // no child will clean up, or write the metrics row
      await rm($, lock, traceFile)
      await relLog($, s, await row(false))
    }
    await relLog($, s, { timestamp: await nowIso($), event: 'learn_dispatched', hook, session_id: s.sessionId, agent_id: agentId ?? null,
      agent_type: agentType, task_session_id: tsid ?? null, parent_task_id: state.parent_task_id ?? null, retrieval_id: state.retrieval_id ?? null,
      applied_log_ids: applied.length, patterns_used: playbook.length, tools_executed: recs.length, success, spawn_exit: spawned?.exitCode ?? null,
      used_source: source, ...bySource, source: 'mod' })
    return !!spawned && spawned.exitCode === 0
  }

  // item D / H1: main agent, patterns injected -> a Haiku self-eval (review + evidenced ids) before the learn goes out.
  // Not awaited: the turn ends now; a failed or timed-out call falls back to the token evidence (H2). item 3: the
  // "learning sent" line goes out once the learn really did, with the review's parts (none at 0% or without one).
  // item 1a: non-interactive (-p, SDK): the process may exit right after this turn, so no wait; H2 only.
  if (hook === 'Stop' && playbook.length && L.interactive && (await $.env.get('ACE_SELF_EVAL')) !== '0') {  // a rejecting call falls back too
    // item 1b: session.end flushes a still-pending chain with H2 ids; whichever comes first dispatches, once.
    let fired = false
    const p = { ctl: new AbortController(), flush: () => once(null) }
    const once = (ids: string[] | null): Promise<boolean> => {
      if (fired) return Promise.resolve(false)
      fired = true
      L.pendingLearns.delete(p)
      return dispatch(ids)
    }
    L.pendingLearns.add(p)
    void selfEval($, s, prompt, answer, playbook, state.pattern_contents ?? {}, recs, p.ctl.signal).catch(() => null)
      .then(async m => {
        if (!(await once(m?.ids ?? null))) return
        const rv = m?.review
        $.ui.log(learnLine(rv && Number(rv.quality_pct) > 0 ? rv : { time_saved: rv?.time_saved }))
      })
      .catch(async err => { await rm($, lock).catch(() => {}); await relLog($, s, { timestamp: await nowIso($), event: 'error', hook, location: 'mod.self_eval', error: String(err).slice(0, 300), source: 'mod' }) })
    return 'later'
  }
  return dispatch(null)
}

const SELF_EVAL_MS = 15_000
async function selfEval($: any, s: Sess, task: string, answer: string, ids: string[], contents: Record<string, string>, recs: ToolRec[],
  signal?: AbortSignal): Promise<{ ids: string[]; review: any } | null> {
  const r = await $.model.complete({ model: 'haiku', effort: 'low', timeoutMs: SELF_EVAL_MS, prompt: selfEvalPrompt({ task, answer, ids, contents, tools: recs }) }, { signal })
  if (!r?.isAnswered || typeof r.text !== 'string') return null
  const review = parseAceReview(r.text)
  if (review && await logsSafe($, s, 'ace-review-result.json')) await $.fs.write(`${s.logs}/ace-review-result.json`, pyDumps(review))
  return { ids: parseUsedIds(r.text, ids), review }
}

async function onPrompt($: any, L: Load, e: any): Promise<any> {
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

const logSubagentError = async ($: any, s: Sess, sr: any) => relLog($, s, { timestamp: await nowIso($), event: 'error', hook: 'SubagentStart', location: 'mod.search', error: sr.error ?? null, stderr_sample: sr.stderr, pin_failed: sr.pinFailed || undefined, pin_ms: sr.pinMs, session_id: s.sessionId, source: 'mod' })

async function subagentRender($: any, s: Sess, sr: any, query: string, agentType: string, tsid: string, t0: number, parent: string | undefined, extra: any) {
  const attr = `agent-type="${String(agentType).replace(/"/g, '&quot;')}"`
  const r = await renderArm($, sr.resp, 'ace-patterns-subagent', attr, s)
  await relLog($, s, searchRow({ hook: 'SubagentStart', sessionId: s.sessionId, userPrompt: query, query, returned: sr.resp.similar_patterns || [], injected: r.patterns,
    projectId: s.project, orgId: s.org, agentType, cohort: r.cohort, hookMs: await $.clock.now() - t0, nowIso: await nowIso($),
    extra: { search_ms: sr.ms, pin_ms: sr.pinMs, pin_failed: sr.pinFailed || undefined, pin_skipped: sr.pinSkipped, truncated_for_cap: r.truncated || undefined, context_chars: r.context?.length ?? 0,
      task_session_id: tsid, parent_task_id: parent ?? null, engine: sr.engine, engine_reason: sr.engineWhy, source: 'mod', ...extra } }))
  return r
}

// A run whose prompt no hook can rewrite (a resume, a wake, a workflow placeholder): its own task, a fresh pin (§12),
// and the search waits for its first tool call, the first place this run takes context. ace_subagent_start.py: an agent
// resumed after stopping searches afresh.
async function anchorRun($: any, L: Load, s: Sess, key: string, text: string, fallback: string | undefined, agentType: string | undefined, parent: string | undefined) {
  const query = subagentQuery(text)
  await updateState($, L, s, key, { tsid: uuid(), userPrompt: query || fallback, hook: 'SubagentStart', parentTaskId: parent, agentType }, true)
  if (query && !skipReason(query, s.minChars, s.extraPrefixes)) L.late.set(key, query)
}

async function lateInject($: any, L: Load, s: Sess, key: string): Promise<string | null> {
  const query = L.late.get(key)
  if (query === undefined) return null
  L.late.delete(key)
  const st = await readState($, s, key)
  if (!st || await disabled($, s)) return null
  const t0 = await $.clock.now()
  const tsid: string = st.task_session_id
  const sr = await search($, s, query, tsid, undefined, DOMAIN_MS)
  if (!sr.resp) { await logSubagentError($, s, sr); return null }
  const r = await subagentRender($, s, sr, query, st.agent_type ?? 'unknown', tsid, t0, st.parent_task_id, { late: true })
  await updateState($, L, s, key, { ids: r.ids, retrievalId: sr.resp.retrieval_id || null, rlog: r.rlog, rendered: r.rendered, renderVariant: r.cohort,
    contents: injectedContents(r.patterns, r.ids) })
  return r.context
}

// Workflow placeholder (§13.1): the prompt agent.spawn searched for is not what the agent runs, so its patterns never
// reached it: no credit, and a fresh pin so the search stays out of the learn's session. "" says nothing (docs: a run no hook sees).
async function checkPlaceholder($: any, L: Load, s: Sess, agentId: string, prompt: string, text: string) {
  const seen = subagentQuery(prompt).slice(0, 200)
  if (!text || !seen || text.includes(seen)) return
  const st = await readState($, s, agentId)
  if (!st) return
  L.placeholders.add(prompt)
  await anchorRun($, L, s, agentId, text, undefined, st.agent_type, st.parent_task_id ?? undefined)
  const tsid = (await readState($, s, agentId))?.task_session_id ?? null
  await relLog($, s, { timestamp: await nowIso($), event: 'workflow_placeholder', hook: 'SubagentStart', session_id: s.sessionId, agent_id: agentId, task_session_id: tsid, source: 'mod' })
}

async function beforeSpawn($: any, L: Load, s: Sess, e: any) {
  const t0 = await $.clock.now()
  const tsid = uuid()     // §12: every subagent is its own ACE session; the parent's id is correlation only
  const parent = await readState($, s, e.parentAgentId ?? 'main')
  const query = subagentQuery(e.prompt)
  const state: StateUpdate = { tsid, userPrompt: query, hook: 'SubagentStart', parentTaskId: parent?.task_session_id ?? undefined, agentType: e.subagentType }
  const skip = L.placeholders.has(e.prompt) ? 'workflow_placeholder' : skipReason(query, s.minChars, s.extraPrefixes)
  if (skip) {
    await relLog($, s, { timestamp: await nowIso($), event: 'search_skipped', hook: 'SubagentStart', reason: skip, session_id: s.sessionId, project_id: s.project, source: 'mod' })
    return { out: e, state }
  }
  const cached = await reuseGet($, L, s, 'subagent', query, 'spawn:' + tsid)  // a spawn is a new agent: it has used nothing yet
  const sr: any = cached ? hitResult(cached) : await search($, s, query, tsid, undefined, SEARCH_MS)
  if (!cached) await reuseStore($, L, s, 'subagent', query, 'spawn:' + tsid, sr.resp)
  if (!sr.resp) {
    await logSubagentError($, s, sr)
    return { out: e, state }
  }
  const r = await subagentRender($, s, sr, query, e.subagentType, tsid, t0, state.parentTaskId, { workflow: e.workflow?.runId, cache_hit: !!cached })
  return { out: r.context ? { ...e, prompt: `${e.prompt}\n\n${r.context}` } : e,
    state: { ...state, ids: r.ids, retrievalId: sr.resp.retrieval_id || null, rlog: r.rlog, rendered: r.rendered, renderVariant: r.cohort,
      contents: injectedContents(r.patterns, r.ids) } }
}

// ace_domain_shift.main
async function domainShift($: any, L: Load, e: any, key: string): Promise<string | null> {
  const s = await ensure($, L)
  if (!s || await disabled($, s)) return null
  let file: any = e.file_path || e.path
  if (!file && e.tool === 'Glob') { const g = e.pattern; file = typeof g === 'string' && g.includes('/') && !g.split('/').pop()!.includes('*') ? g : null }
  if (!file || typeof file !== 'string') return null
  if (!L.domains) { const d = await readJson($, `${s.pdir}/domains.json`); if (d && typeof d === 'object') L.domains = domainNames(d) }
  if (!L.domains) return null
  const matched = L.domains.find(d => matchDomainToPath(d, file.toLowerCase()))
  if (!matched) return null
  const lastFile = `${s.sdir}/domain-last-${safe(key)}.txt`
  const readLast = async () => ((await readText($, lastFile)) ?? '').trim().toLowerCase()
  if (await readLast() === matched) return null
  // Claim BEFORE searching: parallel Reads of a batch would all see the old domain.
  const claim = `${key}\0${matched}`
  if (L.claims.has(claim)) return null
  L.claims.add(claim)
  L.lastClaim.set(key, matched)
  try {
    const last = await readLast()
    if (last === matched) return null
    const query = basenameQuery(file)
    if (!query) return null
    const t1 = await $.clock.now()
    const state = await readState($, s, key)
    const tsid: string = state?.task_session_id ?? uuid()
    const cached = await reuseGet($, L, s, 'domain', query, key)
    const sr: any = cached ? hitResult(cached) : await search($, s, query, undefined, 8, DOMAIN_MS, tsid)  // §16 P8: no pin; tsid for the state merge and --session-id
    if (!cached) await reuseStore($, L, s, 'domain', query, key, sr.resp)
    // A failed search stays retryable. Parallel domains: the newest claim writes, so the finishing order cannot flip it.
    if (sr.resp && L.lastClaim.get(key) === matched) await $.fs.write(lastFile, matched)
    const rd = sr.resp && (sr.resp.similar_patterns || []).length ? renderDomainShift(sr.resp, matched) : null
    await relLog($, s, { timestamp: await nowIso($), event: 'domain_shift', hook: 'PostToolUse', session_id: s.sessionId, project_id: s.project,
      from_domain: last, to_domain: matched, file_path: file.slice(0, 200), patterns_found: rd?.shown ?? 0, search_succeeded: !!sr.resp,
      patterns_injected: rd?.ids.length ?? 0, hook_ms: await $.clock.now() - t1, agent_id: e.agentId ?? null, cache_hit: !!cached, search_ms: sr.ms, pin_failed: sr.pinFailed || undefined, pin_skipped: sr.pinSkipped, source: 'mod' })
    if (!rd || !rd.shown) return null
    // F-080: merge the injected ids + log ids; keep the task's FIRST retrieval_id.
    await updateState($, L, s, key, { ids: rd.ids, rlog: rd.rlog, tsid, retrievalId: state?.retrieval_id ? undefined : sr.resp.retrieval_id || undefined,
      contents: injectedContents(rd.patterns, rd.ids) })
    return rd.context
  } finally { L.claims.delete(claim) }
}


// Interrupted, refused, or ended by an API error (StopFailure in place of Stop): no outcome to credit (v7.1.3 orphan ruling).
async function abstain($: any, L: Load, s: Sess, key: string, state: any, reason: string, hook: string) {
  await reap($, L, s, key, state)
  if (state) await relLog($, s, { timestamp: await nowIso($), event: 'learn_skipped', hook, session_id: s.sessionId, reason: `turn_${reason}`, agent_id: key === 'main' ? null : key, source: 'mod' })
}

export const register: Register = (on) => {
  const L: Load = { sess: null, pendingMain: undefined, pendingTitle: undefined, stopEffort: undefined, domains: null,
    turnAnchor: new Map(), tools: new Map(), spawnPrompts: new Map(), placeholders: new Set(), late: new Map(), agentTypes: new Map(),
    earlyStart: new Map(), agentEffort: new Map(), lastClaim: new Map(), markerAt: 0, claims: new Set(), queues: new Map(),
    stopDefer: null, deferred: undefined, handback: new Map(), reuseUsed: new Set(), compacted: false, mainSeen: 0,
    interactive: true, pendingLearns: new Set() }
  const effortOf = (e: any): unknown => e.effort && typeof e.effort === 'object' ? e.effort.level : e.effort

  on('session.start', async ($, e, next) => {
    const r = await next(e)
    L.interactive = e.isInteractive !== false
    try {
      L.sess = await resolveSession($, e.cwd)
      if (L.sess) await touchMarker($, L, L.sess, await $.clock.now())
    } catch { /* the Python chain takes over without a marker */ }
    return r
  })

  // item A: patterns survive a main compaction natively. session.compact (not on guarded seats) sets the flag and the
  // mod-compact marker (the Python SessionStart(compact) re-inject steps aside); prompt.compose then adds the task's
  // re-inject copy as its own section until the next prompt injects fresh.
  // The marker goes down BEFORE next(): the Python SessionStart(compact) runs inside it and must already see it.
  on('session.compact', async ($, e, next) => {
    let mark: string | null = null
    try {
      if (!e.agentId && e.trigger !== 'precompute') {
        const s = await ensure($, L)
        if (s && !(await disabled($, s))) { mark = `${s.sdir}/mod-compact`; await $.fs.write(mark, String(await $.clock.now())) }
      }
    } catch { mark = null /* the Python SessionStart(compact) hook re-injects */ }
    let r: any
    try { r = await next(e) } catch (err) { if (mark) await rm($, mark).catch(() => {}); throw err }
    if (!mark) return r
    try {
      if (r && !r.skip) {
        L.compacted = true
        const fi = mark.replace(/mod-compact$/, 'full-injected.json')
        if (await $.fs.exists(fi)) await rm($, fi)  // §31 dedupe starts over
      } else await rm($, mark)  // no compaction: a later real one must not be silenced
    } catch { /* stale marker ages out (MOD_COMPACT_S) */ }
    return r
  })

  on('prompt.compose', async ($, e, next) => {
    const r: any = await next(e)
    if (!L.compacted || !L.sess) return r
    try {
      const st = await readState($, L.sess, 'main')
      const text = st?.rendered_context || await readText($, `${L.sess.sdir}/rendered-main.txt`)
      // ponytail: subagent requests composed in this window get the section too; per-request agent scoping when compose says who asks
      if (text) return { ...r, sections: [...(r?.sections ?? []).filter((x: any) => x.id !== 'ace:patterns'), { id: 'ace:patterns', text, scope: 'session' }] }
    } catch { /* never break the prompt */ }
    return r
  })

  on('prompt.submit', async ($, e, next) => {
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
  })

  // Never clobber a custom /rename or --name title.
  on('classic.UserPromptSubmit', async ($, e: any, next) => {
    await touchClassic($, L)
    const r = await next(e)
    return L.pendingTitle && !e.session_title ? { ...r, sessionTitle: L.pendingTitle } : r
  })

  // turn.complete carries no effort; Stop does (ace_after_task._resolve_effort_level).
  on('classic.Stop', async ($, e: any, next) => {
    await refreshMarker($, L, true)  // handoff to the Python hook of this event  // Stop is the Python hook that would reap the state, and it runs after this one
    await touchClassic($, L)
    const raw = effortOf(e)
    if (typeof raw === 'string' && raw) L.stopEffort = raw
    L.stopDefer = delegatedRunning(e.background_tasks) ? (e.background_tasks as any[]).map(b => String(b?.type)) : null
    return next(e)
  })
  on('classic.SubagentStop', async ($, e: any, next) => {
    await refreshMarker($, L, true)  // handoff to the Python hook of this event
    await touchClassic($, L)
    const raw = effortOf(e)
    if (typeof raw === 'string' && raw && e.agent_id) L.agentEffort.set(e.agent_id, raw)
    return next(e)
  })

  on('turn.start', async ($, e, next) => {
    await refreshMarker($, L)
    try {
      if (e.agentId === undefined) {
        let anchor: string | null | undefined = L.pendingMain
        if (anchor === undefined) { // no prompt.submit bound: a prompt that waited for this turn, else what is on disk (hot reload)
          const s = await ensure($, L)
          const pend = s && await readJson($, pendingFile(s))
          if (s && pend?.text && e.text.includes(String(pend.text).slice(0, 200))) {
            await enqueue(L, stateFile(s, 'main'), () => writePrivate($, stateFile(s, 'main'), pend.state))
            await rm($, pendingFile(s))
            await clearTools($, L, s, 'main')
            L.mainSeen = 0
            anchor = pyLoads(pend.state).task_session_id
          } else anchor = (s && (await readState($, s, 'main'))?.task_session_id) ?? null
        }
        L.turnAnchor.set(e.turnId, anchor)
        L.pendingMain = undefined
      } else {
        const s = await ensure($, L)
        const prompt = L.spawnPrompts.get(e.agentId)
        if (s && prompt !== undefined) {
          L.spawnPrompts.delete(e.agentId)
          await checkPlaceholder($, L, s, e.agentId, prompt, e.text)
        } else if (s && !(await readState($, s, e.agentId))) {
          const type = L.agentTypes.get(e.agentId)
          if (type === undefined) L.earlyStart.set(e.agentId, e.text)
          else if (e.text && !(await disabled($, s))) {  // a teammate woken by a message: no agent.spawn, and its last run's state is reaped
            const parent = await readState($, s, 'main')
            await anchorRun($, L, s, e.agentId, e.text, undefined, type, parent?.task_session_id ?? undefined)
          }
        }
      }
    } catch { /* bookkeeping never breaks a turn */ }
    return next(e)
  })

  on('agent.spawn', async ($, e, next) => {
    await refreshMarker($, L, true)  // handoff to the Python hook of this event
    let out: any = e, pending: any = null
    try {
      const s = await ensure($, L)
      const forkSearch = String(await $.env.get('ACE_SUBAGENT_INJECT_FORKS') ?? '') === '1'
      if (s && (!e.fork || !e.resume) && !(await disabled($, s))) {
        if (e.fork && !forkSearch) {  // §16 P7: a fork inherits the parent context incl. the injected block
          const parent = await readState($, s, e.parentAgentId ?? 'main')
          pending = { out: e, state: { tsid: uuid(), userPrompt: subagentQuery(e.prompt), hook: 'SubagentStart',
            parentTaskId: parent?.task_session_id ?? undefined, agentType: e.subagentType || 'fork' } }
          await relLog($, s, { timestamp: await nowIso($), event: 'search_skipped', hook: 'SubagentStart', reason: 'fork_inherits_context', session_id: s.sessionId, project_id: s.project, source: 'mod' })
        } else if (e.resume) {  // a rewrite of a resume is not applied. Same run with state: same task (§12). Reaped: a new one.
          const key = e.resume.agentId
          L.agentTypes.set(key, e.subagentType)
          if (!(await readState($, s, key))) {
            const parent = await readState($, s, e.parentAgentId ?? 'main')
            await anchorRun($, L, s, key, e.prompt, e.description, e.subagentType, parent?.task_session_id ?? undefined)
          }
        } else {
          pending = await beforeSpawn($, L, s, e)
          out = pending.out
        }
      }
    } catch { pending = null; out = e }
    const res: any = await next(out)
    try {
      const s = L.sess
      if (pending && s && res.agentId && !res.deny) {
        // The docs do not order this against the agent's first events: merge, so nothing it already did is lost.
        const key = res.agentId as string
        // Persist BEFORE publishing the type: a turn.start that sees a known type but no state reads it as a woken
        // teammate and re-anchors the run (second tsid, second search). Unknown type = earlyStart, harmless.
        await updateState($, L, s, key, pending.state)
        L.agentTypes.set(key, (e as any).subagentType)
        const early = L.earlyStart.get(key)
        L.earlyStart.delete(key)
        if ((e as any).workflow) {
          if (early === undefined) L.spawnPrompts.set(key, (e as any).prompt)
          else await checkPlaceholder($, L, s, key, (e as any).prompt, early)
        }
      }
    } catch { /* state failure: this subagent simply is not learned */ }
    return res
  })

  on('tool.call', async ($, e, next) => {
    await refreshMarker($, L, true)  // handoff to the Python hook of this event
    const t0 = Date.now()
    const r: any = await next(e)
    await refreshMarker($, L)  // the call itself can outlast the marker
    const key = (e as any).agentId ?? 'main'
    if (key === 'main') L.mainSeen++
    let s: Sess | null = null
    try {
      s = await ensure($, L)
      if (s) await recordTool($, L, s, key, toolRec(e.tool, e, r.result, !!r.isError, r.deny, t0, Date.now()))
      if (e.tool === 'SubagentHandback' && key !== 'main' && typeof (e as any).message === 'string') L.handback.set(key, (e as any).message)
    } catch { /* accumulation never breaks a tool call */ }
    const contexts: string[] = []
    try {
      const late = s && !r.deny ? await lateInject($, L, s, key) : null
      if (late) contexts.push(late)
      if (!r.deny && !r.isError && ['Read', 'Glob', 'Grep'].includes(e.tool)) {
        const shift = await domainShift($, L, e, key)
        if (shift) contexts.push(shift)
      }
    } catch { /* injection never breaks a tool call */ }
    return contexts.length ? { ...r, context: [...(r.context ?? []), ...contexts] } : r
  })

  on('turn.complete', async ($, e, next) => {
    const res = await next(e)
    let s: Sess | null = null
    let line: string | undefined  // item 2: shown beneath the answer when this hook dispatched the main learn
    try {
      s = await ensure($, L)
      if (!s) return res
      if (!(await classicFresh($, s))) return res  // classic.* hooks are filtered on this seat: the Python Stop/SubagentStop learns
      const agentId = (e as any).agentId as string | undefined
      if (agentId === undefined) {
        const review = parseAceReview(e.answer)
        if (review && await logsSafe($, s, 'ace-review-result.json')) await $.fs.write(`${s.logs}/ace-review-result.json`, pyDumps(review))
        const state = await readState($, s, 'main')
        // undefined = this load never heard the turn start (reload): the task on disk is that turn's. null = machine turn.
        const anchor = L.turnAnchor.has(e.turnId) ? L.turnAnchor.get(e.turnId) : state?.task_session_id
        L.turnAnchor.delete(e.turnId)
        const effort = L.stopEffort; L.stopEffort = undefined
        const running = L.stopDefer; L.stopDefer = null
        if (!anchor || (state && state.task_session_id !== anchor)) await clearTools($, L, s, 'main')
        else if (e.reason !== 'answer' || e.isAborted) { await clearDeferred($, L, s); await abstain($, L, s, 'main', state, e.reason, 'Stop') }
        else if (running && state) {  // §16 P2: state, tools and F-080 ids stay for the Stop after the notification
          L.deferred = anchor
          await $.fs.write(deferFile(s), anchor)
          const types: Record<string, number> = {}
          for (const t of running) types[t] = (types[t] ?? 0) + 1
          await relLog($, s, { timestamp: await nowIso($), event: 'learn_deferred', hook: 'Stop', session_id: s.sessionId, types, task_session_id: anchor, source: 'mod' })
        } else {
          await clearDeferred($, L, s)
          if ((await learn($, L, s, 'main', e.answer, 'Stop', effort)) === true) line = learnLine(review)
        }
      } else {
        const effort = L.agentEffort.get(agentId)
        const handback = L.handback.get(agentId)  // §16 P1: the delivered report, not the closing line
        L.agentEffort.delete(agentId); L.earlyStart.delete(agentId); L.handback.delete(agentId)
        if (e.reason !== 'answer' || e.isAborted) await abstain($, L, s, agentId, await readState($, s, agentId), e.reason, 'SubagentStop')
        else await learn($, L, s, agentId, handback || e.answer, 'SubagentStop', effort, handback ? 4000 : 2000,
          [handback, e.answer].filter(Boolean).join('\n'))  // §31: handback report + closing message, as ace_after_task
      }
    } catch (err) {
      if (s) await relLog($, s, { timestamp: await nowIso($), event: 'error', hook: 'Stop', location: 'mod.turn.complete', error: String(err).slice(0, 300), source: 'mod' })
    }
    return line ? { ...res, text: line } : res
  })

  on('session.end', async ($, e, next) => {
    const s = L.sess ?? await ensure($, L).catch(() => null)
    // item 1b: the process exits after this; a self-eval still waiting would take its learn with it. Stop waiting, send H2.
    for (const p of [...L.pendingLearns]) { p.ctl.abort(); await p.flush().catch(() => false) }
    try {
      if (s) {
        // A detached learn may still run (it owns its lock): keep the dir until the lock is stale, as ace_session_end.py.
        const now = await $.clock.now()
        const entries: any[] = await $.fs.list(s.sdir).catch(() => [])
        let busy = false
        for (const f of entries) {
          if (!/^learn-inflight-.*\.lock$/.test(f.name)) continue
          const st = await $.fs.stat(`${s.sdir}/${f.name}`).catch(() => null)
          if (st && now - st.mtimeMs < LEARN_LOCK_MS) busy = true
        }
        if (!busy) await rm($, s.sdir)
      }
    } catch { /* never block the exit */ }
    L.tools.clear(); L.turnAnchor.clear(); L.spawnPrompts.clear(); L.late.clear(); L.agentTypes.clear(); L.earlyStart.clear()
    L.agentEffort.clear(); L.domains = null; L.sess = null; L.markerAt = 0
    return next(e)
  })
}
