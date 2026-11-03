import { type Cmd, type Kit, cap, failLine, json, oneLine } from './kit.ts'
export const patterns: Cmd = { name: 'patterns', md: 'ace-patterns', description: 'The playbook by section', argumentHint: '[section] [min-reward]', bound: true }
export async function patternsCmd($: any, { args, cli }: Kit): Promise<string> {
    const [section, min] = args.trim().split(/\s+/).filter(Boolean)
    const r = await cli(['patterns', '--json', ...(section ? ['--section', section] : []), ...(min ? ['--min-reward', min] : [])])
    if (r.exitCode !== 0) return failLine(r)
    const pb = json(r)?.playbook
    if (!pb || typeof pb !== 'object') return 'ACE ▼ unerwartete Antwort von ace-cli patterns'
    const out = Object.entries(pb).map(([sec, list]: any) => `## ${sec} (${(list ?? []).length})\n`
      + (list ?? []).map((p: any) => `- ${oneLine(p.content, 200)}  [reward ${p.cumulative_v15_reward ?? 0}]`).join('\n'))
    return cap(out.join('\n\n') || 'Empty playbook')
}
