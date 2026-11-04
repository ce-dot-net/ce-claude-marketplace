// command.run: the model-free answer of every ACE command (commands/index.ts); any other command passes through.
import { findCommand, runCommand } from '../commands/index.ts'
import type { HookArgs, Load } from '../io/state.ts'

export async function commandRun($: HookArgs<'command.run'>[0], L: Load, e: HookArgs<'command.run'>[1], next: HookArgs<'command.run'>[2]) {
  const cmd = findCommand(e.command)
  if (!cmd) return next(e)
  return { text: await runCommand($, L, cmd, e.args) }
}
