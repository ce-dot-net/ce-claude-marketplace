// Learn side (ace_after_task + trace_truncate): tool records, trivial/substantial gates, trace build + truncate,
// learn argv and the detached learn launcher. Pure: no `$`, no I/O.
import { pyDumps } from './pyjson.ts'
import { cpSlice, isMachinePrompt } from './text.ts'
import { toolHaystack, type ToolRec } from './evidence.ts'
import { APPEND_SH } from './sh.ts'

// ---------- ace_after_task ----------
const TRIVIAL = [/<command-message>ace[:\-]/i, /ace:ace-/i, /(?:^|\s)\/ace-[\w:-]*(?:\s|$)/i, /ace-status/i, /ace-patterns/i, /ace-search/i,
  /ace-learn/i, /ace-configure/i, /ace-bootstrap/i, /ace-clear/i, /ace-doctor/i, /ace-export/i, /ace-import/i, /ace-top/i,
  /^(what|how|why|where|when|can you|could you|would you)\s.*\?$/i, /^(list|show|display|print|view|see)\s/i,
  /^(check|status|version|help|info)\s*$/i, /git\s+(status|log|diff|branch|show)\s*$/i, /^ls\s/i, /^cat\s/i,
  /^head\s/i, /^tail\s/i, /^(hi|hello|hey|thanks|thank you|ok|okay|yes|no|sure)\s*$/i,
  /caveat:.*messages below were generated/i, /^plugin\s*$/i, /(?:^|\s)\/plugin(?:\s|$)/i]
// Python re.search without MULTILINE/DOTALL: '.' stops at newlines, '^'/'$' anchor the whole string.
export const isTrivialTask = (t: string, extra: string[] = []) =>
  isMachinePrompt(t.toLowerCase(), extra) || TRIVIAL.some(r => r.test(t.toLowerCase()))

const STATE_CHANGING = ['Edit', 'Write', 'Bash', 'mcp__', 'NotebookEdit']
// v8: a state-changing tool, or a research task of >= MIN_RESEARCH_CALLS calls of any kind (Read/Grep/WebFetch/Agent...)
export const MIN_RESEARCH_CALLS = 3
// fix 3: an orchestrating task (delegates with 1-2 own calls) counts too; exact names (TaskList is not a delegation)
const DELEGATING = new Set(['Agent', 'Workflow', 'Task', 'Skill'])
export const hasSubstantialWork = (tools: ToolRec[]) =>
  tools.length >= MIN_RESEARCH_CALLS || tools.some(t => DELEGATING.has(t.tool) || STATE_CHANGING.some(s => t.tool.includes(s)))

// One trajectory step, summarized when the call settles (results can be huge; Python keeps them in sqlite).
const base = (p: any) => String(p ?? 'unknown file').replace(/\/+$/, '').split('/').pop()
const cut = (s: string, n: number) => s.length > n ? s.slice(0, n) + '...' : s

export function summarizeAction(tool: string, i: any): string {
  i = i || {}
  if (tool === 'Edit') return `Edited ${base(i.file_path)}`
  if (tool === 'Write') return `Wrote ${base(i.file_path)}`
  if (tool === 'Read') return `Read ${base(i.file_path)}`
  if (tool === 'Bash') return `Ran: ${cut(i.command ?? i.description ?? '', 60)}`
  if (tool === 'Grep') return `Searched for: ${i.pattern ?? ''}`
  if (tool === 'Glob') return `Found files matching: ${i.pattern ?? ''}`
  if (tool === 'Task' || tool === 'Agent') return `Spawned task: ${cut(i.description ?? i.prompt ?? '', 60)}` // Python names only 'Task'
  if (tool === 'TodoWrite') return 'Updated todo list'
  if (tool.startsWith('mcp__')) return `Called MCP: ${tool}`
  return tool
}

