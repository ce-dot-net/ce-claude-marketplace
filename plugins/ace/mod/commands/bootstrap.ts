import { type Cmd, type Kit, confirm } from './kit.ts'
import { cliIds } from '../context/index.ts'
const MODES = ['hybrid', 'both', 'local-files', 'git-history', 'docs-only'], LEVELS = ['light', 'medium', 'deep']
export const bootstrap: Cmd = { name: 'bootstrap', md: 'ace-bootstrap', description: 'Build the playbook from the codebase (preview + confirm)', argumentHint: '[mode] [thoroughness]', bound: true }
export async function bootstrapCmd($: any, { c, args }: Kit): Promise<string> {
    const [mode = 'hybrid', level = 'medium'] = args.trim().split(/\s+/).filter(Boolean)
    if (!MODES.includes(mode) || !LEVELS.includes(level)) return `Usage: /ace:ace-bootstrap [${MODES.join('|')}] [${LEVELS.join('|')}]`
    return confirm($, { label: 'Bootstrap starten', kind: 'cli', argv: ['bootstrap', '--json', '--mode', mode, '--thoroughness', level, '--repo-path', c.root, ...cliIds(c)],
      preview: `Bootstrap of ${c.root} into ${(c as any).projectId}: mode ${mode}, thoroughness ${level} (merges with the playbook)` })
}
