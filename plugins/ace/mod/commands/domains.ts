import { type Cmd, type Kit, cap, failLine, json } from './kit.ts'
export const domains: Cmd = { name: 'domains', md: 'ace-domains', description: 'Pattern domains', argumentHint: '[min-patterns]', bound: true }
export async function domainsCmd($: any, { args, cli }: Kit): Promise<string> {
    const min = args.trim()
    if (min && !/^\d+$/.test(min)) return 'Usage: /ace:ace-domains [min-patterns]'
    const r = await cli(['domains', '--json', ...(min ? ['--min-patterns', min] : [])])
    if (r.exitCode !== 0) return failLine(r)
    const ds: any[] = json(r)?.domains ?? []
    return ds.length ? cap(ds.map(d => `${String(d.domain ?? d.name).padEnd(40)} ${d.count ?? d.pattern_count ?? ''}`).join('\n')) : 'No domains yet'
}
