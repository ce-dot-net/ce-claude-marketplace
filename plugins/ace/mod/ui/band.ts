// The AbovePrompt band (8.1.0): nothing when ok; a pending write's ONE confirm button; else exactly one action per
// problem state (unbound -> Verbinden, login states -> Anmelden, not_found/no_access -> Anderes wählen,
// config_refused -> Bereinigt neu schreiben, cli_missing -> installieren). Every action runs only on its press.
import { startContext } from '../handlers/context.ts'
import { type Ctx, writeBinding, WriteRefused } from '../context/index.ts'
import { run } from '../io/fs.ts'
import { cliRun, cap } from '../io/cli.ts'
import { type Load } from '../io/state.ts'

const BAND = { plugin: 'ace', key: 'band' } as const
const PENDING = { plugin: 'ace', key: 'pending' } as const
export const ACTION: Record<string, string | undefined> = { unbound: 'Verbinden', not_logged_in: 'Anmelden', expired: 'Anmelden',
  project_not_found: 'Anderes wählen', no_access: 'Anderes wählen', config_refused: 'Bereinigt neu schreiben', cli_missing: 'ace-cli installieren' }

async function rebind($: any, L: Load, cwd: string) {
  L.ctx = undefined; L.sess = null; L.ctxLogged = false
  await startContext($, L, cwd)
}
export async function bindTo($: any, L: Load, orgId: string, projectId: string) {
  const c = L.ctx as Ctx | undefined
  const main = c?.mainRoot ?? c?.gitRoot
  if (!main) { $.ui.toast('ACE: kein Git-Repo, nichts geschrieben'); return }
  try {
    const r = await writeBinding($, main, orgId, projectId, (argv, init) => run($, argv, init))
    $.ui.log(`ACE: ${r.path} geschrieben${r.gitignore === 'fixed' ? ', .gitignore angepasst' : r.gitignore === 'still_ignored' ? ' (noch ignoriert: globale Regel?)' : ''}. Bitte committen.`)
  } catch (err) { $.ui.toast(`ACE: nicht geschrieben (${err instanceof WriteRefused ? err.message : String(err).slice(0, 120)})`); return }
  await $.state.set(PENDING, null)
  await rebind($, L, await $.session.root())
}
// The cleaned rewrite of a refused .ace/config.json: only orgId/projectId survive, never the token.
export async function cleanRewrite($: any, L: Load) {
  const c: any = L.ctx
  if (!c?.path) return
  let d: any
  try { d = JSON.parse(await $.fs.read(c.path)) } catch { $.ui.toast('ACE: Datei nicht lesbar'); return }
  const main = c.path.replace(/\/\.ace\/config\.json$/, '')
  try { await writeBinding($, main, String(d.orgId ?? d.org_id ?? ''), String(d.projectId ?? d.project_id ?? ''), (argv, init) => run($, argv, init)) }
  catch (err) { $.ui.toast(`ACE: nicht geschrieben (${String((err as Error).message ?? err).slice(0, 120)})`); return }
  $.ui.log(`ACE: ${c.path} ohne apiToken/serverUrl neu geschrieben. Den Token im Git-Verlauf widerrufen.`)
  await rebind($, L, await $.session.root())
}
export async function runPending($: any, L: Load, p: any) {
  await $.state.set(PENDING, null)
  const c: any = L.ctx
  if (p.kind === 'bind') return bindTo($, L, p.orgId, p.projectId)
  if (p.kind === 'clean') return cleanRewrite($, L)
  if (p.kind === 'login') return startLogin($, L)
  if (p.kind === 'install') return install($, L)
  const r = p.kind === 'exec' ? await run($, p.argv, { timeoutMs: 30_000 }) : await cliRun($, c, p.argv, { stdin: p.stdin, timeoutMs: 300_000, cwd: c?.root })
  const ok = r && r.exitCode === 0
  $.ui.toast(`ACE: ${p.label} ${ok ? 'erledigt' : `fehlgeschlagen (exit ${r?.exitCode})`}`)
  const out = String((ok ? r?.stdout : r?.stderr) ?? '').trim()
  if (out) $.ui.log(cap(out, 2000))
}
export async function startLogin($: any, L: Load) {
  $.ui.toast('ACE: Login im Browser bestätigen')
  void (async () => {
    const r = await cliRun($, null, ['login'], { timeoutMs: 300_000 })
    $.ui.toast(r.exitCode === 0 ? 'ACE: angemeldet' : 'ACE: Login nicht abgeschlossen')
    await rebind($, L, await $.session.root())
  })().catch(() => undefined)
}
export async function install($: any, L: Load) {
  $.ui.toast('ACE: ace-cli wird installiert')
  const a = await run($, ['npm', 'ci', '--ignore-scripts'], { cwd: $.plugin.root, timeoutMs: 300_000 })
  const b = a?.exitCode === 0 ? await run($, ['npm', 'rebuild', 'better-sqlite3'], { cwd: $.plugin.root, timeoutMs: 300_000 }) : null
  $.ui.toast(b?.exitCode === 0 ? 'ACE: ace-cli installiert' : 'ACE: Installation fehlgeschlagen')
  await rebind($, L, await $.session.root())
}

