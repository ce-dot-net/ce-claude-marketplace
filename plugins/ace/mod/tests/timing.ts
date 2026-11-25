// Load-proof complexity assertions. A wall-clock bound ("< 2 s") flakes on a loaded host and says nothing about complexity.
// The mod sandbox has only the wall clock (no process.cpuUsage), so the assertion is made independent of the load instead:
//  - the cost is measured at 4 input sizes (1/8, 1/4, 1/2, 1 of full) and the EXPONENT is fitted: the least-squares slope of
//    log(time) over log(size). Linear (also n log n) gives ~1.0-1.1, quadratic 2. A small quadratic share (n^2/8) shows as a
//    rising slope even while the absolute full/small ratio is still far below the quadratic one;
//  - each size is timed with at least equal total work (a size at 1/k is run k times, one measurement, per-run time = total / k) and
//    at least MIN_TOTAL ms in all: a measurement shorter than a scheduler quantum can slip through a loaded host untouched while a long
//    one cannot, which would fake a slope; equally long measurements are hit alike and cancel;
//  - the minimum per size over up to 6 attempts (noise only adds time), after a warm-up; it stops at the first pass;
//  - a constant-factor blow-up (bounded backtracking: n x 65k steps, linear but 100x slower per char) has a fine slope, so a string
//    input is also compared with BENIGN text of the same length, run in the same process and attempt (load hits both alike): the cost
//    per char may exceed the benign one by `maxFactor` at most;
//  - it fails only when the slope or the factor is bad AND the full-size run is slow in absolute terms (floorMs). On a host that is
//    oversubscribed 10-30x wall time is far above CPU time, so before failing the floor is judged in CPU-equivalent terms: the
//    contention is estimated with a fixed busy-loop kernel (slowest-now / fastest-ever in this process) and the run time divided by it.
const FRACS = [1 / 8, 1 / 4, 1 / 2, 1]
const now = () => performance.now()
const MIN_TOTAL = 200  // ms per measurement
let calMin = Infinity
const spin = () => { let x = 123456789; for (let i = 0; i < 4_000_000; i++) { x ^= x << 13; x ^= x >>> 17; x ^= x << 5 } return x }
/** wall time of the fixed kernel (best of 5, ~40 ms each) relative to the fastest ever seen in this process: ~1 idle, 10+ when oversubscribed */
function contention(): number {
  let b = Infinity
  for (let i = 0; i < 5; i++) { const t0 = now(); spin(); b = Math.min(b, now() - t0) }
  calMin = Math.min(calMin, b)
  return b / calMin
}
const TRIVIAL = 15     // ms: a full-size run this cheap is no complexity problem (a regression costs seconds), not measured
const BENIGN = 'The quick brown fox jumps over the lazy dog and walks home. total = sum(items) // ok\n'

export function fitSlope(xs: number[], ts: number[]): number {
  const lx = xs.map(Math.log), ly = ts.map(t => Math.log(Math.max(t, 0.01)))
  const mx = lx.reduce((a, b) => a + b) / lx.length, my = ly.reduce((a, b) => a + b) / ly.length
  return lx.reduce((s, x, i) => s + (x - mx) * (ly[i] - my), 0) / lx.reduce((s, x) => s + (x - mx) ** 2, 0)
}

/** make(frac) builds the input at `frac` of full size. Fails when the fitted exponent exceeds `limit`. */
export function expectLinear<T>(make: (frac: number) => T, run: (x: T) => unknown, label = '', { limit = 1.25, attempts = 8, floorMs = 250, maxFactor = 100 } = {}) {
  const inputs = FRACS.map(make)
  if (calMin === Infinity) contention()  // the first call sets the idle reference
  run(inputs[1])  // warm-up (JIT / regex compile)
  let t0w = now(); run(inputs[inputs.length - 1]); const tFull = now() - t0w
  if (tFull < TRIVIAL) return
  const best = FRACS.map(() => Infinity)
  const full = inputs[inputs.length - 1]
  const ref = typeof full === 'string' ? (BENIGN.repeat(Math.ceil(full.length / BENIGN.length)).slice(0, full.length) as unknown as T) : null
  let slope = NaN, refBest = Infinity, factor = 0
  for (let a = 0; a < attempts; a++) {
    FRACS.forEach((f, i) => {
      const reps = Math.max(Math.round(1 / f), Math.ceil(MIN_TOTAL / Math.max(tFull * f, 0.05))), t0 = now()
      for (let j = 0; j < reps; j++) run(inputs[i])
      best[i] = Math.min(best[i], (now() - t0) / reps)
    })
    if (ref !== null) { const t0 = now(); run(ref); refBest = Math.min(refBest, now() - t0); factor = best[best.length - 1] / Math.max(refBest, 1) }
    slope = fitSlope(FRACS, best)
    // pass: linear exponent and no constant-factor blow-up, or too cheap to matter (a regression on these inputs costs seconds)
    if ((slope <= limit && factor <= maxFactor) || best[best.length - 1] < floorMs) return
  }
  if (best[best.length - 1] / contention() < floorMs) return  // slow only because the host is oversubscribed: cheap in CPU terms
  throw new Error(`not linear${label ? ` (${label})` : ''}: slope ${slope.toFixed(2)} (limit ${limit}; linear ~1, quadratic 2), x${factor.toFixed(0)} the benign cost (limit ${maxFactor}), per-run ms at 1/8..1: ${best.map(t => t.toFixed(1)).join(' / ')}`)
}

/** Prefix of a hostile string at `frac` of its length. */
export const prefix = (s: string) => (frac: number) => s.slice(0, Math.floor(s.length * frac))

/** Wall time of the least-disturbed run: for a bound on ONE operation, take the min of `reps` runs (a preemption spike is not repeatable). */
export function bestMs(run: () => unknown, reps = 5): number {
  let best = Infinity
  for (let i = 0; i < reps; i++) { const t0 = now(); run(); best = Math.min(best, now() - t0) }
  return best
}
