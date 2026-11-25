// Stronger secret filter (full steps send real tool input/output): known prefixes, PEM private keys, .env lines with a secret-like key,
// credential URLs without a scheme, high-entropy strings. New rules write `[redacted:<kind>]`; the 8.1.3 rules keep `[redacted]`.
import { expect } from 'claude-code/testing'
import { test } from './t.ts'
import { NORMAL, PII_NORMAL, PII_SECRETS, SECRETS } from './fixtures/secret_cases.ts'
import { expectLinear, prefix } from './timing.ts'
import { deepRedact, redact, secretKeyCache, shannon } from '../lib/redact.ts'
import { IBAN_LEN } from '../lib/redact_rules.ts'

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
test('the new rules stay linear on hostile 2 MB inputs (scaling at equal work, see timing.ts)', { timeoutMs: 120_000 }, () => {
  for (const big of ['A1b2'.repeat(500_000), 'user:'.repeat(400_000), 'X_AUTH='.repeat(300_000), '-----BEGIN PRIVATE KEY-----'.repeat(70_000), ('a'.repeat(19) + ' ').repeat(100_000)])
    expectLinear(prefix(big), redact, big.slice(0, 12))
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
test('F4: the new format rules stay linear on hostile 2 MB inputs (scaling at equal work, see timing.ts)', { timeoutMs: 120_000 }, () => {
  for (const big of ['machine x login y '.repeat(120_000), 'a:1:b:c:'.repeat(250_000), '"auth": "'.repeat(200_000), 'd\tTRUE\t/\tTRUE\t1\tn\t'.repeat(100_000), "define('A_KEY', '".repeat(120_000)])
    expectLinear(prefix(big), redact, big.slice(0, 12))
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
test('redaction stays linear on long outputs with many secrets (2 MB, 20k key lines)', { timeoutMs: 120_000 }, () => {
  const mk = (frac: number) => 'token: abc\n\nplain line here\n'.repeat(Math.floor(20_000 * frac))  // a blank line ends each block value
  const r = redact(mk(1))
  expect(r.includes('abc')).toBe(false)
  expect(r.split('[redacted]').length - 1).toBe(20_000)
  expectLinear(mk, redact)
})

test('redaction of --password-stdin / --with-token stdin bodies stays linear on hostile 200 KB inputs (scaling at equal work, see timing.ts)', { timeoutMs: 120_000 }, () => {
  // built at n (full: 200 KB) so the trigger flag stays at the tail of every size
  const texts: ((n: number) => string)[] = [n => '<<< a '.repeat(n / 6) + '\n--password-stdin', n => '<<< a '.repeat(n / 6), n => '<'.repeat(n) + '\n--with-token', n => 'x --with-token <<'.repeat(n / 17),
    n => '--password-stdin <<E\n' + 'a\n'.repeat(n / 2), n => '--with-token ' + '<<< "'.repeat(n / 5),
    n => 'a \\\n'.repeat(n / 4) + '--with-token', n => '<<< $(\n'.repeat(n / 7) + '--with-token']
  texts.forEach((t, i) => expectLinear(f => t(Math.floor(200_000 * f)), redact, `stdin ${i}`))  // linear is ~15 ms; a quadratic regression takes tens of seconds
})

// ---- Round 12 / I3.1: the JSON name/value rule on long one-line JSON (unrolled value group; the old `(?:[^"\\\n]|\\.)*` was
// ~350x slower in JSC and stopped matching above ~540k chars: fail-open) ----
const nvPair = (v: string) => '{"name": "API_KEY", "value": "' + v + '"}'
test('Round 12 / I3.1: a 4 MB one-line JSON with 40 name/value pairs stays linear and every value goes', { timeoutMs: 120_000 }, () => {
  const big = '[' + Array.from({ length: 40 }, () => nvPair('a'.repeat(100_000))).join(', ') + ']'
  const r = redact(big)
  expectLinear(f => '[' + Array.from({ length: Math.floor(40 * f) }, () => nvPair('a'.repeat(100_000))).join(', ') + ']', redact)
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
// Round 18b / B2: key values that made the IBAN-shaped value alternative backtrack (Opus hostile18 seeds, 1 MB each)
const R18_KEY_SEEDS: Record<string, string> = { run40: 'iban: DE12' + 'A'.repeat(40) + ' ', run33: 'iban: DE12' + 'A'.repeat(33) + ' ', run33_x: 'iban=DE12' + 'AB1'.repeat(11) + 'Z\n',
  mixed: 'iban: DE12' + 'A1B2'.repeat(10) + '/x ', short: 'iban: DE12ABCDABCDABCD-x ', sp: 'iban: DE12 ABCD ABCD ABCD ABCD ABCD ABCD ABCD ABCDX ', mail: 'mail=AB12' + 'C'.repeat(40) + ' ',
  tel: 'tel: AB12' + 'C1'.repeat(20) + ';x ' }
const R13_HOSTILE: Record<string, string> = { ...Object.fromEntries(Object.entries(R18_KEY_SEEDS).map(([k, s]) => ['key_' + k, s.repeat(Math.ceil(1_000_000 / s.length)).slice(0, 1_000_000)])),
  dot_chain: 'a@' + 'a.'.repeat(100_000) + '1', long_local: 'a@' + 'a'.repeat(1_000_000), many_at: 'a@b.'.repeat(1_000_000),
  many_plus: '+1 '.repeat(1_300_000), digit_run: '+' + '1'.repeat(4_000_000), upper_run: 'AB12' + 'C'.repeat(4_000_000), kw_spam: 'tel '.repeat(1_000_000),
  key_spam: 'phone: '.repeat(570_000), real_emails: 'x@acme-corp.io '.repeat(280_000), iban_spam: 'DE89 3704 0044 0532 0130 00 '.repeat(140_000) }
for (const [k, v] of Object.entries(R13_HOSTILE))
  test(`Round 13: the PII layer stays linear on hostile input: ${k}`, { timeoutMs: 120_000 }, () => {
    expectLinear(prefix(v), redact)
  })

// ---- Round 14 (review of the PII layer): suffix keys, spaced values behind a key, file-name / date / IP / decimal false alarms, no
// 'call' keyword, prototype-safe lookups, float parity. Fixture cases: cases.json "pii" (appended) ----
test('Round 14: prototype keys are no PII keys; floats are read as JS numbers', () => {
  const d = JSON.parse('{"__proto__": "1234567", "constructor": "abc", "toString": "x", "hasOwnProperty": "0301234567"}')
  expect(deepRedact(d)).toEqual(d)
  expect(deepRedact({ phone: 12345.0 })).toEqual({ phone: 12345 })
  expect(deepRedact({ phone: 1234567.0, Phone_Number: 30123456 })).toEqual({ phone: '[redacted:phone]', Phone_Number: '[redacted:phone]' })
  expect(deepRedact({ phoneNumber: '030 1234567', mobile_no: '0151 1234 5678', telNr: 'x' })).toEqual({ phoneNumber: '[redacted:phone]', mobile_no: '[redacted:phone]', telNr: 'x' })
})
test('Round 14: documented limits', () => {
  expect(redact('0049 30 1234567')).toBe('0049 30 1234567')                          // 00-prefix without a keyword
  expect(redact('user@host.acme-corp.io:8080')).toBe('user@host.acme-corp.io:8080')  // host:port reads as the SCP form
  expect(redact('+49\u00a030\u00a01234567')).toBe('[redacted:phone]')                    // NBSP as a separator (optional fix 8)
  expect(redact('Tel.:\u00a0030\u00a01234567')).toBe('Tel.:\u00a0[redacted:phone]')
})
const R14_HOSTILE: Record<string, string> = { suffix_spam: 'Telefonnummer '.repeat(300_000), spaced_key: 'iban: de89 '.repeat(360_000),
  spaced_key2: 'phone_number: 1 2 3 4 5 6 7 8 9 '.repeat(125_000), file_at: 'logo@2x.png '.repeat(330_000), date_plus: '+2026-11-24 10:00:00 '.repeat(190_000) }
for (const [k, v] of Object.entries(R14_HOSTILE))
  test(`Round 14: linear on hostile input: ${k}`, { timeoutMs: 120_000 }, () => {
    expectLinear(prefix(v), redact)
  })

// ---- Round 15 (review of round 14): IBAN groups without a digit and lower case, German deepRedact keys and arrays under a PII key,
// German compound keywords, more date / CIDR rejects, narrow spaces. Fixture: cases.json "pii" ----
test('Round 15: a keyed IBAN stops at its country length', () => {
  expect(redact('iban: gb00 west 1234 5698 7654 32 and more')).toBe('iban: [redacted:iban] and more')
  expect(redact('iban: gb82 west 1234 5698 7654 32 and more')).toBe('iban: [redacted:iban] and more')
  expect(redact('iban: xq12 abcd efgh and more')).toBe('iban: [redacted:iban] and more')  // Round 16 / I1: unknown country: all groups
})
test('Round 15: deepRedact German keys and arrays under a PII key', () => {
  const P = '[redacted:phone]'
  expect(deepRedact({ telefon: '030 1234567', Telefonnummer: '030 1234567', handynummer: '0151 12345678', mobil: '0151 12345678', rufnummer: '030 1234567',
    whatsapp: '0151 12345678', mobilnummer: '0151 12345678', 'handy-nr': '0151 1234567', phone: ['030 1234567', ['0151 2345678', { n: 301234567 }], 'n/a'],
    iban: ['de89 3704 0044 0532 0130 00'], fax: { n: '0301234567' }, mobile: [1234567, true, null] }))
    .toEqual({ telefon: P, Telefonnummer: P, handynummer: P, mobil: P, rufnummer: P, whatsapp: P, mobilnummer: P, 'handy-nr': P,
      phone: [P, [P, { n: P }], 'n/a'], iban: ['[redacted:iban]'], fax: { n: P }, mobile: [P, true, null] })
})
const R15_HOSTILE: Record<string, string> = { prefix_spam: 'Mobiltelefonnummer '.repeat(220_000), prefix_nostem: 'Firmenhandyxyzabcde '.repeat(200_000),
  iban_lower: 'gb82 west '.repeat(400_000), iban_key_words: 'iban: gb00 west 1234 and more '.repeat(130_000), dates_plus: '+24.11.2026 10:00:00 '.repeat(190_000) }
for (const [k, v] of Object.entries(R15_HOSTILE))
  test(`Round 15: linear on hostile input: ${k}`, { timeoutMs: 120_000 }, () => {
    expectLinear(prefix(v), redact)
  })
// ---- Round 16 (review of round 15): an unkeyed IBAN is cut to its country length before the checks, NBSP / tab in an IBAN, keyword
// keys in deepRedact, English '...phone' keys, dotted numbers behind 'Tel/', 'cell' only with ':' / '#' / 'no', a keyed IBAN that does
// not validate loses all its groups, an address with a real TLD before '(' / '[' ----
const iban16 = (cc: string, n: number) => {
  const bban = Array.from({ length: n - 4 }, (_, i) => String((i * 7 + 3) % 10)).join('')
  let m = 0; for (const d of [...bban + cc + '00'].map(ch => parseInt(ch, 36).toString()).join('')) m = (m * 10 + Number(d)) % 97
  return cc + String(98 - m).padStart(2, '0') + bban
}
test('Round 16: every IBAN country, compact and spaced, with a following word: the IBAN goes, the word stays', () => {
  const leaks: string[] = []
  for (const [cc, n] of Object.entries(IBAN_LEN)) {
    const iban = iban16(cc, n), spaced = iban.match(/.{1,4}/g)!.join(' ')
    for (const form of [iban, spaced]) for (const follow of [' bis', ' BANK', ' 1', '.', ', ok', ' und mehr'])
      if (redact('Konto ' + form + follow) !== 'Konto [redacted:iban]' + follow) leaks.push(form + follow)
  }
  expect(leaks).toEqual([])
})
test('Round 16: words after an IBAN stay; a keyed IBAN that does not validate loses all its groups', () => {
  expect(redact('Bitte ueberweisen an AT61 1904 3002 3457 3201 bis Freitag')).toBe('Bitte ueberweisen an [redacted:iban] bis Freitag')
  expect(redact('iban: GB82 WEST 1234 5698 7654 3 and more')).toBe('iban: [redacted:iban] and more')
  expect(redact('iban: xyz and more')).toBe('iban: xyz and more')
  expect(redact('iban: xq12 abcd efgh and more')).toBe('iban: [redacted:iban] and more')
})
test('Round 16: keyword and ...phone keys, cell, dotted numbers, addresses before ( / [', () => {
  const P = '[redacted:phone]'
  expect(deepRedact({ festnetz: '030 1234567', Mobiltelefon: '0151 12345678', Diensthandy: '0151 12345678', Firmenhandy: '0151 12345678', Mobilfunknummer: '0151 12345678',
    cell: '415 555 0123', cellphone: '415 555 0123', MobilePhone: '0151 12345678', HomePhone: '030 1234567', phoneNumbers: ['030 1234567'], home_phone: '030 1234567',
    phone2: '030 1234567', phones: [{ value: '030 1234567' }], iPhone: '15 Pro', cells: '030 1234567' }))
    .toEqual({ festnetz: P, Mobiltelefon: P, Diensthandy: P, Firmenhandy: P, Mobilfunknummer: P, cell: P, cellphone: P, MobilePhone: P, HomePhone: P,
      phoneNumbers: [P], home_phone: P, phone2: P, phones: [{ value: P }], iPhone: '15 Pro', cells: '030 1234567' })
  expect(redact('cell size 1000000 bytes')).toBe('cell size 1000000 bytes')
  expect(redact('Cell: 415 555 0123')).toBe('Cell: ' + P)
  expect([redact('Tel/089.1234.5678'), redact('WhatsApp/2.23.20.0 Android')]).toEqual(['Tel/' + P, 'WhatsApp/2.23.20.0 Android'])
  expect([redact('jane.doe@firma.de(Vertrieb)'), redact('q@k.transpose(-1)'), redact('x@y.name(arg)')]).toEqual(['[redacted:email](Vertrieb)', 'q@k.transpose(-1)', 'x@y.name(arg)'])
})
// ---- Round 17 (review of round 16 / C1'): an unkeyed IBAN is found by a scan over start candidates that walks exactly the country
// length (no group regex): two IBANs in a row, a 'CC+2 digits' token before it, tab columns; Telefax / Fon / Durchwahl, phone_2 ----
const iban17 = (cc: string, n: number, k: number) => {
  const bban = Array.from({ length: n - 4 }, (_, i) => k && i < 4 ? 'ABCDEFGHJK'[(i * 3 + k) % 10] : String((i * (5 + k) + 3 + k) % 10)).join('')
  let m = 0; for (const d of [...bban + cc + '00'].map(ch => parseInt(ch, 36).toString()).join('')) m = (m * 10 + Number(d)) % 97
  return cc + String(98 - m).padStart(2, '0') + bban
}
test('Round 17: every country, two IBANs in a row, a lead token, a follow form: no IBAN survives', () => {
  const seps = [null, ' ', '\t', '\u00a0'], mids = [' ', '\t', ' oder ', ' IBAN ', ', ', ' / ', ' neue ']
  const leads = ['', 'KW47 ', 'Re24 ', 'AB12 ', 'DE00 ', 'Nr12 ', 'IBAN ', 'Zahlung KW47: '], follows = ['', ' bis', ' 1234', '.', ' BANK', '\tBerlin']
  const render = (iban: string, sep: string | null, lower: boolean) => { const t = sep === null ? iban : iban.match(/.{1,4}/g)!.join(sep); return lower ? t.toLowerCase() : t }
  const strip = (s: string) => s.replace(/[^A-Za-z0-9]/g, '').toUpperCase(), ccs = Object.keys(IBAN_LEN).sort(), I = '[redacted:iban]'
  const leaks: string[] = [], off: string[] = []
  let n = 0
  const check = (t: string, ibans: string[], want: string) => {
    n++; const o = redact(t)
    if (ibans.some(i => strip(o).includes(i) || strip(o).includes(i.slice(-8)))) leaks.push(t)
    else if (o !== want) off.push(o)
  }
  ccs.forEach((cc, x) => {
    const b = ccs[(x * 7 + 1) % ccs.length]
    seps.forEach((sep, y) => mids.forEach((mid, z) => {
      const i1 = iban17(cc, IBAN_LEN[cc], (y + z) % 2), i2 = iban17(b, IBAN_LEN[b], (y + z + 1) % 2)
      const lead = leads[(x + y + z) % leads.length], follow = follows[(x + z) % follows.length]
      check(lead + render(i1, sep, z % 3 === 1) + mid + render(i2, sep, z % 3 === 2) + follow, [i1, i2], lead + I + mid + I + follow)
    }))
    leads.forEach((lead, y) => follows.forEach((follow, z) => {
      const i1 = iban17(cc, IBAN_LEN[cc], z % 2)
      check(lead + render(i1, seps[(y + z) % 4], false) + follow, [i1], lead + I + follow)
    }))
  })
  expect([n, leaks]).toEqual([89 * 76, []])
  expect(off.every(o => o.startsWith(I)) && off.length <= Math.floor(n / 97)).toBe(true)  // a lead + first groups validating by chance
})
test('Round 17: review examples, boundaries, Telefax / Fon / Durchwahl, digit suffix on phone keys', () => {
  const I = '[redacted:iban]', P = '[redacted:phone]', AT = 'AT61 1904 3002 3457 3201', DE = 'DE89 3704 0044 0532 0130 00', ATc = AT.replace(/ /g, '')
  expect(redact(`Max\t${AT}\t${DE}\tBerlin`)).toBe(`Max\t${I}\t${I}\tBerlin`)
  expect(redact(`Bitte auf ${AT} oder ${DE} ueberweisen`)).toBe(`Bitte auf ${I} oder ${I} ueberweisen`)
  expect(redact(`IBAN alt ${AT} neue ${DE}`)).toBe(`IBAN alt ${I} neue ${I}`)
  expect(redact(`iban: ${AT} oder ${DE}`)).toBe(`iban: ${I} oder ${I}`)
  expect(redact(`Zahlung KW47 ${DE} danke`)).toBe(`Zahlung KW47 ${I} danke`)
  expect([redact('Re24 ' + ATc), redact(AT + ' oder 12345')]).toEqual(['Re24 ' + I, I + ' oder 12345'])
  expect(redact('AE41 ABCD NO93 8601 1117 947 x')).toBe(I + ' x')  // a valid IBAN inside a found one: the scan goes on after the end
  expect([redact('AB12' + ATc), redact(ATc + 'X'), redact('AT61  1904 3002 3457 3201')]).toEqual(['AB12' + ATc, ATc + 'X', 'AT61  1904 3002 3457 3201'])
  for (const t of ['Telefax: 089 1234567', 'Telefax 089/1234567', 'Fon: 089 1234567', 'Fon 089 1234567', 'Durchwahl: 089 1234-567'])
    expect(redact(t)).toBe(t.slice(0, t.indexOf('0')) + P)
  expect([redact('Fonds 1234567'), redact('cell_2 = 1234567')]).toEqual(['Fonds 1234567', 'cell_2 = 1234567'])
  expect([redact('phone_2: 0151 12345678'), redact('telefon2: 0151 12345678'), redact('fax2: 089 1234567'), redact('phone12: 0151 12345678')])
    .toEqual(['phone_2: ' + P, 'telefon2: ' + P, 'fax2: ' + P, 'phone12: ' + P])
  expect(deepRedact({ Telefax: '089 1234567', fon: '089 1234567', Durchwahl: '1234567', phone_2: '030 1234567', telefon2: '030 1234567', fax2: '030 1234567', cell_2: '1234567', font: '1234567' }))
    .toEqual({ Telefax: P, fon: P, Durchwahl: P, phone_2: P, telefon2: P, fax2: P, cell_2: '1234567', font: '1234567' })
})
// ---- Round 18 (review of round 17): a phone number behind a bare 'call' (B1), a digit suffix on every PII key stem (N2), an
// IBAN-shaped key value ends at a value end (N3) ----
test('Round 18: call before a phone number, code numbers after call stay, iban2 / email2 / mail1, IBAN key value end', () => {
  const P = '[redacted:phone]', I = '[redacted:iban]', E = '[redacted:email]'
  expect([redact('Please call 030 1234567 tomorrow'), redact('Call: (415) 555-0123'), redact('call our hotline 0800 1234567'), redact('call the customer at 0151 23456789')])
    .toEqual(['Please call ' + P + ' tomorrow', 'Call: (' + P, 'call our hotline ' + P, 'call the customer at ' + P])
  expect([redact('call 015112345678'), redact('call 1-800-555-0123')]).toEqual(['call ' + P, 'call ' + P])
  expect([redact('call 4155550123'), redact('API call 12345678 ok')]).toEqual(['call ' + P, 'API call 12345678 ok'])
  for (const t of ['call(123456)', 'call timeout 123456', 'call(timeout=123456)', 'tool call took 1234567 ns', 'API call 1234567 ok', 'call used 1234567 bytes',
    'call ratio 123/456', 'tool call: redact.py:1234-5678', 'call with timeout: 12345678 ms']) expect(redact(t)).toBe(t)
  expect([redact('iban2: DE89 3704 0044 0532 0130 00'), redact('email2: max.mustermann@firma.de'), redact('IBAN10: XX12 3456'), redact('mail1=0301234567')])
    .toEqual(['iban2: ' + I, 'email2: ' + E, 'IBAN10: ' + I, 'mail1=0301234567'])
  expect([redact('iban: DE893704.0044.0532.0130.00'), redact('iban: Re24089.1234.5678'), redact('iban: AT61 1904 3002 3457 3201 oder 12')])
    .toEqual(['iban: ' + I, 'iban: ' + I, 'iban: ' + I + ' oder 12'])
  expect(deepRedact({ iban2: 'DE89 3704 0044 0532 0130 00', email_1: 'max@firma.de' })).toEqual({ iban2: I, email_1: E })
})
// ---- Round 18b (review of round 18): a bare 'call' no longer swallows a following phone keyword, file-name exception only for a
// line range, dates / code words after 'call', 'call  me'; the IBAN-shaped key value alternative is linear again (B2) ----
test('Round 18b: call before another phone keyword, dates and code words after call', () => {
  const red: [string, string][] = [['Call or WhatsApp 91234567', '91234567'], ['call/whatsapp 91234567', '91234567'], ['call or fax 5550123', '5550123'],
    ['Please call my phone number 5550123', '5550123'], ['call mobile 87654321', '87654321'], ['Call Anna (mobile): 5550123', '5550123'], ['Call/Tel. 5550123', '5550123'],
    ['Call (mobil): 299839', '299839'], ['call Tel.Nr:0301234567', '0301234567'], ['call me 5550123', '5550123'], ['call  me 5550123', '5550123'], ['Call:555-0123', '555-0123'],
    ['call timeout 030 1234567', '030 1234567'], ['call(0301234567)', '0301234567'], ['Call Dr.Meier:0301234567', '0301234567'], ['call 0123456', '0123456'], ['call 123456789', '123456789'], ['call timeout 0301234567', '0301234567']]
  expect(red.filter(([t, s]) => redact(t).includes(s) || !redact(t).includes('[redacted:phone]'))).toEqual([])
  const stay = ['per call (2026-11-24)', 'call on 24.11.2026', 'first call 2026-11-24T10:00', 'call settled in 12.5 ms', 'call timeout 123456789', 'call(123456)',
    'call x.py:1234-5678', 'tool call took 1234567 ns', 'call 1234567', 'call 192.168.10.20 failed']
  expect(stay.filter(t => redact(t) !== t)).toEqual([])
  expect(redact('iban: DE12' + 'A'.repeat(40) + ' x')).toBe('iban: [redacted:iban] x')
})
// ---- Round 18c (NB1): a number with a leading 0 and one '.' behind 'call' is a phone number, not a decimal ----
test('Round 18c: call 030.1234567 is redacted, decimals stay', () => {
  expect([redact('call 030.1234567'), redact('Call (030.1234567)')]).toEqual(['call [redacted:phone]', 'Call ([redacted:phone])'])
  const stay = ['call settled in 12.5 ms', 'call 0.5', 'call 09.30 am', '+49.301234567', '+4930.1234567', '+0.123456789']
  expect(stay.filter(t => redact(t) !== t)).toEqual([])
})
test('Round 15: deepRedact on large arrays under PII keys stays linear', { timeoutMs: 120_000 }, () => {
  expectLinear(f => ({ phone: Array(Math.floor(100_000 * f)).fill('030 1234567'), x: Array(Math.floor(50_000 * f)).fill({ tel: '0301234567' }) }), deepRedact)
})

