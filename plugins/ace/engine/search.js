#!/usr/bin/env node
'use strict';
// stdin JSON {query, org, project, session_id?, top_k?} -> stdout: the `ace-cli search --json` object.
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
  const client = new AceClient(ctx, { customHeaders: clientHeaders() });
  // The core rebuilds the search result from a fixed field list and drops the server switches
  // (render_full_pct, feedback_downvote). Capture the raw /patterns/search body; consume-only, no core change.
  const switches = {};
  const rawRequest = typeof client.request === 'function' ? client.request.bind(client) : null;
  if (rawRequest) client.request = async (endpoint, method, body) => {
    const r = await rawRequest(endpoint, method, body);
    if (typeof endpoint === 'string' && endpoint.startsWith('/patterns/search') && r && typeof r === 'object') {
      for (const k of ['render_full_pct', 'feedback_downvote']) if (k in r) switches[k] = r[k];
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
  process.stdout.write(JSON.stringify({ ...result, ...switches }) + '\n');
  // The core's hourly graph-edge refresh finishes in the background, like in ace-cli, but a stalled
  // one must not hold the caller until its timeout discards the result printed above.
  setTimeout(() => process.exit(0), 3000).unref();
})().catch((e) => {
  process.stderr.write(errText(e) + '\n');
  process.exit(1);
});
