// Stronger secret filter (full steps send real tool input/output): known prefixes, PEM private keys, .env lines with a secret-like key,
// credential URLs without a scheme, high-entropy strings. New rules write `[redacted:<kind>]`; the 8.1.3 rules keep `[redacted]`.
import { expect, test } from 'claude-code/testing'
import { NORMAL, PII_NORMAL, PII_SECRETS, SECRETS } from './fixtures/secret_cases.ts'
import { deepRedact, redact, secretKeyCache, shannon } from '../lib/redact.ts'

test('fixture size: >= 30 secret forms, >= 30 normal code/log lines', () => {
  expect(SECRETS.length).toBeGreaterThanOrEqual(30)
  expect(NORMAL.length).toBeGreaterThanOrEqual(30)
})
for (const [kind, text, secret] of SECRETS)
  test(`secret gone [${kind}]: ${text.slice(0, 24).replace(/\n/g, ' ')}…`, () => {
    const r = redact(text)
    expect(r.includes(secret)).toBe(false)
    expect(r.includes('[redacted')).toBe(true)
  })
test('false positives on the normal fixture: 0 (git SHAs, UUIDs, pattern ids, paths, data-URI images, integrity hashes stay)', () => {
  const fp = NORMAL.filter(x => redact(x) !== x)
  expect(fp).toEqual([])
})
for (const name of ['aws', 'google', 'gitlab', 'stripe', 'huggingface', 'private-key'])
  test(`prefix rule ${name} labels its own kind (not masked by the entropy rule)`, () => {
    const cases = SECRETS.filter(([k, text]) => k === 'prefix:' + name && (name !== 'aws' || text.includes('session')))
    expect(cases.length).toBeGreaterThan(0)
    for (const [, text] of cases) expect(redact(text).includes(`[redacted:prefix:${name}]`)).toBe(true)
  })
test('new rules label their kind', () => {
  const one = (k: string) => SECRETS.find(([kind]) => kind === k)!
  for (const [k, label] of [['prefix:google', '[redacted:prefix:google]'], ['prefix:aws', '[redacted'], ['prefix:private-key', '[redacted:prefix:private-key]'],
    ['env', '[redacted:env]'], ['url-cred', '[redacted'], ['entropy', '[redacted:entropy]']] as [string, string][])
    expect([k, redact(one(k)[1]).includes(label)]).toEqual([k, true])
  expect(redact('AUTH_SALT=abc123xyz')).toBe('AUTH_SALT=[redacted:env]')
  expect(redact('redis at admin:pw1234@cache.example.org')).toBe('redis at admin:[redacted:url-cred]@cache.example.org')
  expect(redact('-----BEGIN EC PRIVATE KEY-----\nMHcCAQEE\n-----END EC PRIVATE KEY-----\nrest')).toBe('[redacted:prefix:private-key]\nrest')
  expect(redact('-----BEGIN PRIVATE KEY-----\nMHcCAQEE no end')).toBe('[redacted:prefix:private-key]')  // fail closed: to the text end
})
test('ids the trace relies on are never touched: retrieval/pattern UUIDs, commit SHAs, ctx ids', () => {
  for (const x of ['df8abbe2-f788-4f32-8e3b-8b39cd5ae322', '70c1624', '844a5f1c3d2e1f00aa11bb22cc33dd44ee55ff66', 'ctx-1916239599-9c56', '2b0a4b98-97e9-5cdc-9dc4-745a52ff2bb7'])
    expect(redact(`id ${x} done`)).toBe(`id ${x} done`)
})
test('shannon entropy helper', () => {
  expect(shannon('aaaa')).toBe(0)
  expect(shannon('abcd')).toBe(2)
})
test('the new rules stay linear on hostile 2 MB inputs (< 2 s each)', () => {
  for (const big of ['A1b2'.repeat(500_000), 'user:'.repeat(400_000), 'X_AUTH='.repeat(300_000), '-----BEGIN PRIVATE KEY-----'.repeat(70_000), ('a'.repeat(19) + ' ').repeat(100_000)]) {
    const t0 = Date.now()
    redact(big)
    expect(Date.now() - t0).toBeLessThan(2000)
  }
})
test('C3: .env lines are found behind a tool prefix (Read/cat -n numbers, grep -n file:line:, YAML "- "), labelled env', () => {
  const pre = SECRETS.filter(([k, text]) => k === 'env' && /^(\s*\d+[\t→]|[^\s:]+:\d+:|\s*- )/.test(text))
  expect(pre.length).toBe(4)
  for (const [, text, secret] of pre) expect([text.slice(0, 20), redact(text).includes('[redacted:env]'), redact(text).includes(secret)]).toEqual([text.slice(0, 20), true, false])
  expect(redact('  12\tAUTHOR=dev team')).toBe('  12\tAUTHOR=dev team')   // the harmless-key rules hold behind a prefix too
})
for (const kind of ['netrc', 'pgpass', 'docker-auth', 'cookie-jar', 'php-define'])
  test(`F4: ${kind} is found by its own rule (label [redacted:${kind}])`, () => {
    const cases = SECRETS.filter(([k]) => k === kind)
    expect(cases.length).toBeGreaterThan(0)
    for (const [, text, secret] of cases) expect([redact(text).includes(`[redacted:${kind}]`), redact(text).includes(secret)]).toEqual([true, false])
  })
