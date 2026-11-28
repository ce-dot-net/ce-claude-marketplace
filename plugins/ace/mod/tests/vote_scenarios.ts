// 8.4.3: the vote scenarios of the golden test (vote_golden.test.ts), shared with followup.test.ts (the shadow mode keeps every one of them). Not a *.test.ts file.
import S8 from './fixtures/search_8.ts'
import { HOME, PROOT, ROOT, SDIR, SID, done, host, mainTask, st8a, submit } from './helpers.ts'
import { followupFileFor, sha256Hex, unresolvedFileFor } from '../lib/cohort.ts'
import { flushRejections } from '../handlers/prompt.ts'
import { REJECTION_SYSTEM } from '../lib/rejection.ts'

export const ans = (label: string, confidence: number) => () => ({ isAnswered: true, text: JSON.stringify({ label, confidence }) })
export const NEUTRAL = 'could you look at the second file again please'
const CFG = `${HOME}/.config/ace/config.json`
export const T0S = 1_800_000_000
// the stored follow-up switch (followup-judging.json) in states that must all be OFF: byte-identical to 8.4.2
// the stored switch of THIS session's org/project (review 2: one file per org/project; the legacy global file is ignored)
export const FOLLOWUP_FILE = `${ROOT}/${followupFileFor('org_t', 'prj_t')}`
export const LEGACY_FOLLOWUP_FILE = `${ROOT}/followup-judging.json`
const fj = (o: any) => ({ [FOLLOWUP_FILE]: typeof o === 'string' ? o : JSON.stringify(o) })
export const UNRESOLVED_FILE = `${ROOT}/${unresolvedFileFor('org_t', 'prj_t')}`
const fu = (o: any) => ({ [UNRESOLVED_FILE]: typeof o === 'string' ? o : JSON.stringify(o) })
export const SWITCHES: Record<string, Record<string, string>> = {
  none: {},
  off: fj({ mode: 'off', at: T0S }),
  stale: fj({ mode: 'live', at: T0S - 8 * 86400 }),
  wrong: fj({ mode: 'LIVE', at: T0S }),
  bool: fj({ mode: true, at: T0S }),
  junk: fj('not json'),
  legacy_live: { [LEGACY_FOLLOWUP_FILE]: JSON.stringify({ mode: 'live', at: T0S, org: 'org_t', project: 'prj_t' }) },   // pre-hash name: ignored
  // the feedback-unresolved file in states that must all be OFF (symmetric to the follow-up file)
  unres_off: fu({ on: false, at: T0S, org: 'org_t', project: 'prj_t' }),
  unres_stale: fu({ on: true, at: T0S - 8 * 86400, org: 'org_t', project: 'prj_t' }),
  unres_string: fu({ on: 'true', at: T0S, org: 'org_t', project: 'prj_t' }),
  unres_one: fu({ on: 1, at: T0S, org: 'org_t', project: 'prj_t' }),
  unres_other_project: fu({ on: true, at: T0S, org: 'org_t', project: 'prj_other' }),
  unres_other_org: fu({ on: true, at: T0S, org: 'org_other', project: 'prj_t' }),
  unres_future: fu({ on: true, at: T0S + 3600, org: 'org_t', project: 'prj_t' }),
  unres_junk: fu('not json'),
  unres_legacy: { [`${ROOT}/feedback-unresolved.json`]: JSON.stringify({ on: true, at: T0S, org: 'org_t', project: 'prj_t' }) },   // pre-hash name: ignored
}
export type Ctx = { $: any; h: any; settle: () => Promise<void>; release: () => void }
// reply2: a second reply after the first; script: replaces the default sequence (prev task, reply, next task); selfEval: the Haiku
// self-eval is on and answers only after ctx.release() (the self-eval window)
export type Sc = { prev?: string; reply?: string; reply2?: string; model?: (req: any) => any; env?: Record<string, string>; files?: Record<string, string>; noPrev?: boolean
  script?: (c: Ctx) => Promise<void>; selfEval?: boolean }
