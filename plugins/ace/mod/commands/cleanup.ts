import { type Cmd, type Kit, confirm } from './kit.ts'
// Rotated relevance logs and v7 leftovers older than N days in <log root>/.claude/data/logs; preview, then the button.
export const CLEANUP_NAMES = ['ace-relevance.1.jsonl', 'ace-relevance.2.jsonl', 'ace-relevance.3.jsonl']
export const cleanup: Cmd = { name: 'cleanup', md: 'ace-cleanup', description: 'Delete rotated ACE logs (preview + confirm)', argumentHint: '[days]' }
export async function cleanupCmd($: any, { c, args }: Kit): Promise<string> {
    const days = args.trim() || '7'
    if (!/^\d+$/.test(days)) return 'Usage: /ace:ace-cleanup [days]'
    const dir = `${c.root}/.claude/data/logs`
    const now = await $.clock.now()
    const list: any[] = await $.fs.list(dir).catch(() => [])
    const old = list.filter(f => !f.isLink && (CLEANUP_NAMES.includes(f.name) || /^ace-(posttooluse|stop|errors).*\.jsonl$/.test(f.name))
      && now - (f.mtimeMs ?? now) > Number(days) * 86_400_000).map(f => `${dir}/${f.name}`)
    if (!old.length) return `Nothing older than ${days} days in ${dir}`
    return confirm($, { label: `${old.length} Dateien löschen`, kind: 'exec', argv: ['rm', '-f', '--', ...old],
      preview: `Would delete:\n${old.map(f => `- ${f}`).join('\n')}` })
}
