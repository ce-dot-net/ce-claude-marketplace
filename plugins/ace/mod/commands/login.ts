import { type Cmd, type Kit, confirm } from './kit.ts'
import { classify, problemLine } from '../context/index.ts'
import { cliRun } from '../io/cli.ts'
// Shows the login state. A device login starts only on the button press, never by itself.
export const login: Cmd = { name: 'login', md: 'ace-login', description: 'Login state; device login on a button press' }
export async function loginCmd($: any, { c }: Kit): Promise<string> {
    const cc: any = c
    const s = cc.bound ? await cliRun($, cc, ['status', '--json', '--org', cc.orgId, '--project', cc.projectId], { timeoutMs: 20_000 }) : null
    const st = s ? classify(s.exitCode, s.stderr, !!s.spawnError, !!s.timeout) : null
    if (st === 'ok') return 'ACE · logged in, the server answers.'
    return confirm($, { label: 'Anmelden (Browser)', kind: 'login',
      preview: `${st ? problemLine(st) : 'ACE · login state unknown (repo not bound)'}\nThe button starts the device login (opens the browser).` })
}