const applied = () => 'applied ' + st8a().a
export const SCENARIOS: Record<string, Sc> = {
  phrase_down: { reply: 'das ist falsch' },
  model_down: { reply: NEUTRAL, model: ans('reject', 0.93) },
  model_no: { reply: NEUTRAL, model: ans('neutral', 0.9) },
  model_low: { reply: NEUTRAL, model: ans('reject', 0.79) },
  model_err: { reply: NEUTRAL },
  phrase_up: { reply: 'Perfekt, danke!' },
  empty_ids_down: { prev: 'done', reply: 'das ist falsch' },
  empty_ids_up: { prev: 'done', reply: 'perfekt' },
  empty_ids_model: { prev: 'done', reply: NEUTRAL, model: ans('reject', 1) },
  switch_off: { reply: 'das ist falsch', env: { ACE_FEEDBACK_DOWNVOTE: '0' } },
  too_long: { reply: 'das ist falsch ' + 'x '.repeat(200) },
  prev_stale: { reply: 'das ist falsch', noPrev: true },
  model_off: { reply: NEUTRAL, model: ans('reject', 1), env: { ACE_REJECTION_MODEL: '0' } },
  both_pending: { reply: NEUTRAL, files: { [`${SDIR}/pending-downvote.json`]: '{"applied_log_ids": [7], "at": 1800000000}', [`${SDIR}/pending-upvote.json`]: '{"applied_log_ids": [8], "at": 1800000000}' } },
  held: { reply: 'das ist falsch', files: { [CFG]: '{}', [`${ROOT}/auth-rejected`]: sha256Hex('{}') } },
  // review S3 (8.4.3): more live paths
  // session.end while the model answers (the harness keeps the dir: the vote is still written)
  session_end_inflight: { model: ans('reject', 0.93), script: async ({ $, h, settle }) => {
    await mainTask($, h); await done($, applied()); await submit($, NEUTRAL)
    await $.session.end({ sessionId: SID, reason: 'clear' } as any); await settle()
    await mainTask($, h); await done($, 'did something else'); await settle()
  } },
  revote_lock: { reply: 'das ist falsch', reply2: 'das ist immer noch falsch' },
  cache_hit: { reply: NEUTRAL, reply2: NEUTRAL, model: ans('neutral', 0.9) },
  up_bare_ack: { reply: 'ok' },
  up_reject_phrase: { reply: 'perfekt ist anders, das ist falsch' },
  up_blocked: { reply: 'perfekt, jetzt noch die doku' },
  late_verdict: { model: ans('reject', 0.93), script: async ({ $, h, settle }) => {
    await mainTask($, h); await done($, applied()); await submit($, NEUTRAL)
    await mainTask($, h); await done($, 'did something else'); await settle()   // the verdict lands after this Stop
    await mainTask($, h); await done($, 'a third thing'); await settle()
  } },
  mid_turn: { script: async ({ $, h, settle }) => {
    await mainTask($, h)
    await $.prompt.submit({ text: 'das ist falsch', wait: false, origin: { kind: 'composer' }, turnId: 't1' } as any); await settle()
    await done($, applied()); await mainTask($, h); await done($, 'did something else'); await settle()
  } },
  py_record_down: { noPrev: true, reply: 'das ist falsch', files: { [`${SDIR}/last-main-applied.json`]: '{"task_session_id": null, "applied_log_ids": [1003], "at": 1800000000}' } },
  py_record_empty: { noPrev: true, reply: 'das ist falsch', files: { [`${SDIR}/last-main-applied.json`]: '{"task_session_id": null, "applied_log_ids": [], "at": 1800000000}' } },
  // legacy-file tolerance: a pending vote file in the shape an unreleased 8.4.3 draft wrote ([] ids + unresolved) is dropped, as by 8.4.2
  stale_unresolved_pending: { reply: NEUTRAL, files: { [`${SDIR}/pending-downvote.json`]: JSON.stringify({ applied_log_ids: [], at: T0S, task_session_id: null, detect_source: 'phrase', unresolved: true, target_retrieval_id: '00000000-0000-4000-8000-000000000001' }) } },
  selfeval_window: { selfEval: true, script: async ({ $, h, settle, release }) => {
    await mainTask($, h); await done($, applied())
    await submit($, 'das ist falsch'); await settle()          // the self-eval of the task before is still running
    release(); await settle()
    await mainTask($, h); await done($, 'did something else'); await settle(); await settle()
  } },
  sink_phrase_down: { reply: 'das ist falsch', env: { ACE_TRACE_SINK: 'file:/home/u/sink' } },
}
const VOTE_FILES = ['pending-downvote.json', 'pending-upvote.json', 'last-downvoted-task']
const norm = (r: any) => { const { timestamp, model_ms, ...x } = r; return { ...x, model_ms: model_ms === undefined ? undefined : typeof model_ms } }
export const lma = (h: any) => { const t = h.files.get(`${SDIR}/last-main-applied.json`); if (t === undefined) return null; const { retrieval_id, ...x } = JSON.parse(t); return x }
// task ids are random: each distinct uuid becomes U<n> in order of first appearance (its 8-char prefix U<n>.8)
const canon = (o: any) => {
  // tool step times are wall-clock (not the mock clock): their numbers are masked, also inside JSON strings in argv
  let t = JSON.stringify(o, (k, v) => /^(start|end|duration)_ms$/.test(k) && typeof v === 'number' ? 'ms' : v).split(PROOT).join('<PROOT>')
    .replace(/(\\?"(?:start|end|duration)_ms\\?": ?)\d+/g, (_m: string, a: string) => a + '0')
  const m = new Map<string, string>()
  for (const u of t.match(/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/g) ?? []) if (!m.has(u)) m.set(u, `U${m.size}`)
  for (const [u, k] of m) t = t.split(u).join(k).split(`"${u.slice(0, 8)}"`).join(`"${k}.8"`)
  return JSON.parse(t)
}
const voteFiles = (h: any) => Object.fromEntries(VOTE_FILES.map(f => [f, h.files.get(`${SDIR}/${f}`) ?? null]))

