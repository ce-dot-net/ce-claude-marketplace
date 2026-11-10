// Learn side (ace_after_task + trace_truncate): tool records, trivial/substantial gates, trace build + truncate,
// learn argv and the detached learn launcher. Pure: no `$`, no I/O.
import { pyDumps } from './pyjson.ts'
import { cpSlice, isMachinePrompt } from './text.ts'
import { toolHaystack, type ToolRec } from './evidence.ts'
import { APPEND_SH } from './sh.ts'
import { sha256Hex } from './cohort.ts'

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
  if (tool === 'Bash') return bashAction(i.command)  // 8.1.3: '<family> :: <redacted command <= 200>'
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
export function summarizeResult(tool: string, res: any, isError = false, denied?: string, text?: string): string {
  if (denied) return `Error: ${denied.slice(0, 100)}`
  // 8.1.3: secrets out before any cut
  if (typeof res === 'string') res = redact(res)
  else if (res && typeof res === 'object' && !Array.isArray(res)) res = Object.fromEntries(Object.entries(res).map(([k, v]) => [k, redact(v)]))
  else if (Array.isArray(res)) res = redact(JSON.stringify(res))
  if (isError) return `Error: ${String(typeof text === 'string' ? redact(text) : typeof res === 'string' ? res : JSON.stringify(res)).slice(0, 100)}`
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
// 8.1.4: result.outcome_rule is one value of this fixed list (ace_trace_meta.OUTCOME_RULES, parity test): end-outcome-1 =
// the 8.1.3 end-outcome rule (Stop, SubagentStop, turn.complete), permission-gate-1 = a PermissionDenied trace (Python).
// A future rule change bumps the number and adds a value in both lists. The execution row names the same value.
export const OUTCOME_RULES = ['end-outcome-1', 'permission-gate-1'] as const
export const OUTCOME_RULE = OUTCOME_RULES[0]
export const BENIGN_EXIT1 = ['grep', 'egrep', 'fgrep', 'rg', 'diff', 'cmp', 'test', '[', '[[', 'git diff', 'git grep', 'command -v', 'which', 'type', 'pgrep', 'pidof', 'jq']
// ponytail: a fixed read-only family list (a failed read-only step never fails the task); grow it from probe data.
// Membership is by prefix: 'git diff HEAD~1' is in 'git diff'.
export const READ_ONLY_BASH = ['ls', 'cat', 'head', 'tail', 'wc', 'find', 'grep', 'egrep', 'fgrep', 'rg', 'pwd', 'echo', 'printf', 'which', 'type', 'command -v', 'file', 'stat', 'du', 'df', 'tree', 'jq', 'sort', 'uniq', 'cut', 'tr', 'diff', 'cmp', 'test', '[', '[[', 'date', 'printenv', 'ps', 'pgrep', 'pidof', 'git status', 'git log', 'git show', 'git diff', 'git grep', 'git rev-parse', 'git ls-files', 'git blame', 'cd', 'pushd', 'popd', 'true', 'sleep', 'export', 'set', 'sed', 'awk', 'read']
// State-changing or verifying tools besides non-read-only Bash and state-changing MCP tools (MCP_WRITE_VERBS).
export const DECISIVE_TOOLS = ['Edit', 'Write', 'MultiEdit', 'NotebookEdit', 'Agent', 'Task', 'Workflow']
// Interpreters / multi-tool CLIs: the family adds this many non-flag tokens (subcommand, script basename, -c/-e).
export const SUBCOMMAND_TOOLS: Record<string, number> = {'python': 1, 'python3': 1, 'bash': 1, 'sh': 1, 'node': 1, 'bun': 1, 'deno': 1, 'ruby': 1, 'perl': 1, 'npm': 1, 'npx': 1, 'pnpm': 1, 'yarn': 1, 'cargo': 1, 'go': 1, 'make': 1, 'terraform': 1, 'uv': 1, 'pip': 1, 'pip3': 1, 'gh': 2, 'git': 2, 'docker': 2, 'kubectl': 2, 'aws': 2, 'gcloud': 2, 'claude': 2}
// An MCP tool whose action name (after the last '__') has one of these words is state-changing (decisive).
// ponytail: a verb heuristic on the tool name; a per-server table is the upgrade path.
export const MCP_WRITE_VERBS = ['save', 'create', 'update', 'delete', 'remove', 'send', 'post', 'publish', 'merge', 'push', 'comment', 'reply', 'upload', 'write', 'set', 'add', 'assign', 'close', 'transfer']
const FILE_TOOLS = ['Edit', 'Write', 'MultiEdit', 'NotebookEdit']
const WRAPPERS = ['sudo', 'time', 'env', 'nice', 'nohup', 'exec', 'bunx']
const KW_SKIP = ['do', 'then', 'else', 'elif', 'if', 'while', 'until']  // shell keywords before a command
const KW_NONE = ['done', 'fi', 'esac', 'for', 'case', 'select', 'in', 'function']  // structure, no command
const ASSIGN = /^[A-Za-z_][A-Za-z0-9_]*=/
const REDIR = /^(\d*|&)(<<<|<<-?|<>|<&|<|>>|>&|>\||>)([\s\S]*)/
const SHORT_I = /^-[A-Za-z]*i/  // sed -i, -Ei, -i.bak
const PERL_I = /^-[A-Za-z0-9]*i/  // perl -i, -pi, -0pi, -i.bak
const AWK_INPLACE = / (?:-i ?|--include[= ])inplace /
const LONG_RUN = /^(?:[A-Fa-f0-9]{24,}|(?=[^a-z]*[a-z])(?=[^A-Z]*[A-Z])(?=[^0-9]*[0-9])[A-Za-z0-9+\/_-]{24,}={0,2})$/
const SCHEME = /^[A-Za-z][A-Za-z0-9+.-]*:\/\//
const HASH_INTERP = ['python', 'python3', 'bash', 'sh', 'node', 'ruby', 'perl']  // -c/-e/heredoc script hashed into the key
const CHAIN = ['&&', '||', ';', '\n']

// Split s at seps outside quotes, backticks, $(...)/(...) and heredoc bodies (backslash escapes outside single quotes).
// Same scan as ace_after_task._split_top.
function splitTop(s: string, seps: string[]): string[] {
  const out: string[] = [], pend: string[] = [], n = s.length
  let cur = '', q = '', bt = false, depth = 0, i = 0
  while (i < n) {
    const ch = s[i]
    if (q) {
      if (ch === '\\' && q === '"' && i + 1 < n) { cur += s.slice(i, i + 2); i += 2; continue }
      if (ch === q) q = ''
      cur += ch; i++; continue
    }
    if (ch === '\\' && i + 1 < n) { cur += s.slice(i, i + 2); i += 2; continue }
    if (ch === '`') { bt = !bt; cur += ch; i++; continue }
    if (bt) { cur += ch; i++; continue }
    if (ch === '"' || ch === "'") { q = ch; cur += ch; i++; continue }
    if (s.startsWith('<<', i) && !s.startsWith('<<<', i)) {  // heredoc: remember the delimiter
      let j = i + 2
      if (j < n && s[j] === '-') j++
      while (j < n && ' \t'.includes(s[j])) j++
      let k = j
      while (k < n && !' \t\n;|&<>()'.includes(s[k])) k++
      const d = s.slice(j, k).replace(/['"\\]/g, '')
      if (d) pend.push(d)
      cur += s.slice(i, k); i = k; continue
    }
    if (ch === '\n' && pend.length) {  // the body runs to the delimiter line; nothing in it splits
      let j = i + 1, e = n
      while (pend.length && j <= n) {
        e = s.indexOf('\n', j)
        if (e < 0) e = n
        if (pyStrip(s.slice(j, e), WS) === pend[0]) pend.shift()
        j = e + 1
      }
      pend.length = 0
      cur += s.slice(i, e); i = e; continue
    }
    if (ch === '(') depth++
    else if (ch === ')') depth = Math.max(0, depth - 1)
    const sep = depth === 0 ? seps.find(x => s.startsWith(x, i)) : undefined
    if (sep) { out.push(cur); cur = ''; i += sep.length; continue }
    cur += ch; i++
  }
  out.push(cur)
  return out
}

// fam is in table, by family prefix ('git diff HEAD' is in 'git diff').
const inTable = (fam: string, table: string[]) => table.some(e => fam === e || fam.startsWith(e + ' '))
const pyStrip = (x: string, chars: string) => { let a = 0, b = x.length; while (a < b && chars.includes(x[a])) a++; while (b > a && chars.includes(x[b - 1])) b--; return x.slice(a, b) }
const WS = ' \t\n\r\x0b\x0c'  // Python str.strip()/split() whitespace (ASCII)

// 8 hex chars of sha256 over the whitespace-collapsed text (ace_after_task._norm_hash).
const normHash = (text: string) => sha256Hex(text.split(/[ \t\n\r\x0b\x0c]+/).filter(Boolean).join(' ')).slice(0, 8)
// A token that must never be in a family: a URL, anything with '@', a long hex/base64 run, a secret.
const suspicious = (tok: string) => tok.includes('://') || tok.includes('@') || LONG_RUN.test(tok) || redact(tok) !== tok
const count = (x: string, c: string) => x.split(c).length - 1
// A word without quotes, braces and unbalanced outer parentheses ('make)' -> 'make', 'f()' stays).
function clean(x: string): string {
  x = pyStrip(x.replace(/["']/g, ''), '{}')
  while (x.endsWith(')') && count(x, ')') > count(x, '(')) x = x.slice(0, -1)
  while (x.startsWith('(') && count(x, '(') > count(x, ')')) x = x.slice(1)
  return x
}
const writesTo = (t: string) => !!t && t !== '/dev/null' && !t.startsWith('&')

// curl/wget recovery key: method + host (no userinfo, path or query).
function httpKey(first: string, w: string[]): string {
  let method: string | null = null, host = ''
  for (let i = 1; i < w.length; i++) {
    const x = w[i]
    if ((x === '-X' || x === '--request' || x === '--method') && i + 1 < w.length) { method = method || w[i + 1].toUpperCase(); i++ }
    else if (x.startsWith('--request=') || x.startsWith('--method=')) method = method || x.slice(x.indexOf('=') + 1).toUpperCase()
    else if (x.startsWith('-X') && x.length > 2 && !x.startsWith('--')) method = method || x.slice(2).toUpperCase()
    else if (['-d', '-F', '--form', '--json'].includes(x) || x.startsWith('--data') || x.startsWith('--post-')) method = method || 'POST'
    else if (!host && SCHEME.test(x)) {
      let h = x.slice(x.indexOf('://') + 3)
      for (const c of '/?#') h = h.split(c)[0]
      host = h.split('@').pop()!.toLowerCase()
    }
  }
  return `${first}#${method || 'GET'}${host ? ' ' + host : ''}`
}

// [family, readOnly, key] of one pipeline stage. key = the recovery key: the family, plus a script hash for an
// interpreter's -c/-e/heredoc script, or method+host for curl/wget.
function stageFamily(text: string): [string, boolean, string] {
  let body = ''
  if (text.includes('<<')) {  // the heredoc body is data (hashed into the key)
    const k = text.indexOf('\n')
    if (k >= 0) { body = text.slice(k + 1); text = text.slice(0, k) }
  }
  const raw = splitTop(pyStrip(text, WS), [' ', '\t', '\n']).filter(x => x && x !== '!')
  if (raw.length && raw[0].startsWith('(')) {  // subshell: its own chain decides
    const inner = raw[0].slice(1)
    const [fam, dec, key] = analyze(inner.endsWith(')') ? inner.slice(0, -1) : inner)
    return [fam, !dec, key]
  }
  let w: string[] = [], skip = false, writes = false, outRedir = false
  for (let x of raw) {
    x = clean(x)
    if (skip) { skip = false; writes = writes || (outRedir && writesTo(x)); continue }  // the target of a bare operator
    if (!x) continue
    const m = REDIR.exec(x)
    if (m) {  // a redirection: '>'/'>>'/'1>'/'&>' to a file writes (not '2>&1', not '> /dev/null')
      outRedir = ['>', '>>', '>|'].includes(m[2]) && ['', '1', '&'].includes(m[1])
      if (m[3]) writes = writes || (outRedir && writesTo(m[3]))
      else skip = true
      continue
    }
    w.push(x)
  }
  while (w.length && (WRAPPERS.includes(w[0]) || KW_SKIP.includes(w[0]) || ASSIGN.test(w[0]) || w[0] === 'timeout' || ((w[0] === 'uv' || w[0] === 'poetry') && w[1] === 'run'))) {
    if (w[0] === 'timeout') {
      w = w.slice(1)
      while (w.length && w[0].startsWith('-')) w = w.slice(1)
      w = w.slice(1)
    } else if ((w[0] === 'uv' || w[0] === 'poetry') && w[1] === 'run') w = w.slice(2)
    else w = w.slice(1)
  }
  if (!w.length || KW_NONE.includes(w[0])) return ['', true, '']
  const first = w[0].split('/').pop()!
  let fam = first, script: string | null = null
  if (first === 'sed' && w.slice(1).some(x => SHORT_I.test(x) || x === '--in-place' || x.startsWith('--in-place='))) fam = 'sed-i'  // edits in place: not read-only
  else if ((first === 'awk' || first === 'gawk') && AWK_INPLACE.test(' ' + w.slice(1).join(' ') + ' ')) fam = 'awk-i'
  else if (first === 'perl' && w.slice(1).some(x => PERL_I.test(x))) fam = 'perl-pi'
  else if (first === 'curl' || first === 'wget') return [first, !writes && inTable(first, READ_ONLY_BASH), httpKey(first, w)]
  else if ((first === 'python' || first === 'python3') && w.length > 2 && w[1] === '-m') fam = w[2]
  else if (first === 'command' && (w[1] === '-v' || w[1] === '-V')) fam = 'command -v'
  else if (Object.prototype.hasOwnProperty.call(SUBCOMMAND_TOOLS, first)) {
    const rest = w.slice(1)
    let tok: string | null = null, sus = false
    while (rest.length) {
      const x = rest.shift()!
      if (SUBCOMMAND_TOOLS[first] === 1 && (x === '-c' || x === '-e')) { tok = x; script = rest.length ? rest[0] : ''; break }
      if (x.startsWith('-')) { if (first === 'git' && (x === '-C' || x === '-c') && rest.length) rest.shift(); continue }
      if (/[ \t\n]/.test(x)) continue  // a quoted string is no subcommand or script
      sus = suspicious(x)
      tok = x.replace(/\/+$/, '').split('/').pop() || x
      break
    }
    if (tok && !sus) {
      fam = `${first} ${tok}`
      // ponytail: the second token is taken only right after the first (no flag-value parsing)
      if (SUBCOMMAND_TOOLS[first] === 2 && rest.length && !rest[0].startsWith('-')) {
        if (suspicious(rest[0])) fam = first  // never a URL, userinfo or token in a family: the first word only
        else fam += ` ${rest[0]}`
      }
    }
  }
  let key = fam
  if (HASH_INTERP.includes(first) && (script !== null || body)) key = `${fam}#${normHash(script !== null ? script : body)}`
  return [fam, !writes && inTable(fam, READ_ONLY_BASH), key]
}

// [family, decisive, key] of a Bash command. Pipeline: the LAST stage (its exit code is the one the shell reports).
// &&, ||, ;, newline chain: the LAST NON-READ-ONLY item (a trailing read-only item never decides), else the last item;
// decisive if any item is not read-only.
function analyze(cmd: string): [string, boolean, string] {
  const items: [string, boolean, string][] = []
  for (const it of splitTop(cmd, CHAIN)) {
    const stages = splitTop(it, ['|']).filter(x => pyStrip(x, WS))
    if (stages.length) {
      const r = stageFamily(pyStrip(pyStrip(stages[stages.length - 1], WS), '&'))
      if (r[0]) items.push(r)
    }
  }
  if (!items.length) return ['', true, '']
  const nonro = items.filter(x => !x[1])
  const pick = nonro.length ? nonro[nonro.length - 1] : items[items.length - 1]
  return [pick[0], nonro.length > 0, pick[2]]
}

// [family, decisive, key] of a Bash command (ace_after_task.bash_step); never throws.
export function bashStep(cmd: unknown): [string, boolean, string] {
  const c = typeof cmd === 'string' ? cmd : cmd === null || cmd === undefined ? '' : String(cmd)  // the RAW command: it never leaves the plugin
  try { return analyze(c) } catch {  // ponytail: unparsable input falls back to the first word
    const w = c.split(/[ \t\n\r\x0b\x0c]+/).filter(Boolean)
    let fam = w.length ? w[0].split('/').pop()! : ''
    if (suspicious(fam)) fam = ''
    return [fam, !inTable(fam, READ_ONLY_BASH), fam]
  }
}

// Bash command -> its family (ace_after_task.command_family). ponytail: a heuristic tokenizer, not a shell parser.
export const commandFamily = (cmd: unknown) => bashStep(cmd)[0]

// An MCP tool whose action name (after the last '__') has a MCP_WRITE_VERBS word (snake, kebab or camelCase).
export function mcpWrites(tool: string): boolean {
  if (!String(tool).startsWith('mcp__')) return false
  const act = String(tool).split('__').pop()!.replace(/([a-z])([A-Z])/g, '$1_$2').toLowerCase()
  return act.split(/[^a-z0-9]+/).some(x => MCP_WRITE_VERBS.includes(x))
}

// Secrets in sent text (8.1.3), FAIL-CLOSED (ace_after_task.redact): Claude Code does not redact hook inputs. A secret key
// followed by ':' or '=' redacts from the value start to the end of the line, and on to the next blank line (at most
// REDACT_BLOCK code points) for block values; inside a scheme:// token (a URL query) the value ends at '&', '#' or
// whitespace. --password/--token/--secret/--api-key, mysql/sshpass -p, curl/wget -u user:pass and Bearer redact to the end of the
// line. ponytail: over-redacts on purpose (the rest of the line is lost), never under-redacts.
export const REDACT_BLOCK = 500
const SPAN_RES: [RegExp, boolean][] = [
  [/(?:password|passwd|passphrase|pwd|secret|token|credential|authorization|cookie|api[-_]?key|_key(?![a-z0-9])|pass(?![a-z]))[A-Za-z0-9_-]*["']?[ \t]*[:=][ \t]*/gi, true],
  [/--[A-Za-z0-9-]*(?:token|password|passwd|secret|api[-_]?key|credential)[A-Za-z0-9-]*(?:=|[ \t]+)/gi, false],
  [/\b(?:mysql(?:dump|admin|sh)?|sshpass|7z[a-z]?)\b[^\n]*?[ \t]-p[ \t]*/g, false],
  [/\b(?:unzip|zip)\b[^\n]*?[ \t]-P[ \t]*/g, false],
  [/\bssh-keygen\b[^\n]*?[ \t]-N[ \t]*/g, false],
  [/\bopenssl\b[^\n]*?[ \t]-(?:k|pass|passin|passout)[ \t]+/g, false],
  [/\bhtpasswd\b[ \t]*/g, false],
  [/\b(?:curl|wget)\b[^\n]*?[ \t](?:-u|--user)(?:=|[ \t]+)?(?=["']?[^ \t\n\r"']*:)/g, false],
  [/\bBearer[ \t]+/gi, false],
]
const BLANK_LINE = /\n[ \t\r]*\n/g
const URL_VALUE_END = /[&# \t\n\r\x0b\x0c"']/g
const TOKEN_SEP = ' \t\n\r\x0b\x0c"\''
const SECRET_RES: [RegExp, string][] = [
  // the echo/printf stage that pipes a secret into --password-stdin / --with-token
  [/\b(echo|printf)\b[^\n]*\|(?=[^|\n]*--(?:password-stdin|with-token))/gi, '$1 [redacted] |'],
  [/(\b[A-Za-z][A-Za-z0-9+.-]*:\/\/)[^ \t\n\r\x0b\x0c"']*@/g, '$1[redacted]@'],
  [/\b(?:ghp_|gho_|ghu_|ghs_|ghr_|github_pat_|xox[abprs]-|ace_user_|sk-)[A-Za-z0-9_-]{8,}|\bnpm_[A-Za-z0-9]{20,}|\bAKIA[0-9A-Z]{12,}|\beyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}(?:\.[A-Za-z0-9_-]+)?/g, '[redacted]'],
]
// Run BEFORE the span rules (which cut the line at the flag): the stdin body of --password-stdin / --with-token that the
// span rules cannot see, a here-string BEFORE the flag, and a here-doc body on the lines after it.
const STDIN_RES: [RegExp, string][] = [
  [/(<<<[ \t]*)(?:"[^"\n]*"|'[^'\n]*'|[^ \t\n\r"';&|)]+)(?=[^\n|]*--(?:password-stdin|with-token))/gi, '$1[redacted]'],
  [/(--(?:password-stdin|with-token)\b[^\n]*(?<!<)<<-?[ \t]*['"]?(\w+)['"]?[^\n]*\n)[\s\S]+?(?=\n[ \t]*\2[ \t]*(?:\n|(?![\s\S])))/gi, '$1[redacted]'],
]
const searchFrom = (rx: RegExp, s: string, pos: number) => { rx.lastIndex = pos; return rx.exec(s) }
// The index REDACT_BLOCK code points after start (Python counts code points).
function cpAdvance(s: string, start: number, n: number): number {
  let k = start
  while (k < s.length && n-- > 0) { const c = s.charCodeAt(k); k += c >= 0xd800 && c <= 0xdbff && k + 1 < s.length && (s.charCodeAt(k + 1) & 0xfc00) === 0xdc00 ? 2 : 1 }
  return k
}
function redactSpans(text: string): string {
  let out = '', pos = 0
  for (;;) {
    let best: RegExpExecArray | null = null, block = false
    for (const [rx, b] of SPAN_RES) { const m = searchFrom(rx, text, pos); if (m && (!best || m.index < best.index)) { best = m; block = b } }
    if (!best) break
    const start = best.index + best[0].length
    let k = best.index - 1
    while (k >= 0 && !TOKEN_SEP.includes(text[k])) k--
    let end: number
    if (text.slice(k + 1, best.index).includes('://')) { const e = searchFrom(URL_VALUE_END, text, start); end = e ? e.index : text.length }  // a URL query value
    else {
      end = text.indexOf('\n', start)
      if (end < 0) end = text.length
      if (block) { const b = searchFrom(BLANK_LINE, text, start); end = Math.max(end, Math.min(b ? b.index : text.length, cpAdvance(text, start, REDACT_BLOCK))) }
    }
    out += text.slice(pos, start) + '[redacted]'
    pos = end
  }
  return out + text.slice(pos)
}
export function redact<T>(text: T): T {
  if (typeof text !== 'string' || !text) return text
  let s: string = text
  for (const [rx, rep] of STDIN_RES) s = s.replace(rx, rep)
  s = redactSpans(s)
  for (const [rx, rep] of SECRET_RES) s = s.replace(rx, rep)
  return s as any
}

// The family to SEND (ace_after_task.visible_family): from the raw command, kept only if every word is still in the
// redacted command and holds no secret; else its first word under the same test; else 'unknown'.
export function visibleFamily(c: string): string {
  const fam = commandFamily(c), red = redact(c)
  const ok = (w: string) => red.includes(w) && redact(w) === w && !suspicious(w)
  if (fam && fam.split(' ').every(ok)) return fam
  const first = fam ? fam.split(' ')[0] : ''
  return first && ok(first) ? first : 'unknown'
}

export const ACTION_MAX = 200, FAMILY_MAX = 60
// The Bash trajectory action (ace_after_task.bash_action): '<family> :: <command>', the family first (cut to FAMILY_MAX),
// the redacted command with whitespace collapsed after it, the whole cut to ACTION_MAX chars; 'unknown' when there is none.
export function bashAction(cmd: unknown): string {
  const c = typeof cmd === 'string' ? cmd : cmd === null || cmd === undefined ? '' : String(cmd)
  let body = redact(c).split(/[ \t\n\r\x0b\x0c]+/).filter(Boolean).join(' ')
  if (!body) return 'unknown'
  let fam = visibleFamily(c)
  if ([...fam].length > FAMILY_MAX) fam = cpSlice(fam, FAMILY_MAX - 3) + '...'
  const room = ACTION_MAX - [...fam].length - 4
  if ([...body].length > room) body = cpSlice(body, room - 3) + '...'
  return `${fam} :: ${body}`
}

const EXIT_TEXT = /^Exit code (\d+)/
// The known exit code (structured, or the "Exit code N" text), else null. A code the tool interpreted itself
// (returnCodeInterpretation, e.g. grep's no-matches) counts as 0.
function exitCode(res: any, text?: string): number | null {
  if (typeof text === 'string') { const m = EXIT_TEXT.exec(text); if (m) return Number(m[1]) }  // tool.call: "Exit code N" lives in text
  if (typeof res === 'string') { const m = EXIT_TEXT.exec(res); return m ? Number(m[1]) : null }
  if (!res || typeof res !== 'object' || Array.isArray(res)) return null
  if (res.returnCodeInterpretation) return 0
  for (const k of ['exit_code', 'exitCode']) if (res[k] !== undefined && res[k] !== null) { const c = Number(res[k]); if (Number.isFinite(c)) return Math.trunc(c) }
  for (const k of ['error', 'content']) if (typeof res[k] === 'string') { const m = EXIT_TEXT.exec(res[k]); if (m) return Number(m[1]) }
  return null
}

// 'ok' | 'failed' | 'interrupted'. stderr alone never fails a step; a known Bash exit code decides (benign exit-1
// families are ok); otherwise isError / error / a denial does.
function stepStatus(tool: string, input: any, res: any, isError: boolean, denied: string | undefined, text?: string): 'ok' | 'failed' | 'interrupted' {
  if (res && typeof res === 'object' && res.interrupted === true) return 'interrupted'
  if (denied) return 'failed'
  if (tool === 'Bash') {
    const c = exitCode(res, isError ? text : undefined)
    if (c !== null) return c === 0 || (c === 1 && inTable(commandFamily(input?.command), BENIGN_EXIT1)) ? 'ok' : 'failed'
  }
  return isError || (res && typeof res === 'object' && !Array.isArray(res) && res.error) ? 'failed' : 'ok'
}

// The step's recovery key and whether an unrecovered failure of it fails the task.
function stepKey(tool: string, input: any): { key: string; dec: boolean } {
  if (tool === 'Bash') { const [, dec, k] = bashStep(input?.command); return { key: `Bash:${k}`, dec } }
  const path = input?.file_path || input?.notebook_path
  return { key: FILE_TOOLS.includes(tool) && path ? `file:${path}` : tool, dec: DECISIVE_TOOLS.includes(tool) || mcpWrites(tool) }
}

// success is False only for an unrecovered failed decisive step (a LATER ok step with the same key recovers it) or a
// run whose last step was interrupted. No tool data -> success, 0. Records from before 8.1.3 (no key) count by tool name.
// aborted (internal, not in the trace): the run's LAST step was interrupted, so success is false. The mod sees aborts
// through turn.complete (isAborted / reason) and on purpose sends no trace for them (turn.ts); the classic chain sees none.
export function taskOutcome(tools: ToolRec[]): { success: boolean; failed_steps: number; aborted: boolean } {
  const st = tools.map(t => ({ s: t.intr ? 'interrupted' : t.failed ? 'failed' : 'ok', key: t.key ?? t.tool, dec: t.dec ?? DECISIVE_TOOLS.includes(t.tool) }))
  const aborted = st.length > 0 && st[st.length - 1].s === 'interrupted'
  let success = !aborted
  st.forEach((x, i) => {
    if (x.s === 'failed' && x.dec && !st.slice(i + 1).some(y => y.s === 'ok' && y.key === x.key)) success = false
  })
  return { success, failed_steps: st.filter(x => x.s !== 'ok').length, aborted }
}

// text: the tool.call result's text (a failed Bash call's "Exit code N" first line lives only there).
export function toolRec(tool: string, input: any, res: any, isError: boolean, denied: string | undefined, t0: number, t1: number, text?: string): ToolRec {
  const status = stepStatus(tool, input, res, isError, denied, text)
  const rec: ToolRec = { tool, action: summarizeAction(tool, input), result: summarizeResult(tool, res, isError, denied, text), failed: status !== 'ok',
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
  pluginVersion?: string  // 8.1.4: the manifest x.y.z (the version in X-ACE-Client)
}) {
  const { success, failed_steps } = taskOutcome(a.tools)  // 8.1.3: end outcome + informational count
  const trace: any = {
    task: `User request: ${cpSlice(redact(a.userPrompt), 2000)}`,
    trajectory: a.tools.map((t, k) => ({ step: k + 1, tool: t.tool, action: t.action,
      result: t.result, start_ms: t.start_ms, end_ms: t.end_ms, duration_ms: t.end_ms - t.start_ms })),
    result: { success, failed_steps, output: `Executed ${a.tools.length} tool calls`, summary: a.answer ? cpSlice(redact(a.answer), a.summaryCap ?? 2000) : null,
      plugin_version: a.pluginVersion ?? '0.0.0', outcome_rule: OUTCOME_RULE },  // 8.1.4: inside result (the server keeps result)
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
// 8.1.4: the child first CLAIMS the trace (rename to .owned); a launcher parent that gave up on the launcher claims it
// with its own rename (.parent) instead, so exactly one side owns the file and the reader never loses it. After a
// failed learn the child hands the trace to ace_trace_queue.settle (queue job = argv[9]); after a good one it starts
// the detached replay.
const LEARN_CHILD = `import json,os,re,subprocess,sys,time
trace,lock,log,ok,fail,errlog,retry,cwd,queue=sys.argv[1:10]
cmds=sys.argv[10:]
own=trace+'.owned'
try:
    os.rename(trace,own)
except OSError:
    sys.exit(0)
cmds=[own if a==trace else a for a in cmds]
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
Q=None
if queue:
    try:
        q=json.loads(queue)
        sys.path.insert(0,q['utils'])
        import ace_trace_queue as Q
        if code!=0:
            with open(own) as f:
                body=json.load(f)
            with open(res,errors='replace') as f:
                out=f.read()
            at=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
            for r in Q.settle(os.path.join(q['root'],'trace-queue'),q['id'],body,q['meta'],code,out,on=q.get('on',True),keyed=bool(fb) and cut is None):
                rows.append(json.dumps(dict(timestamp=at,**r,session_id=q['meta'].get('session_id'),source='mod')))
    except Exception:
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
for p in (res,own,lock):
    try:
        os.unlink(p)
    except OSError:
        pass
if Q is not None and code==0:
    Q.spawn_replay(cwd=cwd or None,data_root=q['root'])
`
const LEARN_LAUNCHER = `import subprocess,sys
subprocess.Popen([sys.executable,'-I','-c',${JSON.stringify(LEARN_CHILD)}]+sys.argv[1:],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,close_fds=True,start_new_session=True)
`
// 8.1.4: the launcher parent gave up on the launcher (LAUNCHER_MS or a non-zero exit) but the child may already own the
// trace. Claim it by rename(2): the parked path when the parent won (no child read it: nothing was sent), null when the
// child had it (it writes the rows and releases the lock). Never rm the trace here (the 8.1.3 ENOENT).
export async function reclaimTrace(run: (argv: string[]) => Promise<{ exitCode: number | null } | null>, traceFile: string): Promise<string | null> {
  const parked = `${traceFile}.parent`
  const r = await run(['mv', '-n', traceFile, parked])
  return r && r.exitCode === 0 ? parked : null
}
// ponytail: POSIX-shaped; on Windows the bare `ace-cli` (a .cmd shim) would need a shell. The Python chain covers
// Windows until the mod is proven there (§13.1 m2: Windows untested).
export function detachedLearnArgv(j: { learnArgv: string[]; trace: string; lock: string; log: string; rowOk: string; rowFail: string; errLog?: string; python?: string
  retryRow?: string; cwd?: string; queue?: string }): string[] {
  return [j.python || 'python3', '-I', '-c', LEARN_LAUNCHER, j.trace, j.lock, j.log, j.rowOk, j.rowFail, j.errLog ?? '', j.retryRow ?? '', j.cwd ?? '', j.queue ?? '', ...j.learnArgv]
}

// ace_after_task._delegated_running (§16 P2): a running subagent/workflow of this task defers the main learn.
// Monitors, shells, teammates, crons are long-lived and never defer.
export const delegatedRunning = (bg: unknown): boolean => Array.isArray(bg)
  && bg.some((b: any) => b && typeof b === 'object' && (b.type === 'subagent' || b.type === 'workflow') && b.status === 'running')
