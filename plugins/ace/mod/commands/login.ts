import { type Cmd, type Kit, confirm } from './kit'
import { classify, problemLine } from '../context/index'
import { cliRun } from '../io/cli'
// Shows the login state. A device login starts only on the button press, never by itself.
export const login: Cmd = { name: 'login', md: 'ace-login', description: 'Login state; device login (no browser) on a button press or --approved' }
export async function loginCmd($: any, { c }: Kit): Promise<string> {
    const cc: any = c
    const s = cc.bound ? await cliRun($, cc, ['status', '--json', '--org', cc.orgId, '--project', cc.projectId], { timeoutMs: 20_000 }) : null
    const st = s ? classify(s.exitCode, s.stderr, !!s.spawnError, !!s.timeout) : null
    if (st === 'ok') return 'ACE · logged in, the server answers.'
    return confirm($, { label: 'Anmelden', kind: 'login',
      preview: `${st ? problemLine(st) : 'ACE · login state unknown (repo not bound)'}\nThe button starts the device login: the URL and the code are shown here (no browser needed, works over SSH). Or type: /ace:ace-login --approved` })
}
