import { type Cmd, type Kit, failLine, json } from './kit.ts'
export const status: Cmd = { name: 'status', md: 'ace-status', description: 'Playbook statistics and the binding', bound: true }
export async function statusCmd($: any, { c, cli }: Kit): Promise<string> {
    const r = await cli(['status', '--json'])
    if (r.exitCode !== 0) return failLine(r)
    const pb = json(r)?.playbook ?? json(r) ?? {}
    const doms = Object.entries(pb.by_domain ?? {}).sort((a: any, b: any) => b[1] - a[1]).slice(0, 8).map(([k, v]) => `${k} ${v}`).join(', ')
    return [`ACE · ${(c as any).projectId} (org ${(c as any).orgId})`, `binding: ${(c as any).source}${(c as any).path ? ` · ${(c as any).path}` : ''}`,
      `patterns: ${pb.total_patterns ?? '?'}`, `sections: ${Object.entries(pb.by_section ?? {}).map(([k, v]) => `${k} ${v}`).join(', ') || '-'}`,
      `domains: ${doms || '-'}`].join('\n')
}
