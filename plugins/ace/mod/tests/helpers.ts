// Shared harness of the mod's `claude plugin test` suite: the in-memory engine (host) and the helpers the
// area files share. Not a *.test.ts file, so the kit runs no test from it.
import { expect, test } from 'claude-code/testing'
import S100 from './fixtures/search_100.ts'
import S8 from './fixtures/search_8.ts'
import SEDGE from './fixtures/search_edge.ts'
import G from './fixtures/golden.ts'
import USED_CASES from './fixtures/used_cases.ts'
import REJECTION_CASES from './fixtures/rejection_cases.ts'
import { pyLoads } from '../lib/pyjson.ts'
import { renderPatternsDict } from '../lib/render.ts'
import { traceVariant, renderCohort, serverFullPct, storedFullPct } from '../lib/cohort.ts'
import { hasSubstantialWork, toolRec } from '../lib/trace.ts'
import { rejectionMatch, evalStats, evalInjection, usedPatternIds, toolHaystack } from '../lib/evidence.ts'
import { PRIVATE_WRITE_SH, REALPATH_SH, REMOVE_SHADOW_SH, REPO_WRITE_SH } from '../lib/sh.ts'
import { statusLine, learnLine } from '../ui/status.ts'

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

export const HOME = '/home/u', CWD = '/proj', SID = 'sess-1', PRJ = 'prj_t'
export const PROOT = decodeURIComponent(new URL('../..', import.meta.url).pathname).replace(/\/$/, '')  // $.plugin.root
export const LOCAL_CLI = `${PROOT}/node_modules/@ace-sdk/cli/dist/cli.js`
// the ace-cli arguments of a spawn, whichever head resolved it: the bare global name or [node, plugin-local cli.js]
export const cliOf = (argv: string[]): string[] | null => argv[0] === 'ace-cli' ? argv.slice(1) : argv[0] === 'node' && argv[1] === LOCAL_CLI ? argv.slice(2) : null
export const ROOT = `${HOME}/.claude/plugins/data/ace-inline`
export const PDIR = `${ROOT}/projects/${PRJ}`, SDIR = `${PDIR}/sessions/${SID}`
export const REL = `${CWD}/.claude/data/logs/ace-relevance.jsonl`
export const EVAL_REQ = `${CWD}/.claude/data/logs/ace-eval-request.json`
export const UUID4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/
export const HUMAN = 'please fix the domain shift hook so it injects patterns when reading plugin files'
export const LOCKED = { exitCode: 1, stdout: '', stderr: 'SqliteError: database is locked' }
export const MIN = 60_000

export type SearchAnswer = { exitCode?: number; stdout?: string; stderr?: string; advanceMs?: number; killed?: boolean }
export type Opts = { search?: (argv: string[], stdin?: string) => SearchAnswer; env?: Record<string, string>; files?: Record<string, string>
  engine?: (stdin?: string) => SearchAnswer; links?: string[]; noClassic?: boolean; defaultArm?: boolean
  learnExit?: number; early?: (agentId: string) => Promise<unknown>; beforeWrite?: (path: string) => Promise<unknown>
  selfEval?: boolean; model?: (req: any) => any; compact?: (files: Map<string, string>) => any
  cli?: (args: string[], stdin?: string) => SearchAnswer | undefined; noSettings?: boolean; ignored?: boolean; root?: string; cwd?: string; noPython?: boolean
  installer?: (args: string[]) => { state: string, detail?: string }  // ace_cli_installer.py answers (8.1.1)
  git?: (argv: string[]) => string | undefined  // 8.2.0: git answers (full argv); undefined = the default stub
  realpaths?: Record<string, string>  // REALPATH_SH answers (a symlinked path); default: the path as given
  backfill?: (cmd: string, argv: string[], stdin?: string) => { exit?: number, status?: number, body?: any } | undefined  // 8.2.0: engine/backfill.js answers
  claimed?: boolean }  // 8.1.4: the detached learn child already claimed the trace (the parent's `mv` finds nothing)
