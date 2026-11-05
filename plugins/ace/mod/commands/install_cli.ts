import { type Cmd, type Kit, confirm } from './kit.ts'
import { cliRun } from '../io/cli.ts'
import { installer } from '../io/installer.ts'
export const installCli: Cmd = { name: 'install-cli', md: 'ace-install-cli', description: 'The pinned ace-cli: show, or reinstall on a button press' }
export async function installCliCmd($: any, _k: Kit): Promise<string> {
    let pin = '?'
    try { pin = JSON.parse(await $.fs.read(`${$.plugin.root}/package.json`)).dependencies['@ace-sdk/cli'] } catch { /* below */ }
    const v = await cliRun($, null, ['--version'], { timeoutMs: 10_000 })
    const found = v.exitCode === 0 ? v.stdout.trim() : 'none'
    if (v.exitCode === 0 && found.includes(pin)) {
      const st = await installer($, ['--status'], 15_000)
      if (!st.sqlite || st.sqlite === 'active' || st.sqlite.startsWith('off (better-sqlite3 not installed')) return `ace-cli ${found} (pinned ${pin}) ✓`
      return confirm($, { label: 'SQLite-Cache reparieren', kind: 'install',
        preview: `ace-cli ${found} (pinned ${pin}) ✓, but the SQLite cache is ${st.sqlite}\nThe button runs only \`npm rebuild better-sqlite3\` in ${$.plugin.root} and nothing else; SessionStart does it by itself unless ACE_AUTO_INSTALL=0.` })
    }
    return confirm($, { label: 'ace-cli installieren', kind: 'install',
      preview: `pinned ${pin}, found: ${found}\nThe button runs the plugin's installer (npm ci --ignore-scripts && npm rebuild better-sqlite3) in ${$.plugin.root}; SessionStart does it by itself unless ACE_AUTO_INSTALL=0.` })
}
