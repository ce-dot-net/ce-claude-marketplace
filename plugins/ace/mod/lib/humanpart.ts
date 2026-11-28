// 8.4.3: the human-written part of a follow-up prompt, sent as trace.followup.text for server-side judging (followup_judging).
// Pure. Order: redact FIRST (lib/redact.ts: secrets and the personal-data layer), then extract, then cut.
// Extract: drop fenced code blocks, stack frames, JSON and diff headers; drop log / error / shell-prefixed lines unless prose
// (>= 3 letter-words) follows the prefix; drop tokens of 40+ code points (hashes, base64, long paths) and path-list lines; keep prose.
// Cut: head 300 + ' […] ' + tail 300 code points, only when longer than 600.
// Linear time: every line regex is anchored and sees at most the first LINE_HEAD code units of a line, so no backtracking blow-up.
// ponytail: line heuristics, not a parser; a machine error that reads like a sentence survives. The server judges what it gets.
import { redact } from './redact'
import { cpSlice, cps } from './text'
import { USER_PROMPT_MAX } from './state'

export const HUMAN_HEAD = 300, HUMAN_TAIL = 300, HUMAN_MARK = ' […] '
const LONG_TOKEN = 40   // code points
const LINE_HEAD = 300   // the regexes look at this much of a line
// always machine: stack frames, Python traces, JSON, diff headers
const MACHINE = [
  /^at [^\s(]+ ?\(/, /^at \S*:\d/,                          // JS stack frame: "at fn (file:1:2)" / "at file:1:2"
  /^File "[^"]*", line \d/, /^Traceback \(most recent call last\)/,
  /^[[\]{}],?$/, /^"[^"]*"\s*:/, /^[[{].*[\]},]$/,         // JSON
  /^(---|\+\+\+) \S/, /^@@ /,
]
// a log / error / shell prefix: the line is machine unless prose follows it. {1,4} chains at most four prefixes (timestamp, level,
// error name, '$'); an odd prefix it does not know just stays in the text, which only costs a few characters of the sent part.
const PREFIX = /^(?:\[?\d{4}-\d{2}-\d{2}[T ][\d:.,]{5,15}Z?\]?\s*|\[?\d{2}:\d{2}:\d{2}\]?\s*|\[?(?:TRACE|DEBUG|INFO|WARN|WARNING|ERROR|FATAL|CRITICAL)\]?[\s:|\]-]*|[\w.$]{0,60}(?:Error|Exception|Warning):\s*|\$ ){1,4}/
const LETTER_WORD = /^\(?\p{L}{2,}[\p{L}\p{M}'’-]*[.,!?;:)]*$/u
const proseWords = (t: string) => { let n = 0; for (const w of t.split(/\s+/)) if (LETTER_WORD.test(w) && ++n >= 3) break; return n }

// orig: the trimmed line (stack frames / JSON are judged on it); t: the same line without its long tokens
function keepLine(orig: string, t: string): boolean {
  if (MACHINE.some(r => r.test(orig.slice(0, LINE_HEAD)))) return false
  const p = PREFIX.exec(t.slice(0, LINE_HEAD))
  if (p && p[0].length && proseWords(t.slice(p[0].length)) < 3) return false
  const toks = t.split(/\s+/)
  if (toks.length >= 2 && toks.every(x => x.includes('/') || x.includes('\\'))) return false  // a list of paths
  if (t.length < 20) return true
  const letters = t.replace(/\P{L}+/gu, '').length, all = t.replace(/\s+/g, '').length
  return letters >= 0.4 * all  // mostly digits / symbols: a table, a dump, a hash list
}

// the uncut human part (already redacted)
export function extractHuman(text: unknown): string {
  if (typeof text !== 'string' || !text.trim()) return ''
  const out: string[] = []
  let fence = false
  // capped before the redactor (the same 200k code points the task state keeps): a huge paste costs a bounded amount
  for (const raw of redact(cpSlice(text.slice(0, 2 * USER_PROMPT_MAX), USER_PROMPT_MAX)).split('\n')) {
    const t = raw.trim()
    if (t.startsWith('```') || t.startsWith('~~~')) { fence = !fence; continue }
    if (fence) continue
    const kept = t.split(/\s+/).filter(x => x && (x.length < LONG_TOKEN || cps(x).length < LONG_TOKEN)).join(' ')  // a long token drops only itself
    if (kept && !keepLine(t, kept)) continue
    if (!kept && out.length && out[out.length - 1] === '') continue  // blank-line runs collapse
    if (!kept && t) continue  // the line was only long tokens
    out.push(kept)
  }
  return out.join('\n').trim()
}
// head 300 + marker + tail 300 code points when longer than 600
export function humanPart(text: unknown): string {
  const c = cps(extractHuman(text))
  return c.length <= HUMAN_HEAD + HUMAN_TAIL ? c.join('') : c.slice(0, HUMAN_HEAD).join('') + HUMAN_MARK + c.slice(c.length - HUMAN_TAIL).join('')
}
