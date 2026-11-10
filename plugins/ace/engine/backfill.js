#!/usr/bin/env node
'use strict';
// 8.2.0 bootstrap backfill through the core client: the plugin never holds the token.
//   node backfill.js post --org O --project P          (stdin: JSON body {source:"bootstrap", items:[...]}) -> POST /traces/backfill
//   node backfill.js get  --org O --project P --job J  -> GET /traces/backfill/J
// stdout: ONE line {status, body} (body = parsed server JSON or null), for ANY HTTP answer, exit 0: lib/backfill_send.ts
// classifies it. The core throws on non-2xx, so the answer is observed through the public `fetchFn` option (as in
// learn.js) and recovered from there. No retry here: the mod's ledger and the per-item idempotency keys handle replays
// (/traces/backfill is a plain fetch in the core, only exactly POST /traces is retried there).
// Exit 3 = gate failed, nothing sent. Exit 2 = bad args/stdin, nothing sent. Exit 1 = no HTTP answer (the POST may
// have been sent). Nothing but the {status, body} line goes to stdout; the token/Authorization never leave the core.
const fs = require('fs');
const { loadCoreOrExit, clientHeaders, errText } = require('./resolve.js');

const args = process.argv.slice(2);
const opt = (k) => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : undefined; };
const die2 = (m) => { process.stderr.write('usage: ' + m + '\n'); process.exit(2); };

const cmd = args[0];
if (cmd !== 'post' && cmd !== 'get') die2('backfill.js post|get --org O --project P [--job J]');
if (!opt('--org') || !opt('--project')) die2('--org and --project are required');
let body;
let endpoint = '/traces/backfill';
if (cmd === 'post') {
  try { body = JSON.parse(fs.readFileSync(0, 'utf8')); } catch (_) { die2('stdin must be a JSON object'); }
  if (!body || typeof body !== 'object' || Array.isArray(body)) die2('stdin must be a JSON object');
} else {
  const job = opt('--job');
  if (!job || job.startsWith('--')) die2('get needs --job <job_id>');
  endpoint += '/' + encodeURIComponent(job);
}

const { AceClient, createContext } = loadCoreOrExit(['request']);

let last = null;  // the backfill answer as the server sent it
async function observe(url, init) {
  let isBf = false;
  try { isBf = new URL(String(url)).pathname.startsWith('/traces/backfill'); } catch (_) { /* not a URL */ }
  const r = await globalThis.fetch(url, init);
  if (isBf) {
    let b = null;
    try { b = await r.clone().json(); } catch (_) { /* not JSON */ }
    last = { status: r.status, body: b };
  }
  return r;
}

(async () => {
  const ctx = await createContext({ org: opt('--org'), project: opt('--project') });
  const quiet = { warn: () => {}, error: () => {}, info: () => {}, success: () => {}, debug: () => {}, trace: () => {}, isTrace: () => false };
  const client = new AceClient(ctx, { customHeaders: clientHeaders(), logger: quiet, fetchFn: observe });
  let answer;
  try {
    const result = await client.request(endpoint, cmd === 'post' ? 'POST' : 'GET', body);
    answer = { status: last ? last.status : 200, body: result ?? null };
  } catch (e) {
    if (!last) throw e;  // no HTTP answer: transport failure
    answer = last;       // the core threw on a non-2xx: the status/body the server sent
  }
  process.stdout.write(JSON.stringify({ status: answer.status, body: answer.body && typeof answer.body === 'object' ? answer.body : null }) + '\n');
})().catch((e) => {
  process.stderr.write(errText(e) + '\n');
  process.exit(1);
});
