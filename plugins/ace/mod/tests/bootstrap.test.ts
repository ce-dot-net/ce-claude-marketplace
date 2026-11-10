// 8.2.0 /ace:ace-bootstrap: both argument forms, validated passthrough, a short facts preview (argv-only git), the honest warning about
// what leaves the machine, and ONE readable result line after the CLI run (report formatter chosen by name).
import { expect, test } from 'claude-code/testing'
import { parseBootstrapArgs } from '../lib/bootstrap_args.ts'
import { bootstrapReport, reportLine } from '../lib/reports.ts'
import { CWD, PRJ, cliOf, host } from './helpers.ts'

const start = ($: any) => $.session.start({ cwd: CWD, surface: null, isInteractive: false } as any)
const run = async ($: any, args = '') => (await $.command.run({ command: 'ace:ace-bootstrap', args })).text as string
const cliRuns = (h: any, sub: string) => h.runs.filter((r: any) => cliOf(r.argv)?.[0] === sub)
const flagOf = (argv: string[], f: string) => { const i = argv.indexOf(f); return i < 0 ? undefined : argv[i + 1] }
const FILES = ['CLAUDE.md', 'README.md', 'docs/a.md', 'docs/b.md', 'docs/img/x.png', 'src/a.ts', 'src/b.ts', 'src/c.py', 'package.json'].join('\n') + '\n'
const gitStub = (commits: number) => (argv: string[]) => argv.includes('ls-files') ? FILES : argv.includes('rev-list') ? `${commits}\n` : undefined
const status = (n: number) => (a: string[]) => a[0] === 'status' ? { stdout: JSON.stringify({ playbook: { total_patterns: n } }) } : undefined

test('args: positional [mode] [level], flags, the = form, a mix; nothing given gives nothing (server defaults)', () => {
  expect(parseBootstrapArgs('')).toEqual({ ok: true, flags: [] })
  expect(parseBootstrapArgs('hybrid light')).toEqual({ ok: true, mode: 'hybrid', level: 'light', flags: [] })
  expect(parseBootstrapArgs('docs-only')).toEqual({ ok: true, mode: 'docs-only', flags: [] })
  expect(parseBootstrapArgs('light')).toEqual({ ok: true, level: 'light', flags: [] })
  expect(parseBootstrapArgs('--mode git-history --thoroughness deep')).toEqual({ ok: true, mode: 'git-history', level: 'deep', flags: [] })
  expect(parseBootstrapArgs('--mode=docs-only --thoroughness=medium')).toEqual({ ok: true, mode: 'docs-only', level: 'medium', flags: [] })
  expect(parseBootstrapArgs('docs-only --commit-limit 200 --days-back 30 --max-files 100'))
    .toEqual({ ok: true, mode: 'docs-only', flags: ['--commit-limit', '200', '--days-back', '30', '--max-files', '100'] })
  expect(parseBootstrapArgs('--days-back=7 both')).toEqual({ ok: true, mode: 'both', flags: ['--days-back', '7'] })
})

test('args: invalid values, conflicts, unknown flags and extra words are refused with the usage', () => {
  for (const bad of ['nope', 'hybrid nope', 'hybrid light extra', '--mode nope', '--mode', '--thoroughness huge', '--commit-limit 0', '--commit-limit -5',
    '--commit-limit abc', '--commit-limit 1.5', '--days-back 1e3', '--max-files 99999999999', '--max-files', '--evil 1', '--repo-path /etc',
    'hybrid --mode docs-only', 'light --thoroughness deep', '--mode hybrid --mode both', '--commit-limit 5 --commit-limit 6', '--commit-limit=', '--mode=x=y'])
    expect([bad, (parseBootstrapArgs(bad) as any).ok]).toEqual([bad, false])
  expect((parseBootstrapArgs('nope') as any).usage).toContain('/ace:ace-bootstrap')
  expect(parseBootstrapArgs('hybrid --mode hybrid')).toEqual({ ok: true, mode: 'hybrid', flags: [] })  // the same value twice is no conflict
})

