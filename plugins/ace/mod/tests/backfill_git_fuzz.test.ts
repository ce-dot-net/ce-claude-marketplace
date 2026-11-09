// 8.2.0 git reader: seeded adversarial fuzz of the redaction (readGitLog / readMergeLog). Deterministic (own PRNG), so a
// failure prints its seed and case and reproduces. Invariant: a canary secret value never appears in any output field.
// Accepted limits (not generated): a value with no key word, no separator and no token shape; a key word followed by
// whitespace only ("refresh token expiry" must stay readable); homoglyph LETTERS inside a key word (Cyrillic "p\u0430ssword").
import { expect, test } from 'claude-code/testing'
import { readGitLog, readMergeLog } from '../lib/backfill_git.ts'

const RS = '\x1e', NUL = '\x00', DATE = '2026-03-02T10:00:00Z'
const MARK = 'zq9xk7'  // lowercased prefix of every canary
const commit = (sha: string, subject: string, files: string[] = ['src/a.ts'], body = '') =>
  `${RS}${sha}${NUL}${DATE}${NUL}${subject}${NUL}${body}${NUL}\n\n${files.join('\n')}\n`
const merge = (sha: string, body: string) => `${RS}${sha}${NUL}${DATE}${NUL}Merge pull request #7 from o/b${NUL}${body}${NUL}\n`
const leaks = (x: unknown) => JSON.stringify(x).toLowerCase().includes(MARK)

