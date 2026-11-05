import { type Cmd, type Kit, confirm } from './kit.ts'
import { cliRun } from '../io/cli.ts'
export const installCli: Cmd = { name: 'install-cli', md: 'ace-install-cli', description: 'The pinned ace-cli: show, or reinstall on a button press' }
export async function installCliCmd($: any, _k: Kit): Promise<string> {
    let pin = '?'
    try { pin = JSON.parse(await $.fs.read(`${$.plugin.root}/package.json`)).dependencies['@ace-sdk/cli'] } catch { /* below */ }
    const v = await cliRun($, null, ['--version'], { timeoutMs: 10_000 })
    if (v.exitCode === 0 && v.stdout.trim().includes(pin)) return `ace-cli ${v.stdout.trim()} (pinned ${pin}) ✓`
    return confirm($, { label: 'ace-cli installieren', kind: 'install',
      preview: `pinned ${pin}, found: ${v.exitCode === 0 ? v.stdout.trim() : 'none'}\nThe button runs the plugin's installer (npm ci --ignore-scripts && npm rebuild better-sqlite3) in ${$.plugin.root}; SessionStart does it by itself unless ACE_AUTO_INSTALL=0.` })
}
