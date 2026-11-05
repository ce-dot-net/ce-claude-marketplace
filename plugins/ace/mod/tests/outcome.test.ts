// ACE mod suite, 8.1.3 end-outcome rule: the shared fixture (tests-fixtures/task-outcome, wrapper ./fixtures/outcome_cases.ts).
// Mirror runner: tests/test_task_outcome.py (same cases, same expectations; it also guards table parity and the wrapper sync).
import { expect, test } from 'claude-code/testing'
import { CASES, TABLES } from './fixtures/outcome_cases.ts'
import { BENIGN_EXIT1, DECISIVE_TOOLS, READ_ONLY_BASH, buildTrace, commandFamily, taskOutcome, toolRec } from '../lib/trace.ts'

// A neutral fixture step -> the tool.call result the mod sees -> the real toolRec.
function rec(s: any, i: number) {
  const input: any = {}
  if (s.command !== undefined) input.command = s.command
  if (s.file_path !== undefined) input.file_path = s.file_path
  let res: any, isError = false, denied: string | undefined
  if (s.interrupted) res = { stdout: '', stderr: '', interrupted: true }
  else if (s.denied) denied = `Permission to use ${s.tool} has been denied.`
  else if (s.is_error) { isError = true; res = s.exit !== undefined ? `Exit code ${s.exit}\n${s.stderr ?? ''}` : (s.stderr || 'failed') }
  else if (s.tool === 'Bash') res = { stdout: s.stdout ?? '', stderr: s.stderr ?? '', interrupted: false, ...(s.exit !== undefined ? { exitCode: s.exit } : {}) }
  else if (s.tool === 'Edit' || s.tool === 'Write') res = { filePath: s.file_path }
  else res = { type: 'text' }
  return toolRec(s.tool, input, res, isError, denied, i, i + 1)
}

test('8.1.3: every shared fixture case gives the expected {success, failed_steps}', () => {
  expect(CASES.length >= 30).toBe(true)
  const got = CASES.map((c: any) => { const o = taskOutcome(c.steps.map(rec)); return { name: c.name, success: o.success, failed_steps: o.failed_steps, ...(o.aborted ? { aborted: true } : {}) } })
  expect(got).toEqual(CASES.map((c: any) => ({ name: c.name, ...c.expect })))
})

test('8.1.3: command families and tables equal the shared fixture', () => {
  expect(TABLES.families.map(([cmd]: string[]) => [cmd, commandFamily(cmd)])).toEqual(TABLES.families)
  expect([BENIGN_EXIT1, READ_ONLY_BASH, DECISIVE_TOOLS]).toEqual([TABLES.benign_exit1, TABLES.read_only_bash, TABLES.decisive_tools])
})

test('8.1.3: the trace carries result.success (end outcome) and result.failed_steps', () => {
  const tools = [rec({ tool: 'Bash', command: 'rstest tests', exit: 1, is_error: true }, 0), rec({ tool: 'Edit', file_path: '/p/a.py' }, 1),
    rec({ tool: 'Bash', command: 'rstest tests', exit: 0 }, 2)]
  const a = { userPrompt: 'fix it', answer: 'done', playbookUsed: [], agentType: 'main', appliedLogIds: [], nowIso: 'x', effort: 'normal' }
  const ok = buildTrace({ ...a, tools })
  expect([ok.success, ok.trace.result.success, ok.trace.result.failed_steps]).toEqual([true, true, 1])
  expect('aborted' in ok.trace.result).toBe(false)  // contract: result.aborted only when true
  const cut = buildTrace({ ...a, tools: [...tools, rec({ tool: 'Bash', command: 'rstest tests', interrupted: true }, 3)] })
  expect([cut.trace.result.success, cut.trace.result.failed_steps, cut.trace.result.aborted]).toEqual([false, 2, true])
  const none = buildTrace({ ...a, tools: [] })
  expect([none.trace.result.success, none.trace.result.failed_steps]).toEqual([true, 0])
  const red = buildTrace({ ...a, tools: tools.slice(0, 2) })
  expect([red.trace.result.success, red.trace.result.failed_steps]).toEqual([false, 1])
})

test('8.1.3: stderr alone never marks a step failed; grep exit 1 is not a failed step', () => {
  expect(toolRec('Bash', { command: 'git push' }, { stdout: '', stderr: 'To github.com:o/r.git', interrupted: false, exitCode: 0 }, false, undefined, 0, 1).failed).toBe(false)
  expect(toolRec('Bash', { command: 'npm i' }, { stdout: '', stderr: 'npm warn x' }, false, undefined, 0, 1).failed).toBe(false)
  expect(toolRec('Bash', { command: 'grep x f' }, 'Exit code 1', true, undefined, 0, 1).failed).toBe(false)
  expect(toolRec('Bash', { command: 'make' }, { stdout: '', stderr: '', exitCode: 1, returnCodeInterpretation: 'x' }, false, undefined, 0, 1).failed).toBe(false)
})
