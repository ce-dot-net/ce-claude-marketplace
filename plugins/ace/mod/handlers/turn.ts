// turn.start / turn.complete: task anchors, the learn (Haiku self-eval, F-080 credit, detached launcher), abstain/reap.
import { readText, rm, run, writePrivate, readJson } from '../io/fs'
import { SINK_WRITE_SH } from '../lib/sh'
import { logsSafe, nowIso, relLog } from '../io/log'
import { LAUNCHER_MS, aceEnv, cliHead, engineScript, gitContext, ids } from '../io/spawn'
import { authHeld, noteDeadAuth } from '../io/auth'
import { type Load, type Sess, clearTools, cohortEnv, fullStepsEnabled, readState, stateFile, takeDownvote, takeFollowup, takeTools, takeUpvote, followupTargetFile, followupMode, uuid, type HookArgs, classicFresh, clearDeferred, deferFile, disabled, enqueue, ensure, pendingFile, pendingFile830, pendingMatches, readOrigin, refreshMarker } from '../io/state'
import { appliedControlPct, layoutLabel, traceVariant } from '../lib/cohort'
import { type ToolRec, appliedLogIds, parseAceReview, parseUsedIds, selfEvalPrompt, usedPatternIds } from '../lib/evidence'
import { pyDumps, pyLoads } from '../lib/pyjson'
import { answerTail } from '../lib/rejection'
import { safeComponent as safe } from '../lib/state'
import { FALLBACK_ON_3, OUTCOME_RULE, buildTrace, detachedLearnArgv, hardCapBytes, hasSubstantialWork, textCapChars, isTrivialTask, learnArgv, reclaimTrace } from '../lib/trace'
import { learnLine } from '../ui/status'
import { anchorRun, checkPlaceholder } from './agent'

