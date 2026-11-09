// 8.2.0 git reader (pure library, unwired): the text of `git log` (GIT_LOG_ARGV) -> fix tasks, same shape family as lib/backfill.ts.
import { expect, test } from 'claude-code/testing'
import { GIT_LOG_ARGV, gitTaskKey, readGitLog, readMergeLog } from '../lib/backfill_git.ts'
import { selectTasks } from '../lib/backfill.ts'

const RS = '\x1e', NUL = '\x00'
const c = (sha: string, date: string, subject: string, files: string[] = ['src/a.ts'], body = '') =>
  `${RS}${sha}${NUL}${date}${NUL}${subject}${NUL}${body}${NUL}\n\n${files.join('\n')}\n`
const S1 = 'a'.repeat(40), S2 = 'b'.repeat(40), S3 = 'c'.repeat(40)

test('argv is the fixed git log command', () => {
  expect(GIT_LOG_ARGV.slice(0, 2)).toEqual(['git', 'log'])
  expect(GIT_LOG_ARGV).toContain('--no-merges')
  expect(GIT_LOG_ARGV).toContain('--name-only')
  expect(GIT_LOG_ARGV.join(' ')).not.toMatch(/%a[nNeE]|%c[nNeE]/)  // never asks for author/committer names or emails
})

test('a fix subject becomes a task with its files as steps', () => {
  const r = readGitLog(c(S1, '2026-03-02T10:00:00+01:00', 'Fix crash when the parser sees an empty file', ['src/p.ts', 'tests/p.test.ts']), { projectId: 'prj' })
  expect(r.length).toBe(1)
  expect(r[0].task).toBe('Fix crash when the parser sees an empty file')
  expect(r[0].steps).toEqual(['src/p.ts', 'tests/p.test.ts'])
  expect(r[0].success).toBe(true)
  expect(r[0].failedThenFixed).toBe(false)
  expect(r[0].endMs).toBe(Date.parse('2026-03-02T10:00:00+01:00'))
  expect(r[0].sha).toBe(S1)
})

test('conventional scope is cleaned; non-fix subjects are ignored; bug/hotfix/regression match', () => {
  const r = readGitLog([c(S1, '2026-03-02T10:00:00Z', 'fix(auth)!: refresh token expiry off by one (#42)'),
    c(S2, '2026-03-01T10:00:00Z', 'feat(ui): add a shiny new dashboard panel'),
    c(S3, '2026-02-01T10:00:00Z', 'Hotfix for the REGRESSION in bug tracker import')].join(''), { projectId: 'prj' })
  expect(r.map(t => t.task)).toEqual(['auth: refresh token expiry off by one', 'Hotfix for the REGRESSION in bug tracker import'])
})

test('a Revert is a failed task and marks the original (by body sha) as failed-then-fixed', () => {
  const r = readGitLog([
    c(S2, '2026-03-03T10:00:00Z', 'Revert "Fix cache invalidation on logout"', ['src/c.ts'], `This reverts commit ${S1}.`),
    c(S1, '2026-03-01T10:00:00Z', 'Fix cache invalidation on logout', ['src/c.ts'])].join(''), { projectId: 'prj' })
  const rev = r.find(t => t.sha === S2)!, orig = r.find(t => t.sha === S1)!
  expect(rev.success).toBe(false)
  expect(orig.success).toBe(true)
  expect(orig.failedThenFixed).toBe(true)
  expect(rev.failedThenFixed).toBe(false)
})

test('a Revert pairs by subject when the body has no sha; an unmatched revert pairs nothing', () => {
  const r = readGitLog([
    c(S2, '2026-03-03T10:00:00Z', 'Revert "Fix cache invalidation on logout"'),
    c(S1, '2026-03-01T10:00:00Z', 'Fix cache invalidation on logout'),
    c(S3, '2026-03-04T10:00:00Z', 'Revert "Fix something outside the window entirely"')].join(''), { projectId: 'prj' })
  expect(r.find(t => t.sha === S1)!.failedThenFixed).toBe(true)
  expect(r.filter(t => t.failedThenFixed).length).toBe(1)
})

