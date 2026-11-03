import { type Cmd, type Kit } from './kit.ts'
import { python } from './py.ts'
// The id comes from the core; no newest-DB fallback (ace_graph_builder.resolve_graph_db).
export const graph: Cmd = { name: 'graph', md: 'ace-graph', description: 'Local knowledge graph of this project', argumentHint: '[min-weight]', bound: true }
export async function graphCmd($: any, { c, args }: Kit): Promise<string> {
    const w = args.trim()
    if (w && !/^\d+$/.test(w)) return 'Usage: /ace:ace-graph [min-weight]'
    return python($, 'utils/ace_graph_builder.py', ['--org', (c as any).orgId, '--project', (c as any).projectId, ...(w ? ['--min-weight', w] : [])], c.root)
}
