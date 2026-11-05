// The pinned plugin-local ace-cli installer (8.1.1): ONE implementation, shared-hooks/utils/ace_cli_installer.py.
// Every caller here (the quiet SessionStart window, the band's [Erneut versuchen], /ace:ace-install-cli) only spawns it.
import { python } from '../commands/py.ts'

export type Inst = { state: 'ok' | 'started' | 'running' | 'failed' | 'off' | 'unavailable' | string, detail: string }
// args: --ensure (start in the background when due) | --wait (ensure, then block until done) | --run (install now) | --status
export async function installer($: any, args: string[], timeoutMs = 60_000): Promise<Inst> {
  const out = await python($, 'utils/ace_cli_installer.py', args, $.plugin.root, timeoutMs)
  try {
    const j = JSON.parse(out.trim().split('\n').pop() ?? '')
    return { state: String(j.state), detail: String(j.detail ?? '') }
  } catch { return { state: 'unavailable', detail: out.slice(0, 160) } }
}
