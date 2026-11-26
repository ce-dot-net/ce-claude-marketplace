// The one command table (8.1.0). Every /ace:ace-<name> markdown command is answered here, model-free, wherever
// mods run (the markdown stays the fallback where they do not); `/ace` is the mod's own overview.
import { type Cmd, type Kit, approveOrHint, kitCli, unboundLine, cap } from './kit'
import { flagHint, stripApproved } from '../lib/approved'
import { refreshUnbound } from '../handlers/context'
import { localState, problemLine } from '../context/index'
import { type Load, dataRoot, resolveContextOnce } from '../io/state'
import { search, searchCmd } from './search'
import { patterns, patternsCmd } from './patterns'
import { top, topCmd } from './top'
import { status, statusCmd } from './status'
import { domains, domainsCmd } from './domains'
import { exportPatterns, exportPatternsCmd } from './export_patterns'
import { insights, insightsCmd } from './insights'
import { graph, graphCmd } from './graph'
import { doctor, doctorCmd } from './doctor'
import { test, testCmd } from './test'
import { cleanup, cleanupCmd } from './cleanup'
import { clear, clearCmd } from './clear'
import { delta, deltaCmd } from './delta'
import { importPatterns, importPatternsCmd } from './import_patterns'
import { learn, learnCmd } from './learn'
import { bootstrap, bootstrapCmd } from './bootstrap'
import { tune, tuneCmd } from './tune'
import { configure, configureCmd } from './configure'
import { login, loginCmd } from './login'
import { installCli, installCliCmd } from './install_cli'
import { bandAction } from '../ui/band'
import { authHeld } from '../io/auth'
import { AUTH_GUARDED, noAuthLine } from '../io/pending'

export const ace: Cmd = { name: 'ace', description: 'ACE overview: binding, state and every command' }
export async function aceCmd($: any, { c }: Kit): Promise<string> {
    const cc: any = c
    const head = cc.bound ? `ACE · ${cc.projectId} (org ${cc.orgId}) via ${cc.source}` : problemLine(localState(c), c)!
    return [head, '', ...COMMANDS.filter(x => x.name !== 'ace').map(x => `/ace:${x.md}${x.argumentHint ? ` ${x.argumentHint}` : ''}  ${x.description}`)].join('\n')
}

export const COMMANDS: Cmd[] = [ace, search, patterns, top, status, domains, exportPatterns, insights, graph, doctor, test, cleanup,
  clear, delta, importPatterns, learn, bootstrap, tune, configure, login, installCli]

// `ace` (no markdown twin) is registered; the rest answer their plugin markdown name `ace:ace-<name>`.
export function findCommand(command: string): Cmd | undefined {
  if (command === 'ace' || command === 'ace:ace') return ace
  const m = /^ace:(ace-[a-z-]+)$/.exec(command)
  return m ? COMMANDS.find(c => c.md === m[1]) : undefined
}
export async function registerCommands($: any) {
  await $.command.register({ name: 'ace', description: ace.description })
}
export async function runCommand($: any, L: Load, cmd: Cmd, args: string): Promise<string> {
  let c = await resolveContextOnce($, L, await $.session.root())
  if (!c.bound) { await refreshUnbound($, L, true); c = L.ctx ?? c }  // 8.2.7: a binding file written since: no restart needed
  const hint = flagHint(args ?? '')  // 8.2.7: a near miss of --approved is told, never acted on (after the cap: never cut)
  const withHint = (t: string) => hint ? `${t}\n${hint}` : t
  if (cmd.bound && !c.bound) return withHint(unboundLine(c))
  if (cmd.bound && localState(c)) return withHint(unboundLine(c))
  const a = stripApproved(args ?? '')  // 8.2.0: the standalone token never reaches a command
  // 8.4.2: a held token (io/auth.ts): the confirm-type writes answer one login line (no preview, no call, nothing pending);
  // the read-only tune (no args / show) stays allowed
  const readOnly = cmd.name === 'tune' && /^(show)?$/.test(a.args.trim())
  if (AUTH_GUARDED[cmd.name] && !readOnly && await authHeld($, { root: await dataRoot($) })) return withHint(noAuthLine(AUTH_GUARDED[cmd.name]!))
  const k: Kit = { c, args: a.args, cli: kitCli($, c), approved: a.approved }
  const before = ((await $.state.get({ plugin: 'ace', key: 'pending' })) as any).value
  try { return withHint(cap(await approveOrHint($, k, cmd, before, await dispatch($, cmd.name, k), p => bandAction($, L, p)))) } catch (err) { return `ACE ▼ ${cmd.name} failed: ${String(err).slice(0, 300)}` }
}

// A switch, not a table of functions: `$` reaches only function declarations (the mods loader's rule).
async function dispatch($: any, name: string, k: Kit): Promise<string> {
  switch (name) {
    case 'ace': return aceCmd($, k)
    case 'bootstrap': return bootstrapCmd($, k)
    case 'cleanup': return cleanupCmd($, k)
    case 'clear': return clearCmd($, k)
    case 'configure': return configureCmd($, k)
    case 'delta': return deltaCmd($, k)
    case 'doctor': return doctorCmd($, k)
    case 'domains': return domainsCmd($, k)
    case 'export-patterns': return exportPatternsCmd($, k)
    case 'graph': return graphCmd($, k)
    case 'import-patterns': return importPatternsCmd($, k)
    case 'insights': return insightsCmd($, k)
    case 'install-cli': return installCliCmd($, k)
    case 'learn': return learnCmd($, k)
    case 'login': return loginCmd($, k)
    case 'patterns': return patternsCmd($, k)
    case 'search': return searchCmd($, k)
    case 'status': return statusCmd($, k)
    case 'test': return testCmd($, k)
    case 'top': return topCmd($, k)
    case 'tune': return tuneCmd($, k)
  }
  return 'ACE ▼ unknown command'
}
