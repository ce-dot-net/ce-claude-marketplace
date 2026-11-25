// Mod side of tests/e2e/test_layout_a.py: runs the SAME lib/*.ts the mod imports (node --experimental-strip-types).
// One JSON job on stdin: {"lists": [response json text], "budgets": [int], "caps": [int], "sids": [...], "envs": [{...}]}
import { readFileSync } from 'node:fs'
import * as J from '../../plugins/ace/mod/lib/pyjson.ts'
import * as R from '../../plugins/ace/mod/lib/render.ts'
import * as C from '../../plugins/ace/mod/lib/cohort.ts'
const job = JSON.parse(readFileSync(0, 'utf8'))
const out = { lists: [], members: [], fields: R.LAYOUT_A_FIELDS, hint: R.LAYOUT_A_HINT }
const pack = r => ({ ctx: r.context, ids: r.ids, rlog: r.rlog })
for (const text of job.lists) {
  const resp = J.sanitize(J.pyLoads(text))
  const row = { budget: [], full: [], sub: [], ds: [], hint: [] }
  for (const b of job.budgets) row.budget.push(pack(R.renderLayoutBudget(resp, 'ace-patterns', 'agent-type="main"', false, b)))
  row.sub.push(pack(R.renderLayoutBudget(resp, 'ace-patterns-subagent', 'agent-type="general-purpose"')))
  for (const c of job.caps) row.full.push(pack(R.renderLayoutFull(resp, 'ace-patterns', 'agent-type="main"', false, c)))
  row.ds.push(pack(R.renderLayoutDomainShift(resp, 'ace-"cli"&<x>')))
  row.hint.push(pack(R.renderLayoutBudget(resp, 'ace-patterns', 'agent-type="main"', true)), pack(R.renderLayoutFull(resp, 'ace-patterns', 'agent-type="main"', true)),
    pack(R.renderLayoutDomainShift(resp, 'ace-cli', true)))
  out.lists.push(row)
}
for (const env of job.envs) out.members.push(job.sids.map(s => C.layoutAMember(s || undefined, env)))
const cfg = c => ({ ACE_AB_CONTROL_PCT: String(c.C), ACE_AB_COMPACT_PCT: String(c.K), ACE_RENDER_FULL_PCT: String(c.F) })
out.vectors = (job.vectors?.cases ?? []).map(c => {
  const sid = c.id || undefined
  return { arm_c0: C.renderCohort(sid, cfg(job.vectors.configs.c0)), arm_c10: C.renderCohort(sid, cfg(job.vectors.configs.c10)),
    layout_a: C.layoutA(sid, { ...cfg(job.vectors.configs[job.vectors.layout_config]), ACE_RENDER_LAYOUT_A_PCT: String(job.vectors.L) }) }
})
out.pcts = (job.pcts ?? []).map(v => C.layoutAPct({ ACE_RENDER_LAYOUT_A_PCT: v }))
process.stdout.write(JSON.stringify(out))
