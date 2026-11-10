// 8.2.0 session reader (pure, NOT wired to any send path): a Claude Code transcript JSONL -> tasks, one per real user prompt, each
// built through the SAME toolRec / taskOutcome / buildTrace / redact the live learn path uses (lib/trace.ts). No `$`, no I/O: the caller
// hands over the text (or any line iterator, to stream a big file). The trace carries no session_id, an empty playbook_used and no
// field the live trace body does not have; `source: "bootstrap"` and the original date are the caller's to add (a later slice).
import { buildTrace, hasSubstantialWork, isTrivialTask, taskOutcome, toolRec } from './trace.ts'
import { LEADING_REMINDER, isMachinePrompt, skipReason } from './text.ts'
import type { ToolRec } from './evidence.ts'
import { sha256Hex } from './cohort.ts'
import { denoise } from './backfill_noise.ts'

export type BackfillTask = {
  sessionId: string      // the transcript's session uuid ('' when it names none and the caller gave none)
  index: number          // the prompt's 0-based position among the REAL user prompts of the session (counts the filtered ones too: stable)
  prompt: string
  trace: any             // buildTrace's trace, no session_id
  success: boolean
  steps: number
  decisive: number       // decisive steps (edits, writes, state-changing Bash ...): the task's weight
  startMs: number
  endMs: number
}
// noise = tasks excluded by the tool-noise filter; noiseDropped = steps dropped (all tasks, kept or excluded); noiseBy = those steps per pattern name
export type ReadStats = { prompts: number, tasks: number, trivial: number, noWork: number, machine: number, sidechain: number, malformed: number,
  noise: number, noiseDropped: number, noiseBy: Record<string, number> }
const STATE_STEP = new Set(['Edit', 'Write', 'MultiEdit', 'NotebookEdit'])
export type ReadResult = { tasks: BackfillTask[], stats: ReadStats, sessionId: string }

type Open = { index: number, prompt: string, tools: ToolRec[], answer: string, startMs: number, endMs: number
  calls: Map<string, { name: string, input: any, t0: number }> }

const blockText = (c: unknown): string => typeof c === 'string' ? c
  : Array.isArray(c) ? c.filter((b: any) => b && b.type === 'text' && typeof b.text === 'string').map((b: any) => b.text).join('\n') : ''
const ms = (t: unknown, fallback: number) => { const v = typeof t === 'string' ? Date.parse(t) : NaN; return Number.isFinite(v) ? v : fallback }

// Lines of a string without building the array of them (a session can be tens of MB).
function* linesOf(text: string): Generator<string> {
  let from = 0
  for (;;) {
    const i = text.indexOf('\n', from)
    if (i < 0) { if (from < text.length) yield text.slice(from); return }
    yield text.slice(from, i)
    from = i + 1
  }
}
export const readSession = (text: string, o: { sessionId?: string, denoise?: boolean } = {}): ReadResult => readSessionLines(linesOf(text), o)

