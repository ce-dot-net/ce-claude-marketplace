// 8.2.0 `--approved`: a standalone token (whitespace-delimited, exactly `--approved`) that stands at the start, at the end or next
// to another `--flag` is the approval; anywhere else (inside a lesson text, quoted) it stays part of the text. Pure.
// 8.2.7: a `--` token one or two edits away from `--approved` (case ignored), not the flag itself: a hint, never an approval.
export function flagHint(args: string): string | null {
  for (const [t] of args.matchAll(/--\S+/g)) {
    const d = dist(t.toLowerCase(), '--approved')
    if (t !== '--approved' && d <= 2) return `ACE: unbekanntes Flag ${t}, meintest du --approved?`
  }
  return null
}
function dist(a: string, b: string): number {  // Levenshtein, two rows
  let prev = Array.from({ length: b.length + 1 }, (_, j) => j)
  for (let i = 1; i <= a.length; i++) {
    const cur = [i]
    for (let j = 1; j <= b.length; j++) cur[j] = Math.min(prev[j]! + 1, cur[j - 1]! + 1, prev[j - 1]! + (a[i - 1] === b[j - 1] ? 0 : 1))
    prev = cur
  }
  return prev[b.length]!
}
export function stripApproved(args: string): { args: string, approved: boolean } {
  const toks = [...args.matchAll(/\S+/g)]
  const at = toks.findIndex((m, i) => m[0] === '--approved'
    && (i === 0 || i === toks.length - 1 || toks[i - 1]![0].startsWith('--') || toks[i + 1]![0].startsWith('--')))
  if (at < 0) return { args, approved: false }
  const m = toks[at]!, from = m.index!, to = from + m[0].length
  // drop the token with the whitespace run before it (after it for the first token), keep the rest byte-for-byte
  const head = args.slice(0, from).replace(/\s+$/, ''), tail = args.slice(to)
  return { args: (head ? head + tail : tail.replace(/^\s+/, '')).replace(/\s+$/, ''), approved: true }
}
