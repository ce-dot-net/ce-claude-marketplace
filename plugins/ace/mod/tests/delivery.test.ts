// ACE mod suite, 8.1.4 trace delivery (DESIGN "Trace delivery"): the trace hand-over between the launcher and the
// detached child, the queue job the child gets, the Idempotency-Key, result.plugin_version / result.outcome_rule.
// The queue itself is ONE Python module (shared-hooks/utils/ace_trace_queue.py) for both chains; the real child and
// queue run in tests/e2e/test_e2e_trace_delivery.py. Harness: ./helpers.ts.
import { expect, test } from 'claude-code/testing'
import S8 from './fixtures/search_8.ts'
import { OUTCOME_RULES } from '../lib/trace.ts'
import { CWD, PROOT, REL, ROOT, SDIR, SID, done, host, mainTask } from './helpers.ts'

const MANIFEST = { [`${PROOT}/.claude-plugin/plugin.json`]: '{"name": "ace", "version": "8.1.4"}' }
const job = (argv: string[]) => argv.flatMap(a => { try { const o = JSON.parse(a); return o && o.meta && o.id ? [o] : [] } catch { return [] } })[0]

test('OUTCOME_RULES: the fixed list (same as ace_trace_meta.OUTCOME_RULES)', async () => {
  expect(OUTCOME_RULES).toEqual(['end-outcome-1', 'permission-gate-1'])
})

test('the trace carries result.plugin_version (manifest x.y.z) and result.outcome_rule, nothing top level', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }), files: MANIFEST })
  await mainTask($, h)
  await done($)
  const t = h.trace(h.learns()[0]!)
  expect(t.result.plugin_version).toBe('8.1.4')
  expect(t.result.outcome_rule).toBe('end-outcome-1')
  expect(OUTCOME_RULES.includes(t.result.outcome_rule)).toBe(true)
  expect('plugin_version' in t || 'outcome_rule' in t).toBe(false)
})

test('the learn child gets the queue job: id = trace file uuid, data root, utils, log, meta (no trace content)', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }) })
  await mainTask($, h)
  await done($)
  const L = h.learns()[0]!
  const j = job(L.argv)
  const file = h.flag(h.learnArgv(L), '--transcript')!
  expect(file).toBe(`${ROOT}/tmp/ace-trace-${j.id}.json`)
  expect(j.root).toBe(ROOT)
  expect(j.utils).toBe(`${PROOT}/shared-hooks/utils`)
  expect(j.log).toBe(REL)
  expect(j.cwd).toBe(CWD)
  expect(j.on).toBe(true)
  expect(j.meta).toEqual({ org: 'org_t', project: 'prj_t', retrieval_id: h.trace(L).retrieval_id ?? null,
    applied_log_ids: h.trace(L).applied_log_ids ?? [], hook: 'Stop', agent_type: 'main', session_id: SID })
  expect(JSON.stringify(j).includes('User request')).toBe(false)
})

test('ACE_TRACE_QUEUE=0: the job says off (the child logs learn_lost only)', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }), env: { ACE_TRACE_QUEUE: '0' } })
  await mainTask($, h)
  await done($)
  expect(job(h.learns()[0]!.argv).on).toBe(false)
})

test('engine learn sends the queue id as --idempotency-key; the ace-cli fallback never gets the flag', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }), files: { [`${PROOT}/engine/learn.js`]: '' } })
  await mainTask($, h)
  await done($)
  const a = h.runs.find(r => r.argv.includes(`${PROOT}/engine/learn.js`))!.argv
  const sep = a.indexOf('--ace-fallback-on-3--'), id = job(a).id
  expect(a.slice(0, sep)).toContain('--idempotency-key')
  expect(a[a.indexOf('--idempotency-key') + 1]).toBe(id)
  expect(a.slice(sep).includes('--idempotency-key')).toBe(false)
})

test('a launcher that did not return in time: the parent claims the trace by rename before touching it, then queues it', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }), learnExit: 1 })
  await mainTask($, h)
  await done($)
  const L = h.learns()[0]!, file = h.flag(h.learnArgv(L), '--transcript')!
  const i = h.runs.indexOf(L)
  const after = h.runs.slice(i + 1)
  const mv = after.findIndex(r => r.argv[0] === 'mv')
  expect(after[mv]!.argv).toEqual(['mv', '-n', file, `${file}.parent`])
  const rmTrace = after.findIndex(r => r.argv.includes('rm') && r.argv.includes(file))
  expect(rmTrace).toBe(-1)  // the old 15 s path removed the file under a live child (ENOENT in the CLI)
  const enq = after.find(r => r.argv.some(a => a.endsWith('/shared-hooks/utils/ace_trace_queue.py')))!
  expect(enq.argv.slice(-3, -1)).toEqual(['--enqueue', `${file}.parent`])
  expect(job([enq.argv[enq.argv.length - 1]!]).id.length > 0).toBe(true)
  expect(h.rows().filter((x: any) => x.event === 'execution').map((x: any) => x.learning_sent)).toEqual([false])
  expect(h.files.has(`${SDIR}/learn-inflight-main.lock`)).toBe(false)
})

test('the child already owns the trace: the parent leaves it, queues nothing and writes no row (the child does)', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }), learnExit: 1, claimed: true })
  await mainTask($, h)
  await done($)
  expect(h.runs.some(r => r.argv.some(a => a.endsWith('/ace_trace_queue.py')))).toBe(false)
  expect(h.rows().filter((x: any) => x.event === 'execution')).toEqual([])
  expect(h.files.has(`${SDIR}/learn-inflight-main.lock`)).toBe(true)  // the child releases its own lock
})