// Mirrors summarize_tool_response on the PostToolUse tool_response shape; the mod sees the tool's
// structured result plus isError/deny, so failed and denied calls (which Python only sees via
// PostToolUseFailure / not at all) are recorded too.
export function summarizeResult(tool: string, res: any, isError = false, denied?: string): string {
  if (denied) return `Error: ${denied.slice(0, 100)}`
  if (isError) return `Error: ${String(typeof res === 'string' ? res : JSON.stringify(res)).slice(0, 100)}`
  if (res === null || res === undefined || typeof res !== 'object' || Array.isArray(res))
    return cut(typeof res === 'string' ? res : JSON.stringify(res ?? ''), 100)
  if (res.error) return `Error: ${String(res.error).slice(0, 100)}`
  if (res.stderr) return `Stderr: ${String(res.stderr).slice(0, 100)}`
  if (tool === 'Edit' || tool === 'Write') return 'Success'
  if (tool === 'Read') { const c = res.file?.content ?? res.content ?? ''; return `Read ${c ? c.split('\n').length : 0} lines` }
  if (tool === 'Bash' && exitCode(res)) return `Exit code ${exitCode(res)}`
  if (tool === 'Bash') { const first = String(res.stdout || '').split('\n')[0]; return res.stdout ? (cut(first, 60) || 'Success') : 'Success' }
  if (tool === 'Grep' || tool === 'Glob') { const f = res.filenames ?? res.files; return Array.isArray(f) ? `Found ${f.length} files` : cut(JSON.stringify(res), 100) }
  if (tool === 'Task' || tool === 'Agent') return 'Task completed'
  return cut(JSON.stringify(res), 100)
}

// ---------- 8.1.3 task outcome (docs/technical/ARCHITECTURE.md "Task outcome"; parity: ace_after_task.py, fixture tests-fixtures/task-outcome) ----------
// result.success = the END outcome of the task; result.failed_steps = how many steps failed (informational).
// Exit 1 of these families means "no match / differs / false", never a failure (not even a failed step); exit >= 2 is.
export const OUTCOME_RULE = '8.1.3'  // the execution row names the rule that set success; /ace:ace-doctor shows the last one
export const BENIGN_EXIT1 = ['grep', 'egrep', 'fgrep', 'rg', 'diff', 'cmp', 'test', '[', '[[', 'git diff', 'git grep', 'command -v', 'which', 'type', 'pgrep', 'pidof', 'jq']
// ponytail: a fixed read-only family list (a failed read-only step never fails the task); grow it from probe data.
export const READ_ONLY_BASH = ['ls', 'cat', 'head', 'tail', 'wc', 'find', 'grep', 'egrep', 'fgrep', 'rg', 'pwd', 'echo', 'printf', 'which', 'type', 'command -v', 'file', 'stat', 'du', 'df', 'tree', 'jq', 'sort', 'uniq', 'cut', 'tr', 'diff', 'cmp', 'test', '[', '[[', 'date', 'printenv', 'ps', 'pgrep', 'pidof', 'git status', 'git log', 'git show', 'git diff', 'git grep', 'git rev-parse', 'git ls-files', 'git blame']
// State-changing or verifying tools besides non-read-only Bash. ponytail: MCP tools are never decisive (read vs write
// is unknown per server); a per-server table is the upgrade path.
export const DECISIVE_TOOLS = ['Edit', 'Write', 'MultiEdit', 'NotebookEdit', 'Agent', 'Task', 'Workflow']
const FILE_TOOLS = ['Edit', 'Write', 'MultiEdit', 'NotebookEdit']
const WRAPPERS = ['sudo', 'time', 'env', 'nice', 'nohup', 'exec', 'npx', 'bunx']
const SUBCMD = ['git', 'npm', 'pnpm', 'yarn', 'bun', 'cargo', 'go', 'gh', 'docker', 'uv', 'pip', 'pip3', 'claude']
const ASSIGN = /^[A-Za-z_][A-Za-z0-9_]*=/

