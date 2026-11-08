#!/usr/bin/env node
'use strict';
// `node learn.js --transcript F --json [--retrieval-id R] [--applied-log-ids a,b] [--verbosity V]
// [--timeout MS] [--no-stream] [--org O] [--project P] [--idempotency-key K]`: the same requests as `ace-cli learn --no-stream`.
// 8.1.4: K (the plugin's trace queue id) is the POST's Idempotency-Key on the first send and every replay, so the
// server can drop a duplicate. The answer of the LAST POST /traces is observed through the core's public `fetchFn`
// option and written as ONE stderr line `ace_trace_response {status, stored, duplicate, message, retry_after,
// error_code, path}` (ace_trace_queue.classify decides on it; `message` is never trusted). Exit 0 only for a 2xx with
// stored !== false and duplicate !== true; 5 = quota (429, swallowed by the core); 6 = answered but not proven stored.
// Failures also print the ace-cli shaped {"error":{"code","status","message"}} line.
// Always a sync POST, so --verbosity/--timeout/--no-stream are accepted and have no effect.
// Exit 3 = nothing was sent (safe to fall back to ace-cli). Exit 1 = the POST may have reached the
// server: a retry could duplicate the trace and double F-080 credit.
const fs = require('fs');
const { loadCoreOrExit, clientHeaders, errText } = require('./resolve.js');

const { AceClient, createContext } = loadCoreOrExit();

const args = process.argv.slice(2);
const opt = (k) => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : undefined; };
let sent = false;
const APPLIED_CAP = 20;
// core >= 3.7.0 emits its POST /traces retry line ("[ace] trace retry attempt=N/4 ...") only through logger.warn:
// stderr, unchanged, so the hooks parse the same line as ace-cli's. stdout is the parsed result: nothing else there.
const logger = { warn: (m) => process.stderr.write(m + '\n'), error: () => {}, info: () => {}, success: () => {}, debug: () => {}, trace: () => {}, isTrace: () => false };

let last = null;  // the last POST /traces answer (or a transport failure)
const str = (v, n) => (typeof v === 'string' ? v.slice(0, n) : null);
async function observe(url, init) {
  let path = '';
  try { path = new URL(String(url)).pathname; } catch (_) { /* not a URL */ }
  const traces = /\/traces(\/stream)?$/.test(path) && (init?.method || 'GET') === 'POST';
  let r;
  try { r = await globalThis.fetch(url, init); } catch (e) { if (traces) last = { status: null, network: true, path }; throw e; }
  if (traces) {
    let body = null;
    try { body = await r.clone().json(); } catch (_) { /* not JSON */ }
    const b = body && typeof body === 'object' ? body : {};
    last = { status: r.status, path, retry_after: str(r.headers.get('Retry-After'), 40),
      error_code: str(b.error_code, 80), stored: typeof b.stored === 'boolean' ? b.stored : null,
      duplicate: b.duplicate === true, message: str(b.message, 200) };
  }
  return r;
}
const report = () => { if (last) process.stderr.write('ace_trace_response ' + JSON.stringify(last) + '\n'); };
function errLine(e) {  // the ace-cli shape (core classifyError, plugin side): auth and 4xx are told apart by code
  const st = typeof e?.status === 'number' ? e.status : typeof e?.statusCode === 'number' ? e.statusCode : null;
  const code = e?.name === 'TokenExpiredError' ? 'token_expired' : st === 401 ? 'not_logged_in' : st === 403 ? 'no_access'
    : st === 404 ? 'project_not_found' : st !== null && st >= 500 ? 'server_error' : 'generic';
  return JSON.stringify({ error: { code, status: st, message: String(e?.message ?? e).slice(0, 300) } });
}

(async () => {
  const trace = JSON.parse(fs.readFileSync(opt('--transcript'), 'utf8'));
  if (opt('--retrieval-id')) trace.retrieval_id = opt('--retrieval-id');
  const applied = (opt('--applied-log-ids') || '').split(',').map((s) => parseInt(s.trim(), 10)).filter((n) => !isNaN(n));
  if (applied.length) trace.applied_log_ids = applied;
  else if (!Array.isArray(trace.applied_log_ids)) trace.applied_log_ids = []; // server contract: [] when nothing was used
  // server 5.15.8: more than 20 applied_log_ids in one trace count as "all shown" (the whole trace falls to COLD)
  trace.applied_log_ids = trace.applied_log_ids.slice(0, APPLIED_CAP);
  const ctx = await createContext({ org: opt('--org'), project: opt('--project') });  // 8.1.0: the core's ids, as ace-cli gets them
  const client = new AceClient(ctx, { customHeaders: clientHeaders(), logger, fetchFn: observe });
  try {
    const config = await client.getConfig();
    if (config?.runtime_settings?.learningEnabled === false) process.stderr.write('warn: learning disabled on the server\n');
  } catch (_) { /* like ace-cli: proceed without the config */ }
  sent = true;
  const result = await client.storeExecutionTrace(trace, opt('--idempotency-key') ? { idempotencyKey: opt('--idempotency-key') } : undefined);
  report();
  if (result && result.quota_exceeded) {
    process.stderr.write('ace_trace_quota_exceeded ' + String(result.quota_error_code || '') + '\n');
    process.exit(5);
  }
  if (last && (last.stored === false || last.duplicate === true)) process.exit(6);  // answered, not proven stored
  client.invalidateCache();
  process.stdout.write(JSON.stringify({
    success: true,
    message: 'Execution trace stored successfully',
    task: trace.task,
    timestamp: trace.timestamp,
    analysis_performed: result.analysis_performed,
    learning_statistics: result.learning_statistics,
  }) + '\n');
})().catch((e) => {
  report();
  process.stderr.write(errText(e) + '\n' + errLine(e) + '\n');
  process.exit(sent ? 1 : 3);
});
