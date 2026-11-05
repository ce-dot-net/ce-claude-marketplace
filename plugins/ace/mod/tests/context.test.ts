// The mod's one core (8.1.0): verify classification, export, adopt, remote map, the context row, ▼ status, band,
// worktrees, and every hook taking its ids from it. Mirror: tests/test_project_context_service.py. Harness: ./helpers.ts.
import { expect, test } from 'claude-code/testing'
import VERIFY from './fixtures/verify_cases.ts'
import { classify, fixGitignore, LINES, ADOPT_LINE } from '../context/index.ts'
import { CWD, HUMAN, PRJ, REL, ROOT, cliOf, done, host, mainTask, settle, submit } from './helpers.ts'

const start = ($: any, cwd = CWD) => $.session.start({ cwd, surface: null, isInteractive: false } as any)
const tick = async () => { for (let i = 0; i < 20; i++) await new Promise(r => setTimeout(r, 2)) }
const E = (m: string) => `{"level":"error","message":"{\\"error\\":\\"${m}\\"}"}`
const statusRuns = (h: any) => h.runs.filter((r: any) => cliOf(r.argv)?.[0] === 'status')
const flagOf = (argv: string[], f: string) => { const i = argv.indexOf(f); return i < 0 ? undefined : argv[i + 1] }
const ctxRows = (h: any, path = REL) => h.runs.filter((r: any) => r.argv.includes(path) && typeof r.stdin === 'string')
  .flatMap((r: any) => r.stdin.split('\n').filter(Boolean).map((l: string) => JSON.parse(l))).filter((x: any) => x.event === 'context')

for (const c of VERIFY as any[]) {
  test(`verify classify: ${c.name}`, () => {
    expect(classify(c.exit, c.stderr, !!c.spawnError, !!c.timeout)).toBe(c.state)
  })
}

test('fixGitignore: the same rewrite as the Python chain', () => {
  expect(fixGitignore('').text).toBe('.ace/*\n!.ace/config.json\n')
  expect(fixGitignore('.ace/\n').text).toBe('.ace/*\n!.ace/config.json\n')
  expect(fixGitignore('node_modules\n/.ace\n').text).toBe('node_modules\n/.ace/*\n!.ace/config.json\n')
  expect(fixGitignore('.ace/*\n!.ace/config.json\n').changed).toBe(false)
})

test('bound session: ids exported, ONE status with --org/--project, ONE context row, no ▼', async ($, on) => {
  const h = host(on, { files: { [`${CWD}/.claude/data/logs/.keep`]: '' } })
  await start($)
  await tick()
  expect(h.env.ACE_PROJECT_ID).toBe(PRJ)
  expect(h.env.ACE_ORG_ID).toBe('org_t')
  expect(JSON.parse(h.env.ACE_CONTEXT!)).toMatchObject({ root: CWD, source: 'settings_file', projectId: PRJ })
  const st = statusRuns(h)
  expect(st.length).toBe(1)
  expect([flagOf(st[0].argv, '--org'), flagOf(st[0].argv, '--project')]).toEqual(['org_t', PRJ])
  const rows = ctxRows(h)
  expect(rows.length).toBe(1)
  expect(rows[0]).toMatchObject({ state: 'ok', source: 'settings_file', path: `${CWD}/.claude/settings.json`, project_id: PRJ, chain: 'mod' })
  expect(h.statuses.filter(Boolean)).toEqual([])
  expect(h.band()?.state ?? null).toBe(null)
  await start($)  // a reload of the same load logs nothing new
  await tick()
  expect(ctxRows(h).length).toBe(1)
})

