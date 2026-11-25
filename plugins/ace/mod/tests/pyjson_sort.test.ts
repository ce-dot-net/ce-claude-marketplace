// pyDumps(v, true) sorts keys like Python's json.dumps(sort_keys=True): by CODE POINT, not by UTF-16 unit.
import { expect } from 'claude-code/testing'
import { test } from './t.ts'
import { pyDumps } from '../lib/pyjson.ts'

test('sorted keys follow code point order: an astral key sorts after a key above U+E000', () => {
  const o = JSON.parse('{"\\ud83d\\ude00":1,"\\uffee":2,"Z":3,"a":4,"\\u00fc":5,"10":6,"2":7,"n":{"\\ud83d\\ude00":1,"\\ue000":2}}')
  // expected = python3: json.dumps(o, sort_keys=True)
  expect(pyDumps(o, true)).toBe('{"10": 6, "2": 7, "Z": 3, "a": 4, "n": {"\\ue000": 2, "\\ud83d\\ude00": 1}, "\\u00fc": 5, "\\uffee": 2, "\\ud83d\\ude00": 1}')
})

test('compact separators (the layout-a arm) keep the code point key order', () => {
  const o = JSON.parse('{"\\ud83d\\ude00":1,"\\uffee":2,"Z":3,"a":[1,{"b":2,"a":1}],"10":6,"2":7}')
  // expected = python3: json.dumps(o, sort_keys=True, separators=(',', ':'))
  expect(pyDumps(o, true, true)).toBe('{"10":6,"2":7,"Z":3,"a":[1,{"a":1,"b":2}],"\\uffee":2,"\\ud83d\\ude00":1}')
})
