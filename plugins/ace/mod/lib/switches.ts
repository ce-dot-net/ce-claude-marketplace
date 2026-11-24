// Round 5 C4: one reading for the switches this work added. Pure.
// Opt-outs (ACE_TRACE_FULL_STEPS, ACE_AUTO_UPDATE): 0 / false / off / no, any case, turn them off; anything else keeps them on.
// Opt-ins (ACE_FORK_RETRIEVAL_ID): 1 / true / on / yes turn them on; anything else keeps them off.
const norm = (v: unknown) => String(v ?? '').trim().toLowerCase()
export const switchOff = (v: unknown): boolean => ['0', 'false', 'off', 'no'].includes(norm(v))
export const switchOn = (v: unknown): boolean => ['1', 'true', 'on', 'yes'].includes(norm(v))