test('a leaked foreign env never wins over the repo file, and the child env carries the core ids', async ($, on) => {
  const h = host(on, { env: { ACE_ORG_ID: 'org_foreign', ACE_PROJECT_ID: 'prj_foreign' },
    files: { [`${CWD}/.ace/config.json`]: JSON.stringify({ orgId: 'org_mine', projectId: 'prj_mine' }),
      [`${ROOT}/projects/prj_mine/sessions/sess-1/mod-classic`]: '1' } })
  await start($)
  await tick()
  expect([h.env.ACE_ORG_ID, h.env.ACE_PROJECT_ID]).toEqual(['org_mine', 'prj_mine'])
  await mainTask($, h)
  const s = h.searches()[0]
  expect([flagOf(s.argv, '--org'), flagOf(s.argv, '--project')]).toEqual(['org_mine', 'prj_mine'])
  expect(s.env?.ACE_PROJECT_ID).toBe('prj_mine')
  await done($)
  await settle(h)
  const l = h.learns()[0]
  expect(flagOf(h.learnArgv(l), '--project')).toBe('prj_mine')
})

test('unbound: ▼ status, band state unbound, env unset, no status call, no search', async ($, on) => {
  const h = host(on, { noSettings: true, env: { ACE_PROJECT_ID: '' } })
  await start($)
  await tick()
  expect(statusRuns(h).length).toBe(0)
  expect(h.statuses.at(-1)).toBe('ACE ▼ nicht verbunden')
  expect(h.band()).toMatchObject({ state: 'unbound' })
  expect(LINES.unbound).toBe('ACE ▼ Repo nicht verbunden: /ace:ace-configure')
  expect(h.env.ACE_PROJECT_ID).toBe(undefined)
  await submit($)
  expect(h.searches().length).toBe(0)
})

test('unbound with a name match: the band suggests exactly that project', async ($, on) => {
  const h = host(on, { noSettings: true, cli: a => a[0] === 'projects' ? { stdout: JSON.stringify({ projects: [
    { project_id: 'prj_x', project_name: 'other', org_id: 'org_a' }, { project_id: 'prj_p', project_name: 'proj', org_id: 'org_a' }] }) } : undefined })
  await start($)
  await tick()
  expect(h.band()?.suggestion).toEqual({ orgId: 'org_a', projectId: 'prj_p', name: 'proj' })
  expect(h.runs.some((r: any) => cliOf(r.argv)?.[0] === 'login')).toBe(false)
})

for (const [stderr, state, short] of [[E('Server error (401): token expired'), 'expired', 'Anmeldung abgelaufen'],
  [E('No API token found for organization org_t.'), 'not_logged_in', 'nicht angemeldet'], [E('Server error (404): project not found'), 'project_not_found', 'Projekt fehlt'],
  [E('Server error (403): no access'), 'no_access', 'kein Zugriff']] as const) {
  test(`verify ${state} (pinned 4.3.4 stderr): ▼ status, band, never a login by itself`, async ($, on) => {
    const h = host(on, { cli: a => a[0] === 'status' ? { exitCode: 1, stderr } : undefined })
    await start($)
    await tick()
    expect(h.statuses.at(-1)).toBe(`ACE ▼ ${short}`)
    expect(h.band()?.state).toBe(state)
    expect(h.runs.some((r: any) => cliOf(r.argv)?.[0] === 'login')).toBe(false)
  })
}

test('verify with the upcoming CLI exit codes (4 = token_expired)', async ($, on) => {
  const h = host(on, { cli: a => a[0] === 'status' ? { exitCode: 4, stderr: '{"error":{"code":"token_expired","status":401,"message":"x"}}' } : undefined })
  await start($)
  await tick()
  expect(h.band()?.state).toBe('expired')
})

test('config_refused (.ace with apiToken): no CLI call at all, env does not take over, nothing searched', async ($, on) => {
  const h = host(on, { env: { ACE_ORG_ID: 'org_t', ACE_PROJECT_ID: PRJ },
    files: { [`${CWD}/.ace/config.json`]: JSON.stringify({ orgId: 'org_t', projectId: PRJ, apiToken: 'ace_user_secret' }) } })
  await start($)
  await tick()
  await submit($)
  expect(h.runs.filter((r: any) => cliOf(r.argv) && cliOf(r.argv)![0] !== 'context').length).toBe(0)  // only the seam probe (offline)
  expect(h.band()?.state).toBe('config_refused')
  expect(h.env.ACE_PROJECT_ID).toBe(undefined)
})

