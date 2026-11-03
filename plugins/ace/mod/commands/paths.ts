// A user-given path for a command (export target, import source): it must stay inside the repo root (c.root) by
// text AND by the realpath of its parent dir, and the target must not be a symlink (security review 8.1.0).
import { normPath } from '../context/resolve.ts'
import { run } from '../io/fs.ts'

export type Checked = { ok: true, abs: string, rel: string, exists: boolean } | { ok: false, why: string }
async function realDir($: any, dir: string): Promise<string | null> {
  const r = await run($, ['/bin/sh', '-c', 'cd -- "$1" 2>/dev/null && pwd -P', 'sh', dir])
  return r && r.exitCode === 0 ? String(r.stdout).trim() : null
}
export async function insideRoot($: any, root: string, arg: string): Promise<Checked> {
  if (!arg || /[\0\n\r]/.test(arg)) return { ok: false, why: 'bad path' }
  const abs = normPath(arg.startsWith('/') ? arg : `${root}/${arg}`), base = normPath(root)
  if (abs === base || !abs.startsWith(base + '/')) return { ok: false, why: `outside the repo root ${base}` }
  const rel = abs.slice(base.length + 1)
  let cur = base
  for (const part of rel.split('/')) {  // no symlinked component, the target included
    const list: any[] = await $.fs.list(cur).catch(() => [])
    const hit = list.find(f => f.name === part)
    if (hit?.isLink) return { ok: false, why: `symlink: ${cur}/${part}` }
    if (!hit) break
    cur = `${cur}/${part}`
  }
  const parent = abs.slice(0, abs.lastIndexOf('/'))
  const [rp, rr] = [await realDir($, parent), await realDir($, base)]
  if (rp !== null && rr !== null && rp !== rr && !rp.startsWith(rr + '/')) return { ok: false, why: `outside the repo root (realpath ${rp})` }
  return { ok: true, abs, rel, exists: !!await $.fs.exists(abs).catch(() => false) }
}
// argv values a user typed: never an option, never a path or metacharacter.
export const safeToken = (v: string) => /^[A-Za-z0-9._:-]+$/.test(v) && !v.startsWith('-')
