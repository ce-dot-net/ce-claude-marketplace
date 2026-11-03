// The plugin's Python helpers as argv-only spawns (the same python the hooks use).
import { readText } from '../io/fs.ts'
import { dataRoot } from '../io/state.ts'
import { cap } from '../io/cli.ts'

export async function python($: any, script: string, args: string[], cwd: string, timeoutMs = 60_000): Promise<string> {
  const py = (await readText($, `${await dataRoot($)}/python_path`))?.trim() || 'python3'
  try {
    const r = await $.process.run([py, `${$.plugin.root}/shared-hooks/${script}`, ...args], { cwd, timeoutMs })
    const out = String(r.stdout ?? '').trim()
    return cap(r.exitCode === 0 ? out || '(no output)' : `exit ${r.exitCode}\n${out}\n${String(r.stderr ?? '').trim().slice(0, 500)}`)
  } catch (err) { return `ACE ▼ python failed: ${String(err).slice(0, 200)}` }
}
