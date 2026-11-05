// ACE mod suite, 8.1.3 end-outcome rule: the shared fixture (tests-fixtures/task-outcome, wrapper ./fixtures/outcome_cases.ts).
// Mirror runner: tests/test_task_outcome.py (same cases, same expectations; it also guards table parity and the wrapper sync).
import { expect, test } from 'claude-code/testing'
import { CASES, RANDOM, TABLES } from './fixtures/outcome_cases.ts'
import { BENIGN_EXIT1, DECISIVE_TOOLS, MCP_WRITE_VERBS, READ_ONLY_BASH, SUBCOMMAND_TOOLS, bashStep, buildTrace, commandFamily, redact, summarizeAction, taskOutcome, toolRec } from '../lib/trace.ts'

// A neutral fixture step -> the tool.call result the mod sees -> the real toolRec.
function rec(s: any, i: number) {
  const input: any = {}
  if (s.command !== undefined) input.command = s.command
  if (s.file_path !== undefined) input.file_path = s.file_path
  let res: any, isError = false, denied: string | undefined, text: string | undefined
  if (s.interrupted) res = { stdout: '', stderr: '', interrupted: true }
  else if (s.denied) denied = `Permission to use ${s.tool} has been denied.`
  else if (s.is_error && s.tool === 'Bash' && s.exit !== undefined) {  // tool.call: result keeps stdout/stderr, "Exit code N" is only in text
    isError = true; res = { stdout: '', stderr: s.stderr ?? '', interrupted: false }; text = `Exit code ${s.exit}\n${s.stderr ?? ''}`
  } else if (s.is_error) { isError = true; res = s.stderr || 'failed' }
  else if (s.tool === 'Bash') res = { stdout: s.stdout ?? '', stderr: s.stderr ?? '', interrupted: false, ...(s.exit !== undefined ? { exitCode: s.exit } : {}) }
  else if (s.tool === 'Edit' || s.tool === 'Write') res = { filePath: s.file_path }
  else res = { type: 'text' }
  return toolRec(s.tool, input, res, isError, denied, i, i + 1, text)
}

test('8.1.3: every shared fixture case gives the expected {success, failed_steps}', () => {
  expect(CASES.length >= 30).toBe(true)
  const got = CASES.map((c: any) => { const o = taskOutcome(c.steps.map(rec)); return { name: c.name, success: o.success, failed_steps: o.failed_steps, ...(o.aborted ? { aborted: true } : {}) } })
  expect(got).toEqual(CASES.map((c: any) => ({ name: c.name, ...c.expect })))
})

test('8.1.3: command families and tables equal the shared fixture', () => {
  expect(TABLES.families.map(([cmd]: string[]) => [cmd, commandFamily(cmd)])).toEqual(TABLES.families)
  expect([BENIGN_EXIT1, READ_ONLY_BASH, DECISIVE_TOOLS, SUBCOMMAND_TOOLS, MCP_WRITE_VERBS]).toEqual(
    [TABLES.benign_exit1, TABLES.read_only_bash, TABLES.decisive_tools, TABLES.subcommand_tools, TABLES.mcp_write_verbs])
})

test('8.1.3 property: the 400 seeded random sequences give what the Python chain computed', () => {
  expect(RANDOM.length).toBe(400)
  const got = RANDOM.map((c: any) => { const o = taskOutcome(c.steps.map(rec)); return { name: c.name, success: o.success, failed_steps: o.failed_steps, ...(o.aborted ? { aborted: true } : {}) } })
  expect(got).toEqual(RANDOM.map((c: any) => ({ name: c.name, ...c.expect })))
})

test('8.1.3: Bash action = "<family> :: <redacted command <= 200>", unknown when there is none; redaction table', () => {
  expect(TABLES.actions.map(([cmd]: any[]) => [cmd, summarizeAction('Bash', cmd === null ? {} : { command: cmd })])).toEqual(TABLES.actions)
  expect(TABLES.redact.map(([t]: string[]) => [t, redact(t)])).toEqual(TABLES.redact)
  expect(TABLES.keys.map(([c]: string[]) => [c, bashStep(c)[2]])).toEqual(TABLES.keys)
  for (const c of ['git clone https://u:Zq7c@github.com/o/r', 'git push https://Zq7c@h/o/r', 'gh auth login Zq7cZq7cZq7cZq7cZq7cZq7c0',
    'curl -u a:Zq7c https://h', 'npm publish --token=Zq7c', 'docker login ghp_Zq7cZq7cZq7c']) expect(commandFamily(c).includes('Zq7c')).toBe(false)
  for (const c of ['"', "'", '$(', '`', '((', '))', '<<', '<<EOF', '| |', '&& ;', '\\', 'a |& b', '\x00', 123]) { commandFamily(c); expect(!!summarizeAction('Bash', { command: c })).toBe(true) }
})

