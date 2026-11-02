#!/usr/bin/env node
'use strict';
// stdin JSON {query, org, project, session_id?, top_k?} -> stdout: the `ace-cli search --json` object.
// Exit 3 = gate failed, exit 1 = runtime/server failure (error on stderr, nothing on stdout).
// Mirrors @ace-sdk/cli dist/commands/search.js minus SessionStorage: session_id reaches the server
// for its retrieval-log stamp, sessions.db is never opened.
const fs = require('fs');
const { loadCoreOrExit, clientHeaders } = require('./resolve.js');

const { AceClient, createContext } = loadCoreOrExit();

(async () => {
  const input = JSON.parse(fs.readFileSync(0, 'utf8'));
  const query = String(input.query || '').trim();
  if (!query) throw new Error('query is required');
  const ctx = await createContext({ org: input.org, project: input.project });
  // Default cacheDir on purpose: the graph sqlite feeds result.expanded (CLI parity) and /ace:ace-graph.
  const client = new AceClient(ctx, { customHeaders: clientHeaders() });
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
  // No process.exit: the core's hourly graph-edge refresh finishes in the background, like in ace-cli.
  process.stdout.write(JSON.stringify(result) + '\n');
})().catch((e) => {
  process.stderr.write(((e && e.message) || String(e)) + '\n');
  process.exit(1);
});
