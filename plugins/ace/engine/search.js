#!/usr/bin/env node
'use strict';
// stdin JSON {query, org, project, session_id?, top_k?, interactive?, human_prompt_count?} -> stdout: the `ace-cli search --json` object.
// Exit 3 = gate failed, exit 1 = runtime/server failure (error on stderr, nothing on stdout).
// Mirrors @ace-sdk/cli dist/commands/search.js minus SessionStorage: session_id reaches the server
// for its retrieval-log stamp, sessions.db is never opened.
const fs = require('fs');
const { loadCoreOrExit, clientHeaders, errText } = require('./resolve.js');

const { AceClient, createContext } = loadCoreOrExit();

(async () => {
  const input = JSON.parse(fs.readFileSync(0, 'utf8'));
  const query = String(input.query || '').trim();
  if (!query) throw new Error('query is required');
  const ctx = await createContext({ org: input.org, project: input.project });
  // Default cacheDir on purpose: the graph sqlite feeds result.expanded (CLI parity) and /ace:ace-graph.
  // 8.1.0 audit: the core's default logger writes to stdout ("Cache hit ..."), which broke the one JSON line the hooks
  // parse ("lib failed: no similar_patterns list" -> needless ace-cli fallback). Its lines go to stderr, as in learn.js.
  const toErr = (m) => process.stderr.write(String(m) + '\n');
  const logger = { warn: toErr, error: toErr, info: () => {}, success: () => {}, debug: () => {}, trace: () => {}, isTrace: () => false };
  const client = new AceClient(ctx, { customHeaders: clientHeaders(), logger });
  // Cores < 3.4.0 rebuild the search result from a fixed field list and drop the server switches
  // (render_full_pct, feedback_downvote): capture the raw /patterns/search body as the fallback.
  // 3.4.0+ passes them through, so the result wins and the capture is unused.
  const switches = {};
  // 8.2.3: the headless signal for the server (headless = interactive === false AND human_prompt_count 0/null).
  // Each only when valid, never defaulted; the core has no parameter for them, so they join its body here.
  const origin = {};
  if (typeof input.interactive === 'boolean') origin.interactive = input.interactive;
  if (Number.isSafeInteger(input.human_prompt_count) && input.human_prompt_count >= 0) origin.human_prompt_count = input.human_prompt_count;
  const rawRequest = typeof client.request === 'function' ? client.request.bind(client) : null;
  if (rawRequest) client.request = async (endpoint, method, body) => {
    const isSearch = typeof endpoint === 'string' && endpoint.startsWith('/patterns/search');
    // a plain-object body only (core 3.3.x: searchPatterns builds one); any other shape is sent untouched
    if (isSearch && body && Object.getPrototypeOf(body) === Object.prototype) body = { ...body, ...origin };
    const r = await rawRequest(endpoint, method, body);
    if (isSearch && r && typeof r === 'object') {
      for (const k of ['render_full_pct', 'feedback_downvote', 'client_policy']) if (k in r) switches[k] = r[k];  // 8.1.4: client_policy (dormant)
    }
    return r;
  };
  const config = await client.getConfig();
  const threshold = config?.search_threshold ?? config?.constitution_threshold;
  if (threshold === undefined) throw new Error('server gave no search_threshold');
  const result = await client.searchPatterns({
    query,
    threshold,
    section: (config?.runtime_settings || ctx.runtimeSettings).patternDefaultSection,
    top_k: input.top_k ?? config?.search_top_k,
    include_metadata: true,
    session_id: input.session_id,
    expandNeighbors: true,
  });
  process.stdout.write(JSON.stringify({ ...switches, ...result }) + '\n');
  // The core's hourly graph-edge refresh finishes in the background, like in ace-cli, but a stalled
  // one must not hold the caller until its timeout discards the result printed above.
  setTimeout(() => process.exit(0), 3000).unref();
})().catch((e) => {
  process.stderr.write(errText(e) + '\n');
  process.exit(1);
});
