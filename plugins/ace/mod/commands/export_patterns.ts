import { type Cmd, type Kit, failLine } from './kit.ts'
export const exportPatterns: Cmd = { name: 'export-patterns', md: 'ace-export-patterns', description: 'Export the playbook to a JSON file', argumentHint: '[file]', bound: true }
export async function exportPatternsCmd($: any, { c, args, cli }: Kit): Promise<string> {
    const f = args.trim() || `ace-playbook-${(c as any).projectId}.json`
    if (/[\0\n]/.test(f)) return 'Usage: /ace:ace-export-patterns [file]'
    const out = f.startsWith('/') ? f : `${c.root}/${f}`
    const r = await cli(['export', '--output', out])
    return r.exitCode === 0 ? `Exported to ${out}` : failLine(r)
}