test('F4: the new format rules stay linear on hostile 2 MB inputs (< 2 s each)', () => {
  for (const big of ['machine x login y '.repeat(120_000), 'a:1:b:c:'.repeat(250_000), '"auth": "'.repeat(200_000), 'd\tTRUE\t/\tTRUE\t1\tn\t'.repeat(100_000), "define('A_KEY', '".repeat(120_000)]) {
    const t0 = Date.now()
    redact(big)
    expect(Date.now() - t0).toBeLessThan(2000)
  }
})

// ---- Shopify (Round 7): shpat_ / shpca_ / shppa_ / shpss_ + >= 32 hex (either case); same rule as ace_after_task.py ----
test('Shopify (Round 7): all 8 fixture tokens become [redacted:prefix:shopify], no hex rest after the label', () => {
  const cases = SECRETS.filter(([k]) => k === 'prefix:shopify')
  expect(cases.length).toBe(9)  // round 8 I2: + one after a non-ASCII letter
  for (const [, text, secret] of cases) {
    const r = redact(text)
    // a token behind a secret key / header (JSON access_token, X-Shopify-Access-Token) goes by the older key rule ('[redacted]')
    const labelled = !text.toLowerCase().replace(/-/g, '_').includes('access_token')
    expect([r.includes('[redacted:prefix:shopify]'), r.includes(secret), /\[redacted[^\]]*\][0-9a-fA-F]/.test(r)]).toEqual([labelled, false, false])
  }
})

// a literal copy of ENV_SEGS / ENV_HARMLESS on purpose: a row dropped from the table turns this red
test('every .env key segment redacts on its own; a harmless last segment keeps the line', () => {
  expect(['SALT', 'SIGNING', 'DSN', 'PRIVATE', 'AUTH', 'CRED', 'CREDS', 'CERT', 'SEED', 'SIG', 'SIGNATURE', 'HMAC', 'ENCRYPTION', 'OTP', 'PASS', 'PWD', 'ACCESS', 'SESSION'].filter(x => !redact(`X_${x}=abc123`).includes('[redacted'))).toEqual([])
  expect(['TIMEOUT', 'MINUTES', 'SECONDS', 'TTL', 'URL', 'HOST', 'PORT', 'NAME', 'USER', 'ID', 'ENABLED', 'MODE', 'LEVEL', 'PATH', 'DIR', 'FILE', 'COUNT', 'MAX', 'MIN', 'LIMIT'].filter(x => redact(`X_AUTH_${x}=abc123`) !== `X_AUTH_${x}=abc123`)).toEqual([])
})

// a keyword-flag rule (mysql -p, zip -P, openssl -k, curl -u) needs both on ONE line (lazySearch skips a line without the flag)
test('a keyword and its flag on different lines redact nothing', () => {
  for (const t of ['mysql x\n -p secret', 'zip a\n -P pw', 'openssl x\n -k pw', 'curl x\n -u a:b']) expect(redact(t)).toBe(t)
})

