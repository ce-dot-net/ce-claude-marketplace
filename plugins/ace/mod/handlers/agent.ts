// agent.spawn: the subagent search + inject (fork, resume and workflow-placeholder rules), and the anchors a run
// gets when no hook can rewrite its prompt.
import { renderArm } from './prompt.ts'
import { nowIso, relLog, searchRow } from '../io/log.ts'
import { SEARCH_MS, hitResult, reuseGet, reuseStore, search } from '../io/spawn.ts'
import { type Load, type Sess, readState, updateState, uuid, type HookArgs, disabled, ensure, refreshMarker } from '../io/state.ts'
import { injectedContents } from '../lib/evidence.ts'
import { type StateUpdate } from '../lib/state.ts'
import { skipReason, subagentQuery } from '../lib/text.ts'

export async function logSubagentError($: any, s: Sess, sr: any) { return relLog($, s, { timestamp: await nowIso($), event: 'error', hook: 'SubagentStart', location: 'mod.search', error: sr.error ?? null, stderr_sample: sr.stderr, pin_failed: sr.pinFailed || undefined, pin_ms: sr.pinMs, session_id: s.sessionId, source: 'mod' }) }
export async function subagentRender($: any, s: Sess, sr: any, query: string, agentType: string, tsid: string, t0: number, parent: string | undefined, extra: any) {
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
export async function anchorRun($: any, L: Load, s: Sess, key: string, text: string, fallback: string | undefined, agentType: string | undefined, parent: string | undefined) {
  const query = subagentQuery(text)
  await updateState($, L, s, key, { tsid: uuid(), userPrompt: query || fallback, hook: 'SubagentStart', parentTaskId: parent, agentType }, true)
  if (query && !skipReason(query, s.minChars, s.extraPrefixes)) L.late.set(key, query)
}
// Workflow placeholder (§13.1): the prompt agent.spawn searched for is not what the agent runs, so its patterns never
// reached it: no credit, and a fresh pin so the search stays out of the learn's session. "" says nothing (docs: a run no hook sees).
export async function checkPlaceholder($: any, L: Load, s: Sess, agentId: string, prompt: string, text: string) {
  const seen = subagentQuery(prompt).slice(0, 200)
  if (!text || !seen || text.includes(seen)) return
  const st = await readState($, s, agentId)
  if (!st) return
  L.placeholders.add(prompt)
  await anchorRun($, L, s, agentId, text, undefined, st.agent_type, st.parent_task_id ?? undefined)
  const tsid = (await readState($, s, agentId))?.task_session_id ?? null
  await relLog($, s, { timestamp: await nowIso($), event: 'workflow_placeholder', hook: 'SubagentStart', session_id: s.sessionId, agent_id: agentId, task_session_id: tsid, source: 'mod' })
}
export async function beforeSpawn($: any, L: Load, s: Sess, e: any) {
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

export async function agentSpawn($: HookArgs<'agent.spawn'>[0], L: Load, e: HookArgs<'agent.spawn'>[1], next: HookArgs<'agent.spawn'>[2]) {
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
}
