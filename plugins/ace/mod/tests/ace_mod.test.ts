// ACE v8.0.0 production mod - `claude plugin test plugins/ace` suite (DESIGN §13.1, §12, §9 G9, §4/C1).
//
// Contract pinned here (the mod under plugins/ace/mod/ must satisfy it):
// - Data root = <HOME>/.claude/plugins/data/<name>-<marketplace> derived from $.plugin.root
//   (.../plugins/cache/<marketplace>/<name>/<ver>), else <name>-inline (a --plugin-dir load, as
//   here). Never $.env.get('CLAUDE_PLUGIN_DATA') (F1: that is the HOST env, not this plugin's).
// - State layout and JSON formats are the Python ones (plugin_data_dir.py, patterns_used_state.py):
//   <root>/projects/<prj>/sessions/<sid>/patterns-used-<main|agentId>.json, domain-last-<agent>.txt,
//   learn-inflight-<agent>.lock, rendered-main.txt, mod-active, disabled.flag; <root>/pin-backoff;
//   <root>/projects/<prj>/domains.json; relevance rows APPENDED to <cwd>/.claude/data/logs/ace-relevance.jsonl
//   through $.process.run (stdin = one JSON row per line; argv names the log path).
// - ace-cli consumed as-is through $.process.run(['ace-cli', ...], { stdin, env, timeoutMs }).
// - Files are removed through $.process.run with an `rm` (the kit host below emulates it).
// - Goldens come from tests/e2e/mod_reference.py (the Python chain's own render/state writers).
import { expect, test } from 'claude-code/testing'
import S100 from './fixtures/search_100.ts'
import S8 from './fixtures/search_8.ts'
import SEDGE from './fixtures/search_edge.ts'
import G from './fixtures/golden.ts'

const HOME = '/home/u', CWD = '/proj', SID = 'sess-1', PRJ = 'prj_t'
const ROOT = `${HOME}/.claude/plugins/data/ace-inline`
const PDIR = `${ROOT}/projects/${PRJ}`, SDIR = `${PDIR}/sessions/${SID}`
const REL = `${CWD}/.claude/data/logs/ace-relevance.jsonl`
const EVAL_REQ = `${CWD}/.claude/data/logs/ace-eval-request.json`
const UUID4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/
const HUMAN = 'please fix the domain shift hook so it injects patterns when reading plugin files'
const LOCKED = { exitCode: 1, stdout: '', stderr: 'SqliteError: database is locked' }
const MIN = 60_000

type SearchAnswer = { exitCode?: number; stdout?: string; stderr?: string; advanceMs?: number }
type Opts = { search?: (argv: string[], stdin?: string) => SearchAnswer; env?: Record<string, string>; files?: Record<string, string> }
type Run = { argv: string[]; stdin?: string; env?: Record<string, string>; timeoutMs?: number; files: Set<string> }

