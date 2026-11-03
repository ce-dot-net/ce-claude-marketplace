import { type Cmd, type Kit, json } from './kit.ts'
import { classify, globalConfigPath, problemLine } from '../context/index.ts'
import { cliRun } from '../io/cli.ts'
// Local checks plus one status call: binding (source, path, tried, warnings), CLI, auth/server, global projectId warning.
export const doctor: Cmd = { name: 'doctor', md: 'ace-doctor', description: 'Diagnose binding, CLI, login and server' }
export async function doctorCmd($: any, { c, cli }: Kit): Promise<string> {
    const out: string[] = []
    const cc: any = c
    out.push(cc.bound ? `binding  ✓ ${cc.projectId} (org ${cc.orgId}) via ${cc.source}${cc.path ? ` · ${cc.path}` : ''}`
      : `binding  ✗ ${cc.reason}${cc.path ? ` · ${cc.path}` : ''}`)
    if (!cc.bound && cc.tried) out.push('  tried: ' + cc.tried.map((t: any) => t.path ?? `${t.source}${t.key ? ` (${t.key})` : ''}`).join(', '))
    for (const w of cc.warnings ?? []) out.push(`warning  ${w === 'global_project_id_ignored'
      ? `global projectId in ${globalConfigPath({})} is ignored: bind each repo with .ace/config.json` : w}`)
    out.push(`log root ${c.root}`)
    const v = await cliRun($, null, ['--version'], { timeoutMs: 10_000 })
    out.push(v.exitCode === 0 ? `ace-cli  ✓ ${v.stdout.trim().split('\n')[0]}` : `ace-cli  ✗ ${problemLine('cli_missing')}`)
    if (cc.bound && v.exitCode === 0) {
      const s = await cli(['status', '--json'], { timeoutMs: 20_000 })
      const st = classify(s.exitCode, s.stderr, !!s.spawnError, !!s.timeout)
      out.push(st === 'ok' ? `server   ✓ ${json(s)?.playbook?.total_patterns ?? '?'} patterns` : `server   ✗ ${problemLine(st)}`)
    }
    return out.join('\n')
}
