// Runs a pending write exactly as the band's button does (ui/band.ts runPending) and as `--approved` does (commands/kit.ts):
// one executor, so the button and the typed line cannot drift apart. No band, no rebind: only the action and its result lines.
import { run } from './fs.ts'
import { cap, cliRun } from './cli.ts'
import { cliIds, repoWrite } from '../context/index.ts'
import { reportLine } from '../lib/reports.ts'

export type Done = { ok: boolean, toast: string, out: string }
// kind cli | exec. The result line: `<label> erledigt` / `fehlgeschlagen (exit N)`; out = the named report line, else stdout/stderr (2000 chars).
export async function execPending($: any, c: any, p: any): Promise<Done> {
  const r = p.kind === 'exec' ? await run($, p.argv, { timeoutMs: 30_000 }) : await cliRun($, c, p.argv, { stdin: p.stdin, timeoutMs: 300_000, cwd: c?.root })
  const ok = !!r && r.exitCode === 0
  const raw = String((ok ? r?.stdout : r?.stderr) ?? '').trim()
  const rep = ok && p.report ? reportLine(String(p.report), raw) : undefined
  return { ok, toast: `ACE: ${p.label} ${ok ? 'erledigt' : `fehlgeschlagen (exit ${r?.exitCode})`}`, out: rep ?? (raw ? cap(raw, 2000) : '') }
}
// export: stdout of `ace-cli export`, written inside the repo root through REPO_WRITE_SH (no symlink, never outside).
export async function execExport($: any, c: any, rel: string): Promise<Done> {
  const r = await cliRun($, c, ['export', ...cliIds(c)], { timeoutMs: 120_000, cwd: c.root })
  if (r.exitCode !== 0) return { ok: false, toast: `ACE: Export fehlgeschlagen (exit ${r.exitCode})`, out: '' }
  try { await repoWrite((argv, init) => run($, argv, init), c.root, rel, r.stdout) }
  catch (err) { return { ok: false, toast: `ACE: Export nicht geschrieben (${String((err as Error).message).slice(0, 120)})`, out: '' } }
  return { ok: true, toast: `ACE: exportiert nach ${c.root}/${rel}`, out: '' }
}
