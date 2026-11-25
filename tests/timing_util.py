"""Load-proof complexity assertions (a wall-clock bound like "< 3 s" flakes on a loaded host and says nothing about complexity).

- CPU time of this process (time.process_time), not wall time: preemption by other processes does not count;
- the cost is measured at 4 input sizes (1/8, 1/4, 1/2, 1 of full) and the EXPONENT is fitted: the least-squares slope of
  log(time) over log(size). Linear (also n log n) ~1.0-1.1, quadratic 2; a small quadratic share (n^2/8) shows as a rising slope;
- each size runs with equal total work (a size at 1/k runs k times, per-run time = total / k);
- the minimum per size over up to 6 attempts (noise only adds time), after a warm-up; it stops at the first pass;
- a constant-factor blow-up (bounded backtracking: n x 65k steps, linear but 100x slower per char) has a fine slope, so a string input is also
  compared with BENIGN text of the same length (same process, same attempt): the cost per char may exceed the benign one by MAX_FACTOR at most;
- it fails only when the slope or the factor is bad AND the full-size run is slow in absolute terms (floor).
Same algorithm as plugins/ace/mod/tests/timing.ts; BUN_LINEAR_JS is the bun-side copy (process.cpuUsage) for the subprocess tests.
"""
import math
import time

FRACS = (1 / 8, 1 / 4, 1 / 2, 1)
LIMIT = 1.25
MAX_FACTOR = 100
BENIGN = 'The quick brown fox jumps over the lazy dog and walks home. total = sum(items) // ok\n'


def fit_slope(xs, ts):
    lx, ly = [math.log(x) for x in xs], [math.log(max(t, 1e-5)) for t in ts]
    mx, my = sum(lx) / len(lx), sum(ly) / len(ly)
    return sum((x - mx) * (y - my) for x, y in zip(lx, ly)) / sum((x - mx) ** 2 for x in lx)


def assert_linear(run, make, label="", limit=LIMIT, attempts=6, floor=0.25, max_factor=MAX_FACTOR, clock=time.process_time):
    """make(frac) builds the input at `frac` of full size; run(x) is the operation."""
    inputs = [make(f) for f in FRACS]
    run(inputs[1])
    best = [float("inf")] * len(FRACS)
    full = inputs[-1]
    ref = (BENIGN * (len(full) // len(BENIGN) + 1))[: len(full)] if isinstance(full, str) else None
    slope, ref_best, factor = float("nan"), float("inf"), 0.0
    for _ in range(attempts):
        for i, f in enumerate(FRACS):
            reps = round(1 / f)
            t0 = clock()
            for _ in range(reps):
                run(inputs[i])
            best[i] = min(best[i], (clock() - t0) / reps)
        if ref is not None:
            t0 = clock()
            run(ref)
            ref_best = min(ref_best, clock() - t0)
            factor = best[-1] / max(ref_best, 0.001)
        slope = fit_slope(FRACS, best)
        if (slope <= limit and factor <= max_factor) or best[-1] < floor:  # linear and no constant-factor blow-up, or too cheap to matter
            return
    raise AssertionError("not linear (%s): slope %.2f (limit %s; linear ~1, quadratic 2), x%.0f the benign cost (limit %s), per-run s at 1/8..1: %s" % (label, slope, limit, factor, max_factor, " / ".join("%.3f" % t for t in best)))


def prefix(s):
    return lambda frac: s[: int(len(s) * frac)]


# bun side: `linear(make, run)` returns the fitted slope (CPU time); the test asserts it <= LIMIT.
BUN_LINEAR_JS = """
const FR = [1 / 8, 1 / 4, 1 / 2, 1], cpu = () => { const u = process.cpuUsage(); return (u.user + u.system) / 1000 }
const slopeOf = (ts: number[]) => { const lx = FR.map(Math.log), ly = ts.map(t => Math.log(Math.max(t, 0.01))), mx = lx.reduce((a, b) => a + b) / 4, my = ly.reduce((a, b) => a + b) / 4
  return lx.reduce((s, x, i) => s + (x - mx) * (ly[i] - my), 0) / lx.reduce((s, x) => s + (x - mx) ** 2, 0) }
const BEN = 'The quick brown fox jumps over the lazy dog and walks home. total = sum(items) // ok\\n'
const linear = (make: (f: number) => any, run: (x: any) => any, limit = %s, attempts = 6, floorMs = 250, maxFactor = 100) => {
  const ins = FR.map(make); run(ins[1])
  const best = FR.map(() => Infinity); let slope = NaN, refBest = Infinity, factor = 0
  const ref = typeof ins[3] === 'string' ? BEN.repeat(Math.ceil(ins[3].length / BEN.length)).slice(0, ins[3].length) : null
  for (let a = 0; a < attempts; a++) {
    FR.forEach((f, i) => { const reps = Math.round(1 / f), t0 = cpu(); for (let j = 0; j < reps; j++) run(ins[i]); best[i] = Math.min(best[i], (cpu() - t0) / reps) })
    if (ref !== null) { const t0 = cpu(); run(ref); refBest = Math.min(refBest, cpu() - t0); factor = best[3] / Math.max(refBest, 1) }
    slope = slopeOf(best)
    if ((slope <= limit && factor <= maxFactor) || best[3] < floorMs) return Math.min(slope, limit)
  }
  return factor > maxFactor ? 99 : slope
}
""" % LIMIT
