import { type Cmd, type Kit, confirm } from './kit.ts'
import { cliIds } from '../context/index.ts'
export const delta: Cmd = { name: 'delta', md: 'ace-delta', description: 'Add, update or remove patterns (preview + confirm)', argumentHint: '<add|update|remove> <json>', bound: true }
export async function deltaCmd($: any, { c, args }: Kit): Promise<string> {
    const m = /^\s*(add|update|remove)\s+([\s\S]+)$/.exec(args)
    if (!m) return 'Usage: /ace:ace-delta <add|update|remove> <bullets JSON>'
    let bullets: any
    try { bullets = JSON.parse(m[2]) } catch { return 'ACE ▼ the bullets are not valid JSON' }
    const list = Array.isArray(bullets) ? bullets : [bullets]
    return confirm($, { label: `delta ${m[1]} senden`, kind: 'cli', argv: ['delta', m[1], '--stdin', '--json', ...cliIds(c)], stdin: JSON.stringify(list),
      preview: `delta ${m[1]}: ${list.length} bullet(s) for ${(c as any).projectId}\n${JSON.stringify(list, null, 2).slice(0, 4000)}` })
}
