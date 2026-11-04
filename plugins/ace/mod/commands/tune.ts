import { type Cmd, type Kit, cap, confirm, failLine } from './kit.ts'
import { cliIds } from '../context/index.ts'
import { safeToken } from './paths.ts'
const KEYS = ['constitution-threshold', 'search-top-k', 'dedup-similarity-threshold', 'dedup-enabled', 'pruning-threshold', 'max-playbook-tokens',
  'token-budget-enforcement', 'max-batch-size', 'auto-learning-enabled', 'reflector-enabled', 'curator-enabled']
export const tune: Cmd = { name: 'tune', md: 'ace-tune', description: 'Show or change server settings (writes: preview + confirm)', argumentHint: '[show | key=value ...]', bound: true }
export async function tuneCmd($: any, { c, args, cli }: Kit): Promise<string> {
    const a = args.trim()
    if (!a || a === 'show') {
      const r = await cli(['tune', 'show', '--json'])
      return r.exitCode === 0 ? cap(r.stdout.trim()) : failLine(r)
    }
    const flags: string[] = []
    for (const kv of a.split(/\s+/)) {
      const m = /^([a-z-]+)=([^\s]+)$/.exec(kv)
      if (!m || !KEYS.includes(m[1]) || !safeToken(m[2])) return `Usage: /ace:ace-tune key=value ...  (keys: ${KEYS.join(', ')})`
      flags.push(`--${m[1]}`, m[2])
    }
    return confirm($, { label: 'Einstellungen schreiben', kind: 'cli', argv: ['tune', ...flags, ...cliIds(c)],
      preview: `Server settings for ${(c as any).projectId}:\n${a.split(/\s+/).map(x => `- ${x}`).join('\n')}` })
}
