// What every model-free command gets: the core's binding, an argv-only CLI with the core's ids, the 60 KB cap,
// and the confirm step of the writing commands (a preview + one button in the band; nothing runs before the press).
import { type Ctx, classify, cliIds, problemLine, localState } from '../context/index.ts'
import { cap, cliRun, type CliResult } from '../io/cli.ts'
import type { AcePending } from '../types/index.d.ts'

const PENDING = { plugin: 'ace', key: 'pending' } as const
export type Kit = { c: Ctx, args: string, cli: (argv: string[], o?: { stdin?: string, timeoutMs?: number }) => Promise<CliResult> }
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
export async function confirm($: any, p: NonNullable<AcePending>): Promise<string> {
  await $.state.set(PENDING, p)
  $.ui.log(`ace pending ${JSON.stringify({ label: p.label, kind: p.kind, argv: p.argv })}`, { to: 'debug' })
  return `${p.preview}\n\nNoch nichts geändert. Bestätigen mit [${p.label}] über der Eingabe.`
}
export { cap }
export const oneLine = (t: unknown, n = 160) => String(t ?? '').replace(/\s+/g, ' ').trim().slice(0, n)
export function patternLines(ps: any[]): string {
  return ps.map((p, i) => `${i + 1}. ${oneLine(p.content, 400)}\n   ${p.domain ?? '-'} · ${p.section ?? '-'} · reward ${p.cumulative_v15_reward ?? 0}`
    + (p.match_factors?.bandit_rank ?? p.bandit_rank ? ` · rank ${p.match_factors?.bandit_rank ?? p.bandit_rank}` : '')).join('\n')
}