export type Run = { argv: string[]; stdin?: string; env?: Record<string, string>; timeoutMs?: number; files: Set<string> }

// In-memory engine: fs (with mtimes on the mocked clock), env, clock, session, process. Every argv is recorded.
export function host(on: any, o: Opts = {}) {
  const T0 = 1_800_000_000_000
  let now = T0
  const files = new Map<string, string>(), mtime = new Map<string, number>()
  const put = (p: string, t: string) => { files.set(p, t); mtime.set(p, now) }
  if (!o.noSettings) put(`${CWD}/.claude/settings.json`, JSON.stringify({ env: { ACE_PROJECT_ID: PRJ, ACE_ORG_ID: 'org_t' } }))
  for (const [k, v] of Object.entries(o.files ?? {})) put(k, v)
  if (!o.noClassic) put(`${SDIR}/mod-classic`, String(now))  // classic.* hooks fire (no managed-settings guard)
  const debug: string[] = [], registered: string[] = [], runs: Run[] = [], logs: string[] = [], statuses: (string | undefined)[] = [], envAsked: string[] = [], envSet: [string, string | undefined][] = []
  // §31 default is ACE_RENDER_FULL_PCT=50 (50/50 split); this suite pins the full arm unless defaultArm (its own tests below)
  // item D: the Haiku self-eval is off in this suite unless selfEval (its own tests below): learns stay synchronous
  const env: Record<string, string> = { HOME, ...(o.defaultArm ? {} : { ACE_RENDER_FULL_PCT: '100' }), ...(o.selfEval ? {} : { ACE_SELF_EVAL: '0' }), ...(o.env ?? {}) }
  const modelCalls: any[] = []
  let spawnN = 0
  const res = (exitCode: number, stdout: string, stderr = '') =>
    ({ value: { exitCode, stdout, stderr, isStdoutTruncated: false, isStderrTruncated: false } })
  const dflt = (argv: string[]): SearchAnswer => ({ stdout: argv.includes('--top-k') ? S8 : S100 })
  const git = (argv: string[]) => argv.includes('--abbrev-ref') ? 'main\n'
    : argv.includes('rev-parse') && argv.includes('HEAD') ? 'abc123\n'
    : argv.includes('--git-dir') ? '.git\n' : argv.includes('--is-inside-work-tree') ? 'true\n' : ''

  on('session.id', () => ({ value: SID }))
  on('session.cwd', () => ({ value: o.cwd ?? o.root ?? CWD }))
  on('session.root', () => ({ value: o.root ?? CWD }))
  on('env.get', (_$: any, e: any) => { envAsked.push(e.name); return { value: env[e.name] } })
  on('env.set', (_$: any, e: any) => { if (e.value === undefined) delete env[e.name]; else env[e.name] = e.value; envSet.push([e.name, e.value]); return { value: {} } })
  on('clock.now', () => ({ value: now }))
  on('fs.exists', (_$: any, e: any) => ({ value: files.has(e.path) || [...files.keys()].some(k => k.startsWith(e.path + '/')) }))
  on('fs.read', (_$: any, e: any) => { if (!files.has(e.path)) throw new Error('ENOENT: ' + e.path); return { value: files.get(e.path) } })
  on('fs.write', (_$: any, e: any) => { put(e.path, e.text); return { value: undefined } })
  on('fs.list', (_$: any, e: any) => ({ value: [...files.keys()].filter(k => k.startsWith(e.path + '/') && !k.slice(e.path.length + 1).includes('/'))
    .map(k => ({ name: k.slice(e.path.length + 1), kind: 'file', size: files.get(k)!.length, mtimeMs: mtime.get(k), isLink: false }))
    .concat((o.links ?? []).filter(l => l.slice(0, l.lastIndexOf('/')) === e.path).map(l => ({ name: l.slice(l.lastIndexOf('/') + 1), kind: 'file', size: 0, mtimeMs: now, isLink: true }))) }))
  on('fs.stat', (_$: any, e: any) => {
    if (!files.has(e.path)) throw new Error('ENOENT: ' + e.path)
    return { value: { kind: 'file', size: files.get(e.path)!.length, mtimeMs: mtime.get(e.path), isLink: false } }
  })
  on('process.run', (_$: any, e: any) => {
    let argv = [...e.argv] as string[]
    const init = e.init ?? {}
    runs.push({ argv, stdin: init.stdin, env: init.env, timeoutMs: init.timeoutMs, files: new Set(files.keys()) })
    if (argv[0] === 'node' && argv[1] === `${PROOT}/engine/search.js`) {
      const a = o.engine ? o.engine(init.stdin) : { exitCode: 3, stderr: 'gate: no_cli' }
      now += a.advanceMs ?? 0
      if (a.killed) throw new Error('ace: $.process.run(node) aborted: still running after timeoutMs')
      return res(a.exitCode ?? 0, a.stdout ?? '', a.stderr ?? '')
    }
    if (cliOf(argv)?.[0] === 'search') {
      argv = ['ace-cli', ...cliOf(argv)!]
      const a = (o.search ?? dflt)(argv, init.stdin)
      now += a.advanceMs ?? 0
      if (a.killed) throw new Error('ace: $.process.run(ace-cli) aborted: still running after timeoutMs')
      return res(a.exitCode ?? 0, a.stdout ?? '', a.stderr ?? '')
    }
    if (o.backfill && argv[0] === 'node' && argv[1]?.endsWith('/engine/backfill.js')) {
      const a = o.backfill(argv[2], argv, init.stdin) ?? { status: 200, body: null }
      if (a.exit) return res(a.exit, '', 'x')
      return res(0, JSON.stringify({ status: a.status, body: a.body }) + '\n')
    }
    if (argv[0] === 'sleep') { now += Number(argv[1]) * 1000; return res(0, '') }
    if (o.cli && cliOf(argv)) { const a = o.cli(cliOf(argv)!, init.stdin); if (a) { now += a.advanceMs ?? 0; if (a.killed) throw new Error('ace: $.process.run aborted: still running after timeoutMs'); return res(a.exitCode ?? 0, a.stdout ?? '', a.stderr ?? '') } }
    if (o.installer && argv.some(a => a.endsWith('/ace_cli_installer.py'))) return res(0, JSON.stringify(o.installer(argv.slice(argv.findIndex(a => a.endsWith('/ace_cli_installer.py')) + 1))) + '\n')
    if (argv[0].endsWith('/scripts/ace-python')) return o.noPython ? res(1, '') : res(0, '/usr/bin/python3.13\n')
    if (argv[0] === '/bin/sh' && argv[2] === REALPATH_SH) return res(0, o.realpaths?.[argv[4]] ?? argv[4])
    if (argv[0] === '/bin/sh' && argv[2] === REPO_WRITE_SH) { const t = `${argv[4]}/${argv[5]}`; if ((o.links ?? []).some(l => t === l || t.startsWith(l + '/'))) return res(3, ''); put(t, init.stdin ?? ''); if (argv[5] === '.gitignore') put(`${argv[4]}/.gitignore-fixed`, ''); return res(0, '') }
    if (argv[0] === '/bin/sh' && argv[2] === REMOVE_SHADOW_SH) { if ((o.links ?? []).some(l => argv[4] === l || argv[4].startsWith(l + '/'))) return res(3, ''); if (!files.has(argv[4])) return res(5, ''); files.delete(argv[4]); return res(0, '') }  // real sh: tests/test_mod_repo_write_sh.py
    if (argv[0] === '/bin/sh' && argv[2] === PRIVATE_WRITE_SH) { if (o.beforeWrite) return Promise.resolve(o.beforeWrite(argv[4])).then(() => { put(argv[4], init.stdin ?? ''); return res(0, '') }); put(argv[4], init.stdin ?? ''); return res(0, '') }  // umask 077 + rename
    if (o.git && (argv[0] === 'git' || argv[0].endsWith('/git'))) { const a = o.git(argv); if (a !== undefined) return res(0, a) }  // 8.2.0: answers for the bootstrap facts (throws = a spawn failure)
    if ((argv[0] === 'git' || argv[0].endsWith('/git')) && argv.includes('check-ignore')) return res(o.ignored && !files.has(`${argv[2]}/.gitignore-fixed`) ? 0 : 1, '')
    if ((argv[0] === 'git' || argv[0].endsWith('/git')) && argv.includes('--error-unmatch')) return res(1, '')
    if (argv[0] === 'git' || argv[0].endsWith('/git')) return res(0, git(argv))
    if (o.learnExit !== undefined && argv.includes('ace-cli') && argv.includes('learn')) return res(o.learnExit, '')
    if (argv[0] === 'mv' && argv[1] === '-n') {  // rename(2): the trace hand-over between launcher and child (8.1.4)
      if (o.claimed) files.delete(argv[2])
      if (!files.has(argv[2])) return res(1, '')
      put(argv[3], files.get(argv[2])!); files.delete(argv[2]); return res(0, '')
    }
    if (argv.some(a => /(^|[\s;&|(])rm($|\s)/.test(a) || a === 'rm'))
      for (const a of argv) for (const k of [...files.keys()]) if (k === a || k.startsWith(a + '/')) files.delete(k)
    return res(0, '')
  })
  on('ui.log', (_$: any, e: any) => { if (e.to !== 'debug') logs.push(e.text); else debug.push(e.text); return { value: undefined } })
  on('ui.status', (_$: any, e: any) => { statuses.push(e.text); return { value: undefined } })
  on('ui.toast', () => ({ value: undefined }))
  on('prompt.submit', (_$: any, e: any) => ({ text: e.text, context: e.context }))
  on('agent.spawn', async (_$: any, e: any) => {
    const agentId = e.resume?.agentId ?? `agent-${++spawnN}`
    if (o.early) await o.early(agentId)
    return { model: 'claude-haiku-4-5', agentId, seenPrompt: e.prompt }
  })
  on('tool.call', (_$: any, e: any) => e.tool === 'Bash' ? ({ result: { stdout: e.command === 'big' ? 'y'.repeat(30000) : 'ok', stderr: '', interrupted: false } })
    : e.tool === 'Edit' || e.tool === 'Write' ? ({ result: { filePath: e.file_path } })
    : ({ result: { type: 'text', file: { content: 'a\nb', filePath: e.file_path } } }))
  on('turn.start', (_$: any, e: any) => ({ turnId: e.turnId }))
  on('turn.complete', (_$: any, e: any) => ({ text: e.answer }))
  on('prompt.compose', () => ({ sections: [{ id: 'intro', text: 'engine intro', scope: 'shared' }] }))
  on('session.compact', () => o.compact ? o.compact(files) : ({ messages: [{ role: 'user', text: 'summary', toolUses: [] }] }))
  on('model.complete', async (_$: any, e: any) => { modelCalls.push(e); return { value: o.model ? await o.model(e) : { isAnswered: false, reason: 'api-error', status: 500, error: 'x' } } })
  on('session.start', (_$: any, e: any) => ({ cwd: e.cwd }))
  on('session.end', (_$: any, e: any) => ({ sessionId: e.sessionId }))
  on('command.register', (_$: any, e: any) => { registered.push(e.name); return { value: { command: e.name } } })
  on('command.run', () => ({ text: 'core ran' }))
  on('classic.UserPromptSubmit', () => ({}))
  on('classic.Stop', () => ({}))
  on('classic.SubagentStop', () => ({}))

  const isSearch = (r: Run) => cliOf(r.argv)?.[0] === 'search'
  const searches = () => runs.filter(isSearch)
  const learns = () => runs.filter(r => !isSearch(r) && (r.argv.includes('ace-cli') || r.argv.includes(LOCAL_CLI)) && r.argv.includes('learn'))
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
  return { files, mtime, runs, logs, statuses, envAsked, envSet, env, registered, debug,
    band: () => { const l = [...debug].reverse().find(x => x.startsWith('ace band ')); return l ? JSON.parse(l.slice(9)) : null },
    pending: () => { const l = [...debug].reverse().find(x => x.startsWith('ace pending ')); return l ? JSON.parse(l.slice(12)) : null }, searches, learns, rows, state, pin, learnArgv, flag, trace, modelCalls,
    advance: (ms: number) => { now += ms }, now: () => now, put }
}

export const submit = ($: any, text = HUMAN, kind = 'composer') => $.prompt.submit({ text, wait: false, origin: { kind } } as any)
export const spawn = ($: any, prompt: string, extra: any = {}) => $.agent.spawn({ prompt, description: 'x', subagentType: 'general-purpose',
  fork: false, background: false, tool_use_id: 'toolu_1', parentModel: 'claude-opus', provider: { plugin: 'engine', tier: 'core' }, ...extra } as any)
export const ranked = (text: string) => JSON.parse(text).similar_patterns.map((p: any, i: number) => ({ p, i }))
  .sort((a: any, b: any) => {
    const ra = a.p.match_factors?.bandit_rank ?? null, rb = b.p.match_factors?.bandit_rank ?? null
    if (ra === null || rb === null) return ra === null && rb === null ? a.i - b.i : ra === null ? 1 : -1
    return ra - rb || a.i - b.i
  }).map((x: any) => x.p)
export const shownOf = (ctx: string) => Number(/shown="(\d+)"/.exec(ctx)![1])
export const bodyOf = (ctx: string) => JSON.parse(ctx.slice(ctx.indexOf('\n') + 1, ctx.lastIndexOf('\n')))


export const PLACEHOLDER = 'workflow agent prompt placeholder text'

export const REAL = 'the real workflow task: port ace_domain_shift matcher to TypeScript'



export const dsSearches = (h: any) => h.searches().filter((s: any) => s.argv.includes('--top-k'))



export async function mainTask($: any, h: any, tools: any[] = [{ tool: 'Edit', file_path: '/proj/x.py', old_string: 'a', new_string: 'b' }, { tool: 'Bash', command: 'pytest -q' }]) {
  await submit($)
  await $.turn.start({ text: HUMAN, turnId: 't1' } as any)
  for (const t of tools) await $.tool.call(t as any)
}

export const done = ($: any, answer = 'done', agentId?: string) =>
  $.turn.complete({ answer, durationMs: 5, isAborted: false, turnId: agentId ? 'ta' : 't1', reason: 'answer', ...(agentId ? { agentId } : {}) } as any)


export const execRow = (h: any) => JSON.parse(h.learns()[0]!.argv.find((x: string) => x.includes('"event": "execution"') && x.includes('"learning_sent": true')))

export const settle = async (h: any, n = 1) => { for (let i = 0; i < 200 && h.learns().length < n; i++) await new Promise(r => setTimeout(r, 5)) }



export const MALFORMED = ['{"a":1,}', '{"a', '[{"x":"tru', '{"a":1 "b":2}', '[1 2]', '{"a" 1}', '{a:1}', '{"a":"b\\', '[', '{', '"', '{"a":', '[1,', '[1,]']


export const SECOND = 'and also make the second change to the trace builder please'



export const cmd = ($: any, name: string, args: string) =>
  $.prompt.submit({ text: `/${name} ${args}`.trim(), wait: false, origin: { kind: 'composer' }, command: { name, args } } as any)


export const FULL_PCT = `${ROOT}/render-full-pct.json`

export const withPct = (pct: unknown) => { const o = JSON.parse(S8); o.render_full_pct = pct; return JSON.stringify(o) }


export async function rejectFlow($: any, h: any, prevAnswer: string, reply: () => Promise<unknown>) {
  await mainTask($, h)
  await done($, prevAnswer)
  await reply()
  await mainTask($, h)
  await done($, 'did something else')
  return h.trace(h.learns()[1]!)
}

export const st8a = () => { const st8 = JSON.parse(G.state_main_8), a = Object.keys(st8.retrieval_log_ids)[0]; return { a, log: st8.retrieval_log_ids[a] } }