export async function renderBand($: any, L: Load, e: any, next: any) {
  const pending: any = (await $.state.get(PENDING)).value
  const band: any = (await $.state.get(BAND)).value
  const { Box, Text, Button, Select } = $.ui.resolve(e) as any
  const dismiss = (onPress: () => unknown) => h(Button, { key: 'x', plain: true, role: 'dismiss', label: '×', onPress })
  if (pending) {
    return h(Box, null, h(Text, null, `ACE: ${pending.label}? `),
      h(Button, { key: 'confirm', variant: 'primary', label: pending.label, onPress: () => runPending($, L, pending) }),
      dismiss(() => $.state.set(PENDING, null)))
  }
  if (!band || band.dismissed || !band.state || band.state === 'ok' || band.state === 'server_error') return next(e)
  const close = dismiss(() => $.state.set(BAND, { ...band, dismissed: true }))
  const line = h(Text, { color: band.state.startsWith('config') ? 'error' : undefined }, `${band.line ?? 'ACE ▼'} `)
  if (band.picking && band.projects?.length) {
    return h(Box, null, h(Text, null, 'ACE Projekt: '),
      h(Select, { key: 'pick', options: band.projects.slice(0, 50).map((p: any) => ({ label: `${p.name} (${p.projectId})`, value: p.projectId })),
        onSelect: (v: string) => { const p = band.projects.find((x: any) => x.projectId === v); return p && bindTo($, L, p.orgId, p.projectId) } }), close)
  }
  const pick = () => $.state.set(BAND, { ...band, picking: true })
  switch (band.state) {
    case 'unbound':
      return band.suggestion
        ? h(Box, null, line, h(Button, { key: 'bind', variant: 'primary', label: `Verbinden: ${band.suggestion.name}`, onPress: () => bindTo($, L, band.suggestion.orgId, band.suggestion.projectId) }), close)
        : band.projects?.length ? h(Box, null, line, h(Button, { key: 'pick', label: 'Projekt wählen', onPress: pick }), close) : h(Box, null, line, close)
    case 'not_logged_in': case 'expired':
      return h(Box, null, line, h(Button, { key: 'login', variant: 'primary', label: 'Anmelden', onPress: () => startLogin($, L) }), close)
    case 'project_not_found': case 'no_access':
      return h(Box, null, line, h(Button, { key: 'pick', label: 'Anderes wählen', onPress: pick }), close)
    case 'config_refused':
      return h(Box, null, line, h(Button, { key: 'clean', label: 'Bereinigt neu schreiben', onPress: () => cleanRewrite($, L) }), close)
    case 'cli_missing':
      return h(Box, null, line, h(Button, { key: 'install', label: 'ace-cli installieren', onPress: () => install($, L) }), close)
  }
  return h(Box, null, line, close)
}
