// The Mod test kit with ONE generous default timeout. `claude plugin test` has no global timeout setting and its
// default (5 s wall clock per test) tears under heavy host load (a test that takes ~1 s alone took 5-7 s at load 260).
// Every test file imports `test` from here instead of 'claude-code/testing'; a test may still pass its own
// `{ timeoutMs }` (it wins). Timing/linearity tests measure with their own method (see timing.ts), not with this limit.
import { test as base } from 'claude-code/testing'

export const DEFAULT_TEST_TIMEOUT_MS = 120_000

export const test: typeof base = ((name: any, a?: any, b?: any) => typeof a === 'function'
  ? (base as any)(name, { timeoutMs: DEFAULT_TEST_TIMEOUT_MS }, a)
  : (base as any)(name, { timeoutMs: DEFAULT_TEST_TIMEOUT_MS, ...(a ?? {}) }, b)) as any
