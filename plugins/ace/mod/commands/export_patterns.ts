import { type Cmd, type Kit, confirm } from './kit.ts'
import { insideRoot } from './paths.ts'
// The export is a write: a path inside the repo root only (no symlink, realpath checked), a preview, the button.
// The press runs `ace-cli export` to stdout and writes the file through REPO_WRITE_SH (atomic, symlink-refusing).
export const exportPatterns: Cmd = { name: 'export-patterns', md: 'ace-export-patterns', description: 'Export the playbook to a JSON file in the repo (preview + confirm)', argumentHint: '[file]', bound: true }
export async function exportPatternsCmd($: any, { c, args }: Kit): Promise<string> {
  const p = await insideRoot($, c.root, args.trim() || `ace-playbook-${(c as any).projectId}.json`)
  if (!p.ok) return `ACE ▼ export refused: ${p.why}`
  return confirm($, { label: p.exists ? 'Exportieren (überschreibt)' : 'Exportieren', kind: 'export', path: p.rel,
    preview: `Exports the playbook of ${(c as any).projectId} to ${p.abs}${p.exists ? '\nThe file exists and will be OVERWRITTEN.' : ''}` })
}