test('nothing given: no --mode/--thoroughness in argv; the preview says the server default; both forms reach the CLI', async ($, on) => {
  const h = host(on, { cli: status(7), git: gitStub(50) })
  await start($)
  const t = await run($)
  expect(t).toContain('Standard des Servers')
  const a = h.pending().argv
  expect(a[0]).toBe('bootstrap')
  expect(a).not.toContain('--mode')
  expect(a).not.toContain('--thoroughness')
  expect(flagOf(a, '--repo-path')).toBe(CWD)
  expect(flagOf(a, '--project')).toBe(PRJ)
  await run($, 'docs-only light')
  const p = h.pending().argv
  expect(p.slice(p.indexOf('--mode'), p.indexOf('--mode') + 4)).toEqual(['--mode', 'docs-only', '--thoroughness', 'light'])
  await run($, '--mode git-history --thoroughness deep --commit-limit 250 --days-back 60 --max-files 10')
  const b = h.pending().argv
  expect([flagOf(b, '--mode'), flagOf(b, '--thoroughness'), flagOf(b, '--commit-limit'), flagOf(b, '--days-back'), flagOf(b, '--max-files')]).toEqual(['git-history', 'deep', '250', '60', '10'])
  expect(h.pending().report).toBe('bootstrap')
  expect(cliRuns(h, 'bootstrap').length).toBe(0)
})

test('a bad argument stores nothing', async ($, on) => {
  const h = host(on, { cli: status(0), git: gitStub(50) })
  await start($)
  expect(await run($, '--commit-limit 0')).toContain('Usage')
  expect(h.pending()).toBe(null)
})

test('preview facts: files by extension, commits in the window, docs, playbook size; short; git argv-only', async ($, on) => {
  const h = host(on, { cli: status(42), git: gitStub(50) })
  await start($)
  const t = await run($, 'docs-only medium')
  expect(t).toContain('9 Dateien')
  expect(t).toMatch(/ts 2/)
  expect(t).toContain('50 Commits')
  expect(t).toContain('90 Tage')
  expect(t).toContain('CLAUDE.md')
  expect(t).toContain('README.md')
  expect(t).not.toContain('ARCHITECTURE.md')
  expect(t).toMatch(/docs\/\*\.md.*2/)
  expect(t).toContain('42 Patterns')
  expect(t.split('\n').length).toBeLessThanOrEqual(15)
  const g = h.runs.filter((r: any) => r.argv[0] === 'git')
  expect(g.some((r: any) => r.argv.includes('ls-files'))).toBe(true)
  expect(g.some((r: any) => r.argv.includes('--count') && r.argv.some((x: string) => x.startsWith('--since=')))).toBe(true)
  expect(h.runs.filter((r: any) => r.argv.includes('ls-files') || r.argv.includes('rev-list')).every((r: any) => r.argv[0] === 'git' && !r.argv.includes('-c'))).toBe(true)
})

test('the window follows the arguments: --days-back wins over the level', async ($, on) => {
  const h = host(on, { cli: status(0), git: gitStub(50) })
  await start($)
  expect(await run($, 'hybrid deep')).toContain('180 Tage')
  expect(await run($, '--days-back 14')).toContain('14 Tage')
  expect(h.runs.some((r: any) => r.argv.includes('--since=14 days ago'))).toBe(true)
})

test('warning: hybrid, both, local-files and the unset default send source bodies and doc/diff text unredacted; docs-only says docs only', async ($, on) => {
  host(on, { cli: status(0), git: gitStub(50) })
  await start($)
  for (const m of ['hybrid', 'both', 'local-files', '']) {
    const t = await run($, m)
    expect([m, t.includes('unredigiert')]).toEqual([m, true])
    expect(t).toContain('Funktionskörper')
    expect(t).toContain('50 Quelldateien')
  }
  const d = await run($, 'docs-only')
  expect(d).toContain('unredigiert')
  expect(d).not.toContain('Funktionskörper')
  expect(d).toContain('20 Docs')
  const g = await run($, 'git-history')
  expect(g).toContain('Diffs')
  expect(g).not.toContain('Funktionskörper')
})

