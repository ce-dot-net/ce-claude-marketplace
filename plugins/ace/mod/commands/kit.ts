// What every model-free command gets: the core's binding, an argv-only CLI with the core's ids, the 60 KB cap,
// and the confirm step of the writing commands (a preview + one button in the band; nothing runs before the press).
import { type Ctx, classify, cliIds, problemLine, localState } from '../context/index.ts'
import { cap, cliRun, type CliResult } from '../io/cli.ts'
import { execExport, execPending } from '../io/pending.ts'
import type { AcePending } from '../types/index.d.ts'

const PENDING = { plugin: 'ace', key: 'pending' } as const
export type Kit = { c: Ctx, args: string, cli: (argv: string[], o?: { stdin?: string, timeoutMs?: number }) => Promise<CliResult>, approved?: boolean }
export type Cmd = { name: string, md?: string, description: string, argumentHint?: string, bound?: boolean }

export function kitCli($: any, c: Ctx) {
  return (argv: string[], o: { stdin?: string, timeoutMs?: number } = {}) => cliRun($, c as any, [...argv, ...cliIds(c)], { ...o, cwd: c.root })
}
// A failed CLI run as one line: classified by exit code + stderr, never stdout.
export function failLine(r: CliResult): string {
  const st = classify(r.exitCode, r.stderr, !!r.spawnError, !!r.timeout)
  const detail = String(r.stderr ?? '').split('\n').find(l => l.trim())?.slice(0, 200) ?? ''
  return (problemLine(st) ?? `ACE ▼ Fehler (exit ${r.exitCode})`) + (detail && st === 'server_error' ? `\n${detail}` : '')
}
export function unboundLine(c: Ctx) { return problemLine(localState(c) ?? 'unbound')! }
export function json(r: CliResult): any {
  try { return JSON.parse(r.stdout) } catch { return undefined }
}
export const CONFIRM_MARK = 'Noch nichts geändert.'
export async function confirm($: any, p: NonNullable<AcePending>): Promise<string> {
  await $.state.set(PENDING, p)
  $.ui.log(`ace pending ${JSON.stringify({ label: p.label, kind: p.kind, argv: p.argv, report: p.report, backfill: p.backfill })}`, { to: 'debug' })
  return `${p.preview}\n\n${CONFIRM_MARK} Bestätigen mit [${p.label}] über der Eingabe.`
}
// 8.2.0 `--approved`, the second half of confirm (runCommand calls it after every command, `before` = the pending that
// waited when the command began). A confirm text gets the exact line to type; with the token the action runs at once through the
// same executor as the button (io/pending.ts). clear and cleanup (destructive) run only when the IDENTICAL pending (label + argv) was
// already waiting; kinds that need the band (bind, clean, login, install) never run from a typed line.
const DESTRUCTIVE = ['clear', 'cleanup'], EXEC_KINDS = ['cli', 'exec', 'export']
const same = (a: any, b: any) => !!a && !!b && a.label === b.label && JSON.stringify(a.argv ?? null) === JSON.stringify(b.argv ?? null)
export async function approveOrHint($: any, k: Kit, cmd: Cmd, before: any, text: string): Promise<string> {
  if (!text.includes(CONFIRM_MARK)) return text
  const p: any = ((await $.state.get(PENDING)) as any).value
  if (!p) return text
  const line = `/ace:${cmd.md} ${k.args.trim()}`.trim() + ' --approved'
  if (!k.approved) return `${text}\nOder tippen: ${line}`
  if (!EXEC_KINDS.includes(p.kind)) return `${text}\n--approved gilt hier nicht: den Button [${p.label}] über der Eingabe benutzen.`
  if (DESTRUCTIVE.includes(cmd.name) && !same(before, p))
    return `${text}\n--approved löscht nur, wenn genau diese Vorschau schon wartet: erst die Vorschau prüfen, dann ${line} (oder den Button).`
  await $.state.set(PENDING, null)
  const d = p.kind === 'export' ? await execExport($, k.c, p.path) : await execPending($, k.c, p)
  return d.out ? `${d.toast}\n${d.out}` : d.toast
}
export { cap }
export const oneLine = (t: unknown, n = 160) => String(t ?? '').replace(/\s+/g, ' ').trim().slice(0, n)
export function patternLines(ps: any[]): string {
  return ps.map((p, i) => `${i + 1}. ${oneLine(p.content, 400)}\n   ${p.domain ?? '-'} · ${p.section ?? '-'} · reward ${p.cumulative_v15_reward ?? 0}`
    + (p.match_factors?.bandit_rank ?? p.bandit_rank ? ` · rank ${p.match_factors?.bandit_rank ?? p.bandit_rank}` : '')).join('\n')
}
