// Secret redaction (8.1.3 + full steps), FAIL-CLOSED: Claude Code does not redact hook inputs, so every text the trace sends,
// the task state stores or Haiku sees goes through redact(). Rule DATA lives in lib/redact_rules.ts; this file is the engine.
// Layers, in this order (each later layer leaves an earlier '[redacted' value alone):
//    1. stdin bodies of --password-stdin / --with-token (here-strings, here-docs)    redactStdin      '[redacted]'
//    2. key / flag / header spans (password=, --token, mysql -p, Bearer ...)          SPAN_RULES       '[redacted]'
//    3. echo | --password-stdin, URL userinfo, the 8.1.3 token prefixes / JWTs        SECRET_RULES     '[redacted]'
//    4. PEM private keys (to the END line, else to the text end)                     redactPem        '[redacted:prefix:private-key]'
//    5. known token prefixes (aws, google, gitlab, stripe, huggingface, shopify)      PREFIX_RULES     '[redacted:prefix:<name>]'
//    6. .env lines with a secret-like key segment                                    ENV_LINE         '[redacted:env]'
//    7. user:password@host without a scheme                                          URL_CRED         '[redacted:url-cred]'
//    8. file formats: .netrc, .pgpass, docker auth, cookie jar, PHP define()         FORMAT_RULES     '[redacted:<kind>]'
//    9. name / value pairs (K8s env YAML, JSON {name|key, value})                    NV_RULES         '[redacted:name-value]'
//   10. personal data: IBAN, e-mail, phone (+CC, national after a keyword), PII keys  PII_RULES        '[redacted:email|phone|iban]'
//   11. high entropy runs                                                            redactEntropy    '[redacted:entropy]'
// deepRedact applies redact() to every string of a structured value and drops the whole value under a secret-named key.
// ponytail: over-redacts on purpose (a key span takes the rest of the line), never under-redacts.
// KNOWN LIMITS (README): bare secrets with no key word and no known format (a lowercase or hex token, anything under 20 chars, an
// unlabelled value in prose), hex-only key material (SHAs and UUIDs must stay readable), a .netrc password on its own line.
// Personal data: names and postal addresses, internationalized domains and quoted local parts (outside the PII key rule), bare national
// phone numbers without a keyword, and a '+' diff constant of 11-15 digits with a valid country code (redacted: a false alarm).
// Parity TS<->Python: shared-hooks/utils/redact.py, rule for rule; fixture tests-fixtures/secret-filter/cases.json (redact.test.ts,
// tests/test_secret_filter_py.py, which also compares both chains' outputs), tables compared by tests/test_redact_parity.py.
// Linear: no backtracking regex, indexOf scans, cached next matches.
import { DOMAIN_MAX, EMAIL_FILE_TLDS, EMAIL_SCALE, ENTROPY_LEN_FACTOR, ENTROPY_MIN, ENTROPY_RUN, ENV_HARMLESS, ENV_LINE, ENV_SEGS, ENV_STRIP,
  EXAMPLE_DOMAINS, EXAMPLE_TLDS, FORMAT_RULES, IBAN_LEN, IBAN_SEP, KW_VERSION, KW_VERSION_DIGITS_MAX, KW_CALL_PHONE, EMAIL_CALL_TLD_MAX, PII_KEY_PHONE, NV_RULES, OBJECT_ID, PHONE_CC, PHONE_REJECT, PII_KEY_KIND, PII_KEY_SUFFIX, PII_RULES,
  PREFIX_RULES, REDACT_BLOCK, SECRET_RULES, SPAN_RULES, SWITCH_MIN, URL_CRED } from './redact_rules'

export { ENTROPY_LEN_FACTOR, ENTROPY_MIN, REDACT_BLOCK, SWITCH_MIN } from './redact_rules'