// In-memory engine: fs (with mtimes on the mocked clock), env, clock, session, process. Every argv is recorded.
function host(on: any, o: Opts = {}) {
  const T0 = 1_800_000_000_000
  let now = T0
  const files = new Map<string, string>(), mtime = new Map<string, number>()
  const put = (p: string, t: string) => { files.set(p, t); mtime.set(p, now) }
  put(`${CWD}/.claude/settings.json`, JSON.stringify({ projectId: PRJ, orgId: 'org_t' }))
  for (const [k, v] of Object.entries(o.files ?? {})) put(k, v)
  const runs: Run[] = [], logs: string[] = [], envAsked: string[] = []
  const env: Record<string, string> = { HOME, ...(o.env ?? {}) }
  let spawnN = 0
  const res = (exitCode: number, stdout: string, stderr = '') =>
    ({ value: { exitCode, stdout, stderr, isStdoutTruncated: false, isStderrTruncated: false } })
  const dflt = (argv: string[]): SearchAnswer => ({ stdout: argv.includes('--top-k') ? S8 : S100 })
  const git = (argv: string[]) => argv.includes('--abbrev-ref') ? 'main\n'
    : argv.includes('rev-parse') && argv.includes('HEAD') ? 'abc123\n'
    : argv.includes('--git-dir') ? '.git\n' : argv.includes('--is-inside-work-tree') ? 'true\n' : ''

  on('session.id', () => ({ value: SID }))
  on('session.cwd', () => ({ value: CWD }))
  on('session.root', () => ({ value: CWD }))
  on('env.get', (_$: any, e: any) => { envAsked.push(e.name); return { value: env[e.name] } })
  on('clock.now', () => ({ value: now }))
  on('fs.exists', (_$: any, e: any) => ({ value: files.has(e.path) || [...files.keys()].some(k => k.startsWith(e.path + '/')) }))
  on('fs.read', (_$: any, e: any) => { if (!files.has(e.path)) throw new Error('ENOENT: ' + e.path); return { value: files.get(e.path) } })
  on('fs.write', (_$: any, e: any) => { put(e.path, e.text); return { value: undefined } })
  on('fs.stat', (_$: any, e: any) => {
    if (!files.has(e.path)) throw new Error('ENOENT: ' + e.path)
    return { value: { kind: 'file', size: files.get(e.path)!.length, mtimeMs: mtime.get(e.path), isLink: false } }
  })
  on('process.run', (_$: any, e: any) => {
    const argv = [...e.argv] as string[], init = e.init ?? {}
    runs.push({ argv, stdin: init.stdin, env: init.env, timeoutMs: init.timeoutMs, files: new Set(files.keys()) })
    if (argv[0] === 'ace-cli' && argv[1] === 'search') {
      const a = (o.search ?? dflt)(argv, init.stdin)
      now += a.advanceMs ?? 0
      return res(a.exitCode ?? 0, a.stdout ?? '', a.stderr ?? '')
    }
    if (argv[0] === 'git' || argv[0].endsWith('/git')) return res(0, git(argv))
    if (argv.some(a => /(^|[\s;&|(])rm($|\s)/.test(a) || a === 'rm'))
      for (const a of argv) for (const k of [...files.keys()]) if (k === a || k.startsWith(a + '/')) files.delete(k)
    return res(0, '')
  })
  on('ui.log', (_$: any, e: any) => { logs.push(e.text); return { value: undefined } })
  on('ui.status', () => ({ value: undefined }))
  on('ui.toast', () => ({ value: undefined }))
  on('prompt.submit', (_$: any, e: any) => ({ text: e.text, context: e.context }))
  on('agent.spawn', (_$: any, e: any) => ({ model: 'claude-haiku-4-5', agentId: e.resume?.agentId ?? `agent-${++spawnN}`, seenPrompt: e.prompt }))
  on('tool.call', (_$: any, e: any) => e.tool === 'Bash' ? ({ result: { stdout: e.command === 'big' ? 'y'.repeat(30000) : 'ok', stderr: '', interrupted: false } })
    : e.tool === 'Edit' || e.tool === 'Write' ? ({ result: { filePath: e.file_path } })
    : ({ result: { type: 'text', file: { content: 'a\nb', filePath: e.file_path } } }))
  on('turn.start', (_$: any, e: any) => ({ turnId: e.turnId }))
  on('turn.complete', (_$: any, e: any) => ({ text: e.answer }))
  on('session.start', (_$: any, e: any) => ({ cwd: e.cwd }))
  on('session.end', (_$: any, e: any) => ({ sessionId: e.sessionId }))
  on('classic.UserPromptSubmit', () => ({}))
  on('classic.Stop', () => ({}))
  on('classic.SubagentStop', () => ({}))

  const isSearch = (r: Run) => r.argv[0] === 'ace-cli' && r.argv[1] === 'search'
  const searches = () => runs.filter(isSearch)
  const learns = () => runs.filter(r => !isSearch(r) && r.argv.includes('ace-cli') && r.argv.includes('learn'))
  const rows = () => runs.filter(r => r.argv.includes(REL) && typeof r.stdin === 'string')
    .flatMap(r => r.stdin!.split('\n').filter(Boolean).map(l => JSON.parse(l)))
  const state = (agent = 'main') => {
    const t = files.get(`${SDIR}/patterns-used-${agent}.json`)
    return t === undefined ? undefined : JSON.parse(t)
  }
  const pin = (r: Run) => { const i = r.argv.indexOf('--pin-session'); return i < 0 ? undefined : r.argv[i + 1] }
  const learnArgv = (r: Run) => r.argv.slice(r.argv.indexOf('ace-cli'))
  const flag = (argv: string[], f: string) => { const i = argv.indexOf(f); return i < 0 ? undefined : argv[i + 1] }
  const trace = (r: Run) => JSON.parse(files.get(flag(learnArgv(r), '--transcript')!)!)
  return { files, mtime, runs, logs, envAsked, searches, learns, rows, state, pin, learnArgv, flag, trace,
    advance: (ms: number) => { now += ms }, now: () => now, put }
}

const submit = ($: any, text = HUMAN, kind = 'composer') => $.prompt.submit({ text, wait: false, origin: { kind } } as any)
const spawn = ($: any, prompt: string, extra: any = {}) => $.agent.spawn({ prompt, description: 'x', subagentType: 'general-purpose',
  fork: false, background: false, tool_use_id: 'toolu_1', parentModel: 'claude-opus', provider: { plugin: 'engine', tier: 'core' }, ...extra } as any)
const ranked = (text: string) => JSON.parse(text).similar_patterns.map((p: any, i: number) => ({ p, i }))
  .sort((a: any, b: any) => {
    const ra = a.p.match_factors?.bandit_rank ?? null, rb = b.p.match_factors?.bandit_rank ?? null
    if (ra === null || rb === null) return ra === null && rb === null ? a.i - b.i : ra === null ? 1 : -1
    return ra - rb || a.i - b.i
  }).map((x: any) => x.p)
const shownOf = (ctx: string) => Number(/shown="(\d+)"/.exec(ctx)![1])
const bodyOf = (ctx: string) => JSON.parse(ctx.slice(ctx.indexOf('\n') + 1, ctx.lastIndexOf('\n')))

// ---------- data dir, marker, coexistence ----------

test('data dir derives from $.plugin.root (<name>-inline here), never from CLAUDE_PLUGIN_DATA', async ($, on) => {
  const h = host(on, { env: { CLAUDE_PLUGIN_DATA: '/elsewhere/other-plugin' } })
  await submit($)
  expect(h.state()).toBeDefined()
  expect([...h.files.keys()].some(k => k.startsWith('/elsewhere'))).toBe(false)
  expect(h.envAsked.includes('CLAUDE_PLUGIN_DATA')).toBe(false)
})

test('session.start writes the mod-active marker in the session dir', async ($, on) => {
  const h = host(on)
  await $.session.start({ cwd: CWD, surface: null, isInteractive: false } as any)
  expect(h.files.has(`${SDIR}/mod-active`)).toBe(true)
})

test('every prompt.submit (human or machine) refreshes the mod-active marker', async ($, on) => {
  const h = host(on)
  await $.session.start({ cwd: CWD, surface: null, isInteractive: false } as any)
  const t0 = h.mtime.get(`${SDIR}/mod-active`)!
  h.advance(5 * MIN)
  await submit($, '<task-notification><task-id>x</task-id> done</task-notification>')
  const t1 = h.mtime.get(`${SDIR}/mod-active`)!
  expect(t1 > t0).toBe(true)
  h.advance(5 * MIN)
  await submit($)
  expect(h.mtime.get(`${SDIR}/mod-active`)! > t1).toBe(true)
})

// ---------- prompt.submit: search, pin, render, state ----------

test('prompt.submit: one pinned search with a fresh uuid4 task pin per human prompt, full render golden', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }) })
  const r: any = await submit($)
  expect(h.searches().length).toBe(1)
  const s = h.searches()[0]!
  expect(s.argv.slice(0, 5)).toEqual(['ace-cli', 'search', '--stdin', '--json', '--pin-session'])
  expect(UUID4.test(h.pin(s)!)).toBe(true)
  expect(s.argv.includes('--top-k')).toBe(false)
  expect(s.stdin).toBe(HUMAN)
  expect(s.env!.ACE_PROJECT_ID).toBe(PRJ)
  expect(s.env!.ACE_ORG_ID).toBe('org_t')
  expect(s.timeoutMs! <= 25000).toBe(true)
  expect(r.context.length).toBe(1)
  expect(r.context[0]).toBe(G.full_main_8)
  await submit($, HUMAN + ' again please')
  expect(h.pin(h.searches()[1]!)).not.toBe(h.pin(s))
  const row = h.rows().find((x: any) => x.event === 'search')!
  expect(row.hook).toBe('UserPromptSubmit')
  expect(row.session_id).toBe(SID)
  expect(row.patterns_returned).toBe(8)
  expect(row.patterns_injected).toBe(8)
  expect(row.render_cohort).toBe('full')
  expect(row.task_session_id).toBe(h.pin(s))
  expect(row.source).toBe('mod')
  expect(/Z$/.test(row.timestamp)).toBe(true)
})

