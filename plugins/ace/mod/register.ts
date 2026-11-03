// ACE v8 production mod (DESIGN §13.1): search -> inject -> domain shift -> subagent inject -> detached learn with
// F-080 credit, in-process. The Python command hooks stay installed as the fallback and step aside while the
// mod-active marker is fresh. ace-cli is consumed as-is via $.process.run; state lives on disk in the Python formats.
// Wiring only: one on(event, hook) per event; each hook hands its arguments and the per-load state to its handler.
import type { Register } from 'claude-code'
import { newLoad } from './io/state.ts'
import { sessionStart, sessionEnd } from './handlers/session.ts'
import { sessionCompact } from './handlers/compact.ts'
import { promptCompose } from './handlers/compose.ts'
import { promptSubmit } from './handlers/prompt.ts'
import { classicUserPromptSubmit, classicStop, classicSubagentStop } from './handlers/classic.ts'
import { turnStart, turnComplete } from './handlers/turn.ts'
import { agentSpawn } from './handlers/agent.ts'
import { toolCall } from './handlers/tool.ts'

export const register: Register = (on) => {
  const L = newLoad()
  on('session.start', ($, e, next) => sessionStart($, L, e, next))
  on('session.compact', ($, e, next) => sessionCompact($, L, e, next))
  on('prompt.compose', ($, e, next) => promptCompose($, L, e, next))
  on('prompt.submit', ($, e, next) => promptSubmit($, L, e, next))
  on('classic.UserPromptSubmit', ($, e, next) => classicUserPromptSubmit($, L, e, next))
  on('classic.Stop', ($, e, next) => classicStop($, L, e, next))
  on('classic.SubagentStop', ($, e, next) => classicSubagentStop($, L, e, next))
  on('turn.start', ($, e, next) => turnStart($, L, e, next))
  on('agent.spawn', ($, e, next) => agentSpawn($, L, e, next))
  on('tool.call', ($, e, next) => toolCall($, L, e, next))
  on('turn.complete', ($, e, next) => turnComplete($, L, e, next))
  on('session.end', ($, e, next) => sessionEnd($, L, e, next))
}
