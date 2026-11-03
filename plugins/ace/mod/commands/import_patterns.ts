import { type Cmd, type Kit, confirm } from './kit.ts'
import { cliIds } from '../context/index.ts'
import { insideRoot } from './paths.ts'
export const importPatterns: Cmd = { name: 'import-patterns', md: 'ace-import-patterns', description: 'Import a playbook JSON (preview + confirm)', argumentHint: '<file>', bound: true }
export async function importPatternsCmd($: any, { c, args }: Kit): Promise<string> {
    const f = args.trim()
    if (!f) return 'Usage: /ace:ace-import-patterns <file>'
    const chk = await insideRoot($, c.root, f)  // never read (and upload) a file outside the repo
    if (!chk.ok) return `ACE ▼ import refused: ${chk.why}`
    const path = chk.abs
    let pb: any
    try { pb = JSON.parse(await $.fs.read(path)) } catch { return `ACE ▼ ${path} is not a readable JSON file` }
    const secs = pb?.playbook ?? pb
    const n = secs && typeof secs === 'object' ? Object.values(secs).reduce((a: number, v: any) => a + (Array.isArray(v) ? v.length : 0), 0) : 0
    return confirm($, { label: 'Import starten', kind: 'cli', argv: ['import', '--file', path, ...cliIds(c)],
      preview: `Imports ${n} patterns from ${path} into ${(c as any).projectId}` })
}
