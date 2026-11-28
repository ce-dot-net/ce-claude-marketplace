// 8.4.3: humanPart, the redacted human-written part of a follow-up prompt (trace.followup.text, server-side judging; never the live gates).
import { expect } from 'claude-code/testing'
import { test } from './t.ts'
import { expectLinear } from './timing.ts'
import { HUMAN_HEAD, HUMAN_MARK, HUMAN_TAIL, extractHuman, humanPart } from '../lib/humanpart.ts'

test('humanPart: empty / whitespace / non-string -> empty', () => {
  for (const t of ['', '   \n\t ', undefined, null, 42]) expect(humanPart(t as any)).toBe('')
})
test('humanPart: plain prose (German, English) passes unchanged', () => {
  expect(humanPart('Das ist nicht das, was ich wollte. Mach es bitte nochmal.')).toBe('Das ist nicht das, was ich wollte. Mach es bitte nochmal.')
  expect(humanPart('please redo the second step, the output is wrong')).toBe('please redo the second step, the output is wrong')
})
test('humanPart: fenced code blocks are dropped (closed and unclosed, ``` and ~~~)', () => {
  expect(humanPart('das geht nicht:\n```ts\nconst x = 1\nfoo(bar)\n```\nbitte fixen')).toBe('das geht nicht:\nbitte fixen')
  expect(humanPart('see:\n~~~\nraw\n~~~\nok?')).toBe('see:\nok?')
  expect(humanPart('still broken\n```\nnever closed\nmore code')).toBe('still broken')
})
test('humanPart: stack traces, log lines and JSON lines are dropped, prose stays', () => {
  const t = ['geht immer noch nicht, schau mal:',
    'Traceback (most recent call last):', '  File "/x/y.py", line 12, in main', 'ValueError: bad value',
    'TypeError: x is undefined', '    at Object.<anonymous> (/a/b.js:10:5)', '    at run (node:internal/main:1:2)',
    '2026-11-26T10:00:01Z INFO server started', '[2026-11-26 10:00:02] ERROR boom', '10:00:03 WARN slow', 'DEBUG: value=3',
    '{"label": "x", "a": 1}', '  "key": "value",', '}', '[1, 2, 3]',
    '--- a/x.ts', '+++ b/x.ts', '@@ -1,2 +1,2 @@', '$ npm test',
    'at least the first part works now'].join('\n')
  expect(humanPart(t)).toBe('geht immer noch nicht, schau mal:\nat least the first part works now')
})
test('humanPart: long token runs (hashes, base64, long paths) and path-list lines are dropped', () => {
  const hash = 'a'.repeat(20) + '0123456789abcdef0123'
  expect(humanPart(`commit ${hash} ist kaputt`)).toBe('commit ist kaputt')
  expect(humanPart('x QUJDREVGR0hJSktMTU5PUFFSU1RVVldYWVo0123456789abc= y')).toBe('x y')
  expect(humanPart('fix these:\nsrc/a/b.ts src/c/d.ts lib/e/f.ts\nthanks')).toBe('fix these:\nthanks')
  expect(humanPart('0x1f 0x2a 0x3b 99 100 101 102 103 104\nwhy')).toBe('why')   // mostly non-letters: dropped
})
test('humanPart: emoji and umlauts are code points, kept as prose', () => {
  expect(humanPart('Super 👍 danke, aber die Größe stimmt nicht 😅')).toBe('Super 👍 danke, aber die Größe stimmt nicht 😅')
})
test('humanPart: redacts secrets first (nothing secret survives)', () => {
  const out = humanPart('my key is sk-' + 'ant-api03-' + 'A1b2C3d4'.repeat(4) + ' please')  // split: no secret-scanner hit on this file
  expect(out.includes('A1b2C3d4')).toBe(false)
})
test('humanPart: head 300 + marker + tail 300 only when longer than 600 code points; exactly 600 stays uncut', () => {
  expect([HUMAN_HEAD, HUMAN_TAIL, HUMAN_MARK]).toEqual([300, 300, ' […] '])
  const head = 'Größe '.repeat(HUMAN_HEAD / 6), mid = 'mitte '.repeat(40), tail = '😀 '.repeat(HUMAN_TAIL / 2)
  const out = humanPart(head + mid + tail)
  expect(out).toBe(head + HUMAN_MARK + ' ' + tail.trim())   // tail 300 code points = ' 😀' x 150
  expect([...out].length).toBe(HUMAN_HEAD + [...HUMAN_MARK].length + HUMAN_TAIL)
  const exact = 'ab '.repeat(199) + 'abc'                         // 600 code points
  expect([...exact].length).toBe(600)
  expect(humanPart(exact)).toBe(exact)
  const over = 'ab '.repeat(200) + 'x'                            // 601 code points
  expect([...over].length).toBe(601)
  expect(humanPart(over)).toBe('ab '.repeat(100) + HUMAN_MARK + over.slice(over.length - 300))
})
test('humanPart: blank-line runs collapse; mixed text keeps the human lines in order', () => {
  expect(humanPart('erste Zeile\n\n\n\nzweite Zeile')).toBe('erste Zeile\n\nzweite Zeile')
  expect(humanPart('ok\n```\ncode\n```\n\n\nINFO: x\nweiter')).toBe('ok\n\nweiter')
})
// 2,500 log lines (~150k, under the 200k input cap): the log goes, the prose around it stays
test('humanPart: a pasted log between prose lines; a huge token past the input cap', () => {
  const big = Array.from({ length: 2_500 }, (_, i) => `2026-11-26T10:00:${String(i % 60).padStart(2, '0')}Z INFO line ${i} ${'x'.repeat(20)}`).join('\n')
  expect(humanPart('bitte schau\n' + big + '\ndanke')).toBe('bitte schau\ndanke')
  expect(humanPart('a ' + 'b'.repeat(2_000_000) + ' c')).toBe('a')            // cut at 200k code points: ' c' is past the cap
  expect(humanPart('{'.repeat(100_000) + '\n' + '`'.repeat(100_000))).toBe('')
})
// review S4: the input is capped (USER_PROMPT_MAX code points) before the redactor runs
test('humanPart: a 10 MB paste stays fast (capped before redaction)', () => {
  const t0 = Date.now()
  expect(humanPart('bitte schau ' + 'wort '.repeat(2_000_000)).startsWith('bitte schau wort')).toBe(true)
  expect(Date.now() - t0 < 3000).toBe(true)
})
test('extractHuman: the uncut human part', () => {
  expect(extractHuman('x '.repeat(400)).length > 600).toBe(true)
})
// review S4 (2): a log / error / shell prefix does not drop a line that still holds prose (>= 3 letter-words) after it.
// ponytail: so a machine error with a sentence ("TypeError: Cannot read properties of undefined") is kept too; the server judges.
test('humanPart: log / error / shell prefixed lines that still hold prose are kept', () => {
  for (const l of ['Error: das ist falsch, mach das anders', 'INFO das passt so nicht', '12:30:00 ist der Termin, das stimmt nicht', '$ npm test schlägt fehl seit gestern'])
    expect(humanPart('hallo\n' + l)).toBe('hallo\n' + l)
  for (const l of ['ValueError: bad value', 'INFO x', '10:00:03 WARN slow', '$ npm test', '    at foo (a.js:1:2) das ist falsch hier', '{"a": "das ist falsch hier"}'])
    expect(humanPart('hallo\n' + l)).toBe('hallo')
})
// review S4 (3): a 40+ code point token drops only itself, never its line
test('humanPart: a long token drops only the token, not the line', () => {
  expect(humanPart('fix 0123456789012345678901234567890123456789abc now')).toBe('fix now')
  expect(humanPart('bitte ' + 'ä'.repeat(45) + ' nochmal machen')).toBe('bitte nochmal machen')
})
// review M1: no quadratic backtracking on 100k-char lines. Load-proof (tests/timing.ts): the exponent is fitted over 4 input sizes,
// linear ~1, quadratic 2; a busy machine slows all sizes alike, so one load spike cannot fake a slope.
test('humanPart: linear on 100k-char lines (stack-frame-like, long URL, low-entropy tokens, prefixes)', () => {
  const shapes: ((n: number) => string)[] = [n => 'at ' + 'x'.repeat(n), n => 'at ' + 'x '.repeat(n / 2), n => 'at https://example.com/' + 'a/'.repeat(n / 2),
    n => 'at x' + ':'.repeat(n), n => 'at ' + 'a('.repeat(n / 2), n => 'File "' + 'x'.repeat(n), n => 'Error' + 'Error'.repeat(n / 5), n => '[' + ' '.repeat(n) + 'x',
    n => '"' + 'a'.repeat(n) + ' :', n => 'ab '.repeat(n / 3), n => 'a'.repeat(n), n => ('aaaa ' + 'a'.repeat(39) + ' ').repeat(n / 50),
    n => '12:30:00 ' + 'INFO '.repeat(n / 5), n => '$ ' + 'a '.repeat(n / 2)]
  shapes.forEach((shape, i) => expectLinear(f => shape(Math.max(50, Math.round(100_000 * f / 50) * 50)), c => { humanPart(c); humanPart(c + '\n' + c) }, `shape ${i}`))
})