test('warnings: playbook >= 100 patterns and fewer than 20 commits: online learning is usually better', async ($, on) => {
  host(on, { cli: status(120), git: gitStub(12) })
  await start($)
  const t = await run($, 'docs-only')
  expect(t).toContain('Online-Lernen ist meist besser')
  expect(t).toContain('120 Patterns')
  expect(t).toContain('12 Commits')
})

test('a failing status or git leaves the preview intact (facts say unknown)', async ($, on) => {
  const h = host(on, { cli: a => a[0] === 'status' ? { exitCode: 1, stderr: 'boom' } : undefined, git: () => { throw new Error('git missing') } })
  await start($)
  const t = await run($, 'docs-only')
  expect(t).toContain('Noch nichts geändert')
  expect(t).toContain('unbekannt')
  expect(h.pending().argv[0]).toBe('bootstrap')
})

test('result line: counts, dedup, time, from the --json stdout', () => {
  const ok = JSON.stringify({ success: true, patternsExtracted: 42, patternsAfterDedup: 30, statistics: { compression_percentage: 28.6 }, processingTime: 12.34, message: 'x' })
  expect(bootstrapReport(ok)).toBe('Bootstrap fertig: 42 Patterns extrahiert, 30 nach Dedup, Kompression 28.6%, 12.3 s')
  expect(bootstrapReport(JSON.stringify({ success: true, patternsExtracted: 5, patternsAfterDedup: 5 }))).toBe('Bootstrap fertig: 5 Patterns extrahiert')
  expect(bootstrapReport(JSON.stringify({ success: true, patternsExtracted: 0, message: 'No patterns found in codebase' }))).toBe('Bootstrap fertig: keine Patterns gefunden')
  expect(bootstrapReport(JSON.stringify({ success: false, message: 'quota' }))).toBe('Bootstrap fehlgeschlagen: quota')
  expect(bootstrapReport('not json')).toBe(undefined)
  expect(bootstrapReport('[1]')).toBe(undefined)
  expect(bootstrapReport('{}')).toBe(undefined)
  expect(reportLine('bootstrap', ok)).toContain('42 Patterns')
  expect(reportLine('unknown', ok)).toBe(undefined)
})

test('the run (--approved) answers with the ONE readable line, not the raw JSON; other commands keep the raw stdout', async ($, on) => {
  const raw = JSON.stringify({ success: true, patternsExtracted: 42, patternsAfterDedup: 30, processingTime: 3, message: 'Playbook initialized successfully' })
  const h = host(on, { cli: a => status(1)(a) ?? (a[0] === 'bootstrap' ? { stdout: raw } : a[0] === 'learn' ? { stdout: '{"stored":true}' } : undefined), git: gitStub(50) })
  await start($)
  const t = await run($, 'docs-only --approved')
  expect(cliRuns(h, 'bootstrap').length).toBe(1)
  expect(t).toContain('erledigt')
  expect(t).toContain('Bootstrap fertig: 42 Patterns extrahiert, 30 nach Dedup, 3.0 s')
  expect(t).not.toContain('"patternsExtracted"')
  const l = (await $.command.run({ command: 'ace:ace-learn', args: 'a lesson --approved' })).text as string
  expect(l).toContain('{"stored":true}')
})

test('an unparseable bootstrap stdout falls back to the raw text', async ($, on) => {
  host(on, { cli: a => status(1)(a) ?? (a[0] === 'bootstrap' ? { stdout: 'plain output' } : undefined), git: gitStub(50) })
  await start($)
  expect(await run($, 'docs-only --approved')).toContain('plain output')
})
