// ACE v8 production mod (DESIGN §13.1): search -> inject -> domain shift -> subagent inject -> detached learn with
// F-080 credit, in-process. The Python command hooks stay installed as the fallback and step aside while the
// mod-active marker is fresh. ace-cli is consumed as-is via $.process.run; state lives on disk in the Python formats.
import type { Register } from 'claude-code'
import {
  pyLoads, pyDumps, sanitize, renderFull, renderBudget, renderCompact, renderDomainShift, renderCohort, renderPatternsDict,
  dataRootFromPluginRoot, safeComponent as safe, mergeState, domainsSummary, skipReason, MACHINE_ORIGINS, expandAbbreviations,
  matchDomainToPath, domainNames, basenameQuery, isTrivialTask, hasSubstantialWork, toolRec, buildTrace, learnArgv,
  detachedLearnArgv, parseAceReview, parseDiffStat, evalInjection, searchRow, searchSummary, searchErrorLine, sessionTitle,
  subagentQuery, STATE_CAP, type StateUpdate, type ToolRec, type Cohort,
} from './core.ts'

const SEARCH_MS = 25000, DOMAIN_MS = 17000 // §11 A2: blocking budget per search, retry included
const PIN_SHARE = 0.6                      // of a search budget, for the pinned attempt
const LEARN_LOCK_MS = 600_000              // ace_session_end.py: learn timeout 300 s + margin

type Sess = { sessionId: string; cwd: string; project: string; org?: string; root: string; pdir: string; sdir: string;
  logs: string; minChars: number; extraPrefixes: string[]; clientId: string }

const uuid = (): string => {
  const c: any = (globalThis as any).crypto
  if (c?.randomUUID) return c.randomUUID()
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, ch => {
    const r = Math.random() * 16 | 0; return (ch === 'x' ? r : (r & 3) | 8).toString(16)
  })
}
const nowIso = async ($: any) => new Date(await $.clock.now()).toISOString() // UTC, trailing Z

async function run($: any, argv: string[], init: any = {}) {
  try { return await $.process.run(argv, { timeoutMs: 5000, ...init }) } catch { return null }
}
const rm = ($: any, ...paths: string[]) => run($, ['rm', '-rf', ...paths])

async function readJson($: any, path: string): Promise<any> {
  try { return pyLoads(await $.fs.read(path) as string) } catch { return undefined }
}
async function readText($: any, path: string): Promise<string | undefined> {
  try { return await $.fs.read(path) as string } catch { return undefined }
}

// O_APPEND through the shell: safe beside the Python hooks writing the same jsonl. Size rotation as ace_relevance_logger.
const APPEND = 'mkdir -p "$(dirname "$1")"; [ "$(wc -c <"$1" 2>/dev/null || echo 0)" -gt 52428800 ] && mv -f "$1" "$1.1"; cat >> "$1"'
const relLog = ($: any, s: Sess, obj: any) =>
  run($, ['/bin/sh', '-c', APPEND, 'sh', `${s.logs}/ace-relevance.jsonl`], { stdin: pyDumps(obj) + '\n' })

// ace_context.get_context: the settings file wins; env only when the file is missing.
async function resolveSession($: any, cwd: string): Promise<Sess | null> {
  let project: string | undefined, org: string | undefined
  const file = `${cwd}/.claude/settings.json`
  if (await $.fs.exists(file)) {
    const st = await readJson($, file)
    if (!st || typeof st !== 'object') return null
    project = st.projectId; org = st.orgId
    if (!project || !org) { project = st.env?.ACE_PROJECT_ID; org = st.env?.ACE_ORG_ID }
  } else {
    project = await $.env.get('ACE_PROJECT_ID'); org = await $.env.get('ACE_ORG_ID')
  }
  if (!project) return null
  const root = dataRootFromPluginRoot(await $.env.get('HOME') ?? '', $.plugin.root, $.plugin.name, await $.env.get('CLAUDE_CONFIG_DIR'))
  const sessionId = await $.session.id()
  const pdir = `${root}/projects/${safe(project)}`
  const minRaw = Number(await $.env.get('ACE_MIN_PROMPT_CHARS'))
  const extra = String(await $.env.get('ACE_MACHINE_PROMPT_PREFIXES') ?? '').split(',').map(x => x.trim().toLowerCase()).filter(Boolean)
  const manifest = await readJson($, `${$.plugin.root}/.claude-plugin/plugin.json`)
  return { sessionId, cwd, project, org, root, pdir, sdir: `${pdir}/sessions/${safe(sessionId)}`, logs: `${cwd}/.claude/data/logs`,
    minChars: Number.isFinite(minRaw) && minRaw > 0 ? minRaw : 12, extraPrefixes: extra,
    clientId: `claude-code-plugin/${manifest?.version ?? '0.0.0'}` }
}

