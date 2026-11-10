// The AbovePrompt band (8.1.0): nothing when ok; a pending write's ONE confirm button; else exactly one action per
// problem state (unbound -> Verbinden, login states -> Anmelden, not_found/no_access -> Anderes wählen,
// config_refused -> Bereinigt neu schreiben, cli_missing -> installieren). Every action runs only on its press.
import { startContext } from '../handlers/context.ts'
import { type Ctx, WARN_LINES, bindInit, cliIds, cliInit, repoWrite, writeBinding, WriteRefused } from '../context/index.ts'
import { REMOVE_SHADOW_SH, REPO_WRITE_WHY } from '../lib/sh.ts'
import { run } from '../io/fs.ts'
import { cliRun, cap } from '../io/cli.ts'
import { installer } from '../io/installer.ts'
import { execExport, execPending } from '../io/pending.ts'
import { type Load } from '../io/state.ts'
import { CLIENT_POLICY_FILE, clientPolicyBand } from '../lib/cohort.ts'
import { readText } from '../io/fs.ts'

const BAND = { plugin: 'ace', key: 'band' } as const
const PENDING = { plugin: 'ace', key: 'pending' } as const
const SHADOW = { plugin: 'ace', key: 'shadow' } as const  // a worktree-local .ace/config.json that overrides main's
const POLICY = { plugin: 'ace', key: 'policy' } as const  // 8.1.4: the dismissed client_policy line
export const ACTION: Record<string, string | undefined> = { unbound: 'Verbinden', not_logged_in: 'Anmelden', expired: 'Anmelden',
  project_not_found: 'Anderes wählen', no_access: 'Anderes wählen', config_refused: 'Bereinigt neu schreiben', cli_missing: 'ace-cli installieren' }

async function rebind($: any, L: Load, cwd: string) {
  L.ctx = undefined; L.sess = null; L.ctxLogged = false
  await startContext($, L, cwd)
}
const GI: Record<string, string> = { fixed: ', .gitignore angepasst', still_ignored: ' (noch ignoriert: globale Regel?)',
  ignored_unfixable: ' (noch ignoriert: globale Regel?)', ignored_declined: ' (noch ignoriert)' }
