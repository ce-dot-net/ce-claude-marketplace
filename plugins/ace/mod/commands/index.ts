// The one command table (8.1.0). Every /ace:ace-<name> markdown command is answered here, model-free, wherever
// mods run (the markdown stays the fallback where they do not); `/ace` is the mod's own overview.
import { type Cmd, type Kit, approveOrHint, kitCli, unboundLine, cap } from './kit.ts'
import { stripApproved } from '../lib/approved.ts'
import { localState, problemLine } from '../context/index.ts'
import { type Load, resolveContextOnce } from '../io/state.ts'
import { search, searchCmd } from './search.ts'
import { patterns, patternsCmd } from './patterns.ts'
import { top, topCmd } from './top.ts'
import { status, statusCmd } from './status.ts'
import { domains, domainsCmd } from './domains.ts'
import { exportPatterns, exportPatternsCmd } from './export_patterns.ts'
import { insights, insightsCmd } from './insights.ts'
import { graph, graphCmd } from './graph.ts'
import { doctor, doctorCmd } from './doctor.ts'
import { test, testCmd } from './test.ts'
import { cleanup, cleanupCmd } from './cleanup.ts'
import { clear, clearCmd } from './clear.ts'
import { delta, deltaCmd } from './delta.ts'
import { importPatterns, importPatternsCmd } from './import_patterns.ts'
import { learn, learnCmd } from './learn.ts'
import { bootstrap, bootstrapCmd } from './bootstrap.ts'
import { tune, tuneCmd } from './tune.ts'
import { configure, configureCmd } from './configure.ts'
import { login, loginCmd } from './login.ts'
import { installCli, installCliCmd } from './install_cli.ts'

export const ace: Cmd = { name: 'ace', description: 'ACE overview: binding, state and every command' }
export async function aceCmd($: any, { c }: Kit): Promise<string> {
    const cc: any = c
    const head = cc.bound ? `ACE · ${cc.projectId} (org ${cc.orgId}) via ${cc.source}` : problemLine(localState(c))!
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
  const c = await resolveContextOnce($, L, await $.session.root())
  if (cmd.bound && !c.bound) return unboundLine(c)
  if (cmd.bound && localState(c)) return unboundLine(c)
  const a = stripApproved(args ?? '')  // 8.2.0: the standalone token never reaches a command
  const k: Kit = { c, args: a.args, cli: kitCli($, c), approved: a.approved }
  const before = ((await $.state.get({ plugin: 'ace', key: 'pending' })) as any).value
  try { return cap(await approveOrHint($, k, cmd, before, await dispatch($, cmd.name, k))) } catch (err) { return `ACE ▼ ${cmd.name} failed: ${String(err).slice(0, 300)}` }
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