// ---------- layer 1: stdin bodies ----------
// Run BEFORE the span rules (which cut the line at the flag): the stdin value of --password-stdin / --with-token that they
// cannot see. A LOGICAL line is the physical lines joined over an unescaped trailing backslash (and, below, over a
// multi-line quoted here-string word). On a logical line holding the flag (any case, left or right of the value, behind a
// pipe): every shell word after a '<<<' (quotes, $'..', backslashes; a word starting $( ` ${ runs to the end of the logical
// line; an open quote runs to the closing quote on a later line, else to the TEXT END) and the body of every here-doc
// ('<<[-]DELIM', quoted or \DELIM; case-sensitive; '<<-' allows leading tabs) on the lines below, up to the terminator line, or
// to the TEXT END when there is none or the delimiter cannot be parsed. Fail closed, a heuristic, not a shell parser. Linear:
// one cheap flag test first, no backtracking regex. Parity: redact.py _redact_stdin.
const STDIN_FLAG = /--(?:password-stdin|with-token)/i
const WORD_END = ' \t\n;&|)'
const DELIM_END = ' \t\n;&|)<>\'"\\('
const DELIM_MAX = 256
// The end of the shell word starting at i in text (an open quote runs to the closing quote on a later line, else to the end).
function stdinWordEnd(t: string, i: number): number {
  const n = t.length
  while (i < n && !WORD_END.includes(t[i]!)) {
    const c = t[i]
    if (c === '\\') i += 2
    else if (c === "'" || c === '"' || (c === '$' && t[i + 1] === "'")) {
      const q = c === '$' ? "'" : c, esc = q === '"' || c === '$'
      let j = c === '$' ? i + 2 : i + 1
      while (j < n && t[j] !== q) j += esc && t[j] === '\\' ? 2 : 1
      if (j >= n) return n
      i = j + 1
    } else i++
  }
  return Math.min(i, n)
}
// The end (index of the '\n' or text end) of the logical line that holds index p.
function logicalEnd(t: string, p: number): number {
  let e = t.indexOf('\n', p)
  while (e >= 0) {
    let b = 0
    while (e - 1 - b >= p && t[e - 1 - b] === '\\') b++
    if (b % 2 === 0) return e
    e = t.indexOf('\n', e + 1)
  }
  return t.length
}
// The delimiters of the here-docs on one logical line: [delimiter, dash][], or null when one cannot be parsed.
function hereDocs(l: string): [string, boolean][] | null {
  const out: [string, boolean][] = []
  let k = 0
  while ((k = l.indexOf('<<', k)) >= 0) {
    if (l[k + 2] === '<') { k += 1; continue }
    if (k > 0 && l[k - 1] === '<') { k += 2; continue }
    let i = k + 2
    const dash = l[i] === '-'
    if (dash) i++
    while (l[i] === ' ' || l[i] === '\t') i++
    let d: string
    if (l[i] === "'" || l[i] === '"') { const e = l.indexOf(l[i]!, i + 1); if (e < 0) return null; d = l.slice(i + 1, e); i = e + 1 }
    else { if (l[i] === '\\') i++; let e = i; while (e < l.length && !DELIM_END.includes(l[e]!)) e++; d = l.slice(i, e); i = e }
    if (!d || d.length > DELIM_MAX) return null
    out.push([d, dash])
    k = i
  }
  return out
}
function redactStdin(t: string): string {
  if (!STDIN_FLAG.test(t)) return t
  const n = t.length, out: string[] = []
  let p = 0, nextK = -2
  while (p <= n) {
    let e = logicalEnd(t, p)
    let flag = STDIN_FLAG.test(t.slice(p, e))
    const words: [number, number][] = []
    let pos = p
    for (;;) {
      if (nextK !== -1 && nextK < pos) nextK = t.indexOf('<<<', pos)
      if (nextK < 0 || nextK >= e) break
      let s = nextK + 3
      while (t[s] === ' ' || t[s] === '\t' || (t[s] === '\\' && t[s + 1] === '\n')) s += t[s] === '\\' ? 2 : 1
      const subst = t[s] === '`' || (t[s] === '$' && (t[s + 1] === '(' || t[s + 1] === '{'))
      const w = subst ? e : stdinWordEnd(t, s)
      words.push([s, w])
      if (w > e) { const e2 = logicalEnd(t, w); flag = flag || STDIN_FLAG.test(t.slice(e, e2)); e = e2 }
      pos = Math.max(w, nextK + 3)
    }
    if (!flag) { out.push(t.slice(p, e)); p = e + 1; continue }
    let line = '', q = p
    for (const [s, w] of words) { line += t.slice(q, s) + (w > s ? '[redacted]' : ''); q = w }
    out.push(line + t.slice(q, e))
    const docs = hereDocs(t.slice(p, e))
    let ls = e + 1
    if (!docs) { if (ls <= n) out.push('[redacted]'); break }
    let done = false
    for (const [d, dash] of docs) {
      if (ls > n) break
      let b = ls, found = false
      while (b <= n) {
        let le = t.indexOf('\n', b); if (le < 0) le = n
        const ln = t.slice(b, le)
        if ((dash ? ln.replace(/^\t+/, '') : ln) === d) { found = true; if (b > ls) out.push('[redacted]'); out.push(ln); ls = le + 1; break }
        b = le + 1
      }
      if (!found) { out.push('[redacted]'); done = true; break }
    }
    if (done) break
    p = ls
  }
  return out.join('\n')
}

