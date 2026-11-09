// 8.2.0 result lines of a finished pending CLI run, chosen BY NAME (the pending is stored state: a name, never a function).
// Pure. A formatter returns undefined when the stdout is not what it expects; the caller then shows the raw stdout.
const num = (v: unknown) => typeof v === 'number' && Number.isFinite(v) ? v : undefined

// `ace-cli bootstrap --json`: { success, patternsExtracted, patternsAfterDedup, statistics, processingTime, message }.
export function bootstrapReport(stdout: string): string | undefined {
  let j: any
  try { j = JSON.parse(stdout) } catch { return undefined }
  if (!j || typeof j !== 'object' || Array.isArray(j)) return undefined
  if (j.success === false) return `Bootstrap fehlgeschlagen${j.message ? `: ${String(j.message).slice(0, 160)}` : ''}`
  const ext = num(j.patternsExtracted), dd = num(j.patternsAfterDedup), t = num(j.processingTime)
  if (ext === undefined && dd === undefined) return undefined
  if (!ext && !dd) return 'Bootstrap fertig: keine Patterns gefunden'
  const parts = [`${ext ?? dd} Patterns extrahiert`]
  if (dd !== undefined && ext !== undefined && dd !== ext) parts.push(`${dd} nach Dedup`)
  const cp = num(j.statistics?.compression_percentage)
  if (cp !== undefined) parts.push(`Kompression ${cp}%`)
  if (t !== undefined) parts.push(`${t.toFixed(1)} s`)
  return `Bootstrap fertig: ${parts.join(', ')}`
}
// The one dispatch (a switch: names, not a table of functions).
export function reportLine(name: string, stdout: string): string | undefined {
  switch (name) {
    case 'bootstrap': return bootstrapReport(stdout)
  }
  return undefined
}
