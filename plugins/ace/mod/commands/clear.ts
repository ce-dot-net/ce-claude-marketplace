import { type Cmd, type Kit, confirm, failLine, json } from './kit.ts'
import { cliIds } from '../context/index.ts'
export const clear: Cmd = { name: 'clear', md: 'ace-clear', description: 'Clear the playbook (preview + confirm)', bound: true }
export async function clearCmd($: any, { c, cli }: Kit): Promise<string> {
    const s = await cli(['status', '--json'])
    if (s.exitCode !== 0) return failLine(s)
    const n = json(s)?.playbook?.total_patterns ?? '?'
    return confirm($, { label: 'Playbook leeren', kind: 'cli', argv: ['clear', '--yes', ...cliIds(c)],
      preview: `Clears ALL ${n} patterns of project ${(c as any).projectId} (org ${(c as any).orgId}) on the server. This cannot be undone.` })
}
