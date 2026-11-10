// 8.2.0 tool-noise filter for session items (pure). A session task is full of failed lookups ("File does not exist", "grep found 0 files")
// that teach nothing; they are dropped from the step list BEFORE the trace is built, so the trace (step numbers, failed_steps, success)
// is computed from the remaining steps by the live buildTrace/taskOutcome. All patterns live in NOISE: one place, one name each.
import type { ToolRec } from './evidence.ts'

// Matched against the step's summarized result. First match names the drop. Only NON-decisive steps (reads, greps, globs, read-only Bash)
// are ever dropped: a failed Edit/Write/build stays, its failure still counts against the task.
export const NOISE: { name: string, re: RegExp }[] = [
  { name: 'file-missing', re: /file does not exist/i },
  { name: 'no-such-file', re: /no such file or directory/i },
  { name: 'enoent', re: /\bENOENT\b/ },
  { name: 'does-not-exist', re: /\bdoes not exist\b/i },
  { name: 'permission', re: /permission denied|\bEACCES\b/i },
  { name: 'zero-files', re: /\bfound 0 files\b/i },
  { name: 'no-matches', re: /\bno matches found\b/i },
  { name: 'no-files', re: /\bno files found\b/i },
  { name: 'exit1', re: /^(?:Error: )?Exit code 1\b/ },   // an empty grep/ls/find (read-only Bash only, see below)
]
const LOOKUP = new Set(['Read', 'Grep', 'Glob', 'LS', 'Bash'])

export type Denoised = { tools: ToolRec[], dropped: Record<string, number>, droppedSteps: number }
export function denoise(tools: ToolRec[]): Denoised {
  const dropped: Record<string, number> = {}
  const keep: ToolRec[] = []
  for (const t of tools) {
    if (t.dec || t.intr || (!LOOKUP.has(t.tool) && !t.failed)) { keep.push(t); continue }
    // an ok Bash step only counts as noise by its exit-1 result: its stdout may legitimately say anything (echo, a log line)
    const hit = NOISE.find(n => (t.failed || t.tool !== 'Bash' || n.name === 'exit1') && n.re.test(t.result))
    const name = hit?.name ?? (t.failed ? 'failed-step' : '')
    if (!name) { keep.push(t); continue }
    dropped[name] = (dropped[name] ?? 0) + 1
  }
  return { tools: keep, dropped, droppedSteps: tools.length - keep.length }
}
