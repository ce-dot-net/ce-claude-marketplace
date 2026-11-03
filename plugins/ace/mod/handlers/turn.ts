// turn.start / turn.complete: task anchors, the learn (Haiku self-eval, F-080 credit, detached launcher), abstain/reap.
import { readText, rm, run, writePrivate } from '../io/fs.ts'
import { logsSafe, nowIso, relLog } from '../io/log.ts'
import { LAUNCHER_MS, aceEnv, cliHead, engineScript, gitContext } from '../io/spawn.ts'
import { type Load, type Sess, clearTools, cohortEnv, readState, stateFile, takeDownvote, takeTools, uuid } from '../io/state.ts'
import { traceVariant } from '../lib/cohort.ts'
import { type ToolRec, appliedLogIds, parseAceReview, parseUsedIds, selfEvalPrompt, usedPatternIds } from '../lib/evidence.ts'
import { pyDumps } from '../lib/pyjson.ts'
import { safeComponent as safe } from '../lib/state.ts'
import { FALLBACK_ON_3, buildTrace, detachedLearnArgv, hasSubstantialWork, isTrivialTask, learnArgv } from '../lib/trace.ts'
import { learnLine } from '../ui/status.ts'

// Reap a finished task's state; main keeps rendered-main.txt for the SessionStart compact re-inject (patterns_used_state).
export async function reap($: any, L: Load, s: Sess, key: string, state: any) {
  if (key === 'main') L.mainSeen = 0
  if (key === 'main' && state?.rendered_context) await writePrivate($, `${s.sdir}/rendered-main.txt`, state.rendered_context)
  await rm($, stateFile(s, key))
  await clearTools($, L, s, key)
  L.late.delete(key)
}
// true = a learn was dispatched (the detached launcher started); 'later' = it goes out after the self-eval, which logs the line
export async function learn($: any, L: Load, s: Sess, key: string, answer: string, hook: 'Stop' | 'SubagentStop', effortEvent: string | undefined, summaryCap = 2000,
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
