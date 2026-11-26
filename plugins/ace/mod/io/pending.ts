// Runs a pending write exactly as the band's button does (ui/band.ts runPending) and as `--approved` does (commands/kit.ts):
// one executor, so the button and the typed line cannot drift apart. No band, no rebind: only the action and its result lines.
import { run } from './fs'
import { cap, cliRun } from './cli'
import { classify, cliIds, repoWrite } from '../context/index'
import { backfillPhase } from './backfill_io'
import { reportLine } from '../lib/reports'
import { authHeld, holdAuth } from './auth'
import { dataRoot } from './state'

export const BOOT_NO_AUTH = 'ACE: Bootstrap nicht gestartet: nicht angemeldet, bitte /ace:ace-login ausführen.'
// 8.4.2: every confirm-type CLI call behind the auth hold (command name -> ace-cli subcommand); one login line while held
export const AUTH_GUARDED: Record<string, string> = { bootstrap: 'bootstrap', clear: 'clear', delta: 'delta', 'import-patterns': 'import', learn: 'learn', tune: 'tune' }
export const noAuthLine = (sub: string) => sub === 'bootstrap' ? BOOT_NO_AUTH : `ACE: ${sub} nicht ausgeführt: nicht angemeldet, bitte /ace:ace-login ausführen.`

export type Done = { ok: boolean, toast: string, out: string }
// kind cli | exec. The result line: `<label> erledigt` / `fehlgeschlagen (exit N)`; out = the named report line, else stdout/stderr (2000 chars).
export async function execPending($: any, c: any, p: any): Promise<Done> {
  const only = p.kind === 'cli' && p.backfill?.only === true  // --backfill-only: the legacy CLI bootstrap never runs
  const sub = p.kind === 'cli' && Object.values(AUTH_GUARDED).includes(p.argv?.[0]) ? p.argv[0] as string : null, root = { root: await dataRoot($) }
  if (sub && await authHeld($, root)) return { ok: false, toast: noAuthLine(sub), out: '' }  // 8.4.1/8.4.2: a pending pressed after the hold
  const r = only ? null : p.kind === 'exec' ? await run($, p.argv, { timeoutMs: 30_000 }) : await cliRun($, c, p.argv, { stdin: p.stdin, timeoutMs: 300_000, cwd: c?.root })
  const ok = only || (!!r && r.exitCode === 0)
  if (sub && r && !ok && ['not_logged_in', 'expired'].includes(classify(r.exitCode, r.stderr ?? ''))) await holdAuth($, root)  // 8.4.1: its 401 holds the token (exit code + stderr, never stdout)
  const raw = String((ok ? r?.stdout : r?.stderr) ?? '').trim()
  const rep = ok && p.report ? reportLine(String(p.report), raw) : undefined
  let out = rep ?? (raw ? cap(raw, 2000) : '')
  if (p.backfill && p.kind === 'cli') {  // 8.2.0: dormant until the server flag; never lets a backfill problem fail the bootstrap result
    const bf = await backfillPhase($, c, p.backfill).catch(err => [`Backfill: Fehler ${String(err).slice(0, 160)}`])
    out = [out, ...bf].filter(Boolean).join('\n')
  }
  return { ok, toast: only ? `ACE: ${p.label}` : `ACE: ${p.label} ${ok ? 'erledigt' : `fehlgeschlagen (exit ${r?.exitCode})`}`, out }
}
// export: stdout of `ace-cli export`, written inside the repo root through REPO_WRITE_SH (no symlink, never outside).
export async function execExport($: any, c: any, rel: string): Promise<Done> {
  const r = await cliRun($, c, ['export', ...cliIds(c)], { timeoutMs: 120_000, cwd: c.root })
  if (r.exitCode !== 0) return { ok: false, toast: `ACE: Export fehlgeschlagen (exit ${r.exitCode})`, out: '' }
  try { await repoWrite((argv, init) => run($, argv, init), c.root, rel, r.stdout) }
  catch (err) { return { ok: false, toast: `ACE: Export nicht geschrieben (${String((err as Error).message).slice(0, 120)})`, out: '' } }
  return { ok: true, toast: `ACE: exportiert nach ${c.root}/${rel}`, out: '' }
}
