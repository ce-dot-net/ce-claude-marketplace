// classic.UserPromptSubmit / Stop / SubagentStop: the mod-classic marker, the session title, the Stop effort and
// the background-task deferral (turn.complete carries neither).
import { type HookArgs, type Load, refreshMarker, touchClassic } from '../io/state.ts'
import { delegatedRunning } from '../lib/trace.ts'

export const effortOf = (e: any): unknown => e.effort && typeof e.effort === 'object' ? e.effort.level : e.effort

// Never clobber a custom /rename or --name title.
export async function classicUserPromptSubmit($: HookArgs<'classic.UserPromptSubmit'>[0], L: Load, e: any, next: HookArgs<'classic.UserPromptSubmit'>[2]) {
  await touchClassic($, L)
  const r = await next(e)
  return L.pendingTitle && !e.session_title ? { ...r, sessionTitle: L.pendingTitle } : r
}

// turn.complete carries no effort; Stop does (ace_after_task._resolve_effort_level).
export async function classicStop($: HookArgs<'classic.Stop'>[0], L: Load, e: any, next: HookArgs<'classic.Stop'>[2]) {
  await refreshMarker($, L, true)  // handoff to the Python hook of this event  // Stop is the Python hook that would reap the state, and it runs after this one
  await touchClassic($, L)
  const raw = effortOf(e)
  if (typeof raw === 'string' && raw) L.stopEffort = raw
  L.stopDefer = delegatedRunning(e.background_tasks) ? (e.background_tasks as any[]).map(b => String(b?.type)) : null
  return next(e)
}

export async function classicSubagentStop($: HookArgs<'classic.SubagentStop'>[0], L: Load, e: any, next: HookArgs<'classic.SubagentStop'>[2]) {
  await refreshMarker($, L, true)  // handoff to the Python hook of this event
  await touchClassic($, L)
  const raw = effortOf(e)
  if (typeof raw === 'string' && raw && e.agent_id) L.agentEffort.set(e.agent_id, raw)
  return next(e)
}
