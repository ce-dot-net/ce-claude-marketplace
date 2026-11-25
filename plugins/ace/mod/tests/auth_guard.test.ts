// ACE mod suite, 8.4.0: after an auth failure no further engine / ace-cli search (each one is a GET /config on the server)
// until the token file changes. Marker <root>/auth-rejected = sha256 of ~/.config/ace/config.json. Python twin: tests/test_auth_guard.py.
import { expect } from 'claude-code/testing'
import { test } from './t.ts'
import S8 from './fixtures/search_8.ts'
import { sha256Hex } from '../lib/cohort.ts'
import { HOME, HUMAN, PROOT, ROOT, host, submit } from './helpers.ts'

const CFG = `${HOME}/.config/ace/config.json`
const ENGINE = { [`${PROOT}/engine/search.js`]: '' }
const EXPIRED = { exitCode: 1, stderr: 'Session expired - please log in again: run `ace-cli login`.' }

test('engine auth failure still tries ace-cli; its auth failure holds: marker =  the token-file hash, later prompts spawn nothing, a new token lets one through', async ($, on) => {
  let engine = 0, cli = 0
  let cliAnswer: any = { exitCode: 1, stderr: 'Error: Not logged in' }
  let answer: any = EXPIRED
  const h = host(on, { files: { ...ENGINE, [CFG]: '{"auth":{"token":"dead"}}' }, search: () => (cli++, cliAnswer), engine: () => (engine++, answer) })
  await submit($)
  expect(engine).toBe(1)
  expect(cli).toBe(1)
  expect(h.files.get(`${ROOT}/auth-rejected`)).toBe(sha256Hex('{"auth":{"token":"dead"}}'))
  await submit($, HUMAN + ' again')
  await submit($, HUMAN + ' once more')
  expect(engine).toBe(1)
  expect(cli).toBe(1)
  h.put(CFG, '{"auth":{"token":"fresh"}}')
  answer = { stdout: S8 }
  await submit($, HUMAN + ' after login')
  expect(engine).toBe(2)
})

test('ace-cli auth failure holds too (no engine)', async ($, on) => {
  const h = host(on, { files: { [CFG]: '{}' }, search: () => ({ exitCode: 1, stderr: 'Error: Not logged in' }) })
  await submit($)
  await submit($, HUMAN + ' again')
  expect(h.searches().length).toBe(1)
  expect(h.files.get(`${ROOT}/auth-rejected`)).toBe(sha256Hex('{}'))
})