// After the init result: its warnings as lines; a shadowing worktree file goes to the band ([Entfernen]), never deleted here.
async function afterInit($: any, c: Ctx | undefined, r: { path: string, gitignore: string, warnings: string[], shadowedBy?: string }) {
  $.ui.log(`ACE: ${r.path} geschrieben${GI[r.gitignore] ?? ''}. Bitte committen.`)
  for (const w of r.warnings) if (w !== 'worktree_file_shadows_main' && (WARN_LINES as Record<string, string>)[w]) $.ui.log((WARN_LINES as Record<string, string>)[w])
  await $.state.set(SHADOW, r.shadowedBy && c?.gitRoot ? { path: r.shadowedBy, root: c.gitRoot } : null)
}
// Bind = `ace-cli init --json --fix-gitignore` (the press is the confirmation), our writer only for a CLI without it.
export async function bindTo($: any, L: Load, orgId: string, projectId: string) {
  const c = L.ctx as Ctx | undefined
  if (!(c?.mainRoot ?? c?.gitRoot)) { $.ui.toast('ACE: kein Git-Repo, nichts geschrieben'); return }
  try { await afterInit($, c, await bindInit($, await $.session.cwd(), orgId, projectId, (argv: string[], o?: any) => cliRun($, null, argv, o), (argv, init) => run($, argv, init))) }
  catch (err) { $.ui.toast(`ACE: nicht geschrieben (${err instanceof WriteRefused ? err.message : String(err).slice(0, 120)})`); return }
  await $.state.set(PENDING, null)
  await rebind($, L, await $.session.root())
}
// [Entfernen]: delete only the shadowing worktree file (REMOVE_SHADOW_SH: no symlink, inside the worktree root).
export async function removeShadow($: any, L: Load) {
  const s: any = (await $.state.get(SHADOW)).value
  if (!s?.path || !s.root || !String(s.path).startsWith(`${s.root}/`) || !String(s.path).endsWith('/.ace/config.json')) { await $.state.set(SHADOW, null); return }
  const r = await run($, ['/bin/sh', '-c', REMOVE_SHADOW_SH, 'sh', s.path, s.root], { timeoutMs: 5000 })
  if (r?.exitCode !== 0) { $.ui.toast(`ACE: nicht entfernt (${REPO_WRITE_WHY[r?.exitCode] ?? 'nicht gefunden'}: ${s.path})`); return }
  await $.state.set(SHADOW, null)
  $.ui.toast(`ACE: ${s.path} entfernt, die Bindung des Haupt-Checkouts gilt`)
  await rebind($, L, await $.session.root())
}
// The cleaned rewrite of a refused .ace/config.json: only orgId/projectId survive, never the token. The CLI's init
// (no ids: it reuses the refused file's ids and strips it where it is); our writer at that file for a CLI without it.
export async function cleanRewrite($: any, L: Load) {
  const c: any = L.ctx
  if (!c?.path) return
  let out = null
  try { out = await cliInit((argv: string[], o?: any) => cliRun($, null, argv, o), await $.session.cwd(), null) }
  catch (err) { $.ui.toast(`ACE: nicht geschrieben (${String((err as Error).message ?? err).slice(0, 120)})`); return }
  if (out) await afterInit($, c, out)
  else {
    let d: any
    try { d = JSON.parse(await $.fs.read(c.path)) } catch { $.ui.toast('ACE: Datei nicht lesbar'); return }
    const main = c.path.replace(/\/\.ace\/config\.json$/, '')
    try { await writeBinding($, main, String(d.orgId ?? d.org_id ?? ''), String(d.projectId ?? d.project_id ?? ''), (argv, init) => run($, argv, init)) }
    catch (err) { $.ui.toast(`ACE: nicht geschrieben (${String((err as Error).message ?? err).slice(0, 120)})`); return }
  }
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
  if (p.kind === 'export') return exportTo($, L, p.path)
  const d = await execPending($, c, p)
  $.ui.toast(d.toast)
  if (d.out) $.ui.log(d.out)
}
// export: see io/pending.ts execExport (stdout of `ace-cli export`, written inside the repo root).
export async function exportTo($: any, L: Load, rel: string) {
  $.ui.toast((await execExport($, L.ctx, rel)).toast)
}
export async function startLogin($: any, L: Load) {
  $.ui.toast('ACE: Login im Browser bestätigen')
  void (async () => {
    const r = await cliRun($, null, ['login'], { timeoutMs: 300_000 })
    $.ui.toast(r.exitCode === 0 ? 'ACE: angemeldet' : 'ACE: Login nicht abgeschlossen')
    await rebind($, L, await $.session.root())
  })().catch(() => undefined)
}
// The same installer SessionStart starts in the background (io/installer.ts); a press is never throttled.
export async function install($: any, L: Load) {
  $.ui.toast('ACE: ace-cli wird installiert')
  const r = await installer($, ['--run'], 600_000)
  $.ui.toast(r.state === 'ok' ? 'ACE: ace-cli installiert' : `ACE: Installation fehlgeschlagen${r.detail ? ` (${r.detail.slice(0, 120)})` : ''}`)
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
  const shadow: any = (await $.state.get(SHADOW)).value
  if (shadow?.path) {
    return h(Box, null, h(Text, null, `${WARN_LINES.worktree_file_shadows_main} `),
      h(Button, { key: 'rm-shadow', label: 'Entfernen', onPress: () => removeShadow($, L) }), dismiss(() => $.state.set(SHADOW, null)))
  }
  if (!band || band.dismissed || !band.state || band.state === 'ok' || band.state === 'server_error') {
    // 8.1.4 client_policy below min (dormant until the server sends it): ONE line, one action (dismiss). Never an
    // update, never code fetched; ACE stays on and keeps learning.
    const s = L.sess
    const text = s ? await readText($, `${s.root}/${CLIENT_POLICY_FILE}`) : undefined
    const pline = s && text ? clientPolicyBand(text, s.clientId.slice(s.clientId.lastIndexOf('/') + 1), await $.clock.now()) : undefined
    if (pline && (await $.state.get(POLICY)).value !== pline)
      return h(Box, null, h(Text, null, `${pline} `), dismiss(() => $.state.set(POLICY, pline)))
    return next(e)
  }
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
      return h(Box, null, line, h(Button, { key: 'install', label: band.retry ? 'Erneut versuchen' : 'ace-cli installieren', onPress: () => install($, L) }), close)
  }
  return h(Box, null, line, close)
}