test('prompt.submit renders ALL 100 patterns, and the edge-case fixture byte-exactly', async ($, on) => {
  let out = S100
  const h = host(on, { search: () => ({ stdout: out }) })
  const r: any = await submit($)
  expect(r.context[0].startsWith('<ace-patterns shown="100" of="100" agent-type="main">\n{')).toBe(true)
  expect(bodyOf(r.context[0]).similar_patterns.length).toBe(100)
  out = SEDGE
  const r2: any = await submit($, HUMAN + ' edge')
  expect(r2.context[0]).toBe(G.full_main_edge)
  expect(h.searches().length).toBe(2)
})

test('state: patterns-used-main.json is byte-identical to the Python writer (shared fixture state_main_8)', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }) })
  await submit($)
  const tsid = h.pin(h.searches()[0]!)!
  const text = h.files.get(`${SDIR}/patterns-used-main.json`)!
  expect(text.split(tsid).join('__TSID__')).toBe(G.state_main_8)
})

test('state: user_prompt <= 4000, rendered_context <= 10000 and a complete envelope, F-080 ids of the injected set', async ($, on) => {
  const h = host(on)
  const long = HUMAN + ' ' + 'x'.repeat(5000)
  await submit($, long)
  const st = h.state()!
  expect(st.user_prompt).toBe(long.slice(0, 4000))
  expect(st.hook_event_name).toBe('UserPromptSubmit')
  expect(st.retrieval_id).toBe(JSON.parse(S100).retrieval_id)
  expect(st.task_session_id).toBe(h.pin(h.searches()[0]!))
  expect(st.pattern_ids.length).toBe(98)
  expect(Object.keys(st.retrieval_log_ids).length).toBe(84)
  expect(Object.values(st.retrieval_log_ids).every((v: any) => Number.isInteger(v))).toBe(true)
  const rc: string = st.rendered_context
  expect(rc.length <= 10000).toBe(true)
  expect(rc.startsWith('<ace-patterns shown="')).toBe(true)
  expect(rc.endsWith('\n</ace-patterns>')).toBe(true)
  expect(bodyOf(rc).similar_patterns.length).toBe(shownOf(rc))
})

