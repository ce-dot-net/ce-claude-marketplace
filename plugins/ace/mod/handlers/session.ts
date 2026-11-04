// session.start / session.end: the session and its marker at start; at the end the pending self-evals are flushed
// and the session dir is removed unless a detached learn still holds its lock.
import { rm } from '../io/fs.ts'
import { type HookArgs, type Load, ensure, resolveSession, touchMarker } from '../io/state.ts'
import { startContext } from './context.ts'
import { registerCommands } from '../commands/index.ts'

export const LEARN_LOCK_MS = 600_000              // ace_session_end.py: learn timeout 300 s + margin

export async function sessionStart($: HookArgs<'session.start'>[0], L: Load, e: HookArgs<'session.start'>[1], next: HookArgs<'session.start'>[2]) {
  const r = await next(e)
  L.interactive = e.isInteractive !== false
  try {
    L.sess = await resolveSession($, e.cwd, L)
    if (L.sess) await touchMarker($, L, L.sess, await $.clock.now())
  } catch { /* the Python chain takes over without a marker */ }
  await registerCommands($).catch(() => undefined)
  await startContext($, L, e.cwd)  // the status call itself runs in the background
  return r
}

export async function sessionEnd($: HookArgs<'session.end'>[0], L: Load, e: HookArgs<'session.end'>[1], next: HookArgs<'session.end'>[2]) {
  const s = L.sess ?? await ensure($, L).catch(() => null)
  // item 1b: the process exits after this; a self-eval still waiting would take its learn with it. Stop waiting, send H2.
  for (const p of [...L.pendingLearns]) { p.ctl.abort(); await p.flush().catch(() => false) }
  try {
    if (s) {
      // A detached learn may still run (it owns its lock): keep the dir until the lock is stale, as ace_session_end.py.
      const now = await $.clock.now()
      const entries: any[] = await $.fs.list(s.sdir).catch(() => [])
      let busy = false
      for (const f of entries) {
        if (!/^learn-inflight-.*\.lock$/.test(f.name)) continue
        const st = await $.fs.stat(`${s.sdir}/${f.name}`).catch(() => null)
        if (st && now - st.mtimeMs < LEARN_LOCK_MS) busy = true
      }
      if (!busy) await rm($, s.sdir)
    }
  } catch { /* never block the exit */ }
  L.tools.clear(); L.turnAnchor.clear(); L.spawnPrompts.clear(); L.late.clear(); L.agentTypes.clear(); L.earlyStart.clear()
  L.agentEffort.clear(); L.domains = null; L.sess = null; L.markerAt = 0
  return next(e)
}
