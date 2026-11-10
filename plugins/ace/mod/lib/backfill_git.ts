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
    // sha, date, subject, body, trailer; the sha is emitted as is, so only a hex sha counts (an RS inside a message cannot forge one)
    if (f.length < 5 || !/^[0-9a-f]{7,64}$/i.test(f[0].trim())) continue
    const ms = Date.parse(f[1].trim())
    out.push({ sha: f[0].trim(), ms: Number.isFinite(ms) ? ms : 0, subject: f[2].trim(), body: f[3],
      files: f[4].split('\n').map(s => s.trim()).filter(Boolean) })
  }
  return out
}

// Nothing leaves as plain text. The text is folded to ONE line (NFKD: fullwidth and compat forms; marks, format and filler
// characters such as zero-width ones dropped; every line break a space), redacted, then fail-closed rules cut it at the first
// secret-key word that has a separator anywhere after it, at a PEM header, and at a value piped into or given to a stdin login;
// then redact runs again (normalizing can create a new match). A separator is ':' or '=' or ANY non-ASCII character left after
// folding (lookalike colons and equals signs), a pipe, '>' or a URL-encoded ':' / '='. Each rule is one forward search, so the work stays linear.
const MAX_TEXT = 500, WINDOW = MAX_TEXT * 4
const KEY_WORD = /pass(?:word|wd)?|pwd|secret|token|api[-_ ]?key|access[-_ ]?key|private[-_ ]?key|credential|bearer|authorization|cookie|session|key/i
const SEP = /[:=|>\u0080-\uffff]|%3[ad]/i  // also a pipe, '->' / '=>' and a URL-encoded ':' or '='
const BEARER = /\bbearer/i  // to the end even with no space after it (a dropped zero-width char joins it to the value)
// any userinfo, even with quotes in it (redact stops a userinfo at a quote)
const USERINFO = /(\b[a-z][a-z0-9+.-]*:\/\/)[^\s\/]*@/gi
// bare token shapes (no key word needed) that lib/trace.ts redact does not know; linear, no nested quantifiers
const SHAPES = /\b(?:[sr]k_(?:live|test)_|glpat-|hf_|shpat_|shpca_|shpss_|dop_v1_|pypi-|hvs\.|SG\.|AIza|A[SKI]IA|ASIA)[A-Za-z0-9_.-]{8,}|hooks\.slack\.com\/services\/[A-Za-z0-9\/]+|\bdckr_pat_[A-Za-z0-9_-]{10,}/g
const ECHO = /\b(?:echo|printf)\b/i  // any case: ECHO works on a case-insensitive filesystem
const KEY_OR_ECHO = new RegExp(`${KEY_WORD.source}|${ECHO.source}`, 'i')
const STDIN_FLAG = /--(?:password-stdin|with-token)\b/i
const PEM = /-{2,}\s*BEGIN\b/i
// the word a cut broke (/\S*$/ would be quadratic on a long run of non-space)
function dropLastWord(s: string): string { let i = s.length; while (i > 0 && !/\s/.test(s[i - 1])) i--; return s.slice(0, i) }
const cutAt = (s: string, k: number) => k >= 0 ? s.slice(0, k) + '[redacted]' : s
const fold = (s: string) => s.normalize('NFKD').replace(/[\p{M}\p{Cf}\u115f\u1160\u3164\uffa0\u2800]/gu, '').replace(/[\r\n\v\f\x85\u2028\u2029]+/g, ' ')
function rules(s: string): string {
  s = redact(s).replace(USERINFO, '$1[redacted]@').replace(SHAPES, '[redacted]')
  const k = s.search(KEY_WORD)
  if (k >= 0 && SEP.test(s.slice(k))) s = cutAt(s, k)
  s = cutAt(s, s.search(PEM))
  s = cutAt(s, s.search(BEARER))
  const f = s.search(STDIN_FLAG)
  if (f >= 0) { const e = s.slice(0, f).search(ECHO); s = cutAt(s, e >= 0 ? e : f) }  // echo x | docker login --password-stdin, or <<< x
  return s
}
export function safeText(s: string): string {
  // bounded work: only a WINDOW is folded and redacted, so context right after the 500-char cut (echo x | docker login
  // --password-stdin) still counts; then the cut. A cut may leave a secret as a prefix no pattern matches, so the broken last
  // word is dropped and, after a cut, a key word with no separator and an echo/printf redact to the end.
  let cut = s.length > WINDOW
  s = s.slice(0, WINDOW)
  if (cut) s = dropLastWord(s)
  s = rules(rules(fold(s)))
  if (s.length > MAX_TEXT) { cut = true; s = dropLastWord(s.slice(0, MAX_TEXT)) }
  return cut ? cutAt(s, s.search(KEY_OR_ECHO)) : s
}

function normalize(s: string): string {
  return s.replace(/^\w+\(([^)]*)\)\s*!?\s*:/, '$1:').replace(/\(([^)]*)\)\s*!?\s*:/g, ' $1:')
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
    key: gitTaskKey(o.projectId, r.sha), sha: r.sha, task: safeText(clean(safeText(normalize(safeText(r.subject))))), steps: r.files.map(f => safeText(f)),
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
