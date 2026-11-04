// prompt.compose: after a main compaction, the task's re-inject copy of the patterns as its own section.
import { readText } from '../io/fs.ts'
import { type HookArgs, type Load, readState } from '../io/state.ts'

export async function promptCompose($: HookArgs<'prompt.compose'>[0], L: Load, e: HookArgs<'prompt.compose'>[1], next: HookArgs<'prompt.compose'>[2]) {
  const r: any = await next(e)
  if (!L.compacted || !L.sess) return r
  try {
    const st = await readState($, L.sess, 'main')
    const text = st?.rendered_context || await readText($, `${L.sess.sdir}/rendered-main.txt`)
    // ponytail: subagent requests composed in this window get the section too; per-request agent scoping when compose says who asks
    if (text) return { ...r, sections: [...(r?.sections ?? []).filter((x: any) => x.id !== 'ace:patterns'), { id: 'ace:patterns', text, scope: 'session' }] }
  } catch { /* never break the prompt */ }
  return r
}