test('bad config (broken JSON): config_invalid, no search', async ($, on) => {
  const h = host(on, { files: { [`${CWD}/.claude/settings.json`]: '{broken' } })
  await start($)
  await tick()
  await submit($)
  expect(h.searches().length).toBe(0)
  expect(h.band()?.state).toBe('config_invalid')
})

test('cli missing: verify says cli_missing (band offers the install, nothing runs by itself)', async ($, on) => {
  const h = host(on, { cli: a => a[0] === 'status' ? { exitCode: 1, stderr: "Error: Cannot find module '/x/cli.js'" } : undefined })
  await start($)
  await tick()
  expect(h.band()?.state).toBe('cli_missing')
  expect(h.runs.some((r: any) => r.argv[0] === 'npm')).toBe(false)
})

// ---- 8.1.1: the pinned CLI is installed in the background; quiet while it runs, a band only on failure ----
const missing = (installed: () => boolean) => (a: string[]) => a[0] === 'status'
  ? (installed() ? { exitCode: 0, stdout: '{"playbook":{"total_patterns":1}}' } : { exitCode: 1, stderr: "Error: Cannot find module '/x/cli.js'" }) : undefined
const instCalls = (h: any) => h.runs.filter((r: any) => r.argv.some((a: string) => a.endsWith('/ace_cli_installer.py'))).map((r: any) => r.argv[r.argv.length - 1])

test('cli missing + background install: no band, no ▼ while it runs, none after success; the CLI is re-verified (no restart)', async ($, on) => {
  let done = false
  const h = host(on, { cli: missing(() => done), installer: a => a[0] === '--wait' ? (done = true, { state: 'ok', detail: '4.4.2' }) : { state: 'started' } })
  await start($)
  await tick()
  expect(instCalls(h)).toEqual(['--ensure', '--wait'])
  expect(h.band()?.state ?? null).toBe(null)
  expect(h.statuses.filter((s: any) => s && s.includes('▼'))).toEqual([])
  expect(statusRuns(h).length).toBe(2)  // before and after the install
  expect(h.runs.some((r: any) => r.argv[0] === 'npm')).toBe(false)  // the mod never runs npm itself
})

test('cli missing + install failed: ONE band line with [Erneut versuchen] (retry set)', async ($, on) => {
  const h = host(on, { cli: missing(() => false), installer: a => a[0] === '--wait' ? { state: 'failed', detail: 'npm ci exit 1' } : { state: 'started' } })
  await start($)
  await tick()
  expect(h.band()).toMatchObject({ state: 'cli_missing', retry: 'npm ci exit 1' })
})

test('cli missing + a recent failure (throttled): the band shows at once, no second install', async ($, on) => {
  const h = host(on, { cli: missing(() => false), installer: () => ({ state: 'failed', detail: 'timeout' }) })
  await start($)
  await tick()
  expect(instCalls(h)).toEqual(['--ensure'])
  expect(h.band()).toMatchObject({ state: 'cli_missing', retry: 'timeout' })
})

for (const state of ['off', 'unavailable']) {
  test(`cli missing + auto-install ${state}: the old behaviour (band offers the confirm install)`, async ($, on) => {
    const h = host(on, { cli: missing(() => false), installer: () => ({ state, detail: 'x' }) })
    await start($)
    await tick()
    expect(h.band()).toMatchObject({ state: 'cli_missing', retry: null })
    expect(instCalls(h)).toEqual(['--ensure'])
  })
}

// ---- worktrees / subfolders: already-bound repos work with zero steps ----
const MAIN = '/repo', WT = '/repo/.claude/worktrees/w1'
const worktreeFiles = (extra: Record<string, string> = {}) => ({
  [`${MAIN}/.git/config`]: '[core]\n[remote "origin"]\n\turl = git@github.com:acme/widget.git\n',
  [`${WT}/.git`]: `gitdir: ${MAIN}/.git/worktrees/w1\n`, [`${MAIN}/.git/worktrees/w1/commondir`]: '../..\n',
  [`${MAIN}/.git/worktrees/w1/gitdir`]: `${WT}/.git\n`, [`${MAIN}/.git/HEAD`]: 'ref: refs/heads/main\n',  // a real git worktree (spec §9 verifies it)
  [`${MAIN}/.claude/settings.json`]: JSON.stringify({ env: { ACE_ORG_ID: 'org_m', ACE_PROJECT_ID: 'prj_m' } }),
  [`${MAIN}/.claude/data/logs/.keep`]: '', [`${WT}/src/x.ts`]: '', ...extra })