function aceEnv(s: Sess): Record<string, string> {
  const env: Record<string, string> = { ACE_PROJECT_ID: s.project, ACE_CLIENT_ID: s.clientId }
  if (s.org) env.ACE_ORG_ID = s.org
  return env
}

const isAuthFailure = (t: string) => /unauthorized|401|not logged in|no api token/i.test(t)
// ace_cli.run_search + §11 A1: while pin-backoff is young no pin at all; a locked/empty pinned search is re-run ONCE
// without the pin, only within what is left of the blocking budget.
async function search($: any, s: Sess, query: string, pin: string | undefined, topK: number | undefined, budgetMs: number) {
  const t0 = await $.clock.now()
  const backoffPath = `${s.root}/pin-backoff`
  let usePin = pin, pinSkipped: string | undefined, pinFailed = false
  if (usePin) {
    const min = Number(await $.env.get('ACE_PIN_BACKOFF_MIN'))
    const age = await $.fs.stat(backoffPath).then((st: any) => t0 - st.mtimeMs, () => Infinity)
    if (age < (Number.isFinite(min) && min > 0 ? min : 30) * 60_000) { usePin = undefined; pinSkipped = 'backoff' }
  }
  const spawn = async (p: string | undefined, timeoutMs: number) => {
    const argv = ['ace-cli', 'search', '--stdin', '--json', ...(p ? ['--pin-session', p] : []), ...(topK ? ['--top-k', String(topK)] : [])]
    try { return { ...(await $.process.run(argv, { stdin: query, env: aceEnv(s), timeoutMs })), threw: '' } }
    catch (err) { return { exitCode: -1, stdout: '', stderr: String(err), threw: String(err) } }
  }
  // A pin stuck on the sqlite lock hangs until killed (live: > 25 s), so it only gets a share of the budget:
  // the unpinned re-run must still fit. A killed unpinned search has no time left, so no retry.
  let r: any = await spawn(usePin, usePin ? Math.floor(budgetMs * PIN_SHARE) : budgetMs)
  const cliMissing = /ENOENT|not found/i.test(r.threw)
  const killed = !!r.threw && !cliMissing
  const locked = /database is locked/i.test(r.stderr)
  if (usePin && (locked || killed)) await $.fs.write(backoffPath, '')   // only the sticky lock suspends pins globally (p2/p6)
  if (usePin && !cliMissing && (locked || killed || (!r.stdout.trim() && !isAuthFailure(r.stderr)))) {
    pinFailed = true
    const left = budgetMs - (await $.clock.now() - t0)
    if (left >= 2000) r = await spawn(undefined, left) // A2: never overrun the hook budget with a floored retry
  }
  let resp: any = null, error: string | undefined
  if (r.threw) error = /ENOENT|not found/i.test(r.threw) ? 'cli_not_found' : 'timeout'
  else if (r.exitCode !== 0) error = isAuthFailure(r.stderr + r.stdout) ? 'not_authenticated' : /timed? ?out/i.test(r.stderr) ? 'timeout' : 'nonzero_exit'
  else { try { resp = sanitize(pyLoads(r.stdout)) } catch { error = 'json_parse_failed' } }
  if (resp && resp.error) { error = String(resp.error); resp = null }
  return { resp, error, ms: await $.clock.now() - t0, pinFailed, pinSkipped, stderr: String(r.stderr).slice(0, 300) }
}