// Split s at any of seps outside quotes (backslash escapes outside single quotes). Same scan as ace_after_task._split_top.
function splitTop(s: string, seps: string[]): string[] {
  const out: string[] = []
  let cur = '', q = '', i = 0
  while (i < s.length) {
    const ch = s[i]
    if (q) {
      if (ch === '\\' && q === '"' && i + 1 < s.length) { cur += s.slice(i, i + 2); i += 2; continue }
      if (ch === q) q = ''
      cur += ch; i++; continue
    }
    if (ch === '\\' && i + 1 < s.length) { cur += s.slice(i, i + 2); i += 2; continue }
    if (ch === '"' || ch === "'") { q = ch; cur += ch; i++; continue }
    const sep = seps.find(x => s.startsWith(x, i))
    if (sep) { out.push(cur); cur = ''; i += sep.length; continue }
    cur += ch; i++
  }
  out.push(cur)
  return out
}
const words = (s: string) => splitTop(s.trim(), [' ', '\t']).filter(Boolean).map(w => w.replace(/["']/g, ''))
const isBlank = (x: string) => !x.trim()
const stripParens = (x: string) => x.replace(/^[(){}]+|[(){}]+$/g, '')

// Bash command -> its family (ace_after_task.command_family). ponytail: a heuristic tokenizer, not a shell parser;
// a heredoc body is ignored (first line only).
export function commandFamily(cmd: unknown): string {
  let c = String(cmd ?? '')
  if (c.includes('<<')) c = c.split('\n')[0]
  const segs = splitTop(c, ['&&', '||', ';', '\n']).filter(x => !isBlank(x))
  if (!segs.length) return ''
  let w = words(splitTop(segs[segs.length - 1], ['|'])[0]).map(stripParens).filter(x => x && x !== '!')
  while (w.length && (WRAPPERS.includes(w[0]) || ASSIGN.test(w[0]) || w[0] === 'timeout' || ((w[0] === 'uv' || w[0] === 'poetry') && w[1] === 'run'))) {
    if (w[0] === 'timeout') {
      w = w.slice(1)
      while (w.length && w[0].startsWith('-')) w = w.slice(1)
      w = w.slice(1)
    } else if ((w[0] === 'uv' || w[0] === 'poetry') && w[1] === 'run') w = w.slice(2)
    else w = w.slice(1)
  }
  if (!w.length) return ''
  const first = w[0].split('/').pop()!
  if ((first === 'python' || first === 'python3') && w.length > 2 && w[1] === '-m') return w[2]
  if (first === 'command' && (w[1] === '-v' || w[1] === '-V')) return 'command -v'
  if (!SUBCMD.includes(first)) return first
  const fam = [first], rest = w.slice(1)
  while (rest.length && fam.length < (first === 'claude' ? 3 : 2)) {
    const x = rest.shift()!
    if (x.startsWith('-')) { if (first === 'git' && (x === '-C' || x === '-c') && rest.length) rest.shift(); continue }
    fam.push(x)
  }
  return fam.join(' ')
}

const EXIT_TEXT = /^Exit code (\d+)/
// The known exit code (structured, or the "Exit code N" text), else null. A code the tool interpreted itself
// (returnCodeInterpretation, e.g. grep's no-matches) counts as 0.
function exitCode(res: any): number | null {
  if (typeof res === 'string') { const m = EXIT_TEXT.exec(res); return m ? Number(m[1]) : null }
  if (!res || typeof res !== 'object' || Array.isArray(res)) return null
  if (res.returnCodeInterpretation) return 0
  for (const k of ['exit_code', 'exitCode']) if (res[k] !== undefined && res[k] !== null) { const c = Number(res[k]); if (Number.isFinite(c)) return Math.trunc(c) }
  for (const k of ['error', 'content']) if (typeof res[k] === 'string') { const m = EXIT_TEXT.exec(res[k]); if (m) return Number(m[1]) }
  return null
}

// 'ok' | 'failed' | 'interrupted'. stderr alone never fails a step; a known Bash exit code decides (benign exit-1
// families are ok); otherwise isError / error / a denial does.
function stepStatus(tool: string, input: any, res: any, isError: boolean, denied: string | undefined): 'ok' | 'failed' | 'interrupted' {
  if (res && typeof res === 'object' && res.interrupted === true) return 'interrupted'
  if (denied) return 'failed'
  if (tool === 'Bash') {
    const c = exitCode(res)
    if (c !== null) return c === 0 || (c === 1 && BENIGN_EXIT1.includes(commandFamily(input?.command))) ? 'ok' : 'failed'
  }
  return isError || (res && typeof res === 'object' && !Array.isArray(res) && res.error) ? 'failed' : 'ok'
}

// The step's recovery key and whether an unrecovered failure of it fails the task.
function stepKey(tool: string, input: any): { key: string; dec: boolean } {
  if (tool === 'Bash') { const f = commandFamily(input?.command); return { key: `Bash:${f}`, dec: !READ_ONLY_BASH.includes(f) } }
  const path = input?.file_path || input?.notebook_path
  return { key: FILE_TOOLS.includes(tool) && path ? `file:${path}` : tool, dec: DECISIVE_TOOLS.includes(tool) }
}

// success is False only for an unrecovered failed decisive step (a LATER ok step with the same key recovers it) or a
// run whose last step was interrupted. No tool data -> success, 0. Records from before 8.1.3 (no key) count by tool name.
// aborted: the run's LAST step was interrupted (a mid-run interrupt the task went on from is no abort). A turn that
// ends aborted (turn.complete isAborted / reason != 'answer') abstains and sends no trace at all.
export function taskOutcome(tools: ToolRec[]): { success: boolean; failed_steps: number; aborted: boolean } {
  const st = tools.map(t => ({ s: t.intr ? 'interrupted' : t.failed ? 'failed' : 'ok', key: t.key ?? t.tool, dec: t.dec ?? DECISIVE_TOOLS.includes(t.tool) }))
  const aborted = st.length > 0 && st[st.length - 1].s === 'interrupted'
  let success = !aborted
  st.forEach((x, i) => {
    if (x.s === 'failed' && x.dec && !st.slice(i + 1).some(y => y.s === 'ok' && y.key === x.key)) success = false
  })
  return { success, failed_steps: st.filter(x => x.s !== 'ok').length, aborted }
}

export function toolRec(tool: string, input: any, res: any, isError: boolean, denied: string | undefined, t0: number, t1: number): ToolRec {
  const status = stepStatus(tool, input, res, isError, denied)
  const rec: ToolRec = { tool, action: summarizeAction(tool, input), result: summarizeResult(tool, res, isError, denied), failed: status !== 'ok',
    start_ms: t0, end_ms: t1, ...stepKey(tool, input) }
  if (status === 'interrupted') rec.intr = true
  const hay = cpSlice(toolHaystack([input]), 2000)
  if (hay) rec.hay = hay
  if (tool === 'Bash' && String(input?.command ?? '').includes('git commit')) { // git_utils.detect_commits_in_session
    const m = /\[[\w\-/]+\s+([a-f0-9]{7,40})\]/.exec(String(res?.stdout ?? ''))
    if (m) rec.commit = m[1]
  }
  return rec
}

// ---------- ace_after_task + trace_truncate ----------
const EFFORT_WEIGHT: Record<string, number> = { auto: 1, low: 1, normal: 1, high: 1.5, xhigh: 2, max: 2 }
export const effortWeight = (level: string) => EFFORT_WEIGHT[level] ?? 1

const stepFailed = (st: any) => typeof st.result === 'string' && /error|failed/i.test(st.result)
const MAX_RECENT_STEPS = 50, MAX_TRACE_BYTES = 2_097_152
const shrink = (s: string, max: number, what: string) => s.length > max ? `<truncated: ${s.length} bytes — ${what}>` : s

// trace_truncate.truncate_trace. Our steps hold summaries (<= 100 chars), so its per-step tool_response cap has nothing to cut.
export function truncateTrace(trace: any): any {
  let truncated = false
  const tr: any[] = trace.trajectory
  if (tr.length > MAX_RECENT_STEPS) {
    const keep = tr.map((_, i) => i).filter(i => i >= tr.length - MAX_RECENT_STEPS || stepFailed(tr[i]))
    trace.trajectory = [{ _truncation_marker: true, original_length: tr.length, kept: keep.length, kept_indices: keep }, ...keep.map(i => tr[i])]
    truncated = true
  }
  if (pyDumps(trace).length > MAX_TRACE_BYTES) {
    trace.task = shrink(trace.task, 2048, 'task')
    if (typeof trace.result.summary === 'string') trace.result.summary = shrink(trace.result.summary, 4096, 'summary')
    truncated = true
  }
  if (truncated) trace.metadata = { ...(trace.metadata ?? {}), trace_truncated: true }
  return trace
}

export function buildTrace(a: {
  userPrompt: string; tools: ToolRec[]; answer: string; playbookUsed: string[]; agentType: string; tsid?: string; agentId?: string
  parentTaskId?: string; retrievalId?: string; appliedLogIds: number[]; nowIso: string; renderVariant?: string; effort: string; git?: any
  conversationId?: string
  usedIds?: { used_ids_model: number; used_ids_tokens: number }  // per-source counters (Haiku, H2), 0 when none
  downvote?: number[]  // the previous main task's evidenced ids after a user rejection
  summaryCap?: number  // 2000 for the closing answer, 4000 for a SubagentHandback report (ace_after_task.handback_summary)
}) {
  const { success, failed_steps, aborted } = taskOutcome(a.tools)  // 8.1.3: end outcome + informational count
  const trace: any = {
    task: `User request: ${cpSlice(a.userPrompt, 2000)}`,
    trajectory: a.tools.map((t, k) => ({ step: k + 1, tool: t.tool, action: t.action,
      result: t.result, start_ms: t.start_ms, end_ms: t.end_ms, duration_ms: t.end_ms - t.start_ms })),
    result: { success, failed_steps, ...(aborted ? { aborted: true } : {}), output: `Executed ${a.tools.length} tool calls`, summary: a.answer ? cpSlice(a.answer, a.summaryCap ?? 2000) : null },
    playbook_used: a.playbookUsed,
    timestamp: a.nowIso,
    agent_type: a.agentType,
  }
  if (a.tsid) trace.session_id = a.tsid
  if (a.renderVariant) trace.render_variant = a.renderVariant // §31: only when known
  if (a.conversationId) trace.conversation_id = a.conversationId.slice(0, 512) // §31: the stable CC session id
  if (a.agentId) trace.agent_id = a.agentId
  if (a.parentTaskId) trace.parent_agent_id = a.parentTaskId // §16 P3: server field name (local state keeps parent_task_id)
  if (a.retrievalId) trace.retrieval_id = a.retrievalId
  trace.applied_log_ids = a.appliedLogIds // server contract: [] when nothing was used, never omitted
  trace.used_ids_model = a.usedIds?.used_ids_model ?? 0
  trace.used_ids_tokens = a.usedIds?.used_ids_tokens ?? 0
  if (a.downvote?.length) trace.feedback = { kind: 'downvote', applied_log_ids: a.downvote }  // never retrieval_id, never text
  trace.effort_level = a.effort
  trace.effort_weight = effortWeight(a.effort)
  if (a.git) trace.git = a.git
  return { trace: truncateTrace(trace), success, failed_steps }
}

// git_utils.parse_diff_stat
export function parseDiffStat(out: string) {
  const last = out.trim().split('\n').pop() ?? ''
  const g = (r: RegExp) => { const m = r.exec(last); return m ? Number(m[1]) : 0 }
  return { insertions: g(/(\d+)\s+insertions?\(\+\)/), deletions: g(/(\d+)\s+deletions?\(-\)/) }
}

// ace_cli.run_learn / ace_engine.learn_command argv (never --pin-session; --no-stream so server 401/500 surface).
// head: the resolved CLI (['ace-cli'] or [node, plugin-local cli.js]) + 'learn', or [node, engine/learn.js].
export function learnArgv(traceFile: string, retrievalId?: string, appliedLogIds: number[] = [], verbosity = 'detailed',
  head: string[] = ['ace-cli', 'learn']) {
  const a = [...head, '--transcript', traceFile, '--json', '--timeout', '300000', '--verbosity', verbosity, '--no-stream']
  if (retrievalId) a.push('--retrieval-id', retrievalId)
  if (appliedLogIds.length) a.push('--applied-log-ids', appliedLogIds.join(','))
  return a
}

// ace_cli._RETRY_LINE: the SDK's retry line, bare (engine logger) or inside ace-cli --json's {"message": ...}
export const RETRY_RE = String.raw`\[ace\] trace retry attempt=(\d+)/(\d+) reason=(.*?) idempotency_key=([^\s"\\]+) at=([^\s"\\]+)`

// The launcher starts the child in its own session (setsid) and returns at once, so neither the hook's return nor
// the session group's SIGHUP/SIGKILL at `claude -p` teardown reaches the learn. The child owns the metrics row and
// all cleanup, lock last (session.end keeps the dir while the lock is fresh). Python: already a hard plugin dependency.
// Engine learn: exit 3 = nothing was sent, so ONLY then the CLI argv after the separator runs (ace_cli.run_learn).
export const FALLBACK_ON_3 = '--ace-fallback-on-3--'
// v8.0.1: every '[ace] trace retry ...' line the learn printed (core >= 3.7.0, engine and ace-cli alike) becomes a
// learn_retry row (retry = the base row JSON), appended with the execution row through APPEND_SH when cwd is known.
const LEARN_CHILD = `import json,os,re,subprocess,sys,time
trace,lock,log,ok,fail,errlog,retry,cwd=sys.argv[1:9]
cmds=sys.argv[9:]
fb=[]
if '${FALLBACK_ON_3}' in cmds:
    k=cmds.index('${FALLBACK_ON_3}')
    cmds,fb=cmds[:k],cmds[k+1:]
res=trace+'.result'
code=1
cut=None
try:
    with open(res,'ab') as f:
        code=subprocess.run(cmds,stdin=subprocess.DEVNULL,stdout=f,stderr=subprocess.STDOUT,timeout=310).returncode
        if code==3 and fb:
            cut=f.tell()
            code=subprocess.run(fb,stdin=subprocess.DEVNULL,stdout=f,stderr=subprocess.STDOUT,timeout=310).returncode
except Exception as e:
    try:
        with open(res,'a') as f:
            f.write(str(e))
    except OSError:
        pass
rows=[]
if retry:
    try:
        with open(res,'rb') as f:
            out=f.read()
        parts=[('lib' if fb else 'cli',out)] if cut is None else [('lib',out[:cut]),('cli',out[cut:])]
        at=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
        for eng,text in parts:
            for m in re.finditer(${JSON.stringify(RETRY_RE)},text.decode('utf-8','replace')):
                rows.append(json.dumps(dict(json.loads(retry),timestamp=at,attempt=int(m.group(1)),max_attempts=int(m.group(2)),
                    reason=m.group(3),idempotency_key=m.group(4),at=m.group(5),engine=eng,learning_sent=code==0)))
    except (OSError,ValueError):
        pass
rows.append(ok if code==0 else fail)
text=chr(10).join(rows)+chr(10)
try:
    if cwd:
        subprocess.run(['/bin/sh','-c',${JSON.stringify(APPEND_SH)},'sh',log,cwd],input=text.encode(),timeout=10)
    else:
        os.makedirs(os.path.dirname(log),exist_ok=True)
        with open(log,'a') as f:
            f.write(text)
except Exception:
    pass
if code!=0 and errlog:
    try:
        os.makedirs(os.path.dirname(errlog),exist_ok=True)
        with open(res,errors='replace') as f, open(errlog,'a') as g:
            g.write('ace-cli learn (mod) exit %d: %s'%(code,f.read()[-500:])+chr(10))
    except OSError:
        pass
for p in (res,trace,lock):
    try:
        os.unlink(p)
    except OSError:
        pass
`
const LEARN_LAUNCHER = `import subprocess,sys
subprocess.Popen([sys.executable,'-I','-c',${JSON.stringify(LEARN_CHILD)}]+sys.argv[1:],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,close_fds=True,start_new_session=True)
`
// ponytail: POSIX-shaped; on Windows the bare `ace-cli` (a .cmd shim) would need a shell. The Python chain covers
// Windows until the mod is proven there (§13.1 m2: Windows untested).
export function detachedLearnArgv(j: { learnArgv: string[]; trace: string; lock: string; log: string; rowOk: string; rowFail: string; errLog?: string; python?: string
  retryRow?: string; cwd?: string }): string[] {
  return [j.python || 'python3', '-I', '-c', LEARN_LAUNCHER, j.trace, j.lock, j.log, j.rowOk, j.rowFail, j.errLog ?? '', j.retryRow ?? '', j.cwd ?? '', ...j.learnArgv]
}

// ace_after_task._delegated_running (§16 P2): a running subagent/workflow of this task defers the main learn.
// Monitors, shells, teammates, crons are long-lived and never defer.
export const delegatedRunning = (bg: unknown): boolean => Array.isArray(bg)
  && bg.some((b: any) => b && typeof b === 'object' && (b.type === 'subagent' || b.type === 'workflow') && b.status === 'running')