test('secrets in subject, body and files are redacted', () => {
  const tok = 'ghp_' + 'A1b2C3d4E5f6G7h8I9j0'
  const r = readGitLog(c(S1, '2026-03-02T10:00:00Z', `Fix leak of ${tok} in the logger`, [`config/${tok}.json`]), { projectId: 'prj' })
  expect(JSON.stringify(r)).not.toContain(tok)
  expect(r[0].task).toContain('[redacted]')
})

test('no author leakage: only the declared fields exist and none carries a name or email', () => {
  const r = readGitLog(c(S1, '2026-03-02T10:00:00Z', 'Fix the broken login redirect for SSO users'), { projectId: 'prj' })
  expect(Object.keys(r[0]).sort()).toEqual(['decisive', 'endMs', 'failedThenFixed', 'key', 'sha', 'steps', 'success', 'task'])
  expect(JSON.stringify(r)).not.toMatch(/@|author/i)
})

test('trivial subjects are skipped', () => {
  const r = readGitLog([c(S1, '2026-03-02T10:00:00Z', 'fix typo'), c(S2, '2026-03-02T10:00:00Z', 'wip'),
    c(S3, '2026-03-02T10:00:00Z', 'Release v1.2.3 fix'), c('d'.repeat(40), '2026-03-02T10:00:00Z', 'fix: bump version to 2.0.1'),
    c('e'.repeat(40), '2026-03-02T10:00:00Z', 'update')].join(''), { projectId: 'prj' })
  expect(r).toEqual([])
})

test('keys are stable, bootstrap-prefixed, per project and sha', () => {
  const k = gitTaskKey('prj', S1)
  expect(k).toMatch(/^bootstrap:[0-9a-f]{32}$/)
  expect(gitTaskKey('prj', S1)).toBe(k)
  expect(gitTaskKey('other', S1)).not.toBe(k)
  expect(gitTaskKey('prj', S2)).not.toBe(k)
  const r = readGitLog(c(S1, '2026-03-02T10:00:00Z', 'Fix the broken login redirect for SSO users'), { projectId: 'prj' })
  expect(r[0].key).toBe(k)
})

test('newest first and capped by limit; selectTasks accepts the tasks', () => {
  const txt = [c(S1, '2026-01-01T00:00:00Z', 'Fix old problem number one here'), c(S2, '2026-03-01T00:00:00Z', 'Fix newest problem number two here'),
    c(S3, '2026-02-01T00:00:00Z', 'Fix middle problem number three here')].join('')
  expect(readGitLog(txt, { projectId: 'p' }).map(t => t.sha)).toEqual([S2, S3, S1])
  expect(readGitLog(txt, { projectId: 'p', limit: 2 }).map(t => t.sha)).toEqual([S2, S3])
  expect(readGitLog(txt, { projectId: 'p', limit: 0 })).toEqual([])
  expect(selectTasks(readGitLog(txt, { projectId: 'p' }), 1)[0].sha).toBe(S2)
})

test('empty and garbage input give no tasks and never throw', () => {
  for (const x of ['', '\n', 'garbage', RS, `${RS}${NUL}${NUL}`, `${RS}onlysha${NUL}notadate${NUL}Fix something long enough${NUL}${NUL}`, '\x00\x1e\x00\x1e'])
    expect(Array.isArray(readGitLog(x, { projectId: 'p' }))).toBe(true)
  expect(readGitLog(undefined as any, { projectId: 'p' })).toEqual([])
  expect(readGitLog(`${RS}onlysha${NUL}notadate${NUL}Fix something long enough${NUL}${NUL}`, { projectId: 'p' })[0]?.endMs ?? 0).toBe(0)
})

test('merge/PR subjects: task is the PR title from the body, branch and author dropped', () => {
  const m = (sha: string, subj: string, body: string) => `${RS}${sha}${NUL}2026-03-02T10:00:00Z${NUL}${subj}${NUL}${body}${NUL}\n`
  const r = readMergeLog([m(S1, 'Merge pull request #7 from someone/feat-x', 'Add retry to the uploader'),
    m(S2, 'Merge branch main into dev', ''), m(S3, 'Merge pull request #8 from someone/y', 'wip')].join(''), { projectId: 'p' })
  expect(r.length).toBe(1)
  expect(r[0].task).toBe('Add retry to the uploader')
  expect(r[0].steps).toEqual([])
  expect(JSON.stringify(r)).not.toContain('someone')
})
