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
  expect(h.runs.filter((r: any) => cliOf(r.argv)).length).toBe(0)
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

// ---- worktrees / subfolders: already-bound repos work with zero steps ----
const MAIN = '/repo', WT = '/repo/.claude/worktrees/w1'
const worktreeFiles = (extra: Record<string, string> = {}) => ({
  [`${MAIN}/.git/config`]: '[core]\n[remote "origin"]\n\turl = git@github.com:acme/widget.git\n',
  [`${WT}/.git`]: `gitdir: ${MAIN}/.git/worktrees/w1\n`, [`${MAIN}/.git/worktrees/w1/commondir`]: '../..\n',
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

test('the seam: ACE_CONTEXT_ENGINE=cli takes `ace-cli context --json`', async ($, on) => {
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