// o.denoise (the send path sets it): drop tool-noise steps and exclude tasks that are not real work after that (lib/backfill_noise.ts).
export function readSessionLines(lines: Iterable<string>, o: { sessionId?: string, denoise?: boolean } = {}): ReadResult {
  const stats: ReadStats = { prompts: 0, tasks: 0, trivial: 0, noWork: 0, machine: 0, sidechain: 0, malformed: 0, noise: 0, noiseDropped: 0, noiseBy: {} }
  const tasks: BackfillTask[] = []
  let sid = o.sessionId ?? '', cur: Open | null = null, index = 0, last = 0

  const finish = () => {
    const t = cur
    cur = null
    if (!t) return
    // a call whose result never came (the session ended mid-call) is an interrupted step: the task is then no success
    for (const c of t.calls.values()) t.tools.push(toolRec(c.name, c.input, { interrupted: true }, false, undefined, c.t0, t.endMs))
    if (isTrivialTask(t.prompt) || skipReason(t.prompt) !== null) { stats.trivial++; return }
    if (!hasSubstantialWork(t.tools)) { stats.noWork++; return }
    // tool noise out (failed lookups, empty greps); the rest must still be a real task: >= 2 steps, one state-changing step, no failure left
    const dn = o.denoise ? denoise(t.tools) : { tools: t.tools, dropped: {}, droppedSteps: 0 }
    stats.noiseDropped += dn.droppedSteps
    for (const [k, v] of Object.entries(dn.dropped)) stats.noiseBy[k] = (stats.noiseBy[k] ?? 0) + v
    const kept = dn.tools
    if (o.denoise && (kept.length < 2 || !kept.some(r => STATE_STEP.has(r.tool) || (r.tool === 'Bash' && !r.failed)) || !taskOutcome(kept).success)) { stats.noise++; return }
    const { trace, success } = buildTrace({ userPrompt: t.prompt, tools: kept, answer: t.answer, playbookUsed: [], agentType: 'main', appliedLogIds: [],
      nowIso: new Date(t.endMs || 0).toISOString(), effort: 'normal' })
    tasks.push({ sessionId: '', index: t.index, prompt: t.prompt, trace, success, steps: kept.length, decisive: kept.filter(r => r.dec).length, startMs: t.startMs, endMs: t.endMs })
    stats.tasks++
  }

  for (const line of lines) {
    if (!line.trim()) continue
    let j: any
    try { j = JSON.parse(line) } catch { stats.malformed++; continue }
    if (!j || typeof j !== 'object' || Array.isArray(j)) continue
    if (!sid && typeof j.sessionId === 'string') sid = j.sessionId
    if (j.type !== 'user' && j.type !== 'assistant') continue  // attachments, queue/title/cost rows ...
    if (j.isSidechain === true) { stats.sidechain++; continue }  // a subagent's own steps are not this task's
    const t = ms(j.timestamp, last)
    last = t
    const c = j.message?.content
    if (cur) cur.endMs = t
    if (j.type === 'assistant') {
      for (const b of Array.isArray(c) ? c : []) {
        if (!cur || !b || typeof b !== 'object') continue
        if (b.type === 'tool_use' && typeof b.id === 'string' && typeof b.name === 'string') cur.calls.set(b.id, { name: b.name, input: b.input ?? {}, t0: t })
        else if (b.type === 'text' && typeof b.text === 'string' && b.text.trim()) cur.answer = b.text  // the closing answer: the LAST text
      }
      if (typeof c === 'string' && cur && c.trim()) cur.answer = c
      continue
    }
    // user: tool results continue the task; anything else is a prompt
    const results = Array.isArray(c) ? c.filter((b: any) => b && b.type === 'tool_result') : []
    if (results.length) {
      for (const b of results) {
        const call = cur?.calls.get(b.tool_use_id)
        if (!cur || !call) continue
        cur.calls.delete(b.tool_use_id)
        const txt = blockText(b.content)
        const res = j.toolUseResult !== undefined && j.toolUseResult !== null ? j.toolUseResult : txt
        cur.tools.push(toolRec(call.name, call.input, res, b.is_error === true, undefined, call.t0, t, txt))
      }
      continue
    }
    if (j.isMeta === true || j.isCompactSummary === true) { stats.machine++; continue }
    const stripped = blockText(c).replace(LEADING_REMINDER, '').trim()
    if (!stripped || isMachinePrompt(stripped)) { stats.machine++; continue }  // task notifications, command echoes, bare reminders
    finish()
    stats.prompts++
    cur = { index: index++, prompt: stripped, tools: [], answer: '', startMs: t, endMs: t, calls: new Map() }
  }
  finish()
  for (const t of tasks) t.sessionId = sid
  return { tasks, stats, sessionId: sid }
}

// The ledger key of a task (slice 2 keeps it): stable for the same project, session and prompt position.
export const taskKey = (projectId: string, sessionId: string, promptIndex: number) =>
  `bootstrap:${sha256Hex(`${projectId}:${sessionId}:${promptIndex}`).slice(0, 32)}`

// At most n tasks: successful first, then the more decisive steps, then the newest; the input is not reordered.
export function selectTasks<T extends Pick<BackfillTask, 'success' | 'decisive' | 'endMs'>>(tasks: T[], n: number): T[] {
  if (!(n > 0)) return []
  return [...tasks].sort((a, b) => Number(b.success) - Number(a.success) || b.decisive - a.decisive || b.endMs - a.endMs).slice(0, Math.floor(n))
}

// 8.2.1 hybrid: at most n tasks, round-robin over the groups (one per source) that have candidates, each ranked by selectTasks.
// A group that runs out hands its share to the others; a single non-empty group gives exactly selectTasks(group, n).
export function selectBalanced<T extends Pick<BackfillTask, 'success' | 'decisive' | 'endMs'>>(groups: T[][], n: number): T[] {
  const ranked = groups.map(g => selectTasks(g, n)).filter(g => g.length), out: T[] = []
  for (let i = 0; out.length < Math.floor(n) && ranked.some(g => i < g.length); i++)
    for (const g of ranked) if (i < g.length && out.length < Math.floor(n)) out.push(g[i])
  return out
}