// Per-load state, created in register (a reload starts over). ponytail: a hot reload loses the tool records of a
// running task (trajectory restarts; the F-080 state is on disk).
type Load = {
  sess: Sess | null
  pendingMain: string | null | undefined        // set by prompt.submit, bound to the next main turn.start
  pendingTitle: string | undefined              // classic.UserPromptSubmit answers it
  stopEffort: string | undefined                // classic.Stop's effort for the turn.complete learn
  domains: string[] | null
  turnAnchor: Map<string, string | null>        // main turnId -> tsid (null = machine turn)
  tools: Map<string, ToolRec[]>                 // key: 'main' or agentId
  spawnPrompts: Map<string, string>             // workflow agentId -> the prompt agent.spawn saw
  claims: Set<string>                           // ponytail: in-process; the marker silences the Python hook, so no second process races this one
  queues: Map<string, Promise<unknown>>         // per state file: parallel hooks read-merge-write in turn
}

async function ensure($: any, L: Load): Promise<Sess | null> {
  if (L.sess && L.sess.sessionId === await $.session.id()) return L.sess
  L.sess = await resolveSession($, await $.session.root())  // the session cwd can move to a subdir; the project cannot
  return L.sess
}
const stateFile = (s: Sess, key: string) => `${s.sdir}/patterns-used-${safe(key)}.json`
async function disabled($: any, s: Sess) {
  return await $.fs.exists(`${s.sdir}/disabled.flag`) || await $.fs.exists(`${s.pdir}/disabled.flag`)
}
function touchMarker($: any, s: Sess) { return $.fs.write(`${s.sdir}/mod-active`, String(Date.now())) }
function readState($: any, s: Sess, key: string) { return readJson($, stateFile(s, key)) }
function updateState($: any, L: Load, s: Sess, key: string, u: StateUpdate, reset = false) {
  const path = stateFile(s, key)
  const job = (L.queues.get(path) ?? Promise.resolve()).then(async () => {
    const state = mergeState(reset ? undefined : await readJson($, path), u)
    await $.fs.write(path, pyDumps(state))
    return state
  })
  L.queues.set(path, job.catch(() => undefined))
  return job
}

async function cohortEnv($: any) {
  return { ACE_AB_CONTROL_PCT: await $.env.get('ACE_AB_CONTROL_PCT'), ACE_AB_COMPACT_PCT: await $.env.get('ACE_AB_COMPACT_PCT'), ACE_RENDER_FULL_PCT: await $.env.get('ACE_RENDER_FULL_PCT') }
}

// §13.1 cohort arms; `rendered` = the ≤ 10K re-inject copy (C1). control: search + anchor, nothing injected.
async function renderArm($: any, resp: any, tag: string, attrs: string, tsid: string) {
  const cohort: Cohort = renderCohort(tsid, await cohortEnv($))
  if (cohort === 'control') return { cohort, context: null as string | null, ids: [] as string[], rlog: {} as Record<string, number>, patterns: [] as any[], rendered: '', truncated: false }
  const r = cohort === 'compact' ? renderCompact(resp, tag, attrs) : cohort === 'budget' ? renderBudget(resp, tag, attrs) : renderFull(resp, tag, attrs)
  const rendered = cohort === 'full' ? renderFull(resp, tag, attrs, STATE_CAP).context : r.context
  return { cohort, context: r.context as string | null, ids: r.ids, rlog: r.rlog, patterns: r.patterns, rendered, truncated: cohort === 'full' && r.shown < r.total }
}

async function gitContext($: any, cwd: string) {
  const git = async (...a: string[]) => run($, ['git', ...a], { cwd })
  const inside = await git('rev-parse', '--is-inside-work-tree')
  if (!inside || inside.exitCode !== 0) return undefined
  const [hash, msg, name, mail, ts, branch, stat] = await Promise.all([git('rev-parse', 'HEAD'), git('log', '-1', '--format=%s'),
    git('log', '-1', '--format=%an'), git('log', '-1', '--format=%ae'), git('log', '-1', '--format=%aI'),
    git('rev-parse', '--abbrev-ref', 'HEAD'), git('diff', '--stat', 'HEAD~1..HEAD')])
  const out = (r: any) => (r && r.exitCode === 0 ? String(r.stdout).trim() : undefined)
  const commit = out(hash)
  if (!commit) return undefined
  let names = await git('diff', '--name-only', `${commit}~1`, commit)
  if (!names || names.exitCode !== 0) names = await git('show', '--name-only', '--format=', commit)
  const ctx: any = { commit_hash: commit }
  const set = (k: string, v: string | undefined) => { if (v !== undefined) ctx[k] = v }
  set('commit_message', out(msg)); set('author', out(name)); set('author_email', out(mail)); set('timestamp', out(ts)); set('branch', out(branch))
  Object.assign(ctx, parseDiffStat(out(stat) ?? ''))
  ctx.files_changed = (out(names) ?? '').split('\n').filter(Boolean)
  return ctx
}

