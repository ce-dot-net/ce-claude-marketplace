// Secret-redaction RULE DATA (the engine is lib/redact.ts). One row per rule; the engine runs the tables in the order of
// lib/redact.ts's header. A new token class (like Shopify) is ONE row here plus ONE case in tests-fixtures/secret-filter/cases.json.
// Parity TS<->Python: shared-hooks/utils/redact.py keeps the same rows (tests/test_redact_parity.py compares the tables; the shared
// fixture and a corpus compare the outputs). Every rule is linear: fixed-width or single-class quantifiers, no nested repeats.

// ---- layer 2: key / flag / header spans (8.1.3, write '[redacted]') ----
// [name, rule, block]: the value runs from the match end to the end of the line; block = on to the next blank line (at most
// REDACT_BLOCK code points). Inside a scheme:// token (a URL query) the value ends at '&', '#' or whitespace.
// A rule [keyword, flag] (Round 10 / L3) is a keyword plus a flag on the same line, searched in two linear steps (lazySearch)
// instead of `kw[^\n]*?flag`.
export const REDACT_BLOCK = 500
export const SPAN_RULES: [string, RegExp | [RegExp, RegExp], boolean][] = [
  ['key', /(?:password|passwd|passphrase|pwd|secret|token|credential|authorization|cookie|api[-_]?key|_key(?![a-z0-9])|pass(?![a-z]))[A-Za-z0-9_-]*["']?[ \t]*[:=][ \t]*/gi, true],
  ['flag', /--[A-Za-z0-9-]*(?:token|password|passwd|secret|api[-_]?key|credential)[A-Za-z0-9-]*(?:=|[ \t]+)/gi, false],
  ['mysql-p', [/\b(?:mysql(?:dump|admin|sh)?|sshpass|7z[a-z]?)\b/g, /[ \t]-p[ \t]*/g], false],
  ['zip-P', [/\b(?:unzip|zip)\b/g, /[ \t]-P[ \t]*/g], false],
  ['ssh-keygen-N', [/\bssh-keygen\b/g, /[ \t]-N[ \t]*/g], false],
  ['openssl-pass', [/\bopenssl\b/g, /[ \t]-(?:k|pass|passin|passout)[ \t]+/g], false],
  ['htpasswd', /\bhtpasswd\b[ \t]*/g, false],
  ['curl-user', [/\b(?:curl|wget)\b/g, /[ \t](?:-u|--user)(?:=|[ \t]+)?(?=["']?[^ \t\n\r"']*:)/g], false],
  ['bearer', /\bBearer[ \t]+/gi, false],
]

// ---- layer 3: substitutions (8.1.3, write '[redacted]') ----
// [name, rule, replacement]. 'stdin-echo' (the echo/printf stage piped into --password-stdin / --with-token) is applied per line by
// the linear echoStdin (Round 11 / W2), 'url-userinfo' by the linear urlUserinfo (Round 13: the regex is quadratic on a long run of
// scheme chars without '://', e.g. 'a.a.a.…'); both give exactly their regex's result, the regexes stay as their specification.
export const SECRET_RULES: [string, RegExp, string][] = [
  ['stdin-echo', /\b(echo|printf)\b[^\n]*\|(?=[^|\n]*--(?:password-stdin|with-token))/gi, '$1 [redacted] |'],
  ['url-userinfo', /(\b[A-Za-z][A-Za-z0-9+.-]*:\/\/)[^ \t\n\r\x0b\x0c"']*@/g, '$1[redacted]@'],
  ['token-8.1.3', /\b(?:ghp_|gho_|ghu_|ghs_|ghr_|github_pat_|xox[abprs]-|ace_user_|sk-)[A-Za-z0-9_-]{8,}|\bnpm_[A-Za-z0-9]{20,}|\bAKIA[0-9A-Z]{12,}|\beyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}(?:\.[A-Za-z0-9_-]+)?/g, '[redacted]'],
]

// ---- layer 5: known token prefixes (write '[redacted:prefix:<name>]') ----
export const PREFIX_RULES: [string, RegExp][] = [
  ['aws', /\b(?:AKIA|ASIA)[0-9A-Z]{16}\b/g],
  ['google', /\bAIza[0-9A-Za-z_-]{35}/g],
  ['gitlab', /\bglpat-[0-9A-Za-z_-]{20,}/g],
  ['stripe', /\b[rs]k_(?:live|test)_[0-9A-Za-z]{16,}/g],
  ['huggingface', /\bhf_[A-Za-z0-9]{30,}/g],
  // Shopify (Round 7): admin / custom-app / partner / shared-secret tokens, >= 32 hex in either case (the whole run, no hex rest)
  ['shopify', /\bshp(?:at|ca|pa|ss)_[0-9a-fA-F]{32,}/g],
]

// ---- layer 6: .env lines (write '[redacted:env]') ----
// KEY=value whose key has a secret-like SEGMENT (split at '_'; AUTHOR or SESSION_TIMEOUT stay). Optional tool prefix before the key:
// Read / cat -n line numbers ('  12\t', '12→'), grep -n ('file:12:'), grep context ('file-12-'), single-file grep ('12:', '12-'),
// a YAML item ('- '), a diff line ('+', '-').
// round 9 N7: JS's \s written out (the same set redact.py JS_WS spells for Python, whose \s differs: \x1c-\x1f, \x85, no U+FEFF)
export const JS_WS = String.raw`\t\n\v\f\r    -     　﻿`
const ENV_HEAD = String.raw`(?:[ \t]*\d+[\t→]|[^${JS_WS}:]{1,256}:\d+:|[^${JS_WS}:]{1,256}-\d+-|\d+[:-]|[ \t]*-[ \t]+|[+-])?`
export const ENV_LINE = new RegExp(String.raw`^(${ENV_HEAD}[ \t]*(?:export[ \t]+)?[A-Za-z_][A-Za-z0-9_]*[ \t]*=[ \t]*)([^${JS_WS}][^\n]*)$`, 'gm')
export const ENV_STRIP = new RegExp(String.raw`^${ENV_HEAD}[ \t]*(?:export[ \t]+)?`)
export const ENV_SEGS = new Set(['SALT', 'SIGNING', 'DSN', 'PRIVATE', 'AUTH', 'CRED', 'CREDS', 'CERT', 'SEED', 'SIG', 'SIGNATURE', 'HMAC', 'ENCRYPTION', 'OTP', 'PASS', 'PWD', 'ACCESS', 'SESSION'])
export const ENV_HARMLESS = new Set(['TIMEOUT', 'MINUTES', 'SECONDS', 'TTL', 'URL', 'HOST', 'PORT', 'NAME', 'USER', 'ID', 'ENABLED', 'MODE', 'LEVEL', 'PATH', 'DIR', 'FILE', 'COUNT', 'MAX', 'MIN', 'LIMIT'])

// ---- layer 7: user:password@host without a scheme (write '[redacted:url-cred]'; 'git@github.com' has no ':' before '@') ----
export const URL_CRED = new RegExp(String.raw`(^|[${JS_WS}"'(=,;])([A-Za-z0-9._~%-]{1,64}):([^${JS_WS}@\/:"']{1,128})@([A-Za-z0-9-]{1,63}(?:\.[A-Za-z0-9-]{1,63})+)`, 'g')

// ---- layer 8: well-known file formats without the usual key word (write '[redacted:<kind>]') ----
// [kind, rule, value group, tail group (0 = none)]: the match becomes group 1 + label + tail group; a value that is empty or already
// starts with '[redacted' stays. .netrc: '[machine M] login L password X' on one line; .pgpass: host:port:db:user:password (no spaces,
// a numeric or * port); docker config.json "auth" / "identitytoken"; Netscape cookie jar (value = the 7th tab field; round 9 N6: the
// fields stop at CR too); PHP define('…KEY|SECRET|PASSWORD|TOKEN|SALT|AUTH…', '…').
const TOOL_PREFIX = String.raw`(?:[ \t]*\d+[\t→]|[^${JS_WS}:]{1,256}:\d+:)?`
export const FORMAT_RULES: [string, RegExp, number, number][] = [
  ['netrc', /\b((?:machine[ \t]+[^ \t\n]+[ \t]+)?login[ \t]+[^ \t\n]+[ \t]+password[ \t]+)([^ \t\n]+)/g, 2, 0],  // exact token order; prose stays
  ['pgpass', new RegExp(String.raw`^(${TOOL_PREFIX}[^${JS_WS}:]{1,253}:(?:\d{1,5}|\*):[^${JS_WS}:]{1,128}:[^${JS_WS}:]{1,128}:)([^${JS_WS}]+)$`, 'gm'), 2, 0],
  ['docker-auth', /("(?:auth|identitytoken)"[ \t]*:[ \t]*")([^"\n]{4,})(")/g, 2, 3],
  ['cookie-jar', new RegExp(String.raw`^(${TOOL_PREFIX}(?:#HttpOnly_)?[^\t\n\r]+\t(?:TRUE|FALSE)\t[^\t\n\r]*\t(?:TRUE|FALSE)\t\d+\t[^\t\n\r]*\t)([^\n\r]+)$`, 'gm'), 2, 0],
  ['php-define', /(\bdefine\([ \t]*(['"])[A-Za-z0-9_]*(?:KEY|SECRET|PASSWORD|PASS|TOKEN|SALT|AUTH)[A-Za-z0-9_]*\2[ \t]*,[ \t]*(['"]))([^'"\n]*)(\3)/gi, 4, 5],
]

// ---- layer 9: a secret split over a name field and the value field right after it (write '[redacted:name-value]') ----
// Round 10 / M3: K8s env YAML 'name: X' + next line 'value: Y'; JSON {"name"|"key": "X", "value": "Y"} (Round 11 / I3.1: the JSON
// value runs over escaped characters; Round 12: as an unrolled loop `[^"\\\n]*(?:\\[^\n][^"\\\n]*)*`, linear in JSC too and without
// the old fail-open above ~540k chars). [kind, rule, tail group]: group 2 = the name, group 4 = the value; when the name is a secret
// name (secretKey, the same test as a KEY=value line) the match becomes groups 1-3 + label + tail group. Linear: bounded name, one line each.
export const NV_RULES: [string, RegExp, number][] = [
  ['yaml', /^([ \t]*(?:-[ \t]+)?name:[ \t]*["']?)([A-Za-z_][A-Za-z0-9_.-]{0,127})(["']?[ \t]*\r?\n[ \t]*(?:-[ \t]+)?value:[ \t]*)([^ \t\r\n\u2028\u2029][^\r\n\u2028\u2029]*)/gm, 0],
  ['json', /("(?:name|key)"[ \t]*:[ \t]*")([^"\n]{1,128})("[ \t]*,[ \t]*"value"[ \t]*:[ \t]*")([^"\\\n]*(?:\\[^\n][^"\\\n]*)*)(")/g, 5],
]

// ---- layer 10: personal data (Round 13, write '[redacted:email]' / '[redacted:phone]' / '[redacted:iban]') ----
// [name, label, prefilter, rule], run in this order; the engine (redact.ts PII_HANDLERS) checks each candidate:
//   iban        a candidate whose length matches its country (IBAN_LEN) and whose mod-97 check is 1 (upper case, groups of 4 may be spaced)
//   email       ASCII local@domain (local <= 64, at most 8 labels + a letters TLD, the whole domain, <= DOMAIN_MAX); not right after a local char
//               or '//' (URL userinfo), not before ':' + a path char (SCP form 'git@github.com:org/repo.git'); reserved example
//               domains stay (EXAMPLE_DOMAINS and their subdomains, EXAMPLE_TLDS); an ssh target without a path is an e-mail
//   phone-intl  '+' + a valid country code (PHONE_CC, ITU E.164) + 8-15 digits in all; without a separator only 11-15 digits
//               (a diff line '+12345678' stays; a '+' + 11-15 digit constant is a known false alarm)
//   phone-kw    a national number (6-15 digits) at most 20 chars (no line break, no digit) after a phone keyword
//   pii-key     the value after an email / mail / iban / phone key (key=value, key: value, JSON "key": "value"), label by PII_KEY_KIND,
//               when it looks like one (email: has '@' and no example domain; phone: >= 6 digits; iban: a digit); deepRedact the same per key
// KNOWN LIMITS: names and postal addresses, internationalized domains and quoted local parts (outside the key rule), bare national
// numbers without context, '+' diff constants of 11-15 digits (redacted).
export const DOMAIN_MAX = 253
export const EXAMPLE_DOMAINS = new Set(['example.com', 'example.org', 'example.net'])
export const EXAMPLE_TLDS = new Set(['test', 'example', 'invalid', 'localhost'])
// ITU E.164 assigned country codes (1-3 digits; prefix-free). Not codes: 28x, 35/37/38 alone, 384, 42, 422, 671, 684, 693-699, 854,
// 857-869, 871-877, 879, 884, 885, 887, 889, 969, 978, 990, 997, 999.
export const PHONE_CC = new Set(['1', '7', '20', '27', '30', '31', '32', '33', '34', '36', '39', '40', '41', '43', '44', '45', '46', '47', '48', '49',
  '51', '52', '53', '54', '55', '56', '57', '58', '60', '61', '62', '63', '64', '65', '66', '81', '82', '84', '86', '90', '91', '92', '93', '94', '95', '98',
  '211', '212', '213', '216', '218', '220', '221', '222', '223', '224', '225', '226', '227', '228', '229', '230', '231', '232', '233', '234', '235', '236',
  '237', '238', '239', '240', '241', '242', '243', '244', '245', '246', '247', '248', '249', '250', '251', '252', '253', '254', '255', '256', '257', '258',
  '260', '261', '262', '263', '264', '265', '266', '267', '268', '269', '290', '291', '297', '298', '299', '350', '351', '352', '353', '354', '355', '356',
  '357', '358', '359', '370', '371', '372', '373', '374', '375', '376', '377', '378', '379', '380', '381', '382', '383', '385', '386', '387', '388', '389',
  '420', '421', '423', '500', '501', '502', '503', '504', '505', '506', '507', '508', '509', '590', '591', '592', '593', '594', '595', '596', '597', '598',
  '599', '670', '672', '673', '674', '675', '676', '677', '678', '679', '680', '681', '682', '683', '685', '686', '687', '688', '689', '690', '691', '692',
  '800', '808', '850', '852', '853', '855', '856', '870', '880', '881', '882', '883', '886', '888', '960', '961', '962', '963', '964', '965', '966', '967',
  '968', '970', '971', '972', '973', '974', '975', '976', '977', '979', '991', '992', '993', '994', '995', '996', '998'])
// ISO 13616 IBAN register: total length per country
export const IBAN_LEN: Record<string, number> = { AD: 24, AE: 23, AL: 28, AT: 20, AZ: 28, BA: 20, BE: 16, BG: 22, BH: 22, BI: 27, BR: 29, BY: 28, CH: 21,
  CR: 22, CY: 28, CZ: 24, DE: 22, DJ: 27, DK: 18, DO: 28, EE: 20, EG: 29, ES: 24, FI: 18, FK: 18, FO: 18, FR: 27, GB: 22, GE: 22, GI: 23, GL: 18, GR: 27,
  GT: 28, HN: 28, HR: 21, HU: 28, IE: 22, IL: 23, IQ: 23, IS: 26, IT: 27, JO: 30, KW: 30, KZ: 20, LB: 28, LC: 32, LI: 21, LT: 20, LU: 20, LV: 21, LY: 25,
  MC: 27, MD: 24, ME: 22, MK: 19, MN: 20, MR: 27, MT: 31, MU: 30, NI: 28, NL: 18, NO: 15, OM: 23, PK: 24, PL: 28, PS: 29, PT: 25, QA: 29, RO: 24, RS: 22,
  RU: 33, SA: 24, SC: 31, SD: 18, SE: 24, SI: 19, SK: 24, SM: 27, SO: 23, ST: 25, SV: 28, TL: 23, TN: 24, TR: 26, UA: 29, VA: 22, VG: 24, XK: 20, YE: 30 }
export const PII_KEY_KIND: Record<string, string> = { 'e-mail': 'email', email: 'email', mail: 'email', iban: 'iban', telephone: 'phone', phone: 'phone',
  tel: 'phone', mobile: 'phone', handy: 'phone', fax: 'phone' }
export const PII_RULES: [string, string, RegExp, RegExp][] = [
  ['iban', 'iban', /[A-Z]{2}\d{2}/, /(?<![A-Za-z0-9])[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,3})?(?![A-Za-z0-9])/g],
  ['email', 'email', /@/, /(?<![A-Za-z0-9._%+\-])(?<!\/\/)[A-Za-z0-9._%+-]{1,64}@((?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.){1,8}[A-Za-z]{2,24})(?![A-Za-z0-9-]|\.[A-Za-z0-9])(?!:[A-Za-z0-9._\/~-])/g],
  ['phone-intl', 'phone', /\+/, /(?<![A-Za-z0-9+])\+(\d(?:[ ().\/-]{0,2}\d){5,16})(?!\d)/g],
  ['phone-kw', 'phone', /tel|phone|mobil|handy|fax|whatsapp|call|rufnummer/i, /\b(telefon|tel|phone|mobile|mobil|handy|fax|whatsapp|call|rufnummer)\b([^\n0-9]{0,20})(\d(?:[ ().\/-]{0,2}\d){5,14})(?!\d)/gi],
  ['pii-key', '', /mail|iban|phone|tel|mobile|handy|fax/i, new RegExp(String.raw`(?<![A-Za-z0-9_.\-])(["']?)(e-mail|email|mail|iban|telephone|phone|tel|mobile|handy|fax)\1[ \t]*[:=](?!=)[ \t]*(?:"([^"\n]{1,256})"|'([^'\n]{1,256})'|([^${JS_WS}"',;}\]]{1,256}))`, 'gi')],
]

// ---- layer 11: high entropy (write '[redacted:entropy]') ----
// A run of >= 20 base64/base62 chars that has upper AND lower case AND a digit, Shannon entropy >= min(ENTROPY_MIN,
// ENTROPY_LEN_FACTOR * log2(length)) bits/char (round 5: a short random string cannot reach 4.0 bits; the fixed 4.0 missed 37% of
// random 20-char base62, the length-aware bound 5%; ENTROPY_MIN chosen on the fixture + local tool outputs) and a class-switch rate
// >= SWITCH_MIN (random key material switches between upper / lower / digit about every 1.6 chars, rate ~0.6; camelCase identifiers
// ~0.3; round 5: 0.4 -> 0.35).
export const ENTROPY_MIN = 4.0, ENTROPY_LEN_FACTOR = 0.85
export const SWITCH_MIN = 0.35
export const ENTROPY_RUN = /[A-Za-z0-9+\/_=-]{20,}/g
// Object ids with a base62 body, never key material: Claude (toolu_, srvtoolu_, msg_, req_, session_, file_, batch_), ACE (org_, prj_),
// Stripe objects (cus_, pi_, ch_, sub_, price_, prod_, acct_, evt_, in_), call_/run_. ponytail: a fixed prefix list from local data.
export const OBJECT_ID = /^(?:toolu|srvtoolu|msg|req|session|file|batch|org|prj|cus|pi|ch|sub|price|prod|acct|evt|in|call|run)_[A-Za-z0-9]{8,}$/