test('prompt.submit writes domains.json (domains_summary) for the domain shift', async ($, on) => {
  const h = host(on)
  await submit($)
  expect(JSON.parse(h.files.get(`${PDIR}/domains.json`)!)).toEqual(JSON.parse(S100).domains_summary)
})

test('machine, short, slash-command and /ace prompts never search', async ($, on) => {
  const h = host(on)
  await submit($, '<task-notification><task-id>x</task-id> done</task-notification>')
  await submit($, 'a long enough notification text body', 'task-notification')
  await submit($, '<system-reminder>only a reminder</system-reminder>')
  await submit($, 'ok thanks')
  await submit($, '/ace-status please now')
  expect(h.searches().length).toBe(0)
})

test('disabled.flag (session or project) → no search, no context', async ($, on) => {
  const h = host(on, { files: { [`${SDIR}/disabled.flag`]: '' } })
  const r: any = await submit($)
  expect(h.searches().length).toBe(0)
  expect(r.context === undefined || r.context.length === 0).toBe(true)
  h.files.delete(`${SDIR}/disabled.flag`)
  h.put(`${PDIR}/disabled.flag`, '')
  await submit($, HUMAN + ' again')
  expect(h.searches().length).toBe(0)
})

// ---------- §13.1 gaps: 100K guard, pin-drop budget, cohorts ----------

test('100K guard: an oversized render is cut to <= 95,000 chars by dropping tail patterns, logged truncated_for_cap', async ($, on) => {
  const big = JSON.parse(S100)
  big.similar_patterns.forEach((p: any, i: number) => { p.content = 'x'.repeat(1500) + ' #' + i })
  const BIG = JSON.stringify(big)
  const h = host(on, { search: () => ({ stdout: BIG }) })
  const r: any = await submit($)
  const ctx: string = r.context[0]
  expect(ctx.length <= 95000).toBe(true)
  expect(ctx.length > 85000).toBe(true)
  const k = shownOf(ctx)
  expect(k < 100).toBe(true)
  expect(ctx.startsWith(`<ace-patterns shown="${k}" of="100" agent-type="main">\n`)).toBe(true)
  expect(bodyOf(ctx).similar_patterns.map((p: any) => p.content)).toEqual(ranked(BIG).slice(0, k).map((p: any) => p.content))
  const row = h.rows().find((x: any) => x.event === 'search')!
  expect(row.truncated_for_cap).toBe(true)
  expect(row.patterns_injected).toBe(k)
  expect(h.state()!.pattern_ids.every((id: string) => bodyOf(ctx).similar_patterns.some((p: any) => p.id === id))).toBe(true)
})

test('pin-drop: "database is locked" → ONE unpinned re-run, pin_failed logged, pin-backoff touched', async ($, on) => {
  const h = host(on, { search: (argv) => argv.includes('--pin-session') ? LOCKED : { stdout: S8 } })
  const r: any = await submit($)
  expect(h.searches().length).toBe(2)
  expect(h.searches()[1]!.argv.includes('--pin-session')).toBe(false)
  expect(r.context[0]).toBe(G.full_main_8)
  expect(h.rows().find((x: any) => x.event === 'search')!.pin_failed).toBe(true)
  expect(h.files.has(`${ROOT}/pin-backoff`)).toBe(true)
})

test('pin-backoff younger than 30 min → no pin up front (pin_skipped backoff); older → pinned again', async ($, on) => {
  const h = host(on, { files: { [`${ROOT}/pin-backoff`]: '' } })
  await submit($)
  expect(h.searches().length).toBe(1)
  expect(h.searches()[0]!.argv.includes('--pin-session')).toBe(false)
  expect(h.rows().find((x: any) => x.event === 'search')!.pin_skipped).toBe('backoff')
  expect(h.state()!.task_session_id).toBeDefined()
  h.advance(31 * MIN)
  await submit($, HUMAN + ' later')
  expect(h.searches()[1]!.argv.includes('--pin-session')).toBe(true)
})

