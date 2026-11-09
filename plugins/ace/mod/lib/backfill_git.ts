// 8.2.0 git reader (pure, NOT wired): the text of `git log` (run GIT_LOG_ARGV, pass stdout) -> fix tasks for the bootstrap backfill.
// No `$`, no I/O. Author/committer name and email are never requested by the format and never emitted; everything that leaves is redacted.
import { redact } from './trace.ts'
import { sha256Hex } from './cohort.ts'

// Per commit: RS, then sha NUL date NUL subject NUL body NUL, then (git's --name-only) a blank line and the touched files.
export const GIT_LOG_FORMAT = '%x1e%H%x00%cI%x00%s%x00%b%x00'
export const GIT_LOG_ARGV = ['git', 'log', '--no-merges', '--date=iso-strict', `--format=${GIT_LOG_FORMAT}`, '--name-only']
// Same format for the merge/PR list (no --name-only: a merge lists no files).
export const GIT_MERGES_ARGV = ['git', 'log', '--merges', '--date=iso-strict', `--format=${GIT_LOG_FORMAT}`]

export type GitTask = {
  key: string              // bootstrap:<sha256(project:sha)[:32]>
  sha: string
  task: string             // the cleaned, redacted subject
  steps: string[]          // redacted files touched
  success: boolean         // false only for a Revert commit
  failedThenFixed: boolean // a Revert in the window undoes this commit
  decisive: number         // always 0: selectTasks (lib/backfill.ts) then ranks success, then newest
  endMs: number
}
type Opts = { projectId: string, limit?: number }
type Raw = { sha: string, ms: number, subject: string, body: string, files: string[] }

export const gitTaskKey = (projectId: string, sha: string) => `bootstrap:${sha256Hex(`${projectId}:${sha}`).slice(0, 32)}`

const FIX_RE = /\b(fix(es|ed)?|bug(fix)?|hotfix|revert|regression)\b/i
const TRIVIAL_RE = /^(wip|update|updates|misc|stuff|tmp|temp)\b\W*$|^(chore(\(.*?\))?:\s*)?(release|bump|version)\b|\bbump(ed)?\s+(the\s+)?version\b|^v?\d+\.\d+(\.\d+)?\b|\bversion\s+bump\b|\brelease\s+v?\d/i
const REVERT_RE = /^revert\b/i

function parse(text: string): Raw[] {
  if (typeof text !== 'string') return []
  const out: Raw[] = []
  for (const chunk of text.split('\x1e')) {
    const f = chunk.split('\x00')
    if (f.length < 5 || !f[0].trim()) continue  // sha, date, subject, body, trailer
    const ms = Date.parse(f[1].trim())
    out.push({ sha: f[0].trim(), ms: Number.isFinite(ms) ? ms : 0, subject: f[2].trim(), body: f[3],
      files: f[4].split('\n').map(s => s.trim()).filter(Boolean) })
  }
  return out
}

// Nothing leaves as plain text: the raw text is redacted, then a fail-closed rule redacts from any secret-key word through a ':' or '='
// (scope lists, brackets and punctuation in between) to the end of the line, then redact runs again (normalizing can create a new match).
const KEY_RE = /(?:pass(?:word|wd)?|pwd|secret|token|api[-_ ]?key|access[-_ ]?key|private[-_ ]?key|credential|bearer)[^:=\n]{0,40}[:=][^\n]*/gi
function safeText(s: string): string {
  const once = (x: string) => redact(x).replace(KEY_RE, '[redacted]')
  return once(once(s))
}

// "fix(auth)!: msg (#42)" -> "auth: msg"; other subjects only lose a trailing "(#N)".
function clean(subject: string): string {
  const s = subject.replace(/\s*\(#\d+\)\s*$/, '')
  const m = /^(?:fix|feat|chore|refactor|docs|test|perf|build|ci|style|revert)(?:\(([^)]*)\))?!?:\s*(.+)$/i.exec(s)
  return m ? (m[1] ? `${m[1]}: ${m[2]}` : m[2]) : s
}

const unquote = (s: string) => s.replace(/^revert\s+"?/i, '').replace(/"\s*$/, '').trim()
const isTrivial = (s: string) => s.length < 12 || TRIVIAL_RE.test(s)

export function readGitLog(text: string, o: Opts): GitTask[] {
  const raws = parse(text).filter(r => FIX_RE.test(r.subject) && !isTrivial(r.subject))
  const tasks: (GitTask & { _s: string })[] = raws.map(r => ({
    key: gitTaskKey(o.projectId, r.sha), sha: r.sha, task: safeText(clean(safeText(r.subject.replace(/^\w+\(([^)]*)\)\s*!?\s*:/, '$1:').replace(/\(([^)]*)\)\s*!?\s*:/g, ' $1:')))), steps: r.files.map(f => redact(f)),
    success: !REVERT_RE.test(r.subject), failedThenFixed: false, decisive: 0, endMs: r.ms, _s: r.subject }))
  // revert pairing: the sha in "This reverts commit <sha>" wins, else the quoted subject; only commits in the window pair
  raws.forEach(r => {
    if (!REVERT_RE.test(r.subject)) return
    const bySha = /reverts commit ([0-9a-f]{7,40})/i.exec(r.body)?.[1]
    const orig = (bySha && tasks.find(t => t.sha.startsWith(bySha) && t.success)) ||
      tasks.find(t => t.success && t._s === unquote(r.subject))
    if (orig) orig.failedThenFixed = true
  })
  tasks.sort((a, b) => b.endMs - a.endMs)
  const n = o.limit === undefined ? tasks.length : Math.max(0, Math.floor(o.limit))
  return tasks.slice(0, n).map(({ _s, ...t }) => t)
}

// "Merge pull request #N from owner/branch" + body "<PR title>": the task is the (redacted) title; owner and branch are dropped.
export function readMergeLog(text: string, o: Opts): GitTask[] {
  const tasks: GitTask[] = []
  for (const r of parse(text)) {
    if (!/^Merge pull request #\d+/i.test(r.subject)) continue
    const title = (r.body.split('\n').find(l => l.trim()) ?? '').trim()
    if (isTrivial(title)) continue
    tasks.push({ key: gitTaskKey(o.projectId, r.sha), sha: r.sha, task: safeText(title), steps: [], success: true, failedThenFixed: false, decisive: 0, endMs: r.ms })
  }
  tasks.sort((a, b) => b.endMs - a.endMs)
  return tasks.slice(0, o.limit === undefined ? tasks.length : Math.max(0, Math.floor(o.limit)))
}