// ---------- layer 2: key / flag / header spans ----------
const BLANK_LINE = /\n[ \t\r]*\n/g
const URL_VALUE_END = /[&# \t\n\r\x0b\x0c"']/g
const TOKEN_SEP = ' \t\n\r\x0b\x0c"\''
const searchFrom = (rx: RegExp, s: string, pos: number) => { rx.lastIndex = pos; return rx.exec(s) }
// Round 10 / L3: the first keyword at or after pos whose own line (after it) holds the flag: the same match as kw[^\n]*?flag,
// linear: when a keyword's line has no flag, no later keyword on that line can have one (its range is a subset): skip the line.
function lazySearch([kw, flag]: [RegExp, RegExp], s: string, pos: number, cache: { f?: RegExpExecArray | null; eol?: number }): RegExpExecArray | null {
  for (;;) {
    const m = searchFrom(kw, s, pos)
    if (!m) return null
    const from = m.index + m[0].length
    // Round 11 / W1: the end of the line cached too (one long line was rescanned per keyword)
    if (cache.eol === undefined || cache.eol < from) { const e = s.indexOf('\n', from); cache.eol = e < 0 ? s.length : e }
    const eol = cache.eol
    // Round 11 / W1: the flag's next match cached like the rule matches (no copy of the rest of the line per keyword)
    if (cache.f === undefined || (cache.f !== null && cache.f.index < from)) cache.f = searchFrom(flag, s, from)
    const f = cache.f
    if (f && f.index < eol) return Object.assign([s.slice(m.index, f.index + f[0].length)], { index: m.index, input: s, groups: undefined }) as any
    pos = eol
  }
}
// The index REDACT_BLOCK code points after start (Python counts code points).
function cpAdvance(s: string, start: number, n: number): number {
  let k = start
  while (k < s.length && n-- > 0) { const c = s.charCodeAt(k); k += c >= 0xd800 && c <= 0xdbff && k + 1 < s.length && (s.charCodeAt(k + 1) & 0xfc00) === 0xdc00 ? 2 : 1 }
  return k
}
function redactSpans(text: string): string {
  let out = '', pos = 0
  // Each rule's next match is cached and searched again only once pos has passed it (same matches as a fresh search from pos:
  // the first match at or after an earlier pos that is still >= pos is the first one at or after pos). Linear on long outputs.
  const next: (RegExpExecArray | null | undefined)[] = SPAN_RULES.map(() => undefined)
  let scanned = 0, lastSep = -1, schemeAt = -1, blank: RegExpExecArray | null | undefined
  const flagCache = SPAN_RULES.map(() => ({} as { f?: RegExpExecArray | null; eol?: number }))
  for (;;) {
    let best = null as RegExpExecArray | null, block = false  // `as`: assigned inside the forEach closure; plain `: T = null` narrows to never (TS2339 in `claude plugin validate`)
    SPAN_RULES.forEach(([, rx, b], k) => {
      let m = next[k]
      if (m === undefined || (m !== null && m.index < pos)) next[k] = m = Array.isArray(rx) ? lazySearch(rx, text, pos, flagCache[k]!) : searchFrom(rx, text, pos)
      if (m && (!best || m.index < best.index)) { best = m; block = b }
    })
    if (!best) break
    const start = best.index + best[0].length
    // Round 10 / L3: the token start remembered forward (was a backward scan per match: quadratic inside one long URL token)
    while (scanned < best.index) {
      if (TOKEN_SEP.includes(text[scanned]!)) lastSep = scanned
      else if (schemeAt <= lastSep && text.startsWith('://', scanned)) schemeAt = scanned  // the token's first '://'
      scanned++
    }
    const k = lastSep
    let end: number
    if (schemeAt > k && schemeAt + 3 <= best.index) { const e = searchFrom(URL_VALUE_END, text, start); end = e ? e.index : text.length }  // a URL query value
    else {
      end = text.indexOf('\n', start)
      if (end < 0) end = text.length
      if (block) {  // Round 10 / L3: the next blank line cached like the rule matches (was searched again per match)
        if (blank === undefined || (blank !== null && blank.index < start)) blank = searchFrom(BLANK_LINE, text, start)
        end = Math.max(end, Math.min(blank ? blank.index : text.length, cpAdvance(text, start, REDACT_BLOCK)))
      }
    }
    out += text.slice(pos, start) + '[redacted]'
    pos = end
  }
  return out + text.slice(pos)
}

// ---------- layer 3: echo | --password-stdin ----------
// Round 11 / W2: SECRET_RULES 'stdin-echo' (`\b(echo|printf)\b[^\n]*\|(?=[^|\n]*--(?:password-stdin|with-token))`) on one line, linear
// and with the same result: the greedy [^\n]* takes the LAST pipe whose segment (up to the next pipe) holds the flag; the match starts
// at the first echo/printf ending before that pipe; one replacement per line (no later qualifying pipe remains). Twin: redact.py _echo_stdin.
const ECHO_WORD = /\b(echo|printf)\b/gi
function echoStdin(l: string): string {
  let q = -1
  for (let p = l.indexOf('|'); p >= 0; ) {
    const nx = l.indexOf('|', p + 1)
    if (STDIN_FLAG.test(l.slice(p + 1, nx < 0 ? l.length : nx))) q = p
    p = nx
  }
  if (q < 0) return l
  ECHO_WORD.lastIndex = 0
  const m = ECHO_WORD.exec(l)
  if (!m || m.index + m[0].length > q) return l
  return l.slice(0, m.index) + m[1] + ' [redacted] |' + l.slice(q + 1)
}

// Round 13: SECRET_RULES 'url-userinfo' (`(\b[A-Za-z][A-Za-z0-9+.-]*:\/\/)[^ \t\n\r\x0b\x0c"']*@` -> '$1[redacted]@') in linear time and
// with the same result: per '://' (left to right, not inside the previous match) a scheme start exists when the run of scheme chars
// before it (not before the previous match end) holds a letter at a word boundary; the value then runs to the LAST '@' before the next
// whitespace / quote. The span end and its last '@' are cached (a long span with many '://' is scanned once). Twin: redact.py _url_userinfo.
const isSchemeCh = (c: string) => /[A-Za-z0-9+.\-]/.test(c)
const isWordCh = (c: string | undefined) => c !== undefined && /[A-Za-z0-9_]/.test(c)
const USERINFO_END = /[ \t\n\r\x0b\x0c"']/g
function urlUserinfo(t: string): string {
  let p = t.indexOf('://')
  if (p < 0) return t
  let out = '', pos = 0, spanEnd = -1, lastAt = -1, nextAt = -2  // nextAt: the first '@' not yet looked at (-1: none left)
  while (p >= 0) {
    let r = p
    while (r > pos && isSchemeCh(t[r - 1]!)) r--
    let ok = false
    for (let s = r; s < p && !ok; s++) ok = /[A-Za-z]/.test(t[s]!) && !isWordCh(t[s - 1])
    if (ok) {
      if (spanEnd < p + 3) {  // a new span: its end and its last '@'
        USERINFO_END.lastIndex = p + 3
        const e = USERINFO_END.exec(t)
        spanEnd = e ? e.index : t.length
        lastAt = -1
        if (nextAt !== -1 && nextAt < p + 3) nextAt = t.indexOf('@', p + 3)
        while (nextAt >= 0 && nextAt < spanEnd) { lastAt = nextAt; nextAt = t.indexOf('@', nextAt + 1) }
      }
      if (lastAt >= p + 3) { out += t.slice(pos, p + 3) + '[redacted]@'; pos = lastAt + 1 }
    }
    p = t.indexOf('://', Math.max(p + 1, pos))
  }
  return out + t.slice(pos)
}

// ---------- layer 4: PEM private keys ----------
// -----BEGIN ... PRIVATE KEY----- through its END line, or to the text end when there is none (fail closed).
function redactPem(t: string): string {
  let out = '', pos = 0
  for (;;) {
    const b = t.indexOf('-----BEGIN ', pos)
    if (b < 0) break
    const hEnd = t.indexOf('-----', b + 11)
    if (hEnd < 0 || hEnd - b > 80 || !t.slice(b, hEnd).endsWith('PRIVATE KEY')) { out += t.slice(pos, b + 11); pos = b + 11; continue }
    const e = t.indexOf('-----END ', hEnd + 5)
    const eEnd = e < 0 ? -1 : t.indexOf('-----', e + 9)
    out += t.slice(pos, b) + '[redacted:prefix:private-key]'
    pos = eEnd < 0 ? t.length : eEnd + 5
  }
  return out + t.slice(pos)
}

// ---------- layer 6: .env lines ----------
const envLine = (m: string, head: string, value: string) => {
  const segs = head.replace(ENV_STRIP, '').replace(/[ \t]*=[ \t]*$/, '').toUpperCase().split('_')
  if (value.startsWith('[redacted') || !segs.some(x => ENV_SEGS.has(x)) || ENV_HARMLESS.has(segs[segs.length - 1]!)) return m
  return head + '[redacted:env]'
}

// ---------- layer 8: file formats ----------
function redactFormats(s: string): string {
  for (const [kind, rx, vg, tg] of FORMAT_RULES)
    s = s.replace(rx, (m: string, ...g: any[]) => {
      const v: string = g[vg - 1]
      return !v || v.startsWith('[redacted') ? m : `${g[0]}[redacted:${kind}]${tg ? g[tg - 1] : ''}`
    })
  return s
}

// ---------- layer 9: name / value pairs ----------
function redactNameValue(s: string): string {
  for (const [, rx, tg] of NV_RULES)
    s = s.replace(rx, (m: string, a: string, n: string, b: string, v: string, ...g: any[]) =>
      !v || v.startsWith('[redacted') || !secretKey(n) ? m : `${a}${n}${b}[redacted:name-value]${tg ? g[tg - 5] : ''}`)
  return s
}

// ---------- layer 10: personal data ----------
const isExampleDomain = (d: string) => {
  const l = d.toLowerCase()
  for (const x of EXAMPLE_DOMAINS) if (l === x || l.endsWith('.' + x)) return true
  return EXAMPLE_TLDS.has(l.slice(l.lastIndexOf('.') + 1))
}
// mod-97 of the IBAN with its first four chars moved to the end, letters as 10..35 (ISO 13616); 1 = valid
const ibanMod97 = (c: string) => {
  let m = 0
  for (const ch of c.slice(4) + c.slice(0, 4)) { const v = parseInt(ch, 36); m = (v < 10 ? m * 10 + v : m * 100 + v) % 97 }
  return m
}
const digits = (x: string) => x.replace(/[^0-9]/g, '')
// Round 14: lookups keyed by user text read own keys only ('constructor', '__proto__' are no keys)
const own = <V>(table: Record<string, V>, k: string): V | undefined => Object.prototype.hasOwnProperty.call(table, k) ? table[k] : undefined
// Round 18 / N2: a digit suffix (iban2, email_1, mail1) is stripped first; the key rule allows it on every stem
const piiKind = (k: string, key = k.replace(/[_-]?[0-9]{1,2}$/, '') || k) => own(PII_KEY_KIND, key.toLowerCase()) ?? own(PII_KEY_KIND, key.toLowerCase().replace(PII_KEY_SUFFIX, ''))  // 'rufnummer' is a stem
  ?? (PII_KEY_PHONE.test(k) ? 'phone' : undefined)  // Round 16: Mobiltelefon, festnetz, cell, MobilePhone, phone2 ...
// whether a value behind a PII key looks like its kind (email: an '@' and no example domain; phone: >= 6 digits; iban: a digit)
const piiValue = (kind: string, v: string) => !v.startsWith('[redacted') && (kind === 'email' ? v.includes('@') && !isExampleDomain(v.slice(v.lastIndexOf('@') + 1))
  : kind === 'phone' ? digits(v).length >= 6 : /[0-9]/.test(v))
// The length of an IBAN-shaped value behind a key: up to its country's IBAN length (alnum chars, single spaces between), when that
// length ends at a space or the value end; else (unknown country, too short, too long) only its first token.
// Round 16: the end of the IBAN's country length in v (alnum chars, separators between), when it ends at a non-alnum char or the end;
// else -1. The candidate holds only alnum chars and IBAN_SEP / spaces, so 'not alnum' is a separator.
const isAlnum = (c: number) => (c >= 48 && c <= 57) || (c >= 65 && c <= 90) || (c >= 97 && c <= 122)
function ibanCountrySpan(v: string): number {
  const want = own(IBAN_LEN, v.slice(0, 2).toUpperCase())
  if (want === undefined) return -1
  let n = 0, i = 0
  for (; i < v.length && n < want; i++) if (isAlnum(v.charCodeAt(i))) n++
  return n === want && (i === v.length || !isAlnum(v.charCodeAt(i))) ? i : -1
}
// Round 17 / C1': from a start candidate at i walk exactly the country's length, one optional IBAN_SEP before each 4-char group; the end
// when a non-alnum char or the text end follows and mod-97 is 1, else -1. At most 2 * 34 chars per start (linear over all starts).
function ibanWalk(s: string, i: number): number {
  const want = own(IBAN_LEN, s.slice(i, i + 2).toUpperCase())
  if (want === undefined) return -1
  let c = '', j = i
  while (c.length < want && j < s.length) {
    if (c.length && c.length % 4 === 0 && IBAN_SEP.test(s.charAt(j)) && j + 1 < s.length && isAlnum(s.charCodeAt(j + 1))) j++
    if (!isAlnum(s.charCodeAt(j))) return -1
    c += s.charAt(j++)
  }
  return c.length === want && (j === s.length || !isAlnum(s.charCodeAt(j))) && ibanMod97(c.toUpperCase()) === 1 ? j : -1
}
// Round 18 / B1, 18b: a number behind a bare 'call' stays when it is no phone number: a compact number after a code word (timeout, took,
// settled, used, ratio), a date / IPv4 / decimal (PHONE_REJECT), a line range behind a file name, call(N) without a leading 0, or a
// number without a phone shape (KW_CALL_PHONE)
const callKeeps = (gap: string, num: string) => /^[1-9][0-9]*$/.test(num) && /(?:^|[^A-Za-z])(?:timeout|took|settled|used|ratio)[ \t:=]*$/i.test(gap)
  || PHONE_REJECT.some(r => r.test(num)) || /[A-Za-z0-9_]\.[A-Za-z0-9]{1,5}:$/.test(gap) && /^[0-9]{1,7}(?:-[0-9]{1,7})?$/.test(num)
  || gap === '(' && /^[1-9][0-9]*$/.test(num) || !KW_CALL_PHONE.test(num)
function ibanSpan(kind: string, v: string): number {
  const first = v.indexOf(' ') < 0 ? v.length : v.indexOf(' ')
  if (kind !== 'iban') return first
  const c = ibanCountrySpan(v)
  if (c >= 0) return c
  // Round 16 / I1 (fail-closed): no country length: every group that has a digit or 4 chars, up to the first other word
  let end = first
  for (let i = first; i < v.length; ) {
    const j = v.indexOf(' ', i + 1) < 0 ? v.length : v.indexOf(' ', i + 1), tok = v.slice(i + 1, j)
    if (!(/[0-9]/.test(tok) || tok.length === 4)) break
    end = j; i = j
  }
  return end
}
const PII_HANDLERS: Record<string, (s: string, rx: RegExp, label: string) => string> = {
  'iban': (s, rx, label) => {  // Round 17 / C1': every start candidate is walked; a valid IBAN is replaced, the scan goes on after its end
    let out = '', pos = 0
    for (const m of s.matchAll(rx)) {
      if (m.index < pos) continue
      const e = ibanWalk(s, m.index)
      if (e >= 0) { out += s.slice(pos, m.index) + `[redacted:${label}]`; pos = e }
    }
    return out + s.slice(pos)
  },
  'email': (s, rx, label) => s.replace(rx, (m, d: string, at: number, str: string) => d.length > DOMAIN_MAX || isExampleDomain(d) || EMAIL_SCALE.test(d)
    || EMAIL_FILE_TLDS.has(d.slice(d.lastIndexOf('.') + 1).toLowerCase())
    || ('(['.includes(str[at + m.length] ?? 'x') && d.length - d.lastIndexOf('.') - 1 > EMAIL_CALL_TLD_MAX) ? m : `[redacted:${label}]`),
  'phone-intl': (s, rx, label) => s.replace(rx, (m, body: string) => {
    const dg = digits(body)
    if (PHONE_REJECT.some(r => r.test(body))) return m  // Round 14: a date, an IPv4 address, a decimal number
    if (dg.length < 8 || dg.length > 15 || !(PHONE_CC.has(dg.slice(0, 1)) || PHONE_CC.has(dg.slice(0, 2)) || PHONE_CC.has(dg.slice(0, 3)))) return m
    return dg.length !== body.length || dg.length >= 11 ? `[redacted:${label}]` : m  // no separator: only 11-15 digits (diff lines)
  }),
  'phone-kw': (s, rx, label) => {
    const one = (m: string, kw: string, gap: string, num: string): string => {
      if (gap.endsWith('/') && KW_VERSION.test(num) && digits(num).length <= KW_VERSION_DIGITS_MAX) return m
      // Round 18b / B1': the gap after a bare 'call' is scanned again (it may hold another phone keyword: 'call or fax 5550123')
      if (kw.toLowerCase() === 'call' && callKeeps(gap, num)) return kw + (gap + num).replace(rx, one)
      return `${kw}${gap}[redacted:${label}]`
    }
    return s.replace(rx, one)
  },
  'pii-key': (s, rx) => s.replace(rx, (m, _q: string, key: string, v1?: string, v2?: string, v3?: string, v4?: string, _v4groups?: string, v5?: string) => {  // Round 18b / B2: v4 is atomic
    const v = (v1 ?? v2 ?? v3 ?? v4 ?? v5)!, kind = piiKind(key)!, close = v1 !== undefined || v2 !== undefined ? 1 : 0
    const span = v4 === undefined ? v.length : ibanSpan(kind, v4)  // Round 15: an IBAN-shaped value only up to its country length
    return piiValue(kind, v.slice(0, span)) ? m.slice(0, m.length - v.length - close) + `[redacted:${kind}]` + v.slice(span) + m.slice(m.length - close) : m
  }),
}
function redactPii(s: string): string {
  for (const [name, label, pre, rx] of PII_RULES) if (pre.test(s)) s = PII_HANDLERS[name]!(s, rx, label)
  return s
}

// ---------- layer 11: high entropy ----------
export const shannon = (x: string): number => {
  const f = new Map<string, number>()
  for (const c of x) f.set(c, (f.get(c) ?? 0) + 1)
  let h = 0
  for (const n of f.values()) { const p = n / x.length; h -= p * Math.log2(p) }
  return Math.round(h * 1e6) / 1e6
}
const cls = (c: string) => c >= 'a' && c <= 'z' ? 1 : c >= 'A' && c <= 'Z' ? 2 : 3
export const classSwitches = (x: string): number => { let n = 0; for (let i = 1; i < x.length; i++) if (cls(x[i]!) !== cls(x[i - 1]!)) n++; return x.length > 1 ? n / (x.length - 1) : 0 }
// Hex-only strings (git SHAs, sha256, UUIDs) never qualify (no upper case); a data-URI image ('base64,...') and an integrity hash
// ('sha512-...') are skipped; the longest '/'-free piece decides (paths stay paths); separators do not count toward the entropy.
function redactEntropy(t: string): string {
  return t.replace(ENTROPY_RUN, (run, at: number) => {
    const before = t.slice(Math.max(0, at - 7), at)
    if (before === 'base64,' || /^sha(?:256|384|512)-/.test(run)) return run
    for (const piece of run.split('/')) {
      if (OBJECT_ID.test(piece)) continue  // a known object id (Claude / ACE / Stripe), not key material
      const core = piece.replace(/[-_=+]/g, '')
      if (core.length >= 20 && /[A-Z]/.test(core) && /[a-z]/.test(core) && /[0-9]/.test(core) && shannon(core) >= Math.min(ENTROPY_MIN, ENTROPY_LEN_FACTOR * Math.log2(core.length)) && classSwitches(core) >= SWITCH_MIN) return '[redacted:entropy]'
    }
    return run
  })
}

// ---------- public API ----------
export function redact<T>(text: T): T {
  if (typeof text !== 'string' || !text) return text
  let s: string = redactSpans(redactStdin(text))
  // Round 10 / L3 + Round 11 / W2: the echo/printf rule only on lines that hold the stdin flag, and there linear (echoStdin)
  for (const [name, rx, rep] of SECRET_RULES)
    s = name === 'stdin-echo' ? s.split('\n').map(l => STDIN_FLAG.test(l) ? echoStdin(l) : l).join('\n') : name === 'url-userinfo' ? urlUserinfo(s) : s.replace(rx, rep)
  s = redactPem(s)
  for (const [name, rx] of PREFIX_RULES) s = s.replace(rx, `[redacted:prefix:${name}]`)
  s = s.replace(ENV_LINE, envLine)
  // Round 13: 'mailto:local@domain' is an e-mail (layer 10), not user:password@host
  s = s.replace(URL_CRED, (_m, a: string, u: string, _p: string, h: string) => u.toLowerCase() === 'mailto' ? _m : `${a}${u}:[redacted:url-cred]@${h}`)
  s = redactFormats(s)
  s = redactNameValue(s)  // Round 10 / M3
  s = redactPii(s)  // Round 13
  return redactEntropy(s) as any
}

// A secret-named key ('password', 'API_KEY', 'token', ...): its whole value goes (the value alone has no key context).
// round 8 I4: memoised (tool inputs repeat the same few keys); ponytail: a cap of 10k keys, then no more caching
export const secretKeyCache = new Map<string, boolean>()
export const secretKey = (k: string) => {
  let v = secretKeyCache.get(k)
  if (v === undefined) { v = redact(`${k}=x`) !== `${k}=x`; if (secretKeyCache.size < 10_000) secretKeyCache.set(k, v) }
  return v
}
// The FULL tool input / output for the step, secrets out: every string at any depth goes through redact(), and the whole
// value under a secret-named key is '[redacted]'. Twin: redact.py deep_redact.
export function deepRedact(v: any, depth = 0): any {
  if (typeof v === 'string') return redact(v)
  if (v === null || typeof v !== 'object') return v
  if (depth > 50) return '[redacted]'  // ponytail: absurd nesting is dropped, never sent unchecked
  if (Array.isArray(v)) return v.map(x => deepRedact(x, depth + 1))
  // Round 10 / M3: {name|key: <secret name>, value: x} (MCP HTTP headers, env arrays): the value goes
  const nm = typeof v.name === 'string' ? v.name : typeof v.key === 'string' ? v.key : undefined
  const nv = nm !== undefined && 'value' in v && secretKey(nm)
  return deepObject(v, depth, undefined, nv)
}
// The entries of an object: secret keys and name/value pairs drop their value; a PII key (email, mail, iban, phone, tel, telefon, ...)
// gives its value a kind (Round 13), which also holds for every element and nested value below it (Round 15: arrays, objects).
function deepObject(v: any, depth: number, inherited: string | undefined, nv: boolean): any {
  return Object.fromEntries(Object.entries(v).map(([k, x]) => {
    if (secretKey(k) || (nv && k === 'value')) return [k, '[redacted]']
    const kind = piiKind(k) ?? inherited
    return [k, kind ? kindValue(x, kind, depth + 1) : deepRedact(x, depth + 1)]
  }))
}
function kindValue(x: any, kind: string, depth: number): any {
  if (typeof x === 'string' || typeof x === 'number') return piiValue(kind, String(x)) ? `[redacted:${kind}]` : deepRedact(x, depth)
  if (x === null || typeof x !== 'object') return x
  if (depth > 50) return '[redacted]'
  if (Array.isArray(x)) return x.map(e => kindValue(e, kind, depth + 1))
  const nm = typeof x.name === 'string' ? x.name : typeof x.key === 'string' ? x.key : undefined
  return deepObject(x, depth, kind, nm !== undefined && 'value' in x && secretKey(nm))
}
