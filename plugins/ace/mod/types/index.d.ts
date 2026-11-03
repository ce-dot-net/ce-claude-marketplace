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
  kind: 'cli' | 'exec' | 'bind' | 'clean' | 'login' | 'install'
  argv?: string[]
  stdin?: string
  orgId?: string
  projectId?: string
} | null
declare module 'claude-code' {
  interface PluginState {
    ace: { band: AceBand; pending: AcePending }
  }
}
