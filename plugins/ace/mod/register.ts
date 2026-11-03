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
import { anchorRun, beforeSpawn, checkPlaceholder } from './handlers/agent.ts'
import { onPrompt } from './handlers/prompt.ts'
import { domainShift, lateInject } from './handlers/tool.ts'
import { abstain, learn } from './handlers/turn.ts'

const LEARN_LOCK_MS = 600_000              // ace_session_end.py: learn timeout 300 s + margin
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
