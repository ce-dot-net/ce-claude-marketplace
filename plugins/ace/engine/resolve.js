#!/usr/bin/env node
'use strict';
// Version + export gate for @ace-sdk/core (DESIGN §14): the public "./client" and "./config" exports
// (core >= 3.4.0), else the private dist/cjs paths of older cores.
// `node resolve.js` prints one JSON object; exit 0 = usable, exit 3 = use ace-cli instead.
const fs = require('fs');
const path = require('path');

const MIN_CORE = '3.2.2';
const CLIENT = 'dist/cjs/client/ace-client.js';
const CONTEXT = 'dist/cjs/config/context.js';

const parts = (v) => String(v).split('-')[0].split('.').map(Number);

function olderThanFloor(version) {
  const a = parts(version);
  const b = parts(MIN_CORE);
  for (let i = 0; i < 3; i++) {
    if ((a[i] || 0) !== b[i]) return !((a[i] || 0) > b[i]);
  }
  return false;
}

function findCli() {
  for (const dir of (process.env.PATH || '').split(path.delimiter)) {
    const candidate = path.join(dir || '.', 'ace-cli');
    try {
      fs.accessSync(candidate, fs.constants.X_OK);
      if (!fs.statSync(candidate).isFile()) continue;
      return fs.realpathSync(candidate);
    } catch (_) { /* next PATH entry */ }
  }
  return null;
}

function readPackage(dir) {
  try {
    return JSON.parse(fs.readFileSync(path.join(dir, 'package.json'), 'utf8'));
  } catch (_) {
    return null;
  }
}

function ancestors(start) {
  const out = [];
  for (let d = start; ; d = path.dirname(d)) {
    out.push(d);
    if (d === path.dirname(d)) return out;
  }
}

// Older cores export only "." so require.resolve cannot reach package.json: walk node_modules.
// Walking up from the CLI package finds the nested copy first, then hoisted (npm) or pnpm siblings.
function findCore(cliPath) {
  const cliPkg = ancestors(path.dirname(cliPath)).find((d) => (readPackage(d) || {}).name === '@ace-sdk/cli');
  if (!cliPkg) return null;
  for (const d of ancestors(cliPkg)) {
    const core = path.join(d, 'node_modules', '@ace-sdk', 'core');
    if ((readPackage(core) || {}).name === '@ace-sdk/core') return core;
  }
  return null;
}

// DESIGN §23: the plugin's own install wins, so PATH and node managers stop mattering.
function findPluginLocalCore() {
  const scope = path.join(__dirname, '..', 'node_modules', '@ace-sdk');
  return [path.join(scope, 'cli', 'node_modules', '@ace-sdk', 'core'), path.join(scope, 'core')]
    .find((d) => (readPackage(d) || {}).name === '@ace-sdk/core') || null;
}

// The located core's public subpath exports, or null (older core: the exports map has no "./client").
function loadPublic(coreDir) {
  const from = { paths: [path.resolve(coreDir, '..', '..', '..')] }; // the dir that holds node_modules/@ace-sdk/core
  try {
    return [require(require.resolve('@ace-sdk/core/client', from)), require(require.resolve('@ace-sdk/core/config', from))];
  } catch (e) {
    if (e && (e.code === 'ERR_PACKAGE_PATH_NOT_EXPORTED' || e.code === 'MODULE_NOT_FOUND')) return null;
    throw e;
  }
}

function resolve() {
  const out = { ok: false, reason: 'no_cli', cli_path: findCli(), core_dir: findPluginLocalCore(), core_version: null, min_core: MIN_CORE };
  if (!out.core_dir) {
    if (!out.cli_path) return out;
    out.core_dir = findCore(out.cli_path);
    if (!out.core_dir) { out.reason = 'core_missing'; return out; }
  }
  out.core_version = readPackage(out.core_dir).version || null;
  const hasDeep = [CLIENT, CONTEXT].every((f) => fs.existsSync(path.join(out.core_dir, f)));
  if (olderThanFloor(out.core_version)) { out.reason = 'core_too_old'; return out; }
  // The export gate only checks method names: a new major is unverified.
  if (parts(out.core_version)[0] > parts(MIN_CORE)[0]) { out.reason = 'core_too_new'; return out; }
  try {
    let mods = loadPublic(out.core_dir);
    out.load = mods ? 'exports' : 'deep';
    if (!mods) {
      if (!hasDeep) { out.reason = 'file_missing'; return out; }
      mods = [require(path.join(out.core_dir, CLIENT)), require(path.join(out.core_dir, CONTEXT))];
    }
    const [{ AceClient }, { createContext }] = mods;
    const proto = typeof AceClient === 'function' ? AceClient.prototype : {};
    const usable = typeof createContext === 'function'
      && ['searchPatterns', 'storeExecutionTrace', 'getConfig'].every((m) => typeof proto[m] === 'function');
    if (!usable) { out.reason = 'export_missing'; return out; }
    out.AceClient = AceClient;
    out.createContext = createContext;
  } catch (_) {
    out.reason = 'export_missing';
    return out;
  }
  out.ok = true;
  out.reason = 'ok';
  return out;
}

// For search.js / learn.js: the core modules, or exit 3 before anything was sent.
function loadCoreOrExit() {
  const core = resolve();
  if (!core.ok) {
    process.stderr.write('gate: ' + core.reason + '\n');
    process.exit(3);
  }
  return core;
}

function clientHeaders() {
  let version = '0.0.0';
  try {
    version = require('../.claude-plugin/plugin.json').version || version;
  } catch (_) { /* attribution only */ }
  return { 'X-ACE-Client': 'claude-code-plugin/' + version };
}

// undici says only "fetch failed"; the cause (ECONNRESET, ECONNREFUSED, ...) is what makes stderr useful (§26).
function errText(e) {
  const c = e && e.cause;
  const why = c && (c.code || c.message);
  return ((e && e.message) || String(e)) + (why ? ' (' + why + ')' : '');
}

module.exports = { loadCoreOrExit, clientHeaders, errText };

if (require.main === module) {
  const { AceClient, createContext, ...report } = resolve();
  process.stdout.write(JSON.stringify(report) + '\n');
  process.exitCode = report.ok ? 0 : 3;
}