test('worktree of a legacy-bound repo: settings_file of the main checkout, logs at the main root, search works', async ($, on) => {
  const h = host(on, { noSettings: true, files: worktreeFiles(), env: { ACE_AUTO_ADOPT: '0' }, root: WT, cwd: `${WT}/src` })
  await start($, `${WT}/src`)
  await tick()
  expect(h.env.ACE_PROJECT_ID).toBe('prj_m')
  const rows = ctxRows(h, `${MAIN}/.claude/data/logs/ace-relevance.jsonl`)
  expect(rows[0]).toMatchObject({ source: 'settings_file', path: `${MAIN}/.claude/settings.json`, root: MAIN, state: 'ok' })
  await submit($)
  expect(h.searches().length).toBe(1)
  expect(flagOf(h.searches()[0].argv, '--project')).toBe('prj_m')
  expect(h.files.has(`${MAIN}/.ace/config.json`)).toBe(false)  // opted out
})

test('auto-adopt: a settings_file binding becomes the tracked .ace/config.json at the main root, one line, gitignore fixed', async ($, on) => {
  const h = host(on, { noSettings: true, ignored: true, root: WT, files: worktreeFiles({ [`${MAIN}/.gitignore`]: '.ace/\n' }) })
  await start($, WT)
  await tick()
  expect(JSON.parse(h.files.get(`${MAIN}/.ace/config.json`)!)).toEqual({ orgId: 'org_m', projectId: 'prj_m' })
  expect(h.files.get(`${MAIN}/.gitignore`)).toBe('.ace/*\n!.ace/config.json\n')
  expect(h.logs.filter(l => l === ADOPT_LINE).length).toBe(1)
  expect(h.runs.some((r: any) => r.argv[0] === 'git' && (r.argv.includes('add') || r.argv.includes('commit')))).toBe(false)
})

test('auto-adopt never for env, never outside git, never over an existing file', async ($, on) => {
  const h = host(on, { noSettings: true, env: { ACE_ORG_ID: 'org_e', ACE_PROJECT_ID: 'prj_e' } })
  await start($)
  await tick()
  expect([...h.files.keys()].some(k => k.endsWith('/.ace/config.json'))).toBe(false)
  expect(h.logs.includes(ADOPT_LINE)).toBe(false)
})

test('auto-adopt refuses a symlinked .ace and logs the reason', async ($, on) => {
  const h = host(on, { noSettings: true, files: worktreeFiles(), links: [`${MAIN}/.ace`], root: WT })
  await start($, WT)
  await tick()
  expect(h.files.has(`${MAIN}/.ace/config.json`)).toBe(false)
  const rows = h.runs.filter((r: any) => r.argv.includes(`${MAIN}/.claude/data/logs/ace-relevance.jsonl`)).flatMap((r: any) => r.stdin.split('\n').filter(Boolean).map((l: string) => JSON.parse(l)))
  expect(rows.some((x: any) => x.event === 'write_refused' && /symlink/.test(x.reason))).toBe(true)
})

test('remote map: a repo_file binding teaches its origin to the machine map (shared with the Python chain)', async ($, on) => {
  const h = host(on, { noSettings: true, root: MAIN, files: { [`${MAIN}/.git/config`]: '[remote "origin"]\n\turl = https://github.com/acme/widget.git\n',
    [`${MAIN}/.ace/config.json`]: JSON.stringify({ orgId: 'org_m', projectId: 'prj_m' }) } })
  await start($, MAIN)
  await tick()
  expect(JSON.parse(h.files.get(`${ROOT}/remote-map.json`)!)['github.com/acme/widget']).toMatchObject({ orgId: 'org_m', projectId: 'prj_m' })
})