// respExtra: changes every search answer (e.g. adds followup_judging); none = the plain fixture, as captured on 8.4.2
export async function snapshot($: any, on: any, sc: Sc, extraFiles: Record<string, string> = {}, extraEnv: Record<string, string> = {}, respExtra?: (o: any) => void) {
  let release = () => {}
  const gate = new Promise<void>(r => { release = r })
  const live = (req: any) => sc.model ? sc.model(req) : { isAnswered: false, reason: 'api-error', status: 500, error: 'x' }
  const model = sc.selfEval ? (req: any) => req.system ? live(req) : gate.then(() => ({ isAnswered: true, text: '{"used": []}' })) : sc.model
  const h = host(on, { defaultArm: true, mockClock: true, search: () => { if (!respExtra) return { stdout: S8 }; const o = JSON.parse(S8); respExtra(o); return { stdout: JSON.stringify(o) } }, env: { ACE_FEEDBACK_DOWNVOTE: '1', ...(sc.env ?? {}), ...extraEnv },
    files: { ...(sc.files ?? {}), ...extraFiles }, ...(model ? { model } : {}), ...(sc.selfEval ? { selfEval: true } : {}) })
  const settle = async () => { await h.clock.advance(1); await flushRejections(); for (let i = 0; i < 5; i++) await new Promise(r => setTimeout(r, 1)) }
  let afterReply: any = null
  if (sc.script) await sc.script({ $, h, settle, release })
  else {
    if (!sc.noPrev) { await mainTask($, h); await done($, sc.prev ?? applied()) }
    await submit($, sc.reply!)
    await settle()
    if (sc.reply2 !== undefined) { await submit($, sc.reply2); await settle() }
    afterReply = { files: voteFiles(h), lma: lma(h) }
    await mainTask($, h)
    await done($, 'did something else')
    await settle()
  }
  const rows = h.rows().filter((x: any) => ['rejection_check', 'rejection_detected', 'upvote_check'].includes(x.event)).map(norm)
  return { h, snap: canon({ afterReply, rows, end: { files: voteFiles(h), lma: lma(h) },
    feedback: h.learns().map((r: any) => h.trace(r).feedback ?? null), enqueued: h.enqueued.map((q: any) => JSON.parse(q.body ?? '{}').feedback ?? null),
    model: h.modelCalls.map((c: any) => c.system === REJECTION_SYSTEM ? 'rejection' : 'other'),
    // review S3: the whole sent traces, the learn argv (incl. the launcher meta) and the sink files
    full: { traces: h.learns().map((r: any) => h.trace(r)), argv: h.learns().map((r: any) => r.argv), parked: h.enqueued.map((q: any) => ({ argv: q.argv, body: JSON.parse(q.body ?? 'null') })),
      sink: [...h.files.keys()].filter((k: string) => k.startsWith('/home/u/sink/')).map((k: string) => JSON.parse(h.files.get(k)!))
        .sort((a: any, b: any) => String(a.result?.summary).localeCompare(String(b.result?.summary))) } }) }
}

