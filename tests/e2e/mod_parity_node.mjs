// Mod side of the renderer parity harness (tests/e2e/test_mod_render_parity.py).
// Runs the SAME lib/*.ts the mod imports (node --experimental-strip-types), one JSON job on stdin:
// {"fixtures": [paths], "sids": [...], "envs": [{...}], "learnJob": {...}|null, "roots": [[home, root, name], ...]}
import { readFileSync } from 'node:fs'
import * as J from '../../plugins/ace/mod/lib/pyjson.ts'
import * as R from '../../plugins/ace/mod/lib/render.ts'
import * as C from '../../plugins/ace/mod/lib/cohort.ts'
import * as S from '../../plugins/ace/mod/lib/state.ts'
import * as T from '../../plugins/ace/mod/lib/trace.ts'
import * as E from '../../plugins/ace/mod/lib/evidence.ts'
import * as SH from '../../plugins/ace/mod/lib/sh.ts'
const M = { ...J, ...R, ...C, ...S, ...T, ...E, ...SH }

const job = JSON.parse(readFileSync(0, 'utf8'))
const out = { fixtures: {}, cohorts: [], roots: [], learnArgv: null }
for (const f of job.fixtures) {
  const resp = M.sanitize(M.pyLoads(readFileSync(f, 'utf8')))
  const { dict, ids, rlog } = M.renderPatternsDict(resp)
  const full = M.renderFull(resp, 'ace-patterns', 'agent-type="main"')
  const capped = M.renderFull(resp, 'ace-patterns', 'agent-type="main"', 10000)
  out.fixtures[f] = {
    patterns_sorted_bytes: dict.similar_patterns.map(p => M.pyDumps(p, true)),
    top_keys: Object.keys(dict),
    top_rest_bytes: Object.fromEntries(Object.keys(dict).filter(k => k !== 'similar_patterns').map(k => [k, M.pyDumps(dict[k])])),
    ids, rlog_entries: Object.entries(rlog),
    full: full.context, full_ids: full.ids,
    state_render: capped.context,
    budget: M.renderBudget(resp, 'ace-patterns', 'agent-type="main"'),
    compact: M.renderCompact(resp, 'ace-patterns', 'agent-type="main"'),
    domain_shift: M.renderDomainShift(resp, 'ace-cli').context,
  }
}
for (const env of job.envs) out.cohorts.push(job.sids.map(s => M.renderCohort(s, env)))
for (const [home, root, name] of job.roots) out.roots.push(M.dataRootFromPluginRoot(home, root, name))
if (job.learnJob) out.learnArgv = M.detachedLearnArgv(job.learnJob)
out.used = (job.used ?? []).map(([ids, contents, msg, inputs]) => M.usedPatternIds(ids, contents, msg, M.toolHaystack(inputs ?? [])))
out.normalized = (job.variants ?? []).map(v => M.normalizeVariant(v) ?? null)
out.shell = { append: M.APPEND_SH, privateWrite: M.PRIVATE_WRITE_SH }
process.stdout.write(JSON.stringify(out))
