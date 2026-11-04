import { type Cmd, type Kit } from './kit.ts'
import { python } from './py.ts'
export const insights: Cmd = { name: 'insights', md: 'ace-insights', description: 'Recap of the relevance log', argumentHint: '[hours]' }
export async function insightsCmd($: any, { c, args }: Kit): Promise<string> {
    const h = args.trim() || '24'
    if (!/^\d+$/.test(h)) return 'Usage: /ace:ace-insights [hours]'
    return python($, 'utils/ace_insights_analyzer.py', ['--mode', 'text', '--hours', h], c.root)
}
