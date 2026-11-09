// Prompt and path text helpers: machine-prompt / skip rules, abbreviations, domain-to-path match, subagent query,
// code-point slicing. Pure: no `$`, no I/O.

export const cps = (s: string) => Array.from(s)
export const cpLen = (s: string) => { let n = 0; for (const _ of s) n++; return n }
export const cpSlice = (s: string, n: number) => cps(s).slice(0, n).join('')
export const normWs = (t: unknown) => String(t ?? '').split(/\s+/).filter(Boolean).join(' ')

// ---------- utils/machine_prompts + ace_before_task._skip_reason ----------
export const MACHINE_PROMPT_PREFIXES = ['<task-notification', '<agent-message', '<cross-session-message',
  '[system notification', '<local-command', '<command-name>', '<bash-input>', '<bash-stdout>', '<bash-stderr>',
  '<system-reminder>']
export const LEADING_REMINDER = /^(?:\s*<system-reminder>[\s\S]*?<\/system-reminder>)+\s*/i
export const isMachinePrompt = (t: string, extra: string[] = []) =>
  [...MACHINE_PROMPT_PREFIXES, ...extra].some(p => (t || '').toLowerCase().trimStart().startsWith(p))

// Python str.strip() strips Unicode whitespace; JS trim() is close enough (both cover \s + NBSP etc.).
export function skipReason(prompt: string, minChars = 12, extra: string[] = []): string | null {
  const raw = prompt.trim()
  const stripped = raw.replace(LEADING_REMINDER, '').trim()
  if (!stripped && raw) return 'machine_prompt'
  if (isMachinePrompt(stripped, extra)) return 'machine_prompt'
  if ([...stripped].length < minChars) return 'prompt_too_short'
  const low = stripped.toLowerCase()
  if (low.startsWith('/ace-') || low.startsWith('/ace:')) return 'ace_command'
  return null
}

// mod-only: slash commands that carry no task of their own (ACE's, and session built-ins whose arguments are not work).
const NO_TASK_COMMANDS = new Set(['compact', 'clear', 'model', 'config', 'help', 'status', 'memory', 'resume', 'mcp', 'hooks',
  'cost', 'context', 'login', 'logout', 'exit', 'quit', 'plugin', 'reload-plugins', 'effort', 'permissions', 'agents', 'rename'])
export const isNoTaskCommand = (name: string) => /^ace([:-]|$)/i.test(name) || NO_TASK_COMMANDS.has(name)

// mod-only: origins that are never a human task (PromptOrigin kinds), checked before the text.
export const MACHINE_ORIGINS = new Set(['task-notification', 'scheduled-trigger', 'peer', 'peer-send-message',
  'observer', 'observer-activity', 'projects-relay', 'coordinator'])

// ace_before_task.expand_abbreviations
export function expandAbbreviations(prompt: string): string {
  const rep: [string, string][] = [[' JWT ', ' JSON Web Token '], [' API ', ' REST API '], [' DB ', ' database '],
    [' env ', ' environment '], [' auth ', ' authentication '], [' config ', ' configuration '],
    [' deps ', ' dependencies '], [' repo ', ' repository ']]
  let r = ` ${prompt} `
  for (const [a, b] of rep) r = r.split(a).join(b)
  return r.trim()
}

// ---------- ace_domain_shift.match_domain_to_path ----------
export function matchDomainToPath(domain: string, path: string): boolean {
  const words = domain.toLowerCase().split(/[-\s]+/).filter(w => w.length >= 3)
  for (const seg of path.toLowerCase().split(/[/._\-\s]+/)) {
    if (seg.length < 3) continue
    for (const w of words) {
      let n = 0; while (n < w.length && n < seg.length && w[n] === seg[n]) n++
      if (seg === w || n >= 4) return true
    }
  }
  return false
}
export const domainNames = (domains: Record<string, unknown>) =>
  [...new Set(Object.keys(domains).map(k => k.split(':')[0].toLowerCase()))].sort()
export const basenameQuery = (p: string) => (p.replace(/\/+$/, '').split('/').pop() || '').replace(/\.[^.]*$/, '')

// ---------- ace_subagent_start ----------
// Workflow agents get a fixed harness preamble ending in this marker; it would make every query identical.
const WORKFLOW_MARKER = 'The computed task text follows:'
export function subagentQuery(prompt: string): string {
  const i = prompt.indexOf(WORKFLOW_MARKER)
  return cpSlice((i >= 0 ? prompt.slice(i + WORKFLOW_MARKER.length) : prompt).trim(), 500)
}
