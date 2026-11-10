// 8.2.0 `--approved` (Moshi/herdr: no button to press): a standalone `--approved` token runs a confirm command at once, like
// the band button; the preview prints the copy-paste line; the destructive pair (clear, cleanup) runs only on an identical waiting pending.
import { expect, test } from 'claude-code/testing'
import { stripApproved } from '../lib/approved.ts'
import { CWD, cliOf, host } from './helpers.ts'

const start = ($: any) => $.session.start({ cwd: CWD, surface: null, isInteractive: false } as any)
const run = async ($: any, name: string, args = '') => (await $.command.run({ command: `ace:ace-${name}`, args })).text as string
const cliRuns = (h: any, sub: string) => h.runs.filter((r: any) => cliOf(r.argv)?.[0] === sub)
const ST = (a: string[]) => a[0] === 'status' ? { stdout: '{"playbook":{"total_patterns":3}}' } : undefined

test('stripApproved: only a standalone token at the end, the start or next to a flag', () => {
  expect(stripApproved('')).toEqual({ args: '', approved: false })
  expect(stripApproved('--approved')).toEqual({ args: '', approved: true })
  expect(stripApproved('always pin the CLI --approved')).toEqual({ args: 'always pin the CLI', approved: true })
  expect(stripApproved('hybrid light --approved')).toEqual({ args: 'hybrid light', approved: true })
  expect(stripApproved('--approved docs-only')).toEqual({ args: 'docs-only', approved: true })
  expect(stripApproved('--mode docs-only --approved --days-back 30')).toEqual({ args: '--mode docs-only --days-back 30', approved: true })
  expect(stripApproved('--mode docs-only --approved')).toEqual({ args: '--mode docs-only', approved: true })
  // prose around it: not a flag position, stays in the text
  expect(stripApproved('say use --approved here')).toEqual({ args: 'say use --approved here', approved: false })
  expect(stripApproved('use "--approved" flag')).toEqual({ args: 'use "--approved" flag', approved: false })
  expect(stripApproved('quote "x --approved"')).toEqual({ args: 'quote "x --approved"', approved: false })
  expect(stripApproved('--approved-not x')).toEqual({ args: '--approved-not x', approved: false })
  expect(stripApproved('a\nb --approved')).toEqual({ args: 'a\nb', approved: true })
})

for (const [name, args, sub] of [['delta', 'add [{"content":"c","section":"s"}]', 'delta'], ['learn', 'always pin the CLI', 'learn'],
  ['bootstrap', 'docs-only light', 'bootstrap'], ['tune', 'search-top-k=20', 'tune']] as const) {
  test(`${name} --approved: runs the action at once, no pending left, the token never reaches argv`, async ($, on) => {
    const h = host(on, { cli: a => ST(a) ?? (a[0] === sub ? { stdout: '{}' } : undefined) })
    await start($)
    const t = await run($, name, `${args} --approved`)
    expect(cliRuns(h, sub).length).toBe(1)
    expect(cliRuns(h, sub)[0].argv.some((a: string) => a.includes('--approved'))).toBe(false)
    expect(t).toContain('erledigt')
    expect(t).not.toContain('Noch nichts geändert')
  })
}

test('without --approved the preview prints the exact line to copy', async ($, on) => {
  const h = host(on)
  await start($)
  const t = await run($, 'learn', 'always pin the CLI')
  expect(t).toContain('Noch nichts geändert')
  expect(t).toContain('/ace:ace-learn always pin the CLI --approved')
  expect(cliRuns(h, 'learn').length).toBe(0)
})

test('an --approved inside the learn text is lesson text, not the flag', async ($, on) => {
  const h = host(on)
  await start($)
  const t = await run($, 'learn', 'say use --approved here')
  expect(t).toContain('Noch nichts geändert')
  expect(cliRuns(h, 'learn').length).toBe(0)
  expect(h.pending().argv).toContain('--task=say use --approved here')
})

test('clear --approved without an identical pending waiting: preview only, nothing cleared', async ($, on) => {
  const h = host(on, { cli: ST })
  await start($)
  const t = await run($, 'clear', '--approved')
  expect(cliRuns(h, 'clear').length).toBe(0)
  expect(t).toContain('Clears ALL 3 patterns')
  expect(t).toContain('/ace:ace-clear --approved')
  expect(t).toMatch(/erst die Vorschau/)
})

test('clear --approved after the identical preview waits: runs; and only once', async ($, on) => {
  const h = host(on, { cli: a => ST(a) ?? (a[0] === 'clear' ? { stdout: '{}' } : undefined) })
  await start($)
  await run($, 'clear')
  expect(cliRuns(h, 'clear').length).toBe(0)
  const t = await run($, 'clear', '--approved')
  expect(cliRuns(h, 'clear').length).toBe(1)
  expect(t).toContain('erledigt')
  await run($, 'clear', '--approved')  // the pending was consumed, and this run only re-previews
  expect(cliRuns(h, 'clear').length).toBe(1)
})

test('clear --approved when another (different) pending waits: not run', async ($, on) => {
  const h = host(on, { cli: ST })
  await start($)
  await run($, 'learn', 'something else')
  await run($, 'clear', '--approved')
  expect(cliRuns(h, 'clear').length).toBe(0)
  expect(cliRuns(h, 'learn').length).toBe(0)
})

test('cleanup --approved: the same rule (identical waiting pending), then rm runs', async ($, on) => {
  const f = `${CWD}/.claude/data/logs/ace-relevance.1.jsonl`
  const h = host(on, { files: { [f]: 'x\n' } })
  await start($)
  h.advance(8 * 86_400_000)
  const t0 = await run($, 'cleanup', '--approved')
  expect(h.files.has(f)).toBe(true)
  expect(t0).toMatch(/erst die Vorschau/)
  await run($, 'cleanup')
  expect(h.files.has(f)).toBe(true)
  const t = await run($, 'cleanup', '--approved')
  expect(h.files.has(f)).toBe(false)
  expect(t).toContain('erledigt')
})

test('a failed action is told as failed, the pending is gone', async ($, on) => {
  const h = host(on, { cli: a => a[0] === 'learn' ? { exitCode: 1, stderr: 'boom' } : undefined })
  await start($)
  const t = await run($, 'learn', 'lesson --approved')
  expect(t).toContain('fehlgeschlagen (exit 1)')
  expect(t).toContain('boom')
  expect(cliRuns(h, 'learn').length).toBe(1)
})

test('--approved on a command that needs the band (login) is not run; the preview says to use the button', async ($, on) => {
  const h = host(on, { cli: a => a[0] === 'status' ? { exitCode: 1, stdout: '', stderr: 'Server error (401): token expired' } : undefined })
  await start($)
  const t = await run($, 'login', '--approved')
  expect(t).toContain('Button')
  expect(h.runs.some((r: any) => cliOf(r.argv)?.[0] === 'login')).toBe(false)
})
