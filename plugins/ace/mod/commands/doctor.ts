import { type Cmd, type Kit, json } from './kit.ts'
import { classify, globalConfigPath, problemLine, readEnv } from '../context/index.ts'
import { cliRun } from '../io/cli.ts'
import { run } from '../io/fs.ts'
// Local checks plus one status call: binding (source, path, tried, warnings), CLI, auth/server, global projectId warning.
export const doctor: Cmd = { name: 'doctor', md: 'ace-doctor', description: 'Diagnose binding, CLI, login and server' }
export async function doctorCmd($: any, { c, cli }: Kit): Promise<string> {
    const out: string[] = []
    const cc: any = c
    out.push(cc.bound ? `binding  ✓ ${cc.projectId} (org ${cc.orgId}) via ${cc.source}${cc.path ? ` · ${cc.path}` : ''}`
      : `binding  ✗ ${cc.reason}${cc.path ? ` · ${cc.path}` : ''}`)
    if (!cc.bound && cc.tried) out.push('  tried: ' + cc.tried.map((t: any) => t.path ?? `${t.source}${t.key ? ` (${t.key})` : ''}`).join(', '))
    const env = await readEnv($)
    const g = globalConfigPath(env), gpath = env.HOME && g.startsWith(env.HOME + '/') ? '~' + g.slice(env.HOME.length) : g
    for (const w of cc.warnings ?? []) out.push(`warning  ${w === 'global_project_id_ignored'
      ? `global projectId in ${gpath} is ignored: bind each repo with .ace/config.json` : w}`)
    out.push(`log root ${c.root}`)
    out.push(await logCounts($, `${c.root}/.claude/data/logs`))
    const py = await run($, [`${$.plugin.root}/scripts/ace-python`])  // the fallback hooks' interpreter (>= 3.10)
    out.push(py && py.exitCode === 0 ? `python   ✓ ${String(py.stdout).trim()}` : 'python   ✗ Python >= 3.10 needed for the fallback hooks; the mod chain is unaffected')
    const v = await cliRun($, null, ['--version'], { timeoutMs: 10_000 })
    out.push(v.exitCode === 0 ? `ace-cli  ✓ ${v.stdout.trim().split('\n')[0]}` : `ace-cli  ✗ ${problemLine('cli_missing')}`)
    if (cc.bound && v.exitCode === 0) {
      const s = await cli(['status', '--json'], { timeoutMs: 20_000 })
      const st = classify(s.exitCode, s.stderr, !!s.spawnError, !!s.timeout)
      out.push(st === 'ok' ? `server   ✓ ${json(s)?.playbook?.total_patterns ?? '?'} patterns` : `server   ✗ ${problemLine(st)}`)
    }
    return out.join('\n')
}

// learn retries, failed learns, the context state/source mix, from the repo root's log and its rotation (.1)
export async function logCounts($: any, dir: string): Promise<string> {
  let retry = 0, failed = 0
  const ctx: Record<string, number> = {}
  for (const f of ['ace-relevance.jsonl', 'ace-relevance.1.jsonl']) {
    let text = ''
    try { text = await $.fs.read(`${dir}/${f}`) as string } catch { continue }
    for (const line of text.split('\n')) {
      if (!line.includes('"event"')) continue
      let r: any
      try { r = JSON.parse(line) } catch { continue }
      if (r.event === 'learn_retry') retry++
      else if (r.event === 'execution' && r.learning_sent === false) failed++
      else if (r.event === 'context') { const k = `${r.source}/${r.state}`; ctx[k] = (ctx[k] ?? 0) + 1 }
    }
  }
  return `logs     learn retries ${retry} · failed learns ${failed} · binding ${Object.entries(ctx).map(([k, v]) => `${k} ${v}`).join(', ') || 'none'}`
}
