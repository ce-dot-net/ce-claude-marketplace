import { type Cmd, type Kit, confirm, json } from './kit.ts'
import { cliIds } from '../context/index.ts'
import { run } from '../io/fs.ts'
import { parseBootstrapArgs } from '../lib/bootstrap_args.ts'
export const bootstrap: Cmd = { name: 'bootstrap', md: 'ace-bootstrap', description: 'Build the playbook from the codebase (preview + confirm)', argumentHint: '[mode] [thoroughness] | --mode X --thoroughness Y', bound: true }
const DAYS: Record<string, number> = { light: 30, medium: 90, deep: 180 }  // the CLI's git window per level (--days-back overrides)

// Local, read-only facts of the repo for the preview: argv-only git, a failure is "unbekannt", never an error.
async function gitOut($: any, root: string, ...a: string[]): Promise<string | null> {
  const r = await run($, ['git', '-C', root, ...a], { timeoutMs: 15_000 })
  return r && r.exitCode === 0 ? String(r.stdout ?? '') : null
}
async function facts($: any, root: string, days: number, cli: Kit['cli']): Promise<{ lines: string[], commits: number | null, patterns: number | null }> {
  const files = (await gitOut($, root, 'ls-files'))?.split('\n').filter(Boolean) ?? null
  const cnt = await gitOut($, root, 'rev-list', '--count', `--since=${days} days ago`, 'HEAD')
  const commits = cnt !== null && /^\d+$/.test(cnt.trim()) ? Number(cnt.trim()) : null
  const st = await cli(['status', '--json']).catch(() => null)
  const total = st && st.exitCode === 0 ? json(st)?.playbook?.total_patterns : undefined
  const patterns = typeof total === 'number' ? total : null
  const lines: string[] = []
  if (files) {
    const ext = new Map<string, number>()
    for (const f of files) { const m = /\.([A-Za-z0-9]+)$/.exec(f.split('/').pop()!); const e = m ? m[1].toLowerCase() : '-'; ext.set(e, (ext.get(e) ?? 0) + 1) }
    const top = [...ext].sort((a, b) => b[1] - a[1] || (a[0] < b[0] ? -1 : 1)).slice(0, 5).map(([e, n]) => `${e} ${n}`).join(', ')
    lines.push(`Dateien: ${files.length} Dateien (${top})`)
    const root1 = ['CLAUDE.md', 'README.md', 'ARCHITECTURE.md'].filter(n => files.includes(n))
    const dd = files.filter(f => /^docs\/[^/]+\.md$/.test(f)).length
    const docs = [...root1, ...(dd ? [`docs/*.md (${dd})`] : [])]
    lines.push(`Docs: ${docs.length ? docs.join(', ') : 'keine gefunden'}`)
  } else lines.push('Dateien: unbekannt (kein Git-Repo?)', 'Docs: unbekannt')
  lines.push(`Commits: ${commits === null ? 'unbekannt' : `${commits} Commits`} in ${days} Tagen`)
  lines.push(`Playbook jetzt: ${patterns === null ? 'unbekannt' : `${patterns} Patterns`}`)
  return { lines, commits, patterns }
}
// What really leaves the machine (CLI services/initialization.js, commands/bootstrap.js): the first 50 source files with function
// bodies, up to 20 docs and commit diffs, as text blocks, without redaction.
function leaveLine(mode: string | undefined): string {
  if (mode === 'docs-only') return 'Hinweis: bis zu 20 Docs gehen unredigiert an den ACE-Server, kein Quellcode.'
  if (mode === 'git-history') return 'Hinweis: Commit-Nachrichten und Diffs gehen unredigiert an den ACE-Server, keine Quelldateien.'
  return 'Achtung: Quellcode-Funktionskörper (erste 50 Quelldateien), Docs (bis 20) und Commit-Diffs gehen unredigiert an den ACE-Server.'
}

export async function bootstrapCmd($: any, { c, args, cli }: Kit): Promise<string> {
    const a = parseBootstrapArgs(args)
    if (!a.ok) return a.usage
    const days = Number(a.flags[a.flags.indexOf('--days-back') + 1]) || (a.level ? DAYS[a.level] : 90)
    const f = await facts($, c.root, days, cli)
    const warn = [leaveLine(a.mode)]
    if (f.patterns !== null && f.patterns >= 100) warn.push(`Playbook hat schon ${f.patterns} Patterns: Online-Lernen ist meist besser.`)
    if (f.commits !== null && f.commits < 20) warn.push(`Nur ${f.commits} Commits im Fenster: Online-Lernen ist meist besser.`)
    const argv = ['bootstrap', '--json', ...(a.mode ? ['--mode', a.mode] : []), ...(a.level ? ['--thoroughness', a.level] : []), ...a.flags, '--repo-path', c.root, ...cliIds(c)]
    return confirm($, { label: 'Bootstrap starten', kind: 'cli', argv, report: 'bootstrap',
      preview: [`Bootstrap von ${c.root} in ${(c as any).projectId}: Modus ${a.mode ?? 'Standard des Servers'}, Tiefe ${a.level ?? 'Standard des Servers'} (merged mit dem Playbook)`,
        ...f.lines, ...warn].join('\n') })
}
