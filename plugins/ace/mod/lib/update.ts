// Round 4 (C102): the update path when the stored client_policy says this plugin is below min_plugin_version. Pure: no `$`, no I/O.
// The command is a FIXED constant (never built from the server's answer): plugin ace from the ce-dot-net-marketplace marketplace.
import { clientPolicyState, storedClientPolicy } from './cohort'

export const UPDATE_PLUGIN = 'ace@ce-dot-net-marketplace'
// argv = [<resolved claude binary>, ...UPDATE_ARGS]; no -y (a marketplace-declared command must never be accepted unseen)
export const UPDATE_ARGS = ['plugin', 'update', UPDATE_PLUGIN] as const
// 4b: the binary, deterministic, checked before the spawn (non-login environments have no ~/.local/bin or ~/.bun/bin on PATH).
// 1. CLAUDE_CODE_EXECPATH: the running Claude Code's own executable (set by Claude Code in its child env; the official
//    security-guidance plugin reads it too). 2. known install paths. 3. each PATH directory. Absolute paths only; nothing from the server.
export const UPDATE_INSTALL_PATHS = ['~/.local/bin/claude', '~/.claude/local/claude', '~/.bun/bin/claude', '/usr/local/bin/claude', '~/.npm-global/bin/claude']
export function updateBinaryCandidates(env: { CLAUDE_CODE_EXECPATH?: string; HOME?: string; PATH?: string }): string[] {
  const out: string[] = []
  const add = (p: string | undefined) => { if (p && p.startsWith('/') && !out.includes(p)) out.push(p) }
  add(env.CLAUDE_CODE_EXECPATH?.trim())
  for (const p of UPDATE_INSTALL_PATHS) add(p.startsWith('~/') ? (env.HOME?.startsWith('/') ? env.HOME.replace(/\/+$/, '') + p.slice(1) : undefined) : p)
  for (const d of String(env.PATH ?? '').split(':')) add(d.startsWith('/') ? d.replace(/\/+$/, '') + '/claude' : undefined)
  return out
}
// Round 6 (F11 redone) + round 8 (L2): the AUTOMATIC run is started detached (own session, like the learn launcher) and never
// waited for: session.end hooks get ~1.5 s. The detached child is a small watchdog: the update with a timeout (UPDATE_MS), then ONE
// text-free auto_update_result row (result ok|failed|timeout|spawn_failed, exit_code, ms; never the command's output or the
// server's message), then it removes the update lock if it still owns it (nonce): while it runs, a click starts no second update.
// argv: python -I -c UPDATE_LAUNCHER <PATH> <log> <base row JSON> <lock dir> <nonce> <timeout s> <bin> ...UPDATE_ARGS
export const UPDATE_WATCHDOG = 'import json, os, signal, subprocess, sys, time\n'
  + 'path, log, base, lock, nonce, to = sys.argv[1:7]\n'
  + 'argv = sys.argv[7:]\n'
  + 'd = subprocess.DEVNULL\n'
  + 't0 = time.time()\n'
  + 'row = json.loads(base) if base else {}\n'
  + 'try:\n'
  // round 9 N3: its own process group, so a timeout ends the update's children too (os.killpg on that group only)
  + '    p = subprocess.Popen(argv, stdin=d, stdout=d, stderr=d, env=dict(os.environ, PATH=path), start_new_session=True)\n'
  + '    try:\n'
  + '        rc = p.wait(timeout=float(to))\n'
  + '        row.update(result="ok" if rc == 0 else "failed", exit_code=rc)\n'
  + '    except subprocess.TimeoutExpired:\n'
  + '        try:\n'
  + '            os.killpg(p.pid, signal.SIGKILL)\n'
  + '        except OSError:\n'
  + '            pass\n'
  + '        p.wait()\n'
  + '        row.update(result="timeout", exit_code=None)\n'
  + 'except OSError:\n'
  + '    row.update(result="spawn_failed", exit_code=None)\n'
  + 'row["ms"] = int((time.time() - t0) * 1000)\n'
  + 'row["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())\n'
  + 'try:\n'
  + '    if os.path.isdir(os.path.dirname(log)) and not os.path.islink(os.path.dirname(log)):\n'
  + '        fd = os.open(log, os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)\n'
  + '        os.write(fd, (json.dumps(row) + "\\n").encode())\n'
  + '        os.close(fd)\n'
  + 'except OSError:\n'
  + '    pass\n'
  + 'try:\n'
  + '    with open(os.path.join(lock, "owner")) as f:\n'
  + '        mine = f.read().strip() == nonce\n'
  + '    if mine:\n'
  + '        os.unlink(os.path.join(lock, "owner"))\n'
  + '        os.rmdir(lock)\n'
  + 'except OSError:\n'
  + '    pass\n'
export const UPDATE_LAUNCHER = 'import subprocess, sys\n'
  + 'd = subprocess.DEVNULL\n'
  + 'subprocess.Popen([sys.executable, "-I", "-c", ' + JSON.stringify(UPDATE_WATCHDOG) + '] + sys.argv[1:], stdin=d, stdout=d, stderr=d, start_new_session=True)\n'
export const UPDATE_MS = 180_000                  // the subprocess timeout
export const UPDATE_DAY_MS = 86_400_000           // automatic runs: at most one per day (any target)
export const UPDATE_LOCK_STALE_MS = 15 * 60_000   // a lock older than this is a dead session's: taken over
export const UPDATE_STATE_FILE = 'auto-update.json'  // {target, at (epoch s), mode}: the last attempt
export const UPDATE_LOCK = 'auto-update.lock'

// Gate order: only a min violation matters (recommended never updates). 'min' means installed < min_plugin_version (cohort.ts
// clientPolicyState), so a downgrade or a same-version run is impossible by construction. Then the opt-out (ACE_AUTO_UPDATE=0, also for the click); automatic runs only: one attempt per target, at most one run a day.
export type UpdateGate = { go: true; target: string } | { go: false; why: string; target?: string }
export function updateGate(a: { optOut: boolean; policyText?: string; version: string; nowMs: number; state?: any; mode: 'auto' | 'click' }): UpdateGate {
  if (clientPolicyState(a.policyText, a.version, a.nowMs) !== 'min') return { go: false, why: 'not_min' }
  const target = storedClientPolicy(a.policyText, a.nowMs)!.min_plugin_version!
  if (a.optOut) return { go: false, why: 'opt_out', target }
  if (a.mode === 'auto') {
    if (a.state?.target === target) return { go: false, why: 'target_tried', target }
    if (typeof a.state?.at === 'number' && a.nowMs - a.state.at * 1000 < UPDATE_DAY_MS) return { go: false, why: 'daily', target }
  }
  return { go: true, target }
}
// The interactive band line (min only); undefined = no band.
export function updateBandLine(policyText: string | undefined, version: string, nowMs: number): string | undefined {
  if (clientPolicyState(policyText, version, nowMs) !== 'min') return undefined
  return `ACE ${version} ist zu alt (min ${storedClientPolicy(policyText, nowMs)!.min_plugin_version})`
}