// Reap a finished task's state; main keeps rendered-main.txt for the SessionStart compact re-inject (patterns_used_state).
async function reap($: any, s: Sess, key: string, state: any) {
  if (key === 'main' && state?.rendered_context) await $.fs.write(`${s.sdir}/rendered-main.txt`, state.rendered_context)
  await rm($, stateFile(s, key))
}

async function learn($: any, L: Load, s: Sess, key: string, answer: string, hook: 'Stop' | 'SubagentStop', effortEvent: string | undefined) {
  const t0 = await $.clock.now()
  const agentId = key === 'main' ? undefined : key
  const recs = L.tools.get(key) || []
  L.tools.delete(key)
  const state = await readState($, s, key)
  if (!state) {
    if (hook === 'Stop') await relLog($, s, { timestamp: await nowIso($), event: 'learn_skipped', hook, session_id: s.sessionId, reason: 'no_task_state', source: 'mod' })
    return
  }
  const prompt: string = state.user_prompt ?? ''
  const agentType: string = agentId ? state.agent_type ?? 'unknown' : 'main'
  const skip = !prompt || isTrivialTask(prompt, s.extraPrefixes) ? 'trivial_task' : !hasSubstantialWork(recs) ? 'no_substantial_work' : null
  if (skip) {
    await reap($, s, key, state)
    await relLog($, s, { timestamp: await nowIso($), event: 'learn_skipped', hook, session_id: s.sessionId, reason: skip, tools: recs.length, agent_id: agentId ?? null, source: 'mod' })
    return
  }
  const playbook: string[] = state.pattern_ids ?? []
  const rlog: Record<string, number> = state.retrieval_log_ids ?? {}
  const applied = playbook.filter(id => id in rlog).map(id => rlog[id])
  const tsid: string | undefined = state.task_session_id ?? undefined
  const env = await cohortEnv($)
  const effort = effortEvent || await $.env.get('CLAUDE_EFFORT') || 'normal'
  let git: any
  try {
    git = await gitContext($, s.cwd)
    const commits = recs.filter(r => r.commit).map(r => r.commit)
    if (git && commits.length) git.session_commits = commits
  } catch { /* git context is optional */ }
  const { trace, success } = buildTrace({ userPrompt: prompt, tools: recs, answer, playbookUsed: playbook, agentType,
    tsid, agentId, parentTaskId: state.parent_task_id, retrievalId: state.retrieval_id ?? undefined, appliedLogIds: applied,
    nowIso: await nowIso($), renderVariant: renderCohort(tsid, env), effort, git })

  // Lock BEFORE the spawn (session.end keeps the dir); the trace lives under <root>/tmp as run_learn's does.
  const lock = `${s.sdir}/learn-inflight-${safe(key)}.lock`
  await $.fs.write(lock, '')
  const traceFile = `${s.root}/tmp/ace-trace-${uuid()}.json`
  await $.fs.write(traceFile, pyDumps(trace))
  const row = async (sent: boolean) => pyDumps({ timestamp: await nowIso($), event: 'execution', hook: 'Stop', session_id: s.sessionId,
    project_id: s.project, agent_type: agentType, patterns_used_count: playbook.length, pattern_ids: playbook.slice(0, 20),
    tools_executed: recs.length, state_changing_tools: recs.filter(r => ['Edit', 'Write', 'Bash', 'mcp__', 'NotebookEdit'].some(x => r.tool.includes(x))).length,
    success, execution_time_seconds: Math.round((await $.clock.now() - t0) / 10) / 100, learning_sent: sent })
  const log = `${s.logs}/ace-relevance.jsonl`
  const python = (await readText($, `${s.root}/python_path`))?.trim()
  const argv = detachedLearnArgv({ learnArgv: learnArgv(traceFile, state.retrieval_id ?? undefined, applied, await $.env.get('ACE_VERBOSITY') || 'detailed'),
    trace: traceFile, lock, log, rowOk: await row(true), rowFail: await row(false), errLog: `${s.root}/logs/ace-hook-errors.log`, python })
  const spawned = await run($, argv, { env: aceEnv(s) })
  if (!spawned || spawned.exitCode !== 0) await rm($, lock, traceFile)  // no child will clean up

  if (hook === 'Stop' && playbook.length) {
    await $.fs.write(`${s.logs}/ace-eval-request.json`, pyDumps({ patterns_injected: playbook.length, avg_relevance: 0, domains: 0,
      tools_executed: recs.length, success: true, timestamp: (await nowIso($)).replace(/\.\d+Z$/, 'Z') }))
  }
  await reap($, s, key, state)
  await relLog($, s, { timestamp: await nowIso($), event: 'learn_dispatched', hook, session_id: s.sessionId, agent_id: agentId ?? null,
    agent_type: agentType, task_session_id: tsid ?? null, parent_task_id: state.parent_task_id ?? null, retrieval_id: state.retrieval_id ?? null,
    applied_log_ids: applied.length, patterns_used: playbook.length, tools_executed: recs.length, success, spawn_exit: spawned?.exitCode ?? null, source: 'mod' })
}