test('8.1.3 fuzz: 300 random passwords x 6 forms reach no sent trace field', () => {
  const strings = (x: any): string[] => typeof x === 'string' ? [x] : x && typeof x === 'object' ? Object.values(x).flatMap(strings) : []
  const leaks: string[] = []
  for (const pw of TABLES.fuzz_passwords) for (const tpl of TABLES.fuzz_templates) {
    const cmd = tpl.split('{pw}').join(pw)
    const tools = [toolRec('Bash', { command: cmd }, { stdout: '', stderr: cmd, interrupted: false }, true, undefined, 0, 1, `Exit code 1\n${cmd}`),
      toolRec('Bash', { command: cmd }, { stdout: cmd, stderr: '', interrupted: false }, false, undefined, 1, 2)]
    const t = buildTrace({ userPrompt: `run ${cmd}`, answer: `ran ${cmd}`, playbookUsed: [], agentType: 'main', appliedLogIds: [], nowIso: 'x', effort: 'normal', tools })
    if (strings(t.trace).some(v => v.includes(pw))) leaks.push(tpl)
  }
  expect(leaks).toEqual([])
})

test('8.1.3: canary secrets reach no sent trace field (action, result, summary, task)', () => {
  const C = 'ghp_CANARYcanary0123456789', U = 'CANARYurl', Y = 'CANARYyaml', M = 'CANARYmysql'
  const tools = [toolRec('Bash', { command: `git clone https://user:${U}@github.com/o/r` }, { stdout: '', stderr: `fatal: https://user:${U}@github.com`, interrupted: false }, true, undefined, 0, 1, `Exit code 128\nfatal: https://user:${U}@github.com/o/r`),
    toolRec('Bash', { command: `mysql -uroot -p${M} db` }, { stdout: `password: ${Y}`, stderr: '', interrupted: false }, false, undefined, 0, 1),
    toolRec('mcp__srv__save_issue', { body: Y }, `{"password":"${Y}"}`, true, undefined, 0, 1),toolRec('Bash', { command: `GITHUB_TOKEN=${C} gh release create v1` }, { stdout: `token ${C}`, stderr: '', interrupted: false }, false, undefined, 0, 1),
    toolRec('Bash', { command: `curl -H "Authorization: Bearer ${C}" https://x` }, { stdout: '', stderr: `bad ${C}`, interrupted: false }, true, undefined, 1, 2, `Exit code 22\nbad ${C}`)]
  const t = buildTrace({ userPrompt: `use ${C} and https://u:${U}@h password: ${Y}`, answer: `ran gh with ${C}, git clone https://user:${U}@github.com, password: ${Y}, mysql -p${M}`, playbookUsed: [], agentType: 'main', appliedLogIds: [], nowIso: 'x', effort: 'normal', tools })
  expect(JSON.stringify(t.trace).includes('CANARY')).toBe(false)
  expect(t.trace.trajectory[3].action.startsWith('gh release create :: ')).toBe(true)
  expect(t.trace.trajectory[0].action).toBe('git :: git clone https://[redacted]@github.com/o/r')
})

test('8.1.3: the trace carries result.success (end outcome) and result.failed_steps', () => {
  const tools = [rec({ tool: 'Bash', command: 'rstest tests', exit: 1, is_error: true }, 0), rec({ tool: 'Edit', file_path: '/p/a.py' }, 1),
    rec({ tool: 'Bash', command: 'rstest tests', exit: 0 }, 2)]
  const a = { userPrompt: 'fix it', answer: 'done', playbookUsed: [], agentType: 'main', appliedLogIds: [], nowIso: 'x', effort: 'normal' }
  const ok = buildTrace({ ...a, tools })
  expect([ok.success, ok.trace.result.success, ok.trace.result.failed_steps]).toEqual([true, true, 1])
  expect('aborted' in ok.trace.result).toBe(false)  // 8.1.3: no result.aborted (no aborted run sends a trace)
  const cut = buildTrace({ ...a, tools: [...tools, rec({ tool: 'Bash', command: 'rstest tests', interrupted: true }, 3)] })
  expect([cut.trace.result.success, cut.trace.result.failed_steps, 'aborted' in cut.trace.result]).toEqual([false, 2, false])  // no aborted key in the contract
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
