// The 422 trap: the server requires GitContext.commit_hash; a trace with `git` but no commit_hash is rejected whole (422).
// gitContext (io/spawn.ts) returns undefined without a HEAD hash; turn.ts sets trace.git only from it and hangs
// session_commits only onto an existing git object (never a git object made of session_commits alone).
import { expect } from 'claude-code/testing'
import { test } from './t.ts'
import S8 from './fixtures/search_8.ts'
import { done, host, mainTask } from './helpers.ts'
import { commitIsFix, gitContext } from '../io/spawn.ts'

// a $ whose process.run answers git by argv; null = the spawn failed
const fake = (ans: (a: string[]) => { exitCode: number; stdout: string } | null) =>
  ({ process: { run: async (argv: string[]) => { const r = ans(argv.slice(1)); if (!r) throw new Error('spawn'); return { ...r, stderr: '' } } } })
const repo = (head: { exitCode: number; stdout: string } | null) => fake(a =>
  a[0] === 'rev-parse' && a[1] === '--is-inside-work-tree' ? { exitCode: 0, stdout: 'true\n' }
  : a[0] === 'rev-parse' && a[1] === 'HEAD' ? head : { exitCode: 0, stdout: 'x\n' })

test('gitContext: no repo -> undefined', async () => {
  expect(await gitContext(fake(() => ({ exitCode: 128, stdout: '' })), '/p')).toBe(undefined)
})
test('gitContext: repo without a commit (rev-parse HEAD exit 128), empty HEAD, failed spawn -> undefined', async () => {
  expect(await gitContext(repo({ exitCode: 128, stdout: 'HEAD\n' }), '/p')).toBe(undefined)
  expect(await gitContext(repo({ exitCode: 0, stdout: '  \n' }), '/p')).toBe(undefined)
  expect(await gitContext(repo(null), '/p')).toBe(undefined)
})
test('gitContext: with a HEAD hash the object carries commit_hash', async () => {
  const g = await gitContext(repo({ exitCode: 0, stdout: 'deadbeef1234\n' }), '/p')
  expect(g.commit_hash).toBe('deadbeef1234')
})

const noHead = (a: string[]) => a[1] === 'rev-parse' && a[2] === '--is-inside-work-tree' ? 'true' : a[1] === 'rev-parse' && a[2] === 'HEAD' ? (() => { throw new Error('no HEAD') })() : undefined
test('trace: no HEAD but a commit in the session -> no git in the trace (session_commits alone never make one)', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }), git: noHead })
  await mainTask($, h, [{ tool: 'Edit', file_path: '/proj/x.py', old_string: 'a', new_string: 'b' }, { tool: 'Bash', command: 'git commit -m x' }])
  await done($)
  expect('git' in h.trace(h.learns()[0]!)).toBe(false)
})
test('trace: with HEAD, the session commit hangs on the git object that has commit_hash', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }), git: (a: string[]) => a[1] === 'rev-parse' && a[2] === '--is-inside-work-tree' ? 'true' : a[1] === 'rev-parse' && a[2] === 'HEAD' ? 'cafe5678' : undefined })
  await mainTask($, h, [{ tool: 'Edit', file_path: '/proj/x.py', old_string: 'a', new_string: 'b' }, { tool: 'Bash', command: 'git commit -m x' }])
  await done($)
  const g = h.trace(h.learns()[0]!).git
  expect([g.commit_hash, g.session_commits]).toEqual(['cafe5678', ['abc1234f']])
})
// backfill (no git object ever) is pinned in tests/test_git_commit_hash_guard.py: the mod test kit has no file reads

// ---- git minimisation (DSGVO): only commit_hash, timestamp, files_changed, insertions, deletions, commit_is_fix (+ session_commits) ----
const ALLOWED = ['commit_hash', 'commit_is_fix', 'deletions', 'files_changed', 'insertions', 'timestamp']
const full = (subject: string) => fake(a => a[0] === 'rev-parse' && a[1] === '--is-inside-work-tree' ? { exitCode: 0, stdout: 'true\n' }
  : a[0] === 'rev-parse' && a[1] === 'HEAD' ? { exitCode: 0, stdout: 'beef01\n' }
  : a[0] === 'log' && a[2] === '--format=%s' ? { exitCode: 0, stdout: subject + '\n' }
  : a[0] === 'log' && a[2] === '--format=%an' ? { exitCode: 0, stdout: 'Jane Doe\n' }
  : a[0] === 'log' && a[2] === '--format=%ae' ? { exitCode: 0, stdout: 'jane@example.org\n' }
  : a[0] === 'log' && a[2] === '--format=%aI' ? { exitCode: 0, stdout: '2026-11-24T10:00:00+01:00\n' }
  : a[0] === 'rev-parse' && a[1] === '--abbrev-ref' ? { exitCode: 0, stdout: 'feature/secret-customer\n' }
  : { exitCode: 0, stdout: '' })
test('git minimisation: gitContext carries only the allowed keys; no author, email, branch or message', async () => {
  const g = await gitContext(full('Fix login for ACME'), '/p')
  expect(Object.keys(g).sort()).toEqual(ALLOWED)
  expect(/Jane|jane@|secret-customer|ACME|login/.test(JSON.stringify(g))).toBe(false)
  expect([g.commit_hash, g.commit_is_fix, g.timestamp]).toEqual(['beef01', true, '2026-11-24T10:00:00+01:00'])
})
test('git minimisation: commit_is_fix from the subject line only', async () => {
  for (const [subj, want] of [['Fix login bug', true], ['fix(8.2.7): x', true], ['Revert "x"', true], ['hotfix: y', true], ['FIXES #12', true], ['bugfix', true],
    ['prefix handling', false], ['fixture update', false], ['suffix', false], ['affix', false], ['Add feature', false], ['', false], ['äfix things', true]] as [string, boolean][])
    expect([subj, commitIsFix(subj)]).toEqual([subj, want])
  expect((await gitContext(full('Add feature'), '/p')).commit_is_fix).toBe(false)
})
test('git minimisation: the trace git object has no forbidden key', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }), git: (a: string[]) => a[1] === 'rev-parse' && a[2] === '--is-inside-work-tree' ? 'true' : a[1] === 'rev-parse' && a[2] === 'HEAD' ? 'cafe5678'
    : a[1] === 'log' && a[3] === '--format=%s' ? 'fix: thing' : a[1] === 'log' && a[3] === '--format=%an' ? 'Jane' : a[1] === 'rev-parse' && a[2] === '--abbrev-ref' ? 'main' : undefined })
  await mainTask($, h, [{ tool: 'Edit', file_path: '/proj/x.py', old_string: 'a', new_string: 'b' }, { tool: 'Bash', command: 'git commit -m x' }])
  await done($)
  const g = h.trace(h.learns()[0]!).git
  expect(Object.keys(g).every(k => [...ALLOWED, 'session_commits'].includes(k))).toBe(true)
  expect([g.commit_is_fix, g.session_commits]).toEqual([true, ['abc1234f']])
})