async function onPrompt($: any, L: Load, e: any): Promise<any> {
  const s = await ensure($, L)
  if (!s) return e
  await touchMarker($, s)   // every prompt, machine ones too: this is what keeps the Python hooks quiet
  if (e.command) { L.pendingMain = null; return e }  // slash commands: ACE stays out (as /ace-* skip)
  const t0 = await $.clock.now()
  const reason = e.origin && MACHINE_ORIGINS.has(e.origin.kind) ? 'machine_prompt'
    : e.isMeta ? 'machine_prompt' : skipReason(e.text, s.minChars, s.extraPrefixes)
  if (reason) {
    L.pendingMain = null
    if (reason !== 'ace_command') await relLog($, s, { timestamp: await nowIso($), event: 'search_skipped', hook: 'UserPromptSubmit', reason, session_id: s.sessionId, project_id: s.project, origin: e.origin?.kind ?? null, source: 'mod' })
    return e
  }
  if (await disabled($, s)) { L.pendingMain = null; return e }
  const tsid = uuid()
  L.pendingMain = tsid
  L.tools.set('main', [])

  // previous Stop's self-eval request -> its own context entry (G9: never concatenated)
  const evalFile = `${s.logs}/ace-eval-request.json`
  let evalCtx: string | null = null
  if (await $.fs.exists(evalFile)) {
    const d = await readJson($, evalFile)
    if (d && typeof d === 'object') evalCtx = evalInjection(d)
    await rm($, evalFile)
  }
  const withEval = (entries: string[]) => {
    const all = [...(e.context ?? []), ...entries, ...(evalCtx ? [evalCtx] : [])]
    return all.length ? { ...e, context: all } : e
  }

  const query = expandAbbreviations(e.text)
  const sr = await search($, s, query, tsid, undefined, SEARCH_MS)
  if (!sr.resp) {
    await updateState($, L, s, 'main', { tsid, userPrompt: e.text, hook: 'UserPromptSubmit' }, true)
    await relLog($, s, { timestamp: await nowIso($), event: 'error', hook: 'UserPromptSubmit', location: 'mod.search', error: sr.error ?? null, stderr_sample: sr.stderr, pin_failed: sr.pinFailed || undefined, session_id: s.sessionId, project_id: s.project, hook_ms: await $.clock.now() - t0, source: 'mod' })
    $.ui.log(searchErrorLine(sr.error))
    return withEval([])
  }
  const r = await renderArm($, sr.resp, 'ace-patterns', 'agent-type="main"', tsid)
  await updateState($, L, s, 'main', { ids: r.ids, retrievalId: sr.resp.retrieval_id || null, rlog: r.rlog, tsid, userPrompt: e.text, rendered: r.rendered, hook: 'UserPromptSubmit' }, true)
  const ds = domainsSummary(sr.resp)
  if (Object.keys(ds).length) {
    L.domains = domainNames(ds)
    await $.fs.write(`${s.pdir}/domains.json`, pyDumps(ds))
  }
  const returned = sr.resp.similar_patterns || []
  await relLog($, s, searchRow({ hook: 'UserPromptSubmit', sessionId: s.sessionId, userPrompt: e.text, query, returned, injected: r.patterns,
    projectId: s.project, orgId: s.org, agentType: 'main', cohort: r.cohort, hookMs: await $.clock.now() - t0, nowIso: await nowIso($),
    extra: { search_ms: sr.ms, pin_failed: sr.pinFailed || undefined, pin_skipped: sr.pinSkipped, truncated_for_cap: r.truncated || undefined,
      context_chars: r.context?.length ?? 0, task_session_id: tsid, source: 'mod' } }))
  const processed = renderPatternsDict(sr.resp).dict.similar_patterns
  $.ui.log(searchSummary(processed))
  L.pendingTitle = sessionTitle(processed, await readJson($, `${s.logs}/ace-review-result.json`))
  return withEval(r.context ? [r.context] : [])
}