test('a fresh clone of a remembered remote binds via remote_map with no file', async ($, on) => {
  const h = host(on, { noSettings: true, root: MAIN, env: { ACE_AUTO_ADOPT: '0' }, files: { [`${MAIN}/.git/config`]: '[remote "origin"]\n\turl = git@github.com:acme/widget.git\n',
    [`${ROOT}/remote-map.json`]: JSON.stringify({ 'github.com/acme/widget': { orgId: 'org_m', projectId: 'prj_m' } }) } })
  await start($, MAIN)
  await tick()
  expect(h.env.ACE_PROJECT_ID).toBe('prj_m')
  expect(JSON.parse(h.env.ACE_CONTEXT!).source).toBe('remote_map')
})

test('the seam: ACE_CONTEXT_ENGINE=cli takes `ace-cli context --json` (explicit)', async ($, on) => {
  const h = host(on, { noSettings: true, env: { ACE_CONTEXT_ENGINE: 'cli' }, cli: a => a[0] === 'context'
    ? { stdout: JSON.stringify({ bound: true, orgId: 'org_c', projectId: 'prj_c', source: 'repo_file', path: '/proj/.ace/config.json' }) } : undefined })
  await start($)
  await tick()
  expect(h.env.ACE_PROJECT_ID).toBe('prj_c')
})

test('no pending state on a plain ok session; a submit after start searches with the human prompt', async ($, on) => {
  const h = host(on)
  await start($)
  await tick()
  expect(h.pending()).toBe(null)
  await submit($, HUMAN)
  expect(h.searches().length).toBe(1)
})

// ---- the seam, feature-detected (the prerelease CLI still says 4.3.4); shapes from the SDK's samples.md ----
const SAMPLE_BOUND = '{\n  "bound": true,\n  "orgId": "org_x",\n  "projectId": "prj_x",\n  "source": "repo_file",\n  "path": "/proj/.ace/config.json",\n  "projectName": null,\n  "auth": {\n    "state": "not_logged_in",\n    "source": null\n  }\n}'
const SAMPLE_REFUSED = '{\n  "bound": false,\n  "reason": "config_refused",\n  "source": "repo_file",\n  "path": "/proj/.ace/config.json",\n  "warnings": [\n    "repo_file_contains_secret"\n  ],\n  "projectName": null,\n  "auth": {\n    "state": "not_logged_in",\n    "source": null\n  }\n}'
const SAMPLE_UNBOUND_ERR = '{"error":{"code":"unbound","status":null,"message":"No ACE project bound to this directory (see \\"tried\\" above). Run: ace-cli init"}}'
const ctxRunsOf = (h: any) => h.runs.filter((r: any) => cliOf(r.argv)?.[0] === 'context')

test('seam: a CLI that has `context` is used (exit 0, samples.md bound shape), whatever its version says', async ($, on) => {
  const h = host(on, { noSettings: true, cli: a => a[0] === 'context' ? { stdout: SAMPLE_BOUND } : a[0] === '--version' ? { stdout: '4.3.4' } : undefined })
  await start($)
  await tick()
  expect(h.env.ACE_PROJECT_ID).toBe('prj_x')
  expect(JSON.parse(h.env.ACE_CONTEXT!)).toMatchObject({ source: 'repo_file', projectId: 'prj_x' })
})

test('seam: config_refused from the CLI comes from stdout JSON (exit 5, generic stderr ignored)', async ($, on) => {
  const h = host(on, { cli: a => a[0] === 'context' ? { exitCode: 5, stdout: SAMPLE_REFUSED, stderr: SAMPLE_UNBOUND_ERR } : undefined })
  await start($)
  await tick()
  expect(h.band()?.state).toBe('config_refused')
  expect(h.env.ACE_PROJECT_ID).toBe(undefined)
})

test('seam: an old CLI ("unknown command") falls back to our resolver, and is not probed again for the same build', async ($, on) => {
  const h = host(on, { cli: a => a[0] === 'context' ? { exitCode: 1, stderr: "error: unknown command 'context'" } : undefined })
  await start($)
  await tick()
  expect(h.env.ACE_PROJECT_ID).toBe(PRJ)
  expect(JSON.parse(h.files.get(`${ROOT}/cli-context-cap.json`)!)).toMatchObject({ has: false })
  expect(ctxRunsOf(h).length).toBe(1)
})