test('blocking budget <= 25 s: the unpinned retry only gets the time left; none left → no retry', async ($, on) => {
  let spent = 20_000
  const h = host(on, { search: (argv) => argv.includes('--pin-session') ? { ...LOCKED, advanceMs: spent } : { stdout: S8 } })
  await submit($)
  const retry = h.searches()[1]!
  expect(retry.timeoutMs! > 0 && retry.timeoutMs! <= 5_000).toBe(true)
  spent = 25_000
  const r: any = await submit($, HUMAN + ' slow')
  expect(h.searches().length).toBe(3)
  expect(r.context === undefined || r.context.length === 0).toBe(true)
})

test('render_cohort ACE_AB_CONTROL_PCT=100 → control: search + state, NO injection', async ($, on) => {
  const h = host(on, { env: { ACE_AB_CONTROL_PCT: '100' } })
  const r: any = await submit($)
  expect(h.searches().length).toBe(1)
  expect(r.context === undefined || r.context.length === 0).toBe(true)
  expect(h.state()!.task_session_id).toBe(h.pin(h.searches()[0]!))
  expect(h.rows().find((x: any) => x.event === 'search')!.render_cohort).toBe('control')
})

test('render_cohort ACE_AB_COMPACT_PCT=100 → compact one-liners <= 9,500 chars', async ($, on) => {
  const h = host(on, { env: { ACE_AB_COMPACT_PCT: '100' } })
  const r: any = await submit($)
  expect(r.context[0].length <= 9500).toBe(true)
  expect(r.context[0].startsWith('<ace-patterns shown="100" of="100" mode="compact" agent-type="main">\n#')).toBe(true)
  expect(h.rows().find((x: any) => x.event === 'search')!.render_cohort).toBe('compact')
})

test('render_cohort ACE_RENDER_FULL_PCT=0 → budget-verbatim (render_patterns, <= 9,500 chars)', async ($, on) => {
  const h = host(on, { env: { ACE_RENDER_FULL_PCT: '0' } })
  const r: any = await submit($)
  const ctx: string = r.context[0]
  expect(ctx.length <= 9500).toBe(true)
  expect(shownOf(ctx) < 100).toBe(true)
  expect(ctx.startsWith(`<ace-patterns shown="${shownOf(ctx)}" of="100" agent-type="main">\n{`)).toBe(true)
  expect(h.rows().find((x: any) => x.event === 'search')!.render_cohort).toBe('budget')
})

test('self-eval request → its OWN context entry (never concatenated), request file removed', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }),
    files: { [EVAL_REQ]: JSON.stringify({ patterns_injected: 100, avg_relevance: 0, domains: 0, tools_executed: 2, success: true }) } })
  const r: any = await submit($)
  expect(r.context.length).toBe(2)
  expect(r.context[0]).toBe(G.full_main_8)
  expect(r.context[1]).toBe(G.eval_injection)
  expect(h.files.has(EVAL_REQ)).toBe(false)
})

// ---------- UI parity: systemMessage / sessionTitle ----------

test('systemMessage parity: a $.ui.log summary on success, an [ACE] error line on failure', async ($, on) => {
  let fail = false
  const h = host(on, { search: () => fail ? { exitCode: 1, stdout: '', stderr: 'boom' } : { stdout: S8 } })
  await submit($)
  expect(h.logs.some(l => l.startsWith('✅ [ACE] Found 8 relevant bullets'))).toBe(true)
  fail = true
  await submit($, HUMAN + ' fail')
  expect(h.logs.some(l => /^(❌|⚠️|⏱️) \[ACE\]/.test(l))).toBe(true)
})

test('sessionTitle via classic.UserPromptSubmit, only when the session has no title yet', async ($, on) => {
  host(on)
  await submit($)
  const c: any = await ($ as any).classic.UserPromptSubmit({ prompt: HUMAN, session_id: SID })
  expect(/^ACE( low| ready)? · /.test(c.sessionTitle)).toBe(true)
  const c2: any = await ($ as any).classic.UserPromptSubmit({ prompt: HUMAN, session_id: SID, session_title: 'my title' })
  expect(c2.sessionTitle).toBe(undefined)
})

// ---------- agent.spawn: §12 own ACE session per subagent ----------

test('agent.spawn: own search, FRESH uuid4 pin per subagent (never the parent pin), parent_task_id, all patterns appended', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }) })
  await submit($)
  const main = h.pin(h.searches()[0]!)!
  const p1 = 'review the domain shift python port for parity bugs'
  const r1: any = await spawn($, p1)
  const r2: any = await spawn($, 'audit the learn trace builder for missing fields')
  expect(h.searches().length).toBe(3)
  const s1 = h.pin(h.searches()[1]!)!, s2 = h.pin(h.searches()[2]!)!
  expect(UUID4.test(s1) && UUID4.test(s2)).toBe(true)
  expect(s1).not.toBe(main)
  expect(s2).not.toBe(main)
  expect(s1).not.toBe(s2)
  expect(h.searches()[1]!.stdin).toBe(p1)
  expect(h.searches()[1]!.timeoutMs! <= 25000).toBe(true)
  expect(r1.seenPrompt).toBe(p1 + '\n\n' + G.full_sub_8)
  expect(r2.seenPrompt.includes('<ace-patterns-subagent shown="8" of="8"')).toBe(true)
  const st = h.state('agent-1')!
  expect(st.task_session_id).toBe(s1)
  expect(st.parent_task_id).toBe(main)
  expect(st.hook_event_name).toBe('SubagentStart')
  expect(st.user_prompt).toBe(p1)
  expect(h.state('agent-2')!.task_session_id).toBe(s2)
})

