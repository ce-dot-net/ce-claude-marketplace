// 8.2.0 /ace:ace-bootstrap arguments: positional `[mode] [level]` and flags `--mode X --thoroughness Y` (`--flag=value` too), plus
// `--commit-limit N --days-back N --max-files N` passed through to the CLI as positive integers. Nothing given gives nothing:
// the CLI then uses the server's defaults. Pure. Anything else (unknown flag, third word, a conflict) is refused with the usage.
export const MODES = ['hybrid', 'both', 'local-files', 'git-history', 'docs-only'], LEVELS = ['light', 'medium', 'deep']
const NUMS = ['--commit-limit', '--days-back', '--max-files']
export const USAGE = `Usage: /ace:ace-bootstrap [${MODES.join('|')}] [${LEVELS.join('|')}] | --mode <mode> --thoroughness <level> [--commit-limit N] [--days-back N] [--max-files N] | --backfill-only [--sources git,merge,session] [--limit N] [--days-back N] [--target-project prj_x [--target-org org_x]]`
export type BootstrapArgs = { ok: true, mode?: string, level?: string, flags: string[] } | { ok: false, usage: string }

export function parseBootstrapArgs(args: string): BootstrapArgs {
  const bad: BootstrapArgs = { ok: false, usage: USAGE }
  const toks = args.trim().split(/\s+/).filter(Boolean)
  let mode: string | undefined, level: string | undefined
  const nums = new Map<string, string>(), pos: string[] = []
  const setOnce = (cur: string | undefined, v: string) => cur === undefined || cur === v ? v : null  // the same value twice is no conflict
  for (let i = 0; i < toks.length; i++) {
    let t = toks[i]
    if (!t.startsWith('--')) { pos.push(t); continue }
    let val: string | undefined
    const eq = t.indexOf('=')
    if (eq > 0) { val = t.slice(eq + 1); t = t.slice(0, eq) } else { val = toks[++i] }
    if (val === undefined || val === '' || val.startsWith('--')) return bad
    if (t === '--mode') { if (!MODES.includes(val)) return bad; const m = setOnce(mode, val); if (m === null) return bad; mode = m }
    else if (t === '--thoroughness') { if (!LEVELS.includes(val)) return bad; const l = setOnce(level, val); if (l === null) return bad; level = l }
    else if (NUMS.includes(t)) { if (!/^[1-9]\d{0,8}$/.test(val) || nums.has(t)) return bad; nums.set(t, val) }
    else return bad
  }
  if (pos.length > 2) return bad
  const [p1, p2] = pos
  if (p1 !== undefined) {
    if (MODES.includes(p1)) { const m = setOnce(mode, p1); if (m === null) return bad; mode = m }
    else if (pos.length === 1 && LEVELS.includes(p1)) { const l = setOnce(level, p1); if (l === null) return bad; level = l }
    else return bad
  }
  if (p2 !== undefined) {
    if (!LEVELS.includes(p2)) return bad
    const l = setOnce(level, p2); if (l === null) return bad; level = l
  }
  const r: BootstrapArgs = { ok: true, flags: NUMS.filter(n => nums.has(n)).flatMap(n => [n, nums.get(n)!]) }
  if (mode) r.mode = mode
  if (level) r.level = level
  return r
}