async function beforeSpawn($: any, L: Load, s: Sess, e: any) {
  const t0 = await $.clock.now()
  const tsid = uuid()     // §12: every subagent is its own ACE session; the parent's id is correlation only
  const parent = await readState($, s, e.parentAgentId ?? 'main')
  const query = subagentQuery(e.prompt)
  const state: StateUpdate = { tsid, userPrompt: query, hook: 'SubagentStart', parentTaskId: parent?.task_session_id ?? undefined, agentType: e.subagentType }
  const skip = skipReason(query, s.minChars, s.extraPrefixes)
  if (skip) {
    await relLog($, s, { timestamp: await nowIso($), event: 'search_skipped', hook: 'SubagentStart', reason: skip, session_id: s.sessionId, project_id: s.project, source: 'mod' })
    return { out: e, state }
  }
  const sr = await search($, s, query, tsid, undefined, SEARCH_MS)
  if (!sr.resp) {
    await relLog($, s, { timestamp: await nowIso($), event: 'error', hook: 'SubagentStart', location: 'mod.search', error: sr.error ?? null, stderr_sample: sr.stderr, pin_failed: sr.pinFailed || undefined, session_id: s.sessionId, source: 'mod' })
    return { out: e, state }
  }
  const attr = `agent-type="${String(e.subagentType).replace(/"/g, '&quot;')}"`
  const r = await renderArm($, sr.resp, 'ace-patterns-subagent', attr, tsid)
  await relLog($, s, searchRow({ hook: 'SubagentStart', sessionId: s.sessionId, userPrompt: query, query, returned: sr.resp.similar_patterns || [], injected: r.patterns,
    projectId: s.project, orgId: s.org, agentType: e.subagentType, cohort: r.cohort, hookMs: await $.clock.now() - t0, nowIso: await nowIso($),
    extra: { search_ms: sr.ms, pin_failed: sr.pinFailed || undefined, pin_skipped: sr.pinSkipped, truncated_for_cap: r.truncated || undefined, context_chars: r.context?.length ?? 0,
      task_session_id: tsid, parent_task_id: state.parentTaskId ?? null, workflow: e.workflow?.runId, source: 'mod' } }))
  return { out: r.context ? { ...e, prompt: `${e.prompt}\n\n${r.context}` } : e,
    state: { ...state, ids: r.ids, retrievalId: sr.resp.retrieval_id || null, rlog: r.rlog, rendered: r.rendered } }
}

