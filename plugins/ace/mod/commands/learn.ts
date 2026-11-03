import { type Cmd, type Kit, confirm } from './kit.ts'
import { cliIds } from '../context/index.ts'
export const learn: Cmd = { name: 'learn', md: 'ace-learn', description: 'Send one lesson (preview + confirm)', argumentHint: '<lesson>', bound: true }
export async function learnCmd($: any, { c, args }: Kit): Promise<string> {
    const t = args.trim()
    if (!t) return 'Usage: /ace:ace-learn <what was learned>'
    return confirm($, { label: 'Lernen senden', kind: 'cli', argv: ['learn', `--task=${t.slice(0, 500)}`, `--output=${t}`, '--success', '--no-stream', '--json', ...cliIds(c)],
      preview: `Sends to ${(c as any).projectId}:\n${t.slice(0, 2000)}` })
}
