// node --import ./ts_resolve.mjs: the mod imports its siblings without the .ts extension (claude plugin validate
// type-checks it without allowImportingTsExtensions), and Claude Code resolves them; node's ESM loader does not,
// so this hook retries a relative extensionless specifier with .ts. Test harness only.
import { register } from 'node:module'

const hook = `export async function resolve(s, c, next) {
  try { return await next(s, c) } catch (e) {
    if (e?.code === 'ERR_MODULE_NOT_FOUND' && /^\\.\\.?\\//.test(s) && !/\\.[cm]?[jt]s$/.test(s)) return next(s + '.ts', c)
    throw e
  }
}`
register('data:text/javascript,' + encodeURIComponent(hook))
