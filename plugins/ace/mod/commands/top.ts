import { type Cmd, type Kit, cap, failLine, json, patternLines } from './kit.ts'
import { safeToken } from './paths.ts'
export const top: Cmd = { name: 'top', md: 'ace-top', description: 'Top-rated patterns', argumentHint: '[limit] [section]', bound: true }
export async function topCmd($: any, { args, cli }: Kit): Promise<string> {
    const [limit, section] = args.trim().split(/\s+/).filter(Boolean)
    if ((limit && !/^\d+$/.test(limit)) || (section && !safeToken(section))) return 'Usage: /ace:ace-top [limit] [section]'
    const r = await cli(['top', '--json', ...(limit ? ['--limit', limit] : []), ...(section ? ['--section', section] : [])])
    if (r.exitCode !== 0) return failLine(r)
    const j = json(r), ps = Array.isArray(j) ? j : j?.patterns ?? j?.top_patterns ?? []
    return ps.length ? cap(patternLines(ps)) : 'No patterns yet'
}