test('agent.spawn from a Workflow: real prompt searched and rewritten, workflow run id logged', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }) })
  const p = 'implement the TS renderer and make the parity harness pass'
  const r: any = await spawn($, p, { workflow: { runId: 'wf_abc', agentIndex: 1 } })
  expect(h.searches().length).toBe(1)
  expect(r.seenPrompt.startsWith(p + '\n\n<ace-patterns-subagent shown="8" of="8"')).toBe(true)
  expect(h.rows().find((x: any) => x.event === 'search' && x.hook === 'SubagentStart')!.workflow).toBe('wf_abc')
})

test('Workflow placeholder prompt: the first turn.start text differs → uninjected ids dropped, real task kept, logged', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }) })
  await spawn($, 'workflow agent prompt placeholder text', { workflow: { runId: 'wf_x', agentIndex: 2 } })
  const pinned = h.state('agent-1')!.task_session_id
  const real = 'the real workflow task: port ace_domain_shift matcher to TypeScript'
  await $.turn.start({ text: real, turnId: 'w1', agentId: 'agent-1' } as any)
  const st = h.state('agent-1')!
  expect(st.pattern_ids).toEqual([])
  expect(st.retrieval_log_ids).toEqual({})
  expect(st.user_prompt).toBe(real)
  expect(st.task_session_id).toBe(pinned)
  expect(h.rows().some((x: any) => x.event === 'workflow_placeholder' && x.agent_id === 'agent-1')).toBe(true)
})

test('agent.spawn resume / fork: no new search, no second pin', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }) })
  await spawn($, 'review the domain shift python port for parity bugs')
  const pinned = h.state('agent-1')!.task_session_id
  await spawn($, 'continue', { resume: { agentId: 'agent-1' } })
  await spawn($, 'fork this context please now', { fork: true, subagentType: 'fork' })
  expect(h.searches().length).toBe(1)
  expect(h.state('agent-1')!.task_session_id).toBe(pinned)
})

// ---------- tool.call Read: domain shift ----------

test('domain shift: Read in a known domain → one --top-k 8 search pinned to the task, context attached, once per domain', async ($, on) => {
  const h = host(on)
  await submit($)
  const main = h.pin(h.searches()[0]!)!
  const r1: any = await $.tool.call({ tool: 'Read', file_path: '/proj/ace-cli/notes.md' } as any)
  const r2: any = await $.tool.call({ tool: 'Read', file_path: '/proj/ace-cli/other.md' } as any)
  const ds = h.searches().filter(s => s.argv.includes('--top-k'))
  expect(ds.length).toBe(1)
  expect(h.flag(ds[0]!.argv, '--top-k')).toBe('8')
  expect(h.pin(ds[0]!)).toBe(main)
  expect(ds[0]!.stdin).toBe('notes')
  expect(ds[0]!.timeoutMs! <= 17000).toBe(true)
  expect(r1.context[r1.context.length - 1]).toBe(G.domain_shift_8)
  expect(r2.context === undefined || r2.context.length === 0).toBe(true)
  expect(h.files.get(`${SDIR}/domain-last-main.txt`)!.trim()).toBe('ace-cli')
  const st = h.state()!
  expect(st.retrieval_id).toBe(JSON.parse(S100).retrieval_id)
  for (const p of JSON.parse(S8).similar_patterns) if (/^[0-9a-f-]{36}$/.test(p.id ?? '')) expect(st.pattern_ids).toContain(p.id)
  expect(h.rows().some((x: any) => x.event === 'domain_shift' && x.to_domain === 'ace-cli')).toBe(true)
})

test('domain-shift claim: two parallel Reads in the same new domain → exactly one search', async ($, on) => {
  const h = host(on)
  await submit($)
  await Promise.all([
    $.tool.call({ tool: 'Read', file_path: '/proj/ace-cli/a.md' } as any),
    $.tool.call({ tool: 'Read', file_path: '/proj/ace-cli/b.md' } as any),
  ])
  expect(h.searches().filter(s => s.argv.includes('--top-k')).length).toBe(1)
})

