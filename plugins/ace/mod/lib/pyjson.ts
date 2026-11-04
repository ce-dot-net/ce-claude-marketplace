// Python-compatible JSON for the mod: json.loads/json.dumps byte parity (PyFloat keeps int vs float apart), sanitize.
// Pure: no `$`, no I/O.

// ---------- Python-compatible JSON (json.loads / json.dumps defaults) ----------
// Python keeps int vs float apart ("1.0" stays 1.0); JS does not. Floats are boxed on parse.
export class PyFloat { v: number; constructor(v: number) { this.v = v } }
export const num = (x: unknown): number | undefined =>
  x instanceof PyFloat ? x.v : typeof x === 'number' ? x : undefined

export function pyLoads(src: string): any {
  let i = 0
  const ws = () => { while (i < src.length && ' \t\n\r'.includes(src[i])) i++ }
  const val = (): any => {
    ws()
    const c = src[i]
    if (c === '{') {
      i++; const o: any = {}; ws()
      if (src[i] === '}') { i++; return o }
      for (;;) {
        ws(); const k = str(); ws()
        if (src[i++] !== ':') throw new SyntaxError('expected : at ' + i)
        o[k] = val(); ws()
        const d = src[i++]
        if (d === '}') return o
        if (d !== ',') throw new SyntaxError('expected , at ' + i)
      }
    }
    if (c === '[') {
      i++; const a: any[] = []; ws()
      if (src[i] === ']') { i++; return a }
      for (;;) {
        a.push(val()); ws()
        const d = src[i++]
        if (d === ']') return a
        if (d !== ',') throw new SyntaxError('expected , at ' + i)
      }
    }
    if (c === '"') return str()
    if (src.startsWith('true', i)) { i += 4; return true }
    if (src.startsWith('false', i)) { i += 5; return false }
    if (src.startsWith('null', i)) { i += 4; return null }
    const m = /^-?\d+(\.\d+)?([eE][+-]?\d+)?/.exec(src.slice(i, i + 40))
    if (!m) throw new SyntaxError('bad JSON at ' + i)
    i += m[0].length
    return m[1] || m[2] ? new PyFloat(Number(m[0])) : Number(m[0]) // ponytail: ints > 2^53 lose precision; none in ACE payloads
  }
  const str = (): string => {
    if (src[i] !== '"') throw new SyntaxError('expected string at ' + i)
    const start = i; i++
    while (i < src.length && src[i] !== '"') i += src[i] === '\\' ? 2 : 1
    if (i >= src.length) throw new SyntaxError('unterminated string at ' + start)
    i++
    return JSON.parse(src.slice(start, i))
  }
  const v = val(); ws()
  if (i !== src.length) throw new SyntaxError('trailing data')
  return v
}

// repr(float) (Python 'r' format): fixed for 1e-4 <= |x| < 1e16, else scientific with >= 2 exponent digits.
export function pyFloatRepr(x: number): string {
  if (Number.isNaN(x)) return 'NaN'
  if (!Number.isFinite(x)) return x > 0 ? 'Infinity' : '-Infinity'
  if (x === 0) return Object.is(x, -0) ? '-0.0' : '0.0'
  const [mant, e] = x.toExponential().split('e')
  const exp = Number(e)
  const neg = mant.startsWith('-')
  const digits = mant.replace('-', '').replace('.', '')
  let out: string
  if (exp >= -5 + 1 && exp < 16) { // Python: -4 <= exp < 16
    if (exp >= 0) {
      const intPart = digits.slice(0, exp + 1).padEnd(exp + 1, '0')
      const frac = digits.slice(exp + 1)
      out = intPart + '.' + (frac || '0')
    } else {
      out = '0.' + '0'.repeat(-exp - 1) + digits
    }
  } else {
    const m = digits.length > 1 ? digits[0] + '.' + digits.slice(1) : digits
    out = m + 'e' + (exp < 0 ? '-' : '+') + String(Math.abs(exp)).padStart(2, '0')
  }
  return (neg ? '-' : '') + out
}

function pyStr(s: string): string {
  let out = '"'
  for (let k = 0; k < s.length; k++) {
    const ch = s[k], c = s.charCodeAt(k)
    if (ch === '"') out += '\\"'
    else if (ch === '\\') out += '\\\\'
    else if (ch === '\n') out += '\\n'
    else if (ch === '\r') out += '\\r'
    else if (ch === '\t') out += '\\t'
    else if (ch === '\b') out += '\\b'
    else if (ch === '\f') out += '\\f'
    else if (c < 0x20 || c > 0x7e) out += '\\u' + c.toString(16).padStart(4, '0')
    else out += ch
  }
  return out + '"'
}

// json.dumps(v[, sort_keys=True]) byte-for-byte (ensure_ascii, ", " / ": ").
export function pyDumps(v: any, sortKeys = false): string {
  if (v === null || v === undefined) return 'null'
  if (v === true) return 'true'
  if (v === false) return 'false'
  if (v instanceof PyFloat) return pyFloatRepr(v.v)
  if (typeof v === 'number') return Number.isInteger(v) ? String(v) : pyFloatRepr(v)
  if (typeof v === 'string') return pyStr(v)
  if (Array.isArray(v)) return '[' + v.map(x => pyDumps(x, sortKeys)).join(', ') + ']'
  const keys = Object.keys(v).filter(k => v[k] !== undefined)
  if (sortKeys) keys.sort()
  return '{' + keys.map(k => pyStr(k) + ': ' + pyDumps(v[k], sortKeys)).join(', ') + '}'
}

// ace_before_task.sanitize_response: a lone surrogate -> 3 x U+FFFD (utf-8 surrogatepass -> replace).
const LONE = /[\ud800-\udbff](?![\udc00-\udfff])|(?<![\ud800-\udbff])[\udc00-\udfff]/g
export function sanitize(v: any): any {
  if (typeof v === 'string') return v.replace(LONE, '���')
  if (Array.isArray(v)) return v.map(sanitize)
  if (v && typeof v === 'object' && !(v instanceof PyFloat)) {
    const o: any = {}; for (const k of Object.keys(v)) o[k] = sanitize(v[k]); return o
  }
  return v
}
