// 8.2.0 `--approved`: a standalone token (whitespace-delimited, exactly `--approved`) that stands at the start, at the end or next
// to another `--flag` is the approval; anywhere else (inside a lesson text, quoted) it stays part of the text. Pure.
export function stripApproved(args: string): { args: string, approved: boolean } {
  const toks = [...args.matchAll(/\S+/g)]
  const at = toks.findIndex((m, i) => m[0] === '--approved'
    && (i === 0 || i === toks.length - 1 || toks[i - 1][0].startsWith('--') || toks[i + 1][0].startsWith('--')))
  if (at < 0) return { args, approved: false }
  const m = toks[at], from = m.index!, to = from + m[0].length
  // drop the token with the whitespace run before it (after it for the first token), keep the rest byte-for-byte
  const head = args.slice(0, from).replace(/\s+$/, ''), tail = args.slice(to)
  return { args: (head ? head + tail : tail.replace(/^\s+/, '')).replace(/\s+$/, ''), approved: true }
}