test('domain shift inside a subagent pins the SUBAGENT id and merges into its own state', async ($, on) => {
  const h = host(on)
  await submit($)
  await spawn($, 'review the domain shift python port for parity bugs')
  const sub = h.state('agent-1')!.task_session_id
  await $.tool.call({ tool: 'Read', file_path: '/proj/ace-cli/notes.md', agentId: 'agent-1' } as any)
  const ds = h.searches().filter(s => s.argv.includes('--top-k'))
  expect(ds.length).toBe(1)
  expect(h.pin(ds[0]!)).toBe(sub)
  expect(h.files.get(`${SDIR}/domain-last-agent-1.txt`)!.trim()).toBe('ace-cli')
  expect(h.state('agent-1')!.task_session_id).toBe(sub)
})

// ---------- turn.complete: learn ----------

async function mainTask($: any, h: any, tools: any[] = [{ tool: 'Edit', file_path: '/proj/x.py', old_string: 'a', new_string: 'b' }, { tool: 'Bash', command: 'pytest -q' }]) {
  await submit($)
  await $.turn.start({ text: HUMAN, turnId: 't1' } as any)
  for (const t of tools) await $.tool.call(t as any)
}
const done = ($: any, answer = 'done', agentId?: string) =>
  $.turn.complete({ answer, durationMs: 5, isAborted: false, turnId: agentId ? 'ta' : 't1', reason: 'answer', ...(agentId ? { agentId } : {}) } as any)

test('turn.complete main: detached learn (--no-stream, F-080 flags, --timeout 300000), lock taken before the spawn', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }) })
  await mainTask($, h)
  await done($)
  expect(h.learns().length).toBe(1)
  const L = h.learns()[0]!, a = h.learnArgv(L)
  expect(a.slice(0, 3)).toEqual(['ace-cli', 'learn', '--transcript'])
  for (const f of ['--json', '--no-stream']) expect(a).toContain(f)
  expect(h.flag(a, '--timeout')).toBe('300000')
  expect(h.flag(a, '--verbosity')).toBe('detailed')
  expect(a.includes('--pin-session')).toBe(false)
  const st8 = JSON.parse(G.state_main_8)
  expect(h.flag(a, '--retrieval-id')).toBe(st8.retrieval_id)
  expect(h.flag(a, '--applied-log-ids')).toBe(st8.pattern_ids.filter((id: string) => id in st8.retrieval_log_ids).map((id: string) => st8.retrieval_log_ids[id]).join(','))
  expect(h.flag(a, '--transcript')!.startsWith(`${ROOT}/tmp/`)).toBe(true)
  expect(L.files.has(`${SDIR}/learn-inflight-main.lock`)).toBe(true)
  expect(L.argv[0] === 'ace-cli').toBe(false)  // never the bare learn: always through the detaching launcher
})

test('trace parity with ace_after_task.py: fields, effort from classic.Stop, git context, render_variant', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }) })
  await mainTask($, h)
  await ($ as any).classic.Stop({ session_id: SID, stop_hook_active: false, last_assistant_message: 'all done', effort: { level: 'high' } })
  await done($, 'all done')
  const t = h.trace(h.learns()[0]!)
  const tsid = h.pin(h.searches()[0]!)
  expect(t.task).toBe('User request: ' + HUMAN)
  expect(t.trajectory.map((s: any) => [s.step, s.tool])).toEqual([[1, 'Edit'], [2, 'Bash']])
  expect(t.trajectory.every((s: any) => typeof s.action === 'string' && typeof s.result === 'string')).toBe(true)
  expect(t.result.success).toBe(true)
  expect(t.result.output).toBe('Executed 2 tool calls')
  expect(t.result.summary).toBe('all done')
  expect(t.playbook_used).toEqual(JSON.parse(G.state_main_8).pattern_ids)
  expect(/^\d{4}-\d\d-\d\dT.*Z$/.test(t.timestamp)).toBe(true)
  expect(t.agent_type).toBe('main')
  expect(t.session_id).toBe(tsid)
  expect(t.render_variant).toBe('full')
  expect(t.retrieval_id).toBe(JSON.parse(S8).retrieval_id)
  expect(t.applied_log_ids.every((x: any) => Number.isInteger(x))).toBe(true)
  expect(t.effort_level).toBe('high')
  expect(t.effort_weight).toBe(1.5)
  expect(t.git.commit_hash).toBe('abc123')
  expect(t.git.branch).toBe('main')
})

test('trace_truncate parity: > 50 steps → truncation marker first + metadata.trace_truncated', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }) })
  const tools: any[] = [{ tool: 'Edit', file_path: '/proj/x.py', old_string: 'a', new_string: 'b' }]
  for (let i = 0; i < 59; i++) tools.push({ tool: 'Bash', command: 'echo ' + i })
  await mainTask($, h, tools)
  await done($)
  const t = h.trace(h.learns()[0]!)
  expect(t.trajectory[0]._truncation_marker).toBe(true)
  expect(t.trajectory[0].original_length).toBe(60)
  expect(t.metadata.trace_truncated).toBe(true)
})

