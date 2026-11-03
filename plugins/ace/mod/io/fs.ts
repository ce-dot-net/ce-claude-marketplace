// File I/O through `$`: process runner, rm, JSON/text reads, private (0600, atomic) writes via lib/sh.ts PRIVATE_WRITE_SH.
import { pyLoads } from '../lib/pyjson.ts'
import { PRIVATE_WRITE_SH } from '../lib/sh.ts'

export async function run($: any, argv: string[], init: any = {}) {
  try { return await $.process.run(argv, { timeoutMs: 5000, ...init }) } catch { return null }
}
export function rm($: any, ...paths: string[]) { return run($, ['rm', '-rf', ...paths]) }
export async function readJson($: any, path: string): Promise<any> {
  try { return pyLoads(await $.fs.read(path) as string) } catch { return undefined }
}
export async function readText($: any, path: string): Promise<string | undefined> {
  try { return await $.fs.read(path) as string } catch { return undefined }
}
// §24: prompts, tool records and traces are 0600 in 0700 dirs. Throws on failure, like $.fs.write.
export async function writePrivate($: any, path: string, text: string) {
  const r = await $.process.run(['/bin/sh', '-c', PRIVATE_WRITE_SH, 'sh', path], { stdin: text, timeoutMs: 5000 })
  if (!r || r.exitCode !== 0) throw new Error('private write failed: ' + path)
}