test('seam: a known-old CLI build is skipped (cached), ACE_CONTEXT_ENGINE=resolver never probes', async ($, on) => {
  const h = host(on, { env: { ACE_CONTEXT_ENGINE: 'resolver' } })
  await start($)
  await tick()
  expect(ctxRunsOf(h).length).toBe(0)
  expect(h.env.ACE_PROJECT_ID).toBe(PRJ)
})

test('seam: the CLI result still meets our id strictness (a metacharacter id is config_invalid)', async ($, on) => {
  const bad = SAMPLE_BOUND.replace('"prj_x"', '"prj_x/../y"')
  const h = host(on, { noSettings: true, cli: a => a[0] === 'context' ? { stdout: bad } : undefined })
  await start($)
  await tick()
  expect(h.band()?.state).toBe('config_invalid')
})

test('unbound: the export tells the Python chain the mod owns this root (no ids)', async ($, on) => {
  const h = host(on, { noSettings: true })
  await start($)
  await tick()
  expect(JSON.parse(h.env.ACE_CONTEXT!)).toMatchObject({ root: CWD, bound: false })
  expect(h.env.ACE_PROJECT_ID).toBe(undefined)
})

test('bound: ACE_BIND_ROOT is exported beside the ids (a child session elsewhere ignores them)', async ($, on) => {
  const h = host(on)
  await start($)
  await tick()
  expect(h.env.ACE_BIND_ROOT).toBe(CWD)
})

// ---- 8.1.0 review: forged commondir, oversized and out-of-repo binding files (mirror: tests/test_binding_file_guards.py) ----
const CTX_CLI = (a: string[]) => a[0] === 'context'
  ? { stdout: JSON.stringify({ bound: true, orgId: 'org_v', projectId: 'prj_v', source: 'settings_file', path: '/victim/.claude/settings.json' }) } : undefined
const askedCli = (h: any) => h.runs.some((r: any) => cliOf(r.argv)?.[0] === 'context')
const forgedFiles = () => ({
  '/victim/.git/HEAD': 'ref: refs/heads/main\n', '/victim/.git/config': '[remote "origin"]\n\turl = git@github.com:victim/repo.git\n',
  '/victim/.claude/settings.json': JSON.stringify({ env: { ACE_ORG_ID: 'org_v', ACE_PROJECT_ID: 'prj_v' } }), '/victim/.claude/data/logs/.keep': '',
  '/a/.git': 'gitdir: /gd\n', '/gd/commondir': '/victim/.git\n', '/gd/gitdir': '/a/.git\n', '/a/.claude/data/logs/.keep': '' })

test('forged .git commondir: no climb into the victim, the CLI is not asked, nothing logged or adopted there', async ($, on) => {
  const h = host(on, { noSettings: true, root: '/a', cwd: '/a', files: forgedFiles(), cli: CTX_CLI })
  await start($, '/a')
  await tick()
  expect(h.env.ACE_PROJECT_ID).toBe(undefined)
  expect(askedCli(h)).toBe(false)
  expect(h.band()?.state).toBe('unbound')
  const rows = ctxRows(h, '/a/.claude/data/logs/ace-relevance.jsonl')
  expect(rows[0]).toMatchObject({ state: 'unbound', reason: 'no_binding', root: '/a', warnings: ['worktree_topology_untrusted'] })
  expect(h.runs.some((r: any) => r.argv.some((x: string) => x.startsWith('/victim/.claude/data') || x.startsWith('/victim/.ace')))).toBe(false)
  expect([...h.files.keys()].some(k => k.startsWith('/victim/.ace'))).toBe(false)
})