test('learn launcher carries the execution metrics rows for both outcomes (learning_sent true/false)', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }) })
  await mainTask($, h)
  await done($)
  const rowsIn = h.learns()[0]!.argv.flatMap(a => { try { const o = JSON.parse(a); return o && o.event === 'execution' ? [o] : [] } catch { return [] } })
  expect(rowsIn.map((r: any) => r.learning_sent).sort()).toEqual([false, true])
  for (const r of rowsIn) {
    expect(r.hook).toBe('Stop')
    expect(r.session_id).toBe(SID)
    expect(r.patterns_used_count).toBe(JSON.parse(G.state_main_8).pattern_ids.length)
    expect(r.tools_executed).toBe(2)
  }
})

test('turn.complete main: eval request written, state reaped, rendered-main.txt kept for the compact re-inject', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }) })
  await mainTask($, h)
  const rendered = h.state()!.rendered_context
  await done($)
  expect(JSON.parse(h.files.get(EVAL_REQ)!).patterns_injected).toBe(JSON.parse(G.state_main_8).pattern_ids.length)
  expect(h.files.has(`${SDIR}/patterns-used-main.json`)).toBe(false)
  expect(h.files.get(`${SDIR}/rendered-main.txt`)).toBe(rendered)
})

test('turn.complete subagent: learn with the SUBAGENT pin, parent_task_id, own lock, default effort', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }) })
  await submit($)
  const main = h.pin(h.searches()[0]!)
  await spawn($, 'review the domain shift python port for parity bugs')
  const sub = h.state('agent-1')!.task_session_id
  await $.turn.start({ text: 'x', turnId: 'ta', agentId: 'agent-1' } as any)
  await $.tool.call({ tool: 'Write', file_path: '/proj/y.py', content: 'z', agentId: 'agent-1' } as any)
  await done($, 'sub done', 'agent-1')
  const L = h.learns()[0]!
  const t = h.trace(L)
  expect(t.session_id).toBe(sub)
  expect(t.parent_task_id).toBe(main)
  expect(t.agent_id).toBe('agent-1')
  expect(t.agent_type).toBe('general-purpose')
  expect(t.result.success).toBe(true)
  expect(t.effort_level).toBe('normal')
  expect(t.effort_weight).toBe(1)
  expect(L.files.has(`${SDIR}/learn-inflight-agent-1.lock`)).toBe(true)
})

test('a machine turn and a read-only task never learn', async ($, on) => {
  const h = host(on)
  await submit($, 'a long enough notification text body', 'task-notification')
  await $.turn.start({ text: 'x', turnId: 'm1' } as any)
  await $.tool.call({ tool: 'Bash', command: 'ls' } as any)
  await $.turn.complete({ answer: 'x', durationMs: 1, isAborted: false, turnId: 'm1', reason: 'answer' } as any)
  await submit($)
  await $.turn.start({ text: HUMAN, turnId: 't2' } as any)
  await $.tool.call({ tool: 'Read', file_path: '/proj/README' } as any)
  await $.turn.complete({ answer: 'x', durationMs: 1, isAborted: false, turnId: 't2', reason: 'answer' } as any)
  expect(h.learns().length).toBe(0)
})

test('task state is read from disk: a learn after a module reload uses the persisted patterns-used-main.json', async ($, on) => {
  const TSID = '11111111-2222-4333-8444-555555555555'
  const seeded = G.state_main_8.split('__TSID__').join(TSID)
  const h = host(on, { files: { [`${SDIR}/patterns-used-main.json`]: seeded } })
  await $.turn.start({ text: HUMAN, turnId: 't1' } as any)
  await $.tool.call({ tool: 'Edit', file_path: '/proj/x.py', old_string: 'a', new_string: 'b' } as any)
  await done($)
  expect(h.searches().length).toBe(0)
  expect(h.learns().length).toBe(1)
  const a = h.learnArgv(h.learns()[0]!)
  expect(h.flag(a, '--retrieval-id')).toBe(JSON.parse(seeded).retrieval_id)
  expect(h.trace(h.learns()[0]!).session_id).toBe(TSID)
})

// ---------- session.end ----------

test('session.end removes the session dir unless a learn lock younger than 10 min exists', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }) })
  await submit($)
  h.put(`${SDIR}/learn-inflight-agent-9.lock`, '')
  await $.session.end({ reason: 'other', sessionId: SID, resume: {} } as any)
  expect(h.files.has(`${SDIR}/patterns-used-main.json`)).toBe(true)
  h.advance(11 * MIN)
  await $.session.end({ reason: 'other', sessionId: SID, resume: {} } as any)
  expect([...h.files.keys()].some(k => k.startsWith(SDIR + '/'))).toBe(false)
})