// ---- deepRedact (moved from full_steps.test.ts) ----
test('I4: secretKey is memoised (a repeated key costs one redact)', () => {
  secretKeyCache.clear()
  for (let i = 0; i < 100; i++) deepRedact({ password: 'x', api_key: 'y', path: '/a' })
  expect(secretKeyCache.size).toBe(3)
})
// ---- Round 10 / M3: deepRedact: an object {name|key: <secret name>, value: x} has its value redacted (MCP HTTP headers, env arrays) ----
test('Round 10 / M3: name/value objects with a secret name lose the value; harmless names stay', () => {
  const r = deepRedact({ headers: [{ name: 'Authorization', value: 'Basic dXNlcjpodW50ZXIy' }, { name: 'Accept', value: 'application/json' }],
    env: [{ name: 'DB_PASSWORD', value: 'hunter2hunter2' }, { key: 'client_secret', value: 'cs-abc' }, { name: 'LOG_LEVEL', value: 'debug' }] })
  expect(r).toEqual({ headers: [{ name: 'Authorization', value: '[redacted]' }, { name: 'Accept', value: 'application/json' }],
    env: [{ name: 'DB_PASSWORD', value: '[redacted]' }, { key: 'client_secret', value: '[redacted]' }, { name: 'LOG_LEVEL', value: 'debug' }] })
})

// ---- linear on long / hostile inputs (moved from full_steps.test.ts and outcome.test.ts) ----
test('redaction stays linear on long outputs with many secrets (2 MB, 20k key lines)', () => {
  const big = 'token: abc\n\nplain line here\n'.repeat(20_000)  // a blank line ends each block value + 'x'.repeat(1_500_000)
  const t0 = Date.now()
  const r = redact(big)
  expect(r.includes('abc')).toBe(false)
  expect(r.split('[redacted]').length - 1).toBe(20_000)
  expect(Date.now() - t0).toBeLessThan(5000)
})

test('redaction of --password-stdin / --with-token stdin bodies stays linear on hostile 200 KB inputs (< 2 s each)', () => {
  const n = 200_000
  const texts = ['<<< a '.repeat(n / 6) + '\n--password-stdin', '<<< a '.repeat(n / 6), '<'.repeat(n) + '\n--with-token', 'x --with-token <<'.repeat(n / 17),
    '--password-stdin <<E\n' + 'a\n'.repeat(n / 2), '--with-token ' + '<<< "'.repeat(n / 5),
    'a \\\n'.repeat(n / 4) + '--with-token', '<<< $(\n'.repeat(n / 7) + '--with-token']
  for (const t of texts) {
    const t0 = performance.now()
    redact(t)
    expect(performance.now() - t0).toBeLessThan(2000)  // linear is ~15 ms; a quadratic regression takes tens of seconds
  }
})

// ---- Round 12 / I3.1: the JSON name/value rule on long one-line JSON (unrolled value group; the old `(?:[^"\\\n]|\\.)*` was
// ~350x slower in JSC and stopped matching above ~540k chars: fail-open) ----
const nvPair = (v: string) => '{"name": "API_KEY", "value": "' + v + '"}'
test('Round 12 / I3.1: a 4 MB one-line JSON with 40 name/value pairs stays linear and every value goes', () => {
  const big = '[' + Array.from({ length: 40 }, () => nvPair('a'.repeat(100_000))).join(', ') + ']'
  const t0 = performance.now()
  const r = redact(big)
  expect(performance.now() - t0).toBeLessThan(2000)
  expect([r.split('[redacted:name-value]').length - 1, r.includes('a'.repeat(1000))]).toEqual([40, false])
})
test('Round 12 / I3.1: a 600k-char API_KEY value is redacted (no fail-open above ~540k)', () => {
  const r = redact(nvPair('x'.repeat(600_000)))
  expect([r.includes('[redacted:name-value]'), r.includes('x'.repeat(1000))]).toEqual([true, false])
})

// ---- Round 13: PII layer (email, phone, IBAN, key context); labels [redacted:email|phone|iban]; after the secret / url-cred /
// name-value rules, before entropy. Fixture: cases.json "pii" (recipes; random or reserved domains; the only IBAN is the official example) ----
for (const [kind, text, secret] of PII_SECRETS)
  test(`Round 13 PII gone and labelled [${kind}]: ${text.slice(0, 28).replace(/\n/g, ' ')}…`, () => {
    const r = redact(text)
    expect([r.includes(secret), r.includes(`[redacted:${kind.split(':')[1]}]`)]).toEqual([false, true])
  })
