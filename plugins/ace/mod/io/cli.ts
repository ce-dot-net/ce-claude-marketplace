// One argv-only ace-cli spawn for the core and the commands: the pinned CLI head, the core's ids in the child env
// (never a leaked binding), stdout capped, a spawn failure / kill told apart from an answer. No shell, ever.
import { cliHead } from './spawn.ts'

export const OUT_CAP = 60_000  // probe 3: a command's output is capped at about 60 KB
export type CliResult = { exitCode: number | null, stdout: string, stderr: string, spawnError?: boolean, timeout?: boolean }
export async function cliRun($: any, c: { orgId?: string, projectId?: string } | null, argv: string[],
  o: { stdin?: string, timeoutMs?: number, cwd?: string, env?: Record<string, string> } = {}): Promise<CliResult> {
  const env: Record<string, string> = { ...(o.env ?? {}) }
  if (c?.orgId) env.ACE_ORG_ID = c.orgId
  if (c?.projectId) env.ACE_PROJECT_ID = c.projectId
  try {
    const r = await $.process.run([...await cliHead($), ...argv], { stdin: o.stdin, env, timeoutMs: o.timeoutMs ?? 30_000, ...(o.cwd ? { cwd: o.cwd } : {}) })
    return { exitCode: r.exitCode, stdout: String(r.stdout ?? ''), stderr: String(r.stderr ?? '') }
  } catch (err) {
    const m = String(err)
    return /ENOENT|not found|spawn/i.test(m) && !/timeout|still running/i.test(m)
      ? { exitCode: null, stdout: '', stderr: m.slice(0, 300), spawnError: true }
      : { exitCode: null, stdout: '', stderr: m.slice(0, 300), timeout: true }
  }
}
export const cap = (t: string, max = OUT_CAP) => (t.length > max ? t.slice(0, max) + `\n… ${t.length - max} Zeichen gekürzt` : t)
