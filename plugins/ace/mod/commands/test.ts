import { type Cmd, type Kit, failLine, json } from './kit.ts'
import { cliRun } from '../io/cli.ts'
// Read-only round trip: CLI version, status, one search with --top-k 1.
export const test: Cmd = { name: 'test', md: 'ace-test', description: 'Read-only connectivity test', bound: true }
export async function testCmd($: any, { cli }: Kit): Promise<string> {
    const v = await cliRun($, null, ['--version'], { timeoutMs: 10_000 })
    if (v.exitCode !== 0) return `[1/3] ace-cli ✗\n${failLine(v)}`
    const s = await cli(['status', '--json'], { timeoutMs: 20_000 })
    if (s.exitCode !== 0) return `[1/3] ace-cli ✓ ${v.stdout.trim()}\n[2/3] status ✗\n${failLine(s)}`
    const q = await cli(['search', '--stdin', '--json', '--top-k', '1'], { stdin: 'ace plugin test', timeoutMs: 25_000 })
    return [`[1/3] ace-cli ✓ ${v.stdout.trim()}`, `[2/3] status ✓ ${json(s)?.playbook?.total_patterns ?? '?'} patterns`,
      q.exitCode === 0 ? `[3/3] search ✓ ${json(q)?.similar_patterns?.length ?? 0} result` : `[3/3] search ✗\n${failLine(q)}`].join('\n')
}
