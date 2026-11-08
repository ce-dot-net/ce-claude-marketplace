import { type Cmd, type Kit, json } from './kit.ts'
import { classify, globalConfigPath, problemLine, readEnv } from '../context/index.ts'
import { cliRun } from '../io/cli.ts'
import { run } from '../io/fs.ts'
import { installer } from '../io/installer.ts'
import { dataRoot } from '../io/state.ts'
import { CLIENT_POLICY_FILE, clientPolicyLine } from '../lib/cohort.ts'
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
    const root = await dataRoot($), now = await $.clock.now()
    out.push(await deliveryLine($, root, `${c.root}/.claude/data/logs`, now))
    const manifest = await $.fs.read(`${$.plugin.root}/.claude-plugin/plugin.json`).then((t: string) => JSON.parse(t), () => null)
    const pol = clientPolicyLine(await $.fs.read(`${root}/${CLIENT_POLICY_FILE}`).catch(() => undefined), String(manifest?.version ?? ''), now)
    if (pol) out.push(pol)
    const py = await run($, [`${$.plugin.root}/scripts/ace-python`])  // the fallback hooks' interpreter (>= 3.10)
    out.push(py && py.exitCode === 0 ? `python   ✓ ${String(py.stdout).trim()}` : 'python   ✗ Python >= 3.10 needed for the fallback hooks; the mod chain is unaffected')
    const v = await cliRun($, null, ['--version'], { timeoutMs: 10_000 })
    out.push(v.exitCode === 0 ? `ace-cli  ✓ ${v.stdout.trim().split('\n')[0]}` : `ace-cli  ✗ ${problemLine('cli_missing')}`)
    const ai = await installer($, ['--status'], 15_000)  // 8.1.1: the background install of the pinned CLI
    out.push(`install  auto-install ${ai.state}${ai.detail ? ` (${ai.detail})` : ''}`)
    if (ai.sqlite) out.push(`SQLite cache: ${ai.sqlite}`)  // 8.1.2: off = RAM-only, never a band
    if (cc.bound && v.exitCode === 0) {
      const s = await cli(['status', '--json'], { timeoutMs: 20_000 })
      const st = classify(s.exitCode, s.stderr, !!s.spawnError, !!s.timeout)
      out.push(st === 'ok' ? `server   ✓ ${json(s)?.playbook?.total_patterns ?? '?'} patterns` : `server   ✗ ${problemLine(st)}`)
    }
    return out.join('\n')
}

// learn retries, failed learns, the context state/source mix, from the repo root's log and its rotation (.1);
// 8.1.3: the outcome rule of the newest execution row (pre-8.1.3 rows carry none)
export async function logCounts($: any, dir: string): Promise<string> {
  let retry = 0, failed = 0, rule: string | undefined
  const ctx: Record<string, number> = {}
  for (const f of ['ace-relevance.jsonl', 'ace-relevance.1.jsonl']) {
    let text = '', fileRule: string | undefined
    try { text = await $.fs.read(`${dir}/${f}`) as string } catch { continue }
    for (const line of text.split('\n')) {
      if (!line.includes('"event"')) continue
      let r: any
      try { r = JSON.parse(line) } catch { continue }
      if (r.event === 'learn_retry') retry++
      if (r.event === 'execution') fileRule = r.outcome_rule ?? 'pre-8.1.3'
      if (r.event === 'execution' && r.learning_sent === false) failed++
      else if (r.event === 'context') { const k = `${r.source}/${r.state}`; ctx[k] = (ctx[k] ?? 0) + 1 }
    }
    rule ??= fileRule
  }
  return `logs     learn retries ${retry} · failed learns ${failed} · binding ${Object.entries(ctx).map(([k, v]) => `${k} ${v}`).join(', ') || 'none'}` +
    (rule ? ` · outcome rule ${rule}` : '')
}

// 8.1.4 trace delivery (ace_trace_queue.doctor_line): queue depth and oldest entry, dead/ (kept 7 days), and the
// replayed/expired rows of the last 7 days from the repo root's log (+ .1).
export const ageText = (s: number) => s < 3600 ? `${Math.floor(s / 60)}m` : s < 86400 ? `${Math.floor(s / 3600)}h` : `${Math.floor(s / 86400)}d`
export async function deliveryLine($: any, root: string, logs: string, nowMs: number): Promise<string> {
  const q = `${root}/trace-queue`, now = nowMs / 1000
  const ages: number[] = []
  for (const d of [q, `${q}/inflight`]) {
    for (const f of (await $.fs.list(d).catch(() => [])) as any[]) {
      if (f.isLink || !f.name.endsWith('.json')) continue
      try { const e = JSON.parse(await $.fs.read(`${d}/${f.name}`)); if (typeof e.created_at === 'number') ages.push(now - e.created_at) } catch { /* skip */ }
    }
  }
  const dead = ((await $.fs.list(`${q}/dead`).catch(() => [])) as any[]).filter(f => f.name.endsWith('.json')).length
  let replayed = 0, expired = 0
  for (const f of ['ace-relevance.jsonl', 'ace-relevance.1.jsonl']) {
    let text = ''
    try { text = await $.fs.read(`${logs}/${f}`) as string } catch { continue }
    for (const line of text.split('\n')) {
      if (!line.includes('learn_replayed') && !line.includes('learn_expired')) continue
      try {
        const r = JSON.parse(line), t = Date.parse(r.timestamp) / 1000
        if (!(now - t < 7 * 86400)) continue
        if (r.event === 'learn_replayed') replayed++
        else if (r.event === 'learn_expired') expired++
      } catch { /* skip */ }
    }
  }
  return `delivery queue ${ages.length} · oldest ${ages.length ? ageText(Math.max(...ages)) : '-'} · 7d replayed ${replayed} · dead ${dead} · expired ${expired}`
}
