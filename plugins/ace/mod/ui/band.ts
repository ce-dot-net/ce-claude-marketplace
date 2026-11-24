// The AbovePrompt band (8.1.0): nothing when ok; a pending write's ONE confirm button; else exactly one action per
// problem state (unbound -> Verbinden, login states -> Anmelden, not_found/no_access -> Anderes wählen,
// config_refused -> Bereinigt neu schreiben, cli_missing -> installieren). Every action runs only on its press.
import { refreshUnbound, startContext } from '../handlers/context'
import { type Ctx, WARN_LINES, bindInit, cliIds, cliInit, repoWrite, writeBinding, WriteRefused } from '../context/index'
import { REMOVE_SHADOW_SH, REPO_WRITE_WHY } from '../lib/sh'
import { run } from '../io/fs'
import { cliRun, cap } from '../io/cli'
import { cliHead } from '../io/spawn'
import { installer } from '../io/installer'
import { execExport, execPending } from '../io/pending'
import { type Load } from '../io/state'
import { CLIENT_POLICY_FILE, clientPolicyBand } from '../lib/cohort'
import { updateBandLine } from '../lib/update'
import { switchOff } from '../lib/switches'
import { clickUpdate } from '../io/update'
import { readText } from '../io/fs'

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
// The returned line is what a typed `--approved` shows (the button ignores it).
export async function bindTo($: any, L: Load, orgId: string, projectId: string, cwd?: string): Promise<string> {
  const c = L.ctx as Ctx | undefined
  const no = (line: string) => { $.ui.toast(line); return line }
  if (!(c?.mainRoot ?? c?.gitRoot)) return no('ACE: kein Git-Repo, nichts geschrieben')
  let path: string
  try { const r = await bindInit($, cwd ?? await $.session.cwd(), orgId, projectId, (argv: string[], o?: any) => cliRun($, null, argv, o), (argv, init) => run($, argv, init)); path = r.path; await afterInit($, c, r) }
  catch (err) { return no(`ACE: nicht geschrieben (${err instanceof WriteRefused ? err.message : String(err).slice(0, 120)})`) }
  await $.state.set(PENDING, null)
  await rebind($, L, await $.session.root())
  return `ACE: verbunden mit ${projectId} (org ${orgId}), ${path} geschrieben. Bitte committen.`
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
  if (p.kind === 'bind') return bindTo($, L, p.orgId, p.projectId, p.cwd)
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
// 8.2.5: the device login without a browser (remote / SSH): `ace-cli login --no-browser` prints the URL and the code, then
// polls until confirmed. Streamed through $.process.spawn (argv only), so both are shown while the CLI still waits.
export const LOGIN_MS = 300_000, LOGIN_UNKNOWN_MS = 10_000
const ANSI = /\u001b\[[0-9;]*[A-Za-z]/g, URL_RE = /https?:\/\/[^\s"'<>]+/
export function parseLogin(raw: string): { url: string, code: string } | null {
  const t = raw.replace(ANSI, '')
  const url = /"verification_url"\s*:\s*"([^"]+)"/.exec(t)?.[1] ?? URL_RE.exec(t)?.[0]
  const code = /"user_code"\s*:\s*"([^"]+)"/.exec(t)?.[1] ?? /code manually:\s*([A-Za-z0-9-]+)/i.exec(t)?.[1]
    ?? /\b[A-Z0-9]{3,}-[A-Z0-9]{3,}\b/.exec(t.replace(new RegExp(URL_RE.source, 'g'), ''))?.[0]
  return url && code ? { url, code } : null
}
// Resolves with the line the person needs (URL + code, else the first ~300 characters of what the CLI said) as soon as
// it is known; the login itself runs on (300 s), then 'angemeldet' / 'Login nicht abgeschlossen' and the rebind.
export function startLogin($: any, L: Load): Promise<string> {
  $.ui.toast('ACE: Login startet …')
  let tell!: (s: string) => void
  const shown = new Promise<string>(r => { tell = r })
  let out = '', told = false
  const say = (line: string) => { if (told) return; told = true; $.ui.toast(line); $.ui.log(line); tell(line) }
  const raw = () => `ACE: ace-cli login sagt: ${out.replace(ANSI, '').trim().slice(0, 300)}`
  void (async () => {
    let code: number | null = null
    const timers: any[] = []
    const after = (ms: number, fn: () => void) => { try { timers.push($.clock.after(ms, fn)) } catch { /* no timer: the CLI's own poll limit ends it */ } }
    try {
      const s = $.process.spawn({ argv: [...await cliHead($), 'login', '--no-browser'], env: { NO_COLOR: '1' } })
      after(LOGIN_MS, () => { void s.return(undefined) })  // leaving the stream kills the child
      after(LOGIN_UNKNOWN_MS, () => { if (out.trim()) say(raw()) })  // output we cannot read: show it
      for await (const { text } of s) {
        if (told) continue
        out = (out + text).slice(0, 20_000)
        const p = parseLogin(out.slice(0, out.lastIndexOf('\n') + 1))  // whole lines only: a piece may end mid-code
        if (p) say(`ACE: Öffne ${p.url} und gib den Code ${p.code} ein`)
      }
      code = (await s.result.catch(() => ({ code: null }))).code
    } catch { /* cannot start (no CLI) or killed: not completed */ }
    for (const t of timers) t?.cancel?.()
    const end = code === 0 ? 'ACE: angemeldet' : 'ACE: Login nicht abgeschlossen'
    if (!told) {  // never got URL + code: the CLI's own words (if any) as a log line, then the end
      told = true
      if (code !== 0 && out.trim()) $.ui.log(raw())
      tell(code !== 0 && out.trim() ? raw() : end)
    }
    $.ui.toast(end)
    await rebind($, L, await $.session.root())
  })().catch(() => tell('ACE: Login nicht abgeschlossen'))
  return shown
}
// The same installer SessionStart starts in the background (io/installer.ts); a press is never throttled.
export async function install($: any, L: Load): Promise<string> {
  $.ui.toast('ACE: ace-cli wird installiert')
  const r = await installer($, ['--run'], 600_000)
  const line = r.state === 'ok' ? 'ACE: ace-cli installiert' : `ACE: Installation fehlgeschlagen${r.detail ? ` (${r.detail.slice(0, 200)})` : ''}`
  $.ui.toast(line)
  await rebind($, L, await $.session.root())
  return line
}
// 8.2.5 `--approved` for the band kinds that run from a typed line (Moshi/herdr: no button to press). 8.2.7: bind (the
// caller, kit.approveOrHint, passes it only for the identical waiting preview).
export async function bandAction($: any, L: Load, p: any): Promise<string> {
  await $.state.set(PENDING, null)
  return p.kind === 'login' ? startLogin($, L) : p.kind === 'bind' ? bindTo($, L, p.orgId, p.projectId, p.cwd) : install($, L)
}

