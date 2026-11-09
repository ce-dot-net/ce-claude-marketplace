// The mod's $.state contract (8.1.0): the context band and a writing command's pending confirmation.
export type AceProject = { orgId: string; projectId: string; name: string }
export type AceBand = {
  state: string | null
  line?: string
  projectId?: string | null
  suggestion?: AceProject | null
  projects?: AceProject[]
  picking?: boolean
  dismissed?: boolean
  busy?: string | null
} | null
export type AcePending = {
  label: string
  preview: string
  kind: 'cli' | 'exec' | 'bind' | 'clean' | 'login' | 'install' | 'export'
  path?: string
  argv?: string[]
  stdin?: string
  report?: string  // 8.2.0 kind 'cli': the NAME of a result formatter (lib/reports.ts reportLine); absent = the raw stdout
  backfill?: { days: number, limit: number }  // 8.2.0 kind 'cli': after the CLI run, the backfill phase (io/backfill_io.ts)
  orgId?: string
  projectId?: string
} | null
export type AceShadow = { path: string; root: string } | null  // band [Entfernen] (cli 4.4.1 worktree_file_shadows_main)
export type AcePolicy = string | null  // 8.1.4: the dismissed client_policy band line
declare module 'claude-code' {
  interface PluginState {
    ace: { band: AceBand; pending: AcePending; shadow: AceShadow; policy: AcePolicy }
  }
}