// ace_domain_shift.main
async function domainShift($: any, L: Load, e: any, key: string): Promise<string | null> {
  const s = await ensure($, L)
  if (!s || await disabled($, s)) return null
  let file: any = e.file_path || e.path
  if (!file && e.tool === 'Glob') { const g = e.pattern; file = typeof g === 'string' && g.includes('/') && !g.split('/').pop()!.includes('*') ? g : null }
  if (!file || typeof file !== 'string') return null
  if (!L.domains) { const d = await readJson($, `${s.pdir}/domains.json`); if (d && typeof d === 'object') L.domains = domainNames(d) }
  if (!L.domains) return null
  const matched = L.domains.find(d => matchDomainToPath(d, file.toLowerCase()))
  if (!matched) return null
  const lastFile = `${s.sdir}/domain-last-${safe(key)}.txt`
  const readLast = async () => ((await readText($, lastFile)) ?? '').trim().toLowerCase()
  if (await readLast() === matched) return null
  // Claim BEFORE searching: parallel Reads of a batch would all see the old domain.
  if (L.claims.has(key)) return null
  L.claims.add(key)
  try {
    const last = await readLast()
    if (last === matched) return null
    const query = basenameQuery(file)
    if (!query) return null
    const t1 = await $.clock.now()
    const state = await readState($, s, key)
    const tsid: string = state?.task_session_id ?? uuid()
    const sr = await search($, s, query, tsid, 8, DOMAIN_MS)
    if (sr.resp) await $.fs.write(lastFile, matched)    // a failed search stays retryable
    const rd = sr.resp && (sr.resp.similar_patterns || []).length ? renderDomainShift(sr.resp, matched) : null
    await relLog($, s, { timestamp: await nowIso($), event: 'domain_shift', hook: 'PostToolUse', session_id: s.sessionId, project_id: s.project,
      from_domain: last, to_domain: matched, file_path: file.slice(0, 200), patterns_found: rd?.shown ?? 0, search_succeeded: !!sr.resp,
      patterns_injected: rd?.ids.length ?? 0, hook_ms: await $.clock.now() - t1, agent_id: e.agentId ?? null, search_ms: sr.ms, pin_failed: sr.pinFailed || undefined, pin_skipped: sr.pinSkipped, source: 'mod' })
    if (!rd || !rd.shown) return null
    // F-080: merge the injected ids + log ids; keep the task's FIRST retrieval_id.
    await updateState($, L, s, key, { ids: rd.ids, rlog: rd.rlog, tsid, retrievalId: state?.retrieval_id ? undefined : sr.resp.retrieval_id || undefined })
    return rd.context
  } finally { L.claims.delete(key) }
}