export async function renderBand($: any, L: Load, e: any, next: any) {
  if (L.ctx && !L.ctx.bound) void refreshUnbound($, L)  // 8.2.7: throttled (unboundStale); a rebind republishes the band state
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
    // 8.1.4 client_policy below min (dormant until the server sends it): ONE line. Round 4: ONE action 'Aktualisieren' (the fixed
    // update command, io/update.ts clickUpdate); ACE_AUTO_UPDATE=0 keeps the 8.1.4 line (dismiss only). ACE stays on meanwhile.
    const s = L.sess
    const text = s ? await readText($, `${s.root}/${CLIENT_POLICY_FILE}`) : undefined
    const version = s ? s.clientId.slice(s.clientId.lastIndexOf('/') + 1) : ''
    const optOut = switchOff(await $.env.get('ACE_AUTO_UPDATE'))
    const now = await $.clock.now()
    const pline = s && text ? (optOut ? clientPolicyBand(text, version, now) : updateBandLine(text, version, now)) : undefined
    if (pline && (await $.state.get(POLICY)).value !== pline)
      return optOut ? h(Box, null, h(Text, null, `${pline} `), dismiss(() => $.state.set(POLICY, pline)))
        : h(Box, null, h(Text, null, `${pline} `), h(Button, { key: 'update', variant: 'primary', label: 'Aktualisieren', onPress: () => clickUpdate($, L) }),
          dismiss(() => $.state.set(POLICY, pline)))
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
