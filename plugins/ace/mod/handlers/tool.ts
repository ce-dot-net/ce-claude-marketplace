// tool.call: tool records for the learn, the late subagent inject at a run's first tool call, the domain shift.
import { logSubagentError, subagentRender } from './agent.ts'
import { readJson, readText } from '../io/fs.ts'
import { nowIso, relLog } from '../io/log.ts'
import { DOMAIN_MS, hitResult, reuseGet, reuseStore, search } from '../io/spawn.ts'
import { type Load, type Sess, disabled, ensure, readState, searchOrigin, updateState, uuid, type HookArgs, recordTool, refreshMarker } from '../io/state.ts'
import { injectedContents } from '../lib/evidence.ts'
import { renderDomainShift } from '../lib/render.ts'
import { safeComponent as safe } from '../lib/state.ts'
import { basenameQuery, domainNames, matchDomainToPath } from '../lib/text.ts'
import { toolRec } from '../lib/trace.ts'

// The subagent report tool. CC 2.1.316's typed tool table (claude-code-tools) has no entry for it (only the Agent
// result's internal `handback` fields mention it), but it exists at runtime as `SubagentHandback({ message })`
// for subagents: matched by name, the input read untyped.
export const HANDBACK_TOOL = 'SubagentHandback'
export async function lateInject($: any, L: Load, s: Sess, key: string): Promise<string | null> {
  const query = L.late.get(key)
  if (query === undefined) return null
  L.late.delete(key)
  const st = await readState($, s, key)
  if (!st || await disabled($, s)) return null
  const t0 = await $.clock.now()
  const tsid: string = st.task_session_id
  const sr = await search($, s, query, tsid, undefined, DOMAIN_MS, tsid, await searchOrigin($, L, s), L)
  if (!sr.resp) { await logSubagentError($, s, sr); return null }
  const r = await subagentRender($, s, sr, query, st.agent_type ?? 'unknown', tsid, t0, st.parent_task_id, { late: true })
  await updateState($, L, s, key, { ids: r.ids, retrievalId: sr.resp.retrieval_id || null, rlog: r.rlog, rendered: r.rendered, renderVariant: r.cohort,
    contents: injectedContents(r.patterns, r.ids) })
  return r.context
}
// ace_domain_shift.main
export async function domainShift($: any, L: Load, e: any, key: string): Promise<string | null> {
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
    const sr: any = cached ? hitResult(cached) : await search($, s, query, undefined, 8, DOMAIN_MS, tsid, await searchOrigin($, L, s), L)  // §16 P8: no pin; tsid for the state merge and --session-id
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

export async function toolCall($: HookArgs<'tool.call'>[0], L: Load, e: HookArgs<'tool.call'>[1], next: HookArgs<'tool.call'>[2]) {
  await refreshMarker($, L, true)  // handoff to the Python hook of this event
  const t0 = Date.now()
  const r: any = await next(e)
  await refreshMarker($, L)  // the call itself can outlast the marker
  const key = (e as any).agentId ?? 'main'
  if (key === 'main') L.mainSeen++
  let s: Sess | null = null
  try {
    s = await ensure($, L)
    if (s) await recordTool($, L, s, key, toolRec(e.tool, e, r.result, !!r.isError, r.deny, t0, Date.now(), typeof r.text === 'string' ? r.text : undefined))
    if ((e.tool as string) === HANDBACK_TOOL && key !== 'main' && typeof (e as any).message === 'string') L.handback.set(key, (e as any).message)
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
}