export const register: Register = (on) => {
  const L: Load = { sess: null, pendingMain: undefined, pendingTitle: undefined, stopEffort: undefined, domains: null,
    turnAnchor: new Map(), tools: new Map(), spawnPrompts: new Map(), claims: new Set(), queues: new Map() }

  on('session.start', async ($, e, next) => {
    const r = await next(e)
    try {
      L.sess = await resolveSession($, e.cwd)
      if (L.sess) await touchMarker($, L.sess)
    } catch { /* the Python chain takes over without a marker */ }
    return r
  })

  on('prompt.submit', async ($, e, next) => {
    let out: any = e
    try { out = await onPrompt($, L, e) } catch (err) {
      if (L.sess) await relLog($, L.sess, { timestamp: await nowIso($), event: 'error', hook: 'UserPromptSubmit', location: 'mod.prompt.submit', error: String(err).slice(0, 300), source: 'mod' })
    }
    return next(out)
  })

  // Never clobber a custom /rename or --name title.
  on('classic.UserPromptSubmit', async ($, e: any, next) => {
    const r = await next(e)
    return L.pendingTitle && !e.session_title ? { ...r, sessionTitle: L.pendingTitle } : r
  })

  // turn.complete carries no effort; Stop does (ace_after_task._resolve_effort_level).
  on('classic.Stop', async ($, e: any, next) => {
    const raw = e.effort && typeof e.effort === 'object' ? e.effort.level : e.effort
    if (typeof raw === 'string' && raw) L.stopEffort = raw
    return next(e)
  })

  on('turn.start', async ($, e, next) => {
    try {
      if (e.agentId === undefined) {
        let anchor: string | null | undefined = L.pendingMain
        if (anchor === undefined) { // no prompt.submit in this load (hot reload): the task is what is on disk
          const s = await ensure($, L)
          anchor = (s && (await readState($, s, 'main'))?.task_session_id) ?? null
        }
        L.turnAnchor.set(e.turnId, anchor)
        L.pendingMain = undefined
      } else if (L.spawnPrompts.has(e.agentId)) {
        // Workflow placeholder (§13.1): the prompt agent.spawn searched for is not what the agent runs, so the
        // patterns never reached it: no credit; the real text stays as the task.
        const seen = L.spawnPrompts.get(e.agentId)!
        L.spawnPrompts.delete(e.agentId)
        const s = await ensure($, L)
        if (s && !e.text.includes(seen)) {
          const st = await readState($, s, e.agentId)
          if (st) {
            await $.fs.write(stateFile(s, e.agentId), pyDumps({ ...st, pattern_ids: [], retrieval_id: null, retrieval_log_ids: {}, user_prompt: subagentQuery(e.text), rendered_context: '' }))
            await relLog($, s, { timestamp: await nowIso($), event: 'workflow_placeholder', hook: 'SubagentStart', session_id: s.sessionId, agent_id: e.agentId, task_session_id: st.task_session_id ?? null, source: 'mod' })
          }
        }
      }
    } catch { /* bookkeeping never breaks a turn */ }
    return next(e)
  })

  on('agent.spawn', async ($, e, next) => {
    let out: any = e, pending: any = null
    try {
      const s = await ensure($, L)
      if (s && !e.fork && !e.resume && !(await disabled($, s))) {
        pending = await beforeSpawn($, L, s, e)
        out = pending.out
      }
    } catch { pending = null; out = e }
    const res: any = await next(out)
    try {
      const s = L.sess
      if (pending && s && res.agentId && !res.deny) {
        const key = res.agentId as string
        L.tools.set(key, [])
        if ((e as any).workflow) L.spawnPrompts.set(key, subagentQuery((e as any).prompt).slice(0, 200))
        await updateState($, L, s, key, pending.state, true)
      }
    } catch { /* state failure: this subagent simply is not learned */ }
    return res
  })

  on('tool.call', async ($, e, next) => {
    const t0 = Date.now()
    const r: any = await next(e)
    const key = (e as any).agentId ?? 'main'
    try {
      const list = L.tools.get(key) || []
      list.push(toolRec(e.tool, e, r.result, !!r.isError, r.deny, t0, Date.now()))
      L.tools.set(key, list)
    } catch { /* accumulation never breaks a tool call */ }
    if (r.deny || r.isError || !['Read', 'Glob', 'Grep'].includes(e.tool)) return r
    try {
      const context = await domainShift($, L, e, key)
      return context ? { ...r, context: [...(r.context ?? []), context] } : r
    } catch { return r }
  })

  on('turn.complete', async ($, e, next) => {
    const res = await next(e)
    let s: Sess | null = null
    try {
      s = await ensure($, L)
      if (!s) return res
      const agentId = (e as any).agentId as string | undefined
      if (agentId === undefined) {
        const review = parseAceReview(e.answer)
        if (review) await $.fs.write(`${s.logs}/ace-review-result.json`, pyDumps(review))
        const anchor = L.turnAnchor.get(e.turnId); L.turnAnchor.delete(e.turnId)
        const effort = L.stopEffort; L.stopEffort = undefined
        if (!anchor || e.isAborted || (await readState($, s, 'main'))?.task_session_id !== anchor) { L.tools.delete('main'); return res }  // machine turn / interrupted (Stop does not run)
        await learn($, L, s, 'main', e.answer, 'Stop', effort)
      } else if (e.isAborted) { // an aborted agent has no outcome to credit (v7.1.3 orphan ruling): abstain
        L.tools.delete(agentId)
        const st = await readState($, s, agentId)
        if (st) await reap($, s, agentId, st)
      } else {
        await learn($, L, s, agentId, e.answer, 'SubagentStop', undefined)
      }
    } catch (err) {
      if (s) await relLog($, s, { timestamp: await nowIso($), event: 'error', hook: 'Stop', location: 'mod.turn.complete', error: String(err).slice(0, 300), source: 'mod' })
    }
    return res
  })

  on('session.end', async ($, e, next) => {
    const s = L.sess ?? await ensure($, L).catch(() => null)
    try {
      if (s) {
        // A detached learn may still run (it owns its lock): keep the dir until the lock is stale, as ace_session_end.py.
        const now = await $.clock.now()
        const entries: any[] = await $.fs.list(s.sdir).catch(() => [])
        let busy = false
        for (const f of entries) {
          if (!/^learn-inflight-.*\.lock$/.test(f.name)) continue
          const st = await $.fs.stat(`${s.sdir}/${f.name}`).catch(() => null)
          if (st && now - st.mtimeMs < LEARN_LOCK_MS) busy = true
        }
        if (!busy) await rm($, s.sdir)
      }
    } catch { /* never block the exit */ }
    L.tools.clear(); L.turnAnchor.clear(); L.spawnPrompts.clear(); L.domains = null; L.sess = null
    return next(e)
  })
}