function mulberry32(seed: number) {
  let a = seed >>> 0
  return () => { a = (a + 0x6d2b79f5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296 }
}

const ZW = ['\u200b', '\u200c', '\u200d', '\u2060', '\ufeff', '\u00ad', '\u180e', '\u034f', '\ufe0f', '\u202e', '\u3164', '\u115f', '\u2800']
const SPACES = ['', ' ', '  ', '\t', '\u00a0', '\u2003', '\u3000', '\u202f']
const SEPS = ['|', '->', '%3D', '%3a', ':', '=', ':=', '=>', '::', '\uff1a', '\uff1d', '\u2236', '\ua789', '\u02f8', '\u02d0', '\ufe55', '\ufe66', '\u2254', '\u207c', '\u0589', '\u2e2c', '\u05c3', '\u00b7=']
const WRAP: [string, string][] = [['', ''], ['"', '"'], ["'", "'"], ['`', '`'], ['(', ')'], ['[', ']'], ['{', '}'], ['<', '>'], ['((', '))'], ['"[', ']"']]
const KEYS = ['password', 'passwd', 'pass', 'pwd', 'secret', 'token', 'api_key', 'apikey', 'api-key', 'api key', 'access_key', 'private key',
  'credential', 'credentials', 'bearer', 'authorization', 'cookie', 'session', 'key', 'DB_PASSWORD', 'GITHUB_TOKEN', 'client_secret',
  'STRIPE_KEY', 'FOO_KEY_ID', 'signing-key', 'x-api-key', 'AWS_SECRET_ACCESS_KEY', 'npmAuthToken', 'session_cookie', 'PGPASSWORD', 'auth_token']
const TYPES = ['fix', 'Fix', 'FIX', 'hotfix', 'bug', 'bugfix', 'regression', 'fixes', 'fixed']
const NOISE = ['the', 'parser', 'crash', 'when', 'login', 'retries', '(x)', '[wip]', '"q"', 'a:b', 'x=y', '->', '#12', 'na\u00efve', '\uff46\uff55\uff4c\uff4c', '\u00e9', '\u2014', '\u2026']
const SCHEMES = ['https', 'HTTP', 'git+ssh', 'postgres', 'redis', 'mongodb+srv', 'ftp', '\uff48\uff54\uff54\uff50\uff53']

type Case = { kind: string, text: string }

function gen(r: () => number, n: number): Case {
  const pick = <T>(a: T[]) => a[Math.floor(r() * a.length)]
  const chance = (p: number) => r() < p
  const canary = `Zq9xK7canary${n}`
  const zw = (w: string) => chance(0.3) ? w.split('').map(ch => ch + (chance(0.25) ? pick(ZW) : '')).join('') : w
  const casing = (w: string) => { const k = Math.floor(r() * 4); return k === 0 ? w.toUpperCase() : k === 1 ? w.toLowerCase() : k === 2 ? w[0].toUpperCase() + w.slice(1) : w }
  const fullwidth = (w: string) => chance(0.1) ? w.replace(/[!-~]/g, ch => String.fromCharCode(ch.charCodeAt(0) + 0xfee0)) : w
  const noise = (k: number) => Array.from({ length: k }, () => pick(NOISE)).join(' ')
  const [wo, wc] = pick(WRAP)
  const kv = () => `${wo}${fullwidth(zw(casing(pick(KEYS))))}${wc}${pick(SPACES)}${pick(SEPS)}${pick(SPACES)}${pick(['', '"', "'", '`', '('])}${canary}`
  const shape = (): string => {
    const k = Math.floor(r() * 11)
    if (k === 0) return `${pick(['ghp_', 'gho_', 'ghu_', 'ghs_', 'ghr_', 'github_pat_', 'xoxb-', 'xoxp-', 'sk-', 'ace_user_'])}${canary}`
    if (k === 1) return `npm_${canary.padEnd(26, '0')}`
    if (k === 2) return `AKIA${canary.toUpperCase()}`
    if (k === 3) return `eyJhbGciOiJIUzI1NiJ9.${canary}.c2lnbmF0dXJl`
    if (k === 4) return `${pick(['-----', '-----', '---- '])}BEGIN ${pick(['RSA ', 'OPENSSH ', 'EC ', ''])}PRIVATE KEY----- MIIEv${canary}`
    if (k === 5) return `${pick(SCHEMES)}://${pick(['user', '', 'a.b', 'u(a)'])}:${pick(['', '"', "'", '`'])}${canary}${pick(['', '"', "'", '`', '@x'])}${pick(['@', '\uff20'])}host.example/p`
    if (k === 6) return `${casing('bearer')}${pick([' ', '\t', '\u00a0', '  ', '\u200b ', '\u2003', '\u200b', '\u2060', '\u00ad'])}${canary}`
    if (k === 7) return `${casing('Authorization')}${pick(SEPS)} ${casing('Bearer')} ${canary}`
    if (k === 8) return `${pick(['echo', 'printf %s', 'ECHO', 'printf'])} ${canary} | ${pick(['docker login -u me --password-stdin', 'gh auth login --with-token', 'podman login --password-stdin r.io', 'helm registry login --password-stdin'])}`
    if (k === 9) return `${pick(['--password', '--token', '--api-key', '--secret', '--db-password'])}${pick(['=', ' ', '\t'])}${canary}`
    return kv()
  }
  const snippet = chance(0.45) ? kv() : shape()
  const type = pick(TYPES)
  const k = Math.floor(r() * 9)
  let subject: string
  if (k === 0) subject = `${type}(${zw(casing(pick(KEYS)))})${pick(['', '!'])}${pick(SPACES)}${pick(SEPS)}${pick(SPACES)}${canary} leaked`  // the key is the scope
  else if (k === 1) subject = `${type}${pick(['((', '[', '{', '(a)(', '(core, ', '(a,'])}${zw(pick(KEYS))}${pick(['))', ']', '}', ')', ', x)', ')'])}${pick(['', '!'])}${pick(SEPS)} ${canary}`
  else if (k === 2) subject = `Revert "${type}(${pick(['x', 'core'])}): ${noise(2)} ${snippet}"`
  else if (k === 3) subject = `Revert "Revert "${type}: ${snippet}""`
  else if (k === 4) subject = `${type}: ${noise(3)}${pick(['\n', '\r\n', '\r', '\u2028', '\n\n'])}${snippet} ${noise(1)}`
  else subject = `${type}${chance(0.5) ? `(${pick(['auth', 'x', 'db-pool'])})` : ''}${pick(['', '!'])}: ${noise(Math.floor(r() * 4))} ${snippet} ${noise(Math.floor(r() * 3))}`
  // straddle the 500-char cut (and the redaction window edge) with the secret often
  if (chance(0.5)) {
    const at = pick([480 + Math.floor(r() * 41), 1990 + Math.floor(r() * 30), 497, 500, 503])
    const head = `${type}: `, len = at - subject.indexOf(canary) - head.length - 1, filler = pick(['x', 'word ', '\u00e9', '\u200b', 'a\u00a0', '\uff58'])
    if (len > 0) subject = head + filler.repeat(Math.ceil(len / filler.length)).slice(0, len) + ' ' + subject
  }
  const p = Math.floor(r() * 10)
  if (p < 6) return { kind: `subject/${k}`, text: commit('a'.repeat(40), subject, ['src/a.ts']) }
  if (p === 6) {  // the secret in a file path
    const path = `${pick(['config/', 'a/b/', 'd/' + 'x'.repeat(480 + Math.floor(r() * 30))])}${snippet.replace(/\n/g, '')}${pick(['', '.json', '/f.env'])}`
    return { kind: 'path', text: commit('b'.repeat(40), 'fix the parser crash on empty input', [path]) }
  }
  if (p === 7) return { kind: 'merge', text: merge('c'.repeat(40), `${pick(['', '\n', '\r\n', '\n\n'])}${subject.replace(/[\r\n\u2028]/g, ' ')}\nmore body ${canary}`) }
  if (p === 8) return { kind: 'rs-inject', text: commit('d'.repeat(40), 'fix the parser crash on empty input', ['src/a.ts'], `body\n${RS}${canary}${NUL}${DATE}${NUL}fix: login retry bug${NUL}${NUL}\n\nsrc/b.ts\n`) }
  return { kind: 'subject-raw', text: commit('e'.repeat(40), subject, ['src/a.ts']) }
}

function run(seed: number, n: number) {
  const r = mulberry32(seed)
  let emitted = 0, slowest = 0
  for (let i = 0; i < n; i++) {
    const c = gen(r, seed * 100000 + i)
    const t0 = performance.now()
    const out = [readGitLog(c.text, { projectId: 'prj' }), readMergeLog(c.text, { projectId: 'prj' })]
    slowest = Math.max(slowest, performance.now() - t0)
    emitted += out[0].length + out[1].length
    if (leaks(out)) throw new Error(`leak seed=${seed} case=${i} kind=${c.kind}\nin=${JSON.stringify(c.text)}\nout=${JSON.stringify(out)}`)
  }
  return { emitted, slowest }
}

// four seeds x 5000 cases = 20000 cases, one test per seed (each well under the 5 s test timeout)
for (const seed of [1, 42, 7777, 20261109])
  test(`fuzz seed ${seed}: no canary secret leaves readGitLog/readMergeLog (5000 cases), bounded time per case`, () => {
    const { emitted, slowest } = run(seed, 5000)
    expect(emitted).toBeGreaterThan(2500)  // most cases really produce a task: the invariant is not passed vacuously
    expect(slowest).toBeLessThan(250)  // per case, JIT warm-up included: catches a regex blow-up, not jitter
  })

// Minimized bypasses the fuzzer found (each leaked before the fix).
const one = (subject: string, files: string[] = ['src/a.ts']) => readGitLog(commit('a'.repeat(40), subject, files), { projectId: 'prj' })
const H = 'hunter2Zq9xK7'

test('regression: unicode separators (fullwidth, ratio, modifier colon, small forms) count as : or =', () => {
  for (const s of [`fix: token\uff1a${H}`, `fix: API_KEY\uff1d${H}`, `fix(token)\u2236 ${H}`, `fix: secret \ua789 ${H}`, `fix: password\ufe55${H}`, `fix: pwd\u2254${H}`])
    expect(leaks(one(s))).toBe(false)
})

test('regression: zero-width and invisible characters inside a key word or Bearer do not hide it', () => {
  for (const s of [`fix: to\u200bken: ${H}`, `fix: sec\u00adret=${H}`, `fix: api\u2060_key: ${H}`, `fix: Bearer\u00a0${H}`, `fix: tok\u3164en: ${H}`])
    expect(leaks(one(s))).toBe(false)
})

test('regression: fullwidth key words and token shapes are folded before matching', () => {
  for (const s of ['fix: \uff54\uff4f\uff4b\uff45\uff4e: ' + H, 'fix: \uff47\uff48\uff50\uff3f' + H, `fix: ${'\uff48\uff54\uff54\uff50\uff53'}://u:${H}@h/p`])
    expect(leaks(one(s))).toBe(false)
})

test('regression: a line break in a raw subject or file path does not end the redaction early', () => {
  for (const s of [`fix: session:\n${H}`, `fix: key =\r\n${H}`, `fix: cookie:\u2028${H}`])
    expect(leaks(one(s))).toBe(false)
})

test('regression: a PEM private key header redacts what follows', () => {
  expect(leaks(one(`fix: leaked -----BEGIN RSA PRIVATE KEY----- MIIEv${H}`))).toBe(false)
})

test('regression: a record injected through RS in a commit body never emits its fake sha', () => {
  const t = commit('d'.repeat(40), 'fix the parser crash on empty input', ['src/a.ts'], `body\n${RS}${H}${NUL}${DATE}${NUL}fix: login retry bug${NUL}${NUL}\n`)
  const out = readGitLog(t, { projectId: 'prj' })
  expect(leaks(out)).toBe(false)
  for (const x of out) expect(x.sha).toMatch(/^[0-9a-f]{7,64}$/)
})

test('regression: the 500-char cut before or inside --password-stdin / --with-token still redacts the piped value', () => {
  for (const pad of [440, 470, 480, 485, 490, 495])
    for (const tail of ['docker login -u me --password-stdin', 'gh auth login --with-token']) {
      const s = `fix: ${'x '.repeat(pad / 2)}echo ${H} | ${tail}`
      expect(leaks(one(s))).toBe(false)
      expect(leaks(readMergeLog(merge('c'.repeat(40), s), { projectId: 'prj' }))).toBe(false)
    }
  expect(leaks(one(`fix: ${'x '.repeat(240)}printf %s ${H} | gh auth login --with-token`))).toBe(false)
})

test('regression: an upper-case ECHO piped into --password-stdin, and a here-string after the flag, are redacted', () => {
  for (const s of [`fix: ECHO ${H} | podman login --password-stdin r.io`, `fix: docker login --password-stdin <<< ${H}`, `fix: Printf ${H} | gh auth login --WITH-TOKEN`])
    expect(leaks(one(s))).toBe(false)
})

test('regression: Bearer joined to its value by a dropped zero-width char, quoted URL userinfo, | -> %3D separators', () => {
  for (const s of [`fix: Bearer\u200b${H}`, `fix: see https://u:"${H}"@h/p`, `fix: see https://u:'${H}'@h/p`, `fix: token|${H}`, `fix: x-api-key->${H}`, `fix: secret%3D${H}`])
    expect(leaks(one(s))).toBe(false)
})

test('benign subjects stay readable after unicode folding', () => {
  expect(one('fix(auth): refresh expiry off by one')[0].task).toBe('auth: refresh expiry off by one')
  expect(one('fix(auth): refresh token expiry off by one (#42)')[0].task).toBe('auth: refresh token expiry off by one')
})
