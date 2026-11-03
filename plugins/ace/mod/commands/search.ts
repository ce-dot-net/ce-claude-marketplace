import { type Cmd, type Kit, cap, failLine, json, patternLines } from './kit.ts'
export const search: Cmd = { name: 'search', md: 'ace-search', description: 'Semantic search in the ACE playbook', argumentHint: '<query>', bound: true }
export async function searchCmd($: any, { args, cli }: Kit): Promise<string> {
    const q = args.trim()
    if (!q) return 'Usage: /ace:ace-search <query>'
    const r = await cli(['search', '--stdin', '--json'], { stdin: q })  // the query on stdin: never an argv the CLI could parse
    if (r.exitCode !== 0) return failLine(r)
    const ps = json(r)?.similar_patterns
    if (!Array.isArray(ps)) return 'ACE ▼ unerwartete Antwort von ace-cli search'
    return ps.length ? cap(`${ps.length} patterns for "${q.slice(0, 80)}"\n\n${patternLines(ps)}`) : `No patterns for "${q.slice(0, 80)}"`
}
