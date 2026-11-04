// session.compact: the mod-compact marker (the Python SessionStart(compact) re-inject steps aside) and the
// §31 dedupe reset after a main compaction.
import { rm } from '../io/fs.ts'
import { type HookArgs, type Load, disabled, ensure } from '../io/state.ts'

// item A: patterns survive a main compaction natively. session.compact (not on guarded seats) sets the flag and the
// mod-compact marker (the Python SessionStart(compact) re-inject steps aside); prompt.compose then adds the task's
// re-inject copy as its own section until the next prompt injects fresh.
// The marker goes down BEFORE next(): the Python SessionStart(compact) runs inside it and must already see it.
export async function sessionCompact($: HookArgs<'session.compact'>[0], L: Load, e: HookArgs<'session.compact'>[1], next: HookArgs<'session.compact'>[2]) {
  let mark: string | null = null
  try {
    if (!e.agentId && e.trigger !== 'precompute') {
      const s = await ensure($, L)
      if (s && !(await disabled($, s))) { mark = `${s.sdir}/mod-compact`; await $.fs.write(mark, String(await $.clock.now())) }
    }
  } catch { mark = null /* the Python SessionStart(compact) hook re-injects */ }
  let r: any
  try { r = await next(e) } catch (err) { if (mark) await rm($, mark).catch(() => {}); throw err }
  if (!mark) return r
  try {
    if (r && !r.skip) {
      L.compacted = true
      const fi = mark.replace(/mod-compact$/, 'full-injected.json')
      if (await $.fs.exists(fi)) await rm($, fi)  // §31 dedupe starts over
    } else await rm($, mark)  // no compaction: a later real one must not be silenced
  } catch { /* stale marker ages out (MOD_COMPACT_S) */ }
  return r
}
