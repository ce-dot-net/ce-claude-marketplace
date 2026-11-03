#!/usr/bin/env node
'use strict';
// `node learn.js --transcript F --json [--retrieval-id R] [--applied-log-ids a,b] [--verbosity V]
// [--timeout MS] [--no-stream]`: the same requests as `ace-cli learn --no-stream`.
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

(async () => {
  const trace = JSON.parse(fs.readFileSync(opt('--transcript'), 'utf8'));
  if (opt('--retrieval-id')) trace.retrieval_id = opt('--retrieval-id');
  const applied = (opt('--applied-log-ids') || '').split(',').map((s) => parseInt(s.trim(), 10)).filter((n) => !isNaN(n));
  if (applied.length) trace.applied_log_ids = applied;
  else if (!Array.isArray(trace.applied_log_ids)) trace.applied_log_ids = []; // server contract: [] when nothing was used
  // server 5.15.8: more than 20 applied_log_ids in one trace count as "all shown" (the whole trace falls to COLD)
  trace.applied_log_ids = trace.applied_log_ids.slice(0, APPLIED_CAP);
  const ctx = await createContext({});
  const client = new AceClient(ctx, { customHeaders: clientHeaders(), logger });
  try {
    const config = await client.getConfig();
    if (config?.runtime_settings?.learningEnabled === false) process.stderr.write('warn: learning disabled on the server\n');
  } catch (_) { /* like ace-cli: proceed without the config */ }
  sent = true;
  const result = await client.storeExecutionTrace(trace);
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
  process.stderr.write(errText(e) + '\n');
  process.exit(sent ? 1 : 3);
});