test('Round 13: the PII negative fixture carries no PII label', () => {
  expect(PII_NORMAL.filter(x => /\[redacted:(?:email|phone|iban)\]/.test(redact(x)))).toEqual([])
})
test('Round 13: exceptions and documented limits', () => {
  expect(redact('ssh ubuntu@host.example.net')).toBe('ssh ubuntu@host.example.net')      // reserved example domain
  expect(redact('ssh ubuntu@host.acme-corp.io')).toBe('ssh [redacted:email]')            // ssh target without a path = an e-mail
  expect(redact('user@host.acme-corp.io:/srv/x')).toBe('user@host.acme-corp.io:/srv/x')  // SCP form with a path stays
  expect(redact('x //bob@acme-corp.io')).toBe('x //bob@acme-corp.io')                    // URL userinfo position stays
  // the diff-constant limit, documented: '+' + 11-15 digits with a valid country code and no separator IS redacted (a false alarm on
  // such diff lines); 8-10 digits without a separator are not
  expect(redact('+123456789012')).toBe('[redacted:phone]')
  expect(redact('+1234567890')).toBe('+1234567890')
  expect(redact('+28 123 456 789')).toBe('+28 123 456 789')    // neither 2, 28 nor 281 is a country code (ITU E.164)
  expect(redact('+422 123 456 789')).toBe('+422 123 456 789')  // 422 is spare
  expect(redact('+423 123 456 789')).toBe('[redacted:phone]')  // Liechtenstein
  expect(redact('030 1234567')).toBe('030 1234567')            // a bare national number without context: known limit
})
const iban = (cc: string, bban: string) => {
  const n = [...bban + cc + '00'].map(ch => parseInt(ch, 36).toString()).join('')
  let m = 0; for (const d of n) m = (m * 10 + Number(d)) % 97
  return cc + String(98 - m).padStart(2, '0') + bban
}
test('Round 13: IBAN checksum and length per country', () => {
  expect(iban('DE', '370400440532013000')).toBe('DE89370400440532013000')  // the official example, checksum computed here
  expect(redact('x ' + iban('DE', '370400440532013000') + ' y')).toBe('x [redacted:iban] y')
  expect(redact('x ' + iban('DE', '3704004405320130001') + ' y').includes('[redacted:iban]')).toBe(false)  // valid checksum, DE needs 22
  expect(redact('x ' + iban('NL', 'ABNA0417164300') + ' y')).toBe('x [redacted:iban] y')                 // NL 18
  expect(redact('x DE89370400440532013001 y')).toBe('x DE89370400440532013001 y')                      // wrong checksum
})
test('Round 13: deepRedact PII keys', () => {
  expect(deepRedact({ email: 'dev at host', Mail: 'ops@intranet', phone: 491701234567, Tel: '+49 30 1234 5678', iban: 'XX12 3456', fax: true, mobile: 'n/a', note: 'x' }))
    .toEqual({ email: 'dev at host', Mail: '[redacted:email]', phone: '[redacted:phone]', Tel: '[redacted:phone]', iban: '[redacted:iban]', fax: true, mobile: 'n/a', note: 'x' })
})
const R13_HOSTILE: Record<string, string> = { dot_chain: 'a@' + 'a.'.repeat(100_000) + '1', long_local: 'a@' + 'a'.repeat(1_000_000), many_at: 'a@b.'.repeat(1_000_000),
  many_plus: '+1 '.repeat(1_300_000), digit_run: '+' + '1'.repeat(4_000_000), upper_run: 'AB12' + 'C'.repeat(4_000_000), kw_spam: 'tel '.repeat(1_000_000),
  key_spam: 'phone: '.repeat(570_000), real_emails: 'x@acme-corp.io '.repeat(280_000), iban_spam: 'DE89 3704 0044 0532 0130 00 '.repeat(140_000) }
for (const [k, v] of Object.entries(R13_HOSTILE))
  test(`Round 13: the PII layer stays linear on hostile input: ${k}`, () => {
    const t0 = performance.now()
    redact(v)
    expect(performance.now() - t0).toBeLessThan(2000)
  })