// cli >= 4.4.2 checks the topology itself (spec §9 (a)-(e)): the seam is asked again on an untrusted topology,
// gated by `ace-cli --version` (probed once per CLI build, cached beside `has`). Older or unknown: our resolver only.
const UNTRUSTED_OUT = JSON.stringify({ bound: false, reason: 'no_binding', tried: [], warnings: ['worktree_topology_untrusted'] })
const topoCli = (v: string) => (a: string[]) => a[0] === 'context' ? { exitCode: 5, stdout: UNTRUSTED_OUT } : a[0] === '--version' ? { stdout: `${v}\n` } : undefined
for (const [v, asked] of [['4.4.2', true], ['4.10.0', true], ['4.4.1', false], ['garbage', false]] as const) {
  test(`forged .git commondir, ace-cli --version ${v}: the CLI is ${asked ? '' : 'not '}asked`, async ($, on) => {
    const h = host(on, { noSettings: true, root: '/a', cwd: '/a', files: forgedFiles(), cli: topoCli(v) })
    await start($, '/a')
    await tick()
    expect(askedCli(h)).toBe(asked)
    expect(h.env.ACE_PROJECT_ID).toBe(undefined)
    expect(ctxRows(h, '/a/.claude/data/logs/ace-relevance.jsonl')[0]).toMatchObject({ state: 'unbound', via: asked ? 'cli' : 'resolver',
      warnings: ['worktree_topology_untrusted'] })
    expect(JSON.parse(h.files.get(`${ROOT}/cli-context-cap.json`) ?? '{}').version ?? null).toBe(v === 'garbage' ? null : v)
  })
}

const GIT = { [`${CWD}/.git/config`]: '[core]\n', [`${CWD}/.claude/data/logs/.keep`]: '' }
const ACE = JSON.stringify({ orgId: 'org_a', projectId: 'prj_a' })
for (const [rel, body] of [['.ace/config.json', ACE], ['.claude/settings.json', JSON.stringify({ env: { ACE_ORG_ID: 'org_a', ACE_PROJECT_ID: 'prj_a' } })]] as const) {
  test(`${rel} over 64 KiB: config_invalid + config_too_large, the CLI is not asked`, async ($, on) => {
    const h = host(on, { noSettings: true, env: { ACE_ORG_ID: 'org_e', ACE_PROJECT_ID: 'prj_e' }, cli: CTX_CLI,
      files: { ...GIT, [`${CWD}/${rel}`]: body + ' '.repeat(64 * 1024 + 1 - body.length) } })
    await start($)
    await tick()
    expect(askedCli(h)).toBe(false)
    expect(h.band()?.state).toBe('config_invalid')
    expect(ctxRows(h)[0]).toMatchObject({ state: 'config_invalid', reason: 'config_invalid', warnings: ['config_too_large'] })
  })
  test(`${rel} of exactly 64 KiB still binds`, async ($, on) => {
    const h = host(on, { noSettings: true, files: { ...GIT, [`${CWD}/${rel}`]: body + ' '.repeat(64 * 1024 - body.length) } })
    await start($)
    await tick()
    expect(h.env.ACE_PROJECT_ID).toBe('prj_a')
  })
}

for (const real of ['/elsewhere/config.json', '/proj2/.ace/config.json']) {
  test(`symlinked .ace/config.json -> ${real}: config_refused + repo_file_outside_root, the CLI is not asked`, async ($, on) => {
    const h = host(on, { noSettings: true, files: { ...GIT, [`${CWD}/.ace/config.json`]: ACE }, realpaths: { [`${CWD}/.ace/config.json`]: real }, cli: CTX_CLI })
    await start($)
    await tick()
    expect(askedCli(h)).toBe(false)
    expect(h.band()?.state).toBe('config_refused')
    expect(ctxRows(h)[0]).toMatchObject({ state: 'config_refused', source: 'repo_file', warnings: ['repo_file_outside_root'] })
  })
}

test('a symlinked .ace/config.json inside the repo still binds', async ($, on) => {
  const h = host(on, { noSettings: true, files: { ...GIT, [`${CWD}/.ace/config.json`]: ACE }, realpaths: { [`${CWD}/.ace/config.json`]: `${CWD}/conf/config.json` } })
  await start($)
  await tick()
  expect(h.env.ACE_PROJECT_ID).toBe('prj_a')
})
