// Evaluation of the rejection classifier over a labelled set, given any `$.model.complete` (a stub in the tests here). Tests only:
// nothing under mod/ imports it. The live evaluation runs from a throwaway local copy of the plugin, never from shipped code.
import { classifyRejection, REJECTION_MIN_CONF } from '../lib/rejection'

export type EvalExample = { text: string; label: 'reject' | 'keep'; lang: string; kind: string; split: string; tail?: string }
export type EvalRow = { ex: EvalExample; failed: string | null; reject: boolean | null; conf: number | null; label: string | null }
// a few neutral previous answers, rotated by index (the classifier sees an answer tail, never an empty one)
const PREVS = ['I updated the function as requested and ran the tests; all of them pass.', 'The refactor is done. I moved the helpers into utils and fixed the imports.',
  'Here is the script. It reads the config, validates it and writes the report to disk.', 'I added the endpoint and the migration. Run the migration before starting the server.']

export async function runEval($: any, examples: readonly EvalExample[], opts: { concurrency?: number; minConf?: number } = {}): Promise<EvalRow[]> {
  const out: EvalRow[] = new Array(examples.length)
  let next = 0
  const worker = async () => { for (let i = next++; i < examples.length; i = next++) {
    const ex = examples[i]!
    const v = await classifyRejection($, ex.text, ex.tail ?? PREVS[i % PREVS.length]!, opts.minConf ?? REJECTION_MIN_CONF)
    out[i] = { ex, failed: v.failed, reject: v.reject, conf: v.conf, label: v.label ?? null }
  } }
  await Promise.all(Array.from({ length: Math.max(1, opts.concurrency ?? 8) }, worker))
  return out
}
export type Counts = { tp: number; fp: number; fn: number; tn: number; err: number }
// positive prediction = label reject at confidence >= thr; an errored call counts as err (not predicted)
export function score(rows: readonly EvalRow[], thr: number): Counts {
  const c: Counts = { tp: 0, fp: 0, fn: 0, tn: 0, err: 0 }
  for (const r of rows) {
    if (r.failed === 'model_error' || r.failed === 'model_timeout') { c.err++; continue }
    const pred = r.reject === true && (r.conf ?? 0) >= thr
    if (pred) r.ex.label === 'reject' ? c.tp++ : c.fp++
    else r.ex.label === 'reject' ? c.fn++ : c.tn++
  }
  return c
}
const pct = (a: number, b: number) => b ? Math.round(100 * a / b) + '%' : 'n/a'
export const pr = (c: Counts) => `P=${pct(c.tp, c.tp + c.fp)} R=${pct(c.tp, c.tp + c.fn)} (tp ${c.tp} fp ${c.fp} fn ${c.fn} tn ${c.tn} err ${c.err})`
export function report(rows: readonly EvalRow[], thr = REJECTION_MIN_CONF, sweep = [0.6, 0.7, 0.8, 0.9]): string {
  const langs = [...new Set(rows.map(r => r.ex.lang))]
  const lines = [`threshold ${thr}, n=${rows.length}`, ...langs.map(l => `${l.padEnd(6)} ${pr(score(rows.filter(r => r.ex.lang === l), thr))}`), `ALL    ${pr(score(rows, thr))}`,
    'sweep: ' + sweep.map(t => `${t}: ${pr(score(rows, t))}`).join(' | ')]
  const miss = rows.filter(r => { const p = r.reject === true && (r.conf ?? 0) >= thr; return r.failed !== 'model_error' && r.failed !== 'model_timeout' && p !== (r.ex.label === 'reject') })
  lines.push(...miss.map(r => `${r.ex.label === 'reject' ? 'FN' : 'FP'} [${r.ex.lang}/${r.ex.kind}] label=${r.label} conf=${r.conf}`))
  return lines.join('\n')
}
