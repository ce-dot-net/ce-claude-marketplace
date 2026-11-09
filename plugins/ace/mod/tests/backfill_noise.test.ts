// 8.2.0 tool-noise filter for session items: failed lookups and empty-result greps are dropped before the trace is built.
import { expect, test } from 'claude-code/testing'
import { denoise, NOISE } from '../lib/backfill_noise.ts'
import { toolRec } from '../lib/trace.ts'

const rec = (tool: string, input: any, res: any, isError = false, text?: string) => toolRec(tool, input, res, isError, undefined, 1000, 2000, text)
const readFail = (msg: string) => rec('Read', { file_path: '/r/x.ts' }, msg, true, msg)
const edit = (file = '/r/a.ts') => rec('Edit', { file_path: file, old_string: 'a', new_string: 'b' }, { filePath: file })

test('every pattern has a name and drops a failed Read that matches it', () => {
  const samples: Record<string, string> = {
    'file-missing': 'File does not exist. Note: your current working directory is /r',
    'enoent': 'ENOENT: open /r/x',
    'no-such-file': 'cat: /r/x: No such file or directory',
    'permission': 'EACCES: Permission denied',
  }
  for (const [name, msg] of Object.entries(samples)) {
    const r = denoise([readFail(msg), edit()])
    expect(r.tools.map(t => t.tool)).toEqual(['Edit'])
    expect(r.dropped[name]).toBe(1)
    expect(r.droppedSteps).toBe(1)
  }
  expect(NOISE.map(n => n.name)).toEqual(expect.arrayContaining(Object.keys(samples)))
})

test('empty-result lookups that did NOT fail are dropped by pattern: Grep/Glob found 0 files, No matches found, No files found', () => {
  const empty = rec('Grep', { pattern: 'x' }, { filenames: [] })
  const glob = rec('Glob', { pattern: '*.zz' }, { files: [] })
  const nm = rec('Grep', { pattern: 'x' }, 'No matches found')
  const nf = rec('Glob', { pattern: 'x' }, 'No files found')
  const r = denoise([empty, glob, nm, nf, edit()])
  expect(r.tools.map(t => t.tool)).toEqual(['Edit'])
  expect(r.droppedSteps).toBe(4)
})

test('Exit code 1 of an empty-result read-only Bash (grep, ls, find) is dropped; a decisive Bash is not', () => {
  const g = rec('Bash', { command: 'grep -rn foo src' }, { stdout: '', stderr: '', exitCode: 1 })
  const ls = rec('Bash', { command: 'ls /nope' }, 'Exit code 1\nls: /nope: No such file or directory', true, 'Exit code 1\nls: /nope: No such file or directory')
  const build = rec('Bash', { command: 'npm run build' }, 'Exit code 1\nerror TS2304', true, 'Exit code 1\nerror TS2304')
  const r = denoise([g, ls, build, edit()])
  expect(r.tools.length).toBe(2)
  expect(r.tools[0].failed).toBe(true)  // the failed build stays: it is real work that failed
})

test('a failed non-decisive step is dropped even when no pattern matches', () => {
  const r = denoise([rec('WebFetch', { url: 'http://x' }, 'timeout', true, 'timeout'), edit()])
  expect(r.tools.map(t => t.tool)).toEqual(['Edit'])
})

test('real work with similar words is NOT dropped: an Edit of does-not-exist.ts, an ok Read, an ok Bash echoing the phrase', () => {
  const e = edit('/r/does-not-exist.ts')
  const read = rec('Read', { file_path: '/r/does-not-exist.ts' }, { file: { content: 'a\nb' } })
  const echo = rec('Bash', { command: 'echo "No such file or directory handled"' }, { stdout: 'No such file or directory handled', stderr: '', exitCode: 0 })
  const r = denoise([e, read, echo])
  expect(r.tools.length).toBe(3)
  expect(r.droppedSteps).toBe(0)
})

test('a failed decisive Edit (File does not exist) is kept: the failure still counts against the task', () => {
  const bad = rec('Edit', { file_path: '/r/z.ts', old_string: 'a', new_string: 'b' }, 'File does not exist.', true, 'File does not exist.')
  expect(denoise([bad, edit()]).tools.length).toBe(2)
})

test('an interrupted step is kept', () => {
  const i = toolRec('Read', { file_path: '/r/q' }, { interrupted: true }, false, undefined, 1, 2)
  expect(denoise([i, edit()]).tools.length).toBe(2)
})