// Reap a finished task's state; main keeps rendered-main.txt for the SessionStart compact re-inject (patterns_used_state).
export async function reap($: any, L: Load, s: Sess, key: string, state: any) {
  if (key === 'main') L.mainSeen = 0
  if (key === 'main' && state?.rendered_context) await writePrivate($, `${s.sdir}/rendered-main.txt`, state.rendered_context)
  await rm($, stateFile(s, key))
  await clearTools($, L, s, key)
  L.late.delete(key)
}
// true = a learn was dispatched (the detached launcher started); 'later' = it goes out after the self-eval, which logs the line
export async function learn($: any, L: Load, s: Sess, key: string, answer: string, hook: 'Stop' | 'SubagentStop', effortEvent: string | undefined,
  legacySummaryCap = 2000, usedText = answer): Promise<boolean | 'later'> {
  const t0 = await $.clock.now()
  const agentId = key === 'main' ? undefined : key
  const recs = await takeTools($, L, s, key)
  if (key === 'main' && !recs.length && L.mainSeen > 0)  // item 4: a seen-once anomaly (Stop learned tools: 0 after Bash calls)
    await relLog($, s, { timestamp: await nowIso($), event: 'tools_mismatch', hook: 'Stop', recorded: 0, seen: L.mainSeen, source: 'mod' })
  const state = await readState($, s, key)
  // 8.2.9: every main Stop with a task state first records it with [] ids (skipped tasks stay so; a turn without state, e.g. a
  // task-notification, keeps the previous record): a rejection must hit the task it rejected, never an older one. The real
  // record further down overwrites it once the evidenced ids are known (after the self-eval).
  const noteMain = async () => {
    if (key === 'main' && hook === 'Stop')
      await writePrivate($, `${s.sdir}/last-main-applied.json`, JSON.stringify({ task_session_id: state?.task_session_id ?? null, applied_log_ids: [], at: await $.clock.now() / 1000, answer_tail: answerTail(answer), retrieval_id: state?.retrieval_id ?? null })).catch(() => {})  // 8.4.3: the target of an unresolved vote (the follow-up target has its own file)
  }
  if (!state) {
    await clearTools($, L, s, key)
    if (hook === 'Stop') await relLog($, s, { timestamp: await nowIso($), event: 'learn_skipped', hook, session_id: s.sessionId, reason: 'no_task_state', source: 'mod' })
    return false
  }
  await noteMain()  // before the self-eval window: a quick rejection then finds [] (empty_ids), never an older task's ids
  const prompt: string = state.user_prompt ?? ''
  const agentType: string = agentId ? state.agent_type ?? 'unknown' : 'main'
  const skip = !prompt || isTrivialTask(prompt, s.extraPrefixes) ? 'trivial_task' : !hasSubstantialWork(recs) ? 'no_substantial_work' : null
  if (skip) {
    await reap($, L, s, key, state)
    await relLog($, s, { timestamp: await nowIso($), event: 'learn_skipped', hook, session_id: s.sessionId, reason: skip, tools: recs.length, agent_id: agentId ?? null, source: 'mod' })
    return false
  }
  // 8.4.1: a held token (io/auth.ts): nothing goes out. Decided here, before the lock and the Haiku self-eval: no model call, no
  // pending vote taken, no last-main-applied record; the trace (H2 evidence only) is PARKED in the trace queue (--enqueue) and sent
  // by the next good learn's replay. The sink sends nothing anyway: it keeps its trace.
  // 8.4.2: an earlier learn child's 401 (its dead/ auth entry) holds here already, not only on the next prompt
  const sinkSet = !!(await $.env.get('ACE_TRACE_SINK'))?.trim()
  if (!sinkSet) await noteDeadAuth($, s, L)
  const park = !sinkSet && await authHeld($, s)
  const playbook: string[] = state.pattern_ids ?? []
  const rlog: Record<string, number> = state.retrieval_log_ids ?? {}
  const cenv = await cohortEnv($, s)
  const variant = traceVariant(state.render_variant, s.sessionId, cenv), controlPct = typeof state.render_control_pct === 'number' ? state.render_control_pct : appliedControlPct(cenv)  // §31: stored label, else the conversation arm; 8.4.3: the share frozen at render
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
    const modelList = playbook.filter(id => m.has(id)), tokenList = playbook.filter(id => tk.has(id))
    const bySource = { used_ids_model: modelList.length, used_ids_tokens: tokenList.length }
    // §31: used only (this agent's own tools, report, self-eval); for the 20-cap Haiku ids first, then H2 ids, injected order
    const dv = key === 'main' && !park ? await takeDownvote($, s, tsid) : undefined
    const downvote = dv?.ids
    // one feedback per trace: a pending downvote wins; a pending upvote then waits for the next main trace (within 6 h)
    const uv = key === 'main' && !park && !dv ? await takeUpvote($, s, tsid) : undefined  // dv: an unresolved downvote has [] ids
    // 8.4.3: the pending follow-up (server-side judging), main only, never while parked
    const followup = key === 'main' && !park ? await takeFollowup($, s, state.retrieval_id, L) : undefined
    const { ids: applied, capped } = appliedLogIds([...used.filter(id => m.has(id)), ...used.filter(id => !m.has(id))], rlog)
    // the record a later rejection downvotes ([] too: rejecting a task without evidenced ids sends nothing); 8.4.3: its retrieval_id is
    // the target of a later follow-up (server-side judging)
    if (key === 'main' && !park) await writePrivate($, `${s.sdir}/last-main-applied.json`, JSON.stringify({ task_session_id: tsid ?? null, applied_log_ids: applied, at: await $.clock.now() / 1000, answer_tail: answerTail(answer), retrieval_id: state.retrieval_id ?? null })).catch(() => {})
    if (key === 'main' && !park && hook === 'Stop' && (await followupMode($, s)) !== 'off')  // 8.4.3: the follow-up target, only with the final record, only while follow-ups are on
      await writePrivate($, followupTargetFile(s), JSON.stringify({ target_retrieval_id: state.retrieval_id ?? null, applied_log_ids: applied, task_session_id: tsid ?? null, at: await $.clock.now() / 1000 })).catch(() => {})
    let git: any
    try {
      git = await gitContext($, s.cwd)
      const commits = recs.filter(r => r.commit).map(r => r.commit)
      if (git && commits.length) git.session_commits = commits
    } catch { /* git context is optional */ }
    const { trace, success, failed_steps, cap, textCaps } = buildTrace({ userPrompt: prompt, tools: recs, answer, playbookUsed: playbook, agentType,
      tsid, agentId, parentTaskId: state.parent_task_id, retrievalId: state.retrieval_id ?? undefined, forkOf: agentId ? state.fork_of_retrieval_id ?? undefined : undefined, appliedLogIds: applied, evidenceSource: source, usedIds: { ...bySource, used_ids_model_list: modelList, used_ids_tokens_list: tokenList }, downvote, downvoteDetect: dv, upvote: uv?.ids, upvoteDetect: uv, followup,
      nowIso: await nowIso($), renderVariant: variant, renderControlPct: controlPct, renderLayout: state.render_layout, conversationId: s.sessionId, effort, git, textCap: textCapChars(await $.env.get('ACE_TEXT_HARD_CAP_CHARS')),
      pluginVersion: s.clientId.slice(s.clientId.lastIndexOf('/') + 1),
      interactive: L.interactive, ...await readOrigin($, s), hardCap: hardCapBytes(await $.env.get('ACE_TRACE_HARD_CAP_BYTES')), fullSteps: await fullStepsEnabled($, s), legacySummaryCap })
    // full steps: how often the hard cap bites (sizes only, never content)
    for (const c of textCaps) await relLog($, s, { timestamp: await nowIso($), event: 'text_cap_hit', hook, session_id: s.sessionId, agent_id: agentId ?? null, task_session_id: tsid ?? null, ...c, source: 'mod' })
    if (cap) await relLog($, s, { timestamp: await nowIso($), event: 'trace_cap_hit', hook, session_id: s.sessionId, agent_id: agentId ?? null, task_session_id: tsid ?? null, ...cap, source: 'mod' })
    const qid = uuid()  // 8.1.4: the trace queue id = the engine's Idempotency-Key = the temp file name
    // ACE_TRACE_SINK=file:<absolute dir>: the finished trace (what engine/learn.js POSTs to /traces: retrieval_id and applied_log_ids
    // are already in it) goes to <dir>/ace-trace-<Idempotency-Key>.json and NOTHING is sent: no launcher, no engine, no ace-cli
    // fallback, no queue. A set but invalid value fails closed (nothing sent, logged). Search is untouched.
    const sinkEnv = (await $.env.get('ACE_TRACE_SINK'))?.trim()
    if (sinkEnv) {
      const dir = /^file:(\/.+)$/.exec(sinkEnv)?.[1]?.replace(/\/+$/, '')
      const body = pyDumps(trace), path = dir ? `${dir}/ace-trace-${qid}.json` : null
      let error: string | null = dir ? null : 'invalid_sink'
      if (path) {  // F9: SINK_WRITE_SH never chmods an existing dir
        const r = await run($, ['/bin/sh', '-c', SINK_WRITE_SH, 'sh', path], { stdin: body })
        if (!r || r.exitCode !== 0) error = 'write_failed'
      }
      await rm($, lock).catch(() => {})
      await relLog($, s, { timestamp: await nowIso($), event: 'trace_sinked', hook, session_id: s.sessionId, agent_id: agentId ?? null, task_session_id: tsid ?? null,
        trace_id: qid, path, bytes: body.length, steps: trace.trajectory.length, error, source: 'mod' })
      return false
    }
    const traceFile = `${s.root}/tmp/ace-trace-${qid}.json`
    await writePrivate($, traceFile, pyDumps(trace))
    const row = async (sent: boolean) => ({ timestamp: await nowIso($), event: 'execution', hook, session_id: s.sessionId,
      project_id: s.project, agent_type: agentType, patterns_used_count: playbook.length, pattern_ids: playbook.slice(0, 20),
      tools_executed: recs.length, state_changing_tools: recs.filter(r => ['Edit', 'Write', 'Bash', 'mcp__', 'NotebookEdit'].some(x => r.tool.includes(x))).length,
      success, failed_steps, outcome_rule: OUTCOME_RULE, execution_time_seconds: Math.round((await $.clock.now() - t0) / 10) / 100, learning_sent: sent,
      used_ids_count: used.length, used_source: source, ...bySource, ...(capped ? { used_ids_capped: true } : {}),
      source: 'mod', agent_id: agentId ?? null, task_session_id: tsid ?? null, render_cohort: variant ? variant + layoutLabel(state.render_layout) : null })  // 8.1.0 audit
    const log = `${s.logs}/ace-relevance.jsonl`
    const python = (await readText($, `${s.root}/python_path`))?.trim()
    const verbosity = await $.env.get('ACE_VERBOSITY') || 'detailed'
    const cliLearn = [...learnArgv(traceFile, state.retrieval_id ?? undefined, applied, verbosity, [...await cliHead($), 'learn']), ...ids(s)]
    const engLearn = await engineScript($, 'learn.js')
    const learnCmd = engLearn  // §14: the engine learns; ace-cli only when it exits 3 (nothing sent)
      ? [...learnArgv(traceFile, state.retrieval_id ?? undefined, applied, verbosity, ['node', engLearn]), '--idempotency-key', qid, ...ids(s), FALLBACK_ON_3, ...cliLearn]
      : cliLearn
    const utils = `${$.plugin.root}/shared-hooks/utils`
    const queue = pyDumps({ id: qid, root: s.root, utils, log, cwd: s.logRoot, on: (await $.env.get('ACE_TRACE_QUEUE')) !== '0',
      meta: { org: s.org ?? null, project: s.project, retrieval_id: state.retrieval_id ?? null, applied_log_ids: applied, hook,
        agent_type: agentType, session_id: s.sessionId } })
    if (park) {  // the launcher's reclaim path entry point: error class not_sent (requeue), never dead/ auth, so it renews no hold
      const q = await run($, [python || 'python3', '-I', `${utils}/ace_trace_queue.py`, '--enqueue', traceFile, queue], { timeoutMs: 5000 })
      const enqueued = !!q && q.exitCode === 0
      await rm($, lock, traceFile)
      await relLog($, s, { timestamp: await nowIso($), event: 'learn_parked', reason: 'auth_held', hook, session_id: s.sessionId, agent_id: agentId ?? null,
        agent_type: agentType, task_session_id: tsid ?? null, trace_id: qid, enqueued, used_source: source, source: 'mod' })
      if (!enqueued) await relLog($, s, { timestamp: await nowIso($), event: 'learn_lost', reason: 'enqueue_failed',
        error_class: 'not_sent', attempts: 1, trace_id: qid, agent_type: agentType, hook, project_id: s.project, session_id: s.sessionId, source: 'mod' })
      return false
    }
    const argv = detachedLearnArgv({ learnArgv: learnCmd,
      trace: traceFile, lock, log, rowOk: pyDumps(await row(true)), rowFail: pyDumps(await row(false)), errLog: `${s.root}/logs/ace-hook-errors.log`, python,
      retryRow: pyDumps({ event: 'learn_retry', hook, session_id: s.sessionId, conversation_id: s.sessionId, task_session_id: tsid ?? null,
        agent_id: agentId ?? null, source: 'mod' }), cwd: s.logRoot, queue })
    const spawned = await run($, argv, { env: aceEnv(s), timeoutMs: LAUNCHER_MS })
    if (!spawned || spawned.exitCode !== 0) {
      // 8.1.4: the launcher may have started the child before it failed or was killed at LAUNCHER_MS; removing the
      // trace here was the ENOENT race. Claim it by rename first: success = no child has it (nothing was sent), so it
      // is queued; failure = the child owns it, and writes the rows and releases the lock itself.
      const parked = await reclaimTrace((argv: string[]) => run($, argv), traceFile)
      if (parked) {
        const q = await run($, [python || 'python3', '-I', `${utils}/ace_trace_queue.py`, '--enqueue', parked, queue], { timeoutMs: 5000 })
        await rm($, lock, parked)
        await relLog($, s, await row(false))
        if (!q || q.exitCode !== 0) await relLog($, s, { timestamp: await nowIso($), event: 'learn_lost', reason: 'enqueue_failed',
          error_class: 'not_sent', attempts: 1, trace_id: qid, agent_type: agentType, hook, project_id: s.project, session_id: s.sessionId, source: 'mod' })
      }
    }
    await relLog($, s, { timestamp: await nowIso($), event: 'learn_dispatched', hook, session_id: s.sessionId, agent_id: agentId ?? null,
      agent_type: agentType, task_session_id: tsid ?? null, parent_task_id: state.parent_task_id ?? null, retrieval_id: state.retrieval_id ?? null,
      applied_log_ids_count: applied.length, patterns_used: playbook.length, tools_executed: recs.length, success, spawn_exit: spawned?.exitCode ?? null,
      used_source: source, ...bySource, source: 'mod' })
    return !!spawned && spawned.exitCode === 0
  }

  // item D / H1: main agent, patterns injected -> a Haiku self-eval (review + evidenced ids) before the learn goes out.
  // Not awaited: the turn ends now; a failed or timed-out call falls back to the token evidence (H2). item 3: the
  // "learning sent" line goes out once the learn really did, with the review's parts (none at 0% or without one).
  // item 1a: non-interactive (-p, SDK): the process may exit right after this turn, so no wait; H2 only.
  if (!park && hook === 'Stop' && playbook.length && L.interactive !== false && (await $.env.get('ACE_SELF_EVAL')) !== '0') {  // a rejecting call falls back too
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
export const SELF_EVAL_MS = 15_000
export async function selfEval($: any, s: Sess, task: string, answer: string, ids: string[], contents: Record<string, string>, recs: ToolRec[],
  signal?: AbortSignal): Promise<{ ids: string[]; review: any } | null> {
  const r = await $.model.complete({ model: 'haiku', effort: 'low', timeoutMs: SELF_EVAL_MS, prompt: selfEvalPrompt({ task, answer, ids, contents, tools: recs }) }, { signal })
  if (!r?.isAnswered || typeof r.text !== 'string') return null
  const review = parseAceReview(r.text)
  if (review && await logsSafe($, s, 'ace-review-result.json')) await $.fs.write(`${s.logs}/ace-review-result.json`, pyDumps(review))
  return { ids: parseUsedIds(r.text, ids), review }
}
// Interrupted, refused, or ended by an API error (StopFailure in place of Stop): no outcome to credit (v7.1.3 orphan ruling).
export async function abstain($: any, L: Load, s: Sess, key: string, state: any, reason: string, hook: string) {
  await reap($, L, s, key, state)
  if (state) await relLog($, s, { timestamp: await nowIso($), event: 'learn_skipped', hook, session_id: s.sessionId, reason: `turn_${reason}`, agent_id: key === 'main' ? null : key, source: 'mod' })
}

export async function turnStart($: HookArgs<'turn.start'>[0], L: Load, e: HookArgs<'turn.start'>[1], next: HookArgs<'turn.start'>[2]) {
  await refreshMarker($, L)
  try {
    if (e.agentId === undefined) {
      let anchor: string | null | undefined = L.pendingMain
      if (anchor === undefined) { // no prompt.submit bound: a prompt that waited for this turn, else what is on disk (hot reload)
        const s = await ensure($, L)
        const pend = s && (await readJson($, pendingFile(s)) ?? await readJson($, pendingFile830(s)))  // Round 10 / L2: an 8.3.0 file too
        if (s && pend && pendingMatches(pend, e.text)) {
          await enqueue(L, stateFile(s, 'main'), () => writePrivate($, stateFile(s, 'main'), pend.state))
          await rm($, pendingFile(s), pendingFile830(s))
          await clearTools($, L, s, 'main')
          L.mainSeen = 0
          const tsid = pyLoads(pend.state)?.task_session_id
          anchor = typeof tsid === 'string' && tsid ? tsid : null  // never store undefined: undefined means "this load never heard the turn"
        } else anchor = (s && (await readState($, s, 'main'))?.task_session_id) ?? null
      }
      L.turnAnchor.set(e.turnId, anchor as string | null)
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
}

export async function turnComplete($: HookArgs<'turn.complete'>[0], L: Load, e: HookArgs<'turn.complete'>[1], next: HookArgs<'turn.complete'>[2]) {
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
      // 8.3.0 (S1): a main answer to a HUMAN prompt that made no task (a short "warum?") is what a following reply reacts to: it replaces the
      // rejection record (no ids), so that reply cannot downvote the task before. A task-notification turn keeps the record (humanPrompt false).
      const human = L.humanPrompt; L.humanPrompt = false
      // 8.4.3: a human turn ends the old follow-up target before anything branches (only this turn's final record may set a new one)
      if ((human || e.reason !== 'answer' || e.isAborted || running) && await $.fs.exists(followupTargetFile(s)).catch(() => false))  // no rm process when there is none
        await rm($, followupTargetFile(s)).catch(() => {})
      if (!anchor && human && e.reason === 'answer' && !e.isAborted)
        await writePrivate($, `${s.sdir}/last-main-applied.json`, JSON.stringify({ task_session_id: null, applied_log_ids: [], at: await $.clock.now() / 1000, answer_tail: answerTail(e.answer), retrieval_id: null })).catch(() => {})
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
      else await learn($, L, s, agentId, handback || e.answer, 'SubagentStop', effort, handback ? 4000 : 2000,  // the cap only when full steps are off
        [handback, e.answer].filter(Boolean).join('\n'))  // §31: handback report + closing message, as ace_after_task
    }
  } catch (err) {
    if (s) await relLog($, s, { timestamp: await nowIso($), event: 'error', hook: 'Stop', location: 'mod.turn.complete', error: String(err).slice(0, 300), source: 'mod' })
  }
  return line ? { ...res, text: line } : res
}
