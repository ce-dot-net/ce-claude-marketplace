"""Shared helpers for the in-process SDK engine tests (DESIGN §14, round 3c).

- `make_prefix()` builds a fake npm global prefix that looks like a real ace-cli install:
    <prefix>/bin/ace-cli -> <prefix>/lib/node_modules/@ace-sdk/cli/dist/cli.js   (symlink, like npm)
    <prefix>/lib/node_modules/@ace-sdk/cli/node_modules/@ace-sdk/core          (nested)  or
    <prefix>/lib/node_modules/@ace-sdk/core                                    (hoisted)
  The fake `cli.js` is a Python script that logs argv to $ACE_FAKE_CLI_LOG (like tests/conftest.py)
  and prints a search result whose patterns carry id "from-cli" (so a test can tell which engine answered).
  The core is either a FAKE core (configurable via $ACE_FAKE_CORE_MODE, logs to $ACE_FAKE_CORE_LOG)
  or a symlink to the REAL installed core (`real_core_dir()`).
- `fake_server()` runs tests/engine_fake_server.py on a free localhost port.
- `ace_config()` writes a fake ~/.config/ace/config.json (fake user token, far-future expiry) into an
  XDG_CONFIG_HOME, so the real core never sees the developer's credentials.
- `GUARD_JS` (from m3 runs/localhost_guard.cjs): a fetch to the real ACE host aborts the process, any other
  non-localhost fetch fails like offline (ace-cli's npm update check): learn never reaches the real server.
"""
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
# hermetic: with a developer/CI `npm ci` in plugins/ace, the repo engine would find the REAL plugin-local core
# (DESIGN §23) and bypass every fake. The copy has no node_modules and is the root the hooks use (conftest).
from plugin_copy import hermetic_root  # noqa: E402
PLUGIN = hermetic_root()
ENGINE = PLUGIN / "engine"
UTILS = REPO / "plugins" / "ace" / "shared-hooks" / "utils"
FAKE_SERVER = Path(__file__).resolve().parent / "engine_fake_server.py"

CORE_RESPONSE = {"similar_patterns": [{"id": "from-lib", "content": "engine pattern", "section": "strategies",
                                       "confidence": 0.9, "cumulative_v15_reward": 1.0, "isAtRisk": False,
                                       "match_factors": {"bandit_rank": 1, "retrieval_log_id": 11}}],
                 "count": 1, "threshold": 0.5, "retrieval_id": "ret-lib-1"}
CLI_RESPONSE = {"similar_patterns": [{"id": "from-cli", "content": "cli pattern", "section": "strategies",
                                      "confidence": 0.9, "cumulative_v15_reward": 1.0, "isAtRisk": False,
                                      "match_factors": {"bandit_rank": 1, "retrieval_log_id": 12}}],
                "count": 1, "threshold": 0.5, "retrieval_id": "ret-cli-1"}

GUARD_JS = r"""
const orig = globalThis.fetch;
globalThis.fetch = async (url, init) => {
  const u = new URL(String(url));
  if (u.hostname === '127.0.0.1' || u.hostname === 'localhost') return orig(url, init).catch((e) => {
    const c = e && e.cause;  // §26: undici says only "fetch failed"; keep the cause in stderr for diagnosis
    process.stderr.write('GUARD: ' + u.pathname + ' failed: ' + ((c && (c.code || c.message)) || e) + '\n');
    throw e;
  });
  if (u.hostname.endsWith('code-engine.app')) { process.stderr.write('GUARD: refused ' + u.host + '\n'); process.exit(97); }
  throw new TypeError('fetch failed (test guard: offline)');  // e.g. ace-cli's npm update check
};
"""

_FAKE_CLI = r'''#!%(py)s
import json, os, sys
argv = sys.argv[1:]
data = sys.stdin.read() if "--stdin" in argv else ""
log = os.environ.get("ACE_FAKE_CLI_LOG")
if log:
    with open(log, "a") as f:
        f.write(json.dumps({"argv": argv, "stdin": data}) + "\n")
if "--version" in argv:
    print("4.2.2")
elif argv[:1] == ["search"]:
    print(%(search)r)
elif argv[:1] == ["learn"]:
    print(json.dumps({"success": True, "message": "Execution trace stored successfully", "via": "cli"}))
else:
    print("{}")
'''

_FAKE_ACE_CLIENT = r"""
const fs = require('fs');
const RESP = %(resp)s;
const mode = () => process.env.ACE_FAKE_CORE_MODE || 'ok';
function log(o) { if (process.env.ACE_FAKE_CORE_LOG) fs.appendFileSync(process.env.ACE_FAKE_CORE_LOG, JSON.stringify(o) + '\n'); }
class AceClient {
  constructor(ctx, opts) { this.ctx = ctx; this.opts = opts || {}; log({ op: 'ctor', ctx, customHeaders: this.opts.customHeaders || null }); }
  async getConfig() { return { search_threshold: 0.5, search_top_k: 100, runtime_settings: { learningEnabled: true, patternDefaultSection: 'general' } }; }
  async searchPatterns(p) {
    log({ op: 'search', params: p });
    if (mode() === 'crash') process.exit(7);
    if (mode() === 'garbage') { process.stdout.write('not json at all\n'); process.exit(0); }
    if (mode() === 'throw') throw new Error('Server error (500): boom');
    if (mode() === 'drift') return {};
    // noisy: a core that logs through its logger (default: console = stdout) during a search, e.g. "Cache hit"
    if (mode() === 'noisy') { (this.opts.logger && this.opts.logger.info ? this.opts.logger.info : console.log)('ℹ Cache hit (SQLite)'); return RESP; }
    if (mode() === 'empty') return { ...RESP, similar_patterns: [], count: 0 };
    // raw_*: the raw /patterns/search body carries switches; raw_new = core >= 3.4.0 passes them through.
    if (mode() === 'raw_new' || mode() === 'raw_old') {
      await this.request('/patterns/search', 'POST', p);
      return mode() === 'raw_new' ? { ...RESP, feedback_downvote: true, render_full_pct: 0 } : RESP;
    }
    return RESP;
  }
  async request(endpoint) { log({ op: 'raw', endpoint }); return { ...RESP, feedback_downvote: false, render_full_pct: 9, client_policy: { min_plugin_version: '8.1.0' } }; }
  async storeExecutionTrace(t, o) {
    log({ op: 'learn', trace: t, opts: o || null });
    if (mode() === 'hang') await new Promise(() => setInterval(() => {}, 1000));
    if (mode() === 'throw') throw new Error('Server error (500): boom');
    // 8.1.4: the real core's exhausted POST /traces retry (stderr dead letter, then the 502 error)
    if (mode() === 'deadletter') { process.stderr.write(JSON.stringify({ event: 'ace_trace_dead_letter', attempts: 4, status: 502, error: 'Server error (502)', timestamp: 'x' }) + '\n'); throw new Error('Server error (502): '); }
    if (mode() === 'quota') return { stored: false, analysis_performed: false, learning_queued: false, quota_exceeded: true, quota_error_code: 'TRACES_LIMIT', message: 'quota' };
    return { analysis_performed: true, learning_statistics: { patterns_created: 1, patterns_updated: 0 } };
  }
  async storeExecutionTraceStream(t) { log({ op: 'learn_stream', trace: t }); return { analysis_performed: true }; }
  invalidateCache() {}
}
module.exports = %(exports)s;
"""

_FAKE_CONTEXT = r"""
const fs = require('fs');
function log(o) { if (process.env.ACE_FAKE_CORE_LOG) fs.appendFileSync(process.env.ACE_FAKE_CORE_LOG, JSON.stringify(o) + '\n'); }
exports.createContext = async (o) => {
  o = o || {};
  log({ op: 'context', org: o.org || null, project: o.project || null });
  return { serverUrl: 'http://127.0.0.1:1', apiToken: 'ace_user_FAKE', projectId: o.project || process.env.ACE_PROJECT_ID,
           orgId: o.org || process.env.ACE_ORG_ID, cacheTtlMinutes: 120, runtimeSettings: { patternDefaultSection: 'general' } };
};
"""


def node_bin():
    """Absolute path of a real `node` (outside the conftest fake bin), or None."""
    p = shutil.which("node")
    return os.path.realpath(p) if p else None


def plugin_version():
    return json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text())["version"]


def real_cli_path():
    """The real installed ace-cli (realpath ends in @ace-sdk/cli/dist/cli.js), skipping the conftest fake."""
    for d in os.environ.get("PATH", "").split(os.pathsep):
        c = Path(d) / "ace-cli"
        if c.exists():
            rp = os.path.realpath(str(c))
            if rp.replace(os.sep, "/").endswith("@ace-sdk/cli/dist/cli.js"):
                return rp
    return None


def real_core_dir():
    """The @ace-sdk/core the real ace-cli uses (nested, else hoisted), or None."""
    cli = real_cli_path()
    if not cli:
        return None
    pkg = Path(cli).parent.parent  # .../@ace-sdk/cli
    for c in (pkg / "node_modules" / "@ace-sdk" / "core", pkg.parent / "core"):
        if (c / "dist" / "cjs" / "client" / "ace-client.js").exists():
            return c
    return None


def _write_fake_core(core: Path, version: str, missing=None, no_export=False, public=False):
    """public=True: core >= 3.4.0 layout with the "./client" and "./config" exports (standalone index files,
    so `missing` can delete a deep file without breaking them)."""
    (core / "dist" / "cjs" / "client").mkdir(parents=True)
    (core / "dist" / "cjs" / "config").mkdir(parents=True)
    exports = {".": {"require": {"default": "./dist/cjs/index.js"}}}
    client = _FAKE_ACE_CLIENT % {"resp": json.dumps(CORE_RESPONSE), "exports": "{}" if no_export else "{ AceClient }"}
    if public:
        exports["./client"] = {"require": {"default": "./dist/cjs/client/index.js"}}
        exports["./config"] = {"require": {"default": "./dist/cjs/config/index.js"}}
        (core / "dist" / "cjs" / "client" / "index.js").write_text(client)
        (core / "dist" / "cjs" / "config" / "index.js").write_text(_FAKE_CONTEXT)
    (core / "package.json").write_text(json.dumps({
        "name": "@ace-sdk/core", "version": version, "main": "./dist/cjs/index.js", "exports": exports}))
    (core / "dist" / "cjs" / "index.js").write_text("module.exports = {};\n")
    (core / "dist" / "cjs" / "client" / "ace-client.js").write_text(client)
    (core / "dist" / "cjs" / "config" / "context.js").write_text(_FAKE_CONTEXT)
    if missing:
        (core / "dist" / "cjs" / missing).unlink()


def make_prefix(root: Path, core="fake", version="3.3.2", layout="nested", missing=None,
                no_export=False, with_node=True, with_cli=True, public=False) -> Path:
    """Fake npm global prefix. core: 'fake' | 'real' | None. Returns <prefix>/bin."""
    prefix = root / "npm-prefix"
    nm = prefix / "lib" / "node_modules" / "@ace-sdk"
    cli_pkg = nm / "cli"
    (cli_pkg / "dist").mkdir(parents=True)
    (cli_pkg / "package.json").write_text(json.dumps({"name": "@ace-sdk/cli", "version": "4.2.2",
                                                      "bin": {"ace-cli": "dist/cli.js"}}))
    cli_js = cli_pkg / "dist" / "cli.js"
    cli_js.write_text(_FAKE_CLI % {"py": sys.executable, "search": json.dumps(CLI_RESPONSE)})
    cli_js.chmod(0o755)
    bin_dir = prefix / "bin"
    bin_dir.mkdir()
    if with_cli:
        os.symlink(os.path.relpath(str(cli_js), str(bin_dir)), str(bin_dir / "ace-cli"))
    if with_node and node_bin():
        os.symlink(node_bin(), str(bin_dir / "node"))
    if core:
        core_dir = (cli_pkg / "node_modules" / "@ace-sdk" / "core") if layout == "nested" else (nm / "core")
        core_dir.parent.mkdir(parents=True, exist_ok=True)
        if core == "real":
            os.symlink(str(real_core_dir()), str(core_dir))
        else:
            _write_fake_core(core_dir, version, missing=missing, no_export=no_export, public=public)
    return bin_dir


def make_plugin_local(root: Path, version="3.3.2", layout="hoisted", core="fake") -> Path:
    """A copy of the plugin with a §23 ${CLAUDE_PLUGIN_ROOT}/node_modules install. Returns the plugin root."""
    plugin = root / "plugin"
    for sub in ("engine", ".claude-plugin", "shared-hooks/utils"):
        shutil.copytree(str(PLUGIN / sub), str(plugin / sub),
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    nm = plugin / "node_modules" / "@ace-sdk"
    core_dir = nm / "cli" / "node_modules" / "@ace-sdk" / "core" if layout == "nested" else nm / "core"
    core_dir.parent.mkdir(parents=True)
    if core == "real":
        os.symlink(str(real_core_dir()), str(core_dir))
    else:
        _write_fake_core(core_dir, version)
    return plugin


def path_with(bin_dir: Path) -> str:
    """PATH = the fake prefix bin + system dirs only (no nvm/real ace-cli, no conftest fake)."""
    return os.pathsep.join([str(bin_dir), "/usr/bin", "/bin"])


def ace_config(xdg: Path, server_url="http://127.0.0.1:1"):
    (xdg / "ace").mkdir(parents=True, exist_ok=True)
    (xdg / "ace" / "config.json").write_text(json.dumps({
        "serverUrl": server_url, "defaultOrgId": "org_fake", "cacheTtlMinutes": 120,
        "auth": {"token": "ace_user_FAKE_TOKEN_0000000000", "user_id": "u_fake", "email": "t@example.invalid",
                 "organizations": [{"org_id": "org_fake", "name": "Fake", "role": "owner"}],
                 "authenticated_at": "2026-11-01T00:00:00Z", "refresh_token": "rfk_FAKE",
                 "expires_at": "2099-01-01T00:00:00Z", "refresh_expires_at": "2099-01-01T00:00:00Z",
                 "absolute_expires_at": "2099-01-01T00:00:00Z"}}))


class FakeServer:
    def __init__(self, root: Path, mode="ok", port=0, **env):
        self.log = root / "requests.jsonl"
        portfile = root / "port"
        if portfile.exists():
            portfile.unlink()
        self.proc = subprocess.Popen([sys.executable, str(FAKE_SERVER), str(port), str(self.log), str(portfile)],
                                     env=dict(os.environ, FAKE_MODE=mode, **env))
        for _ in range(100):
            if portfile.exists() and portfile.read_text().strip():
                break
            time.sleep(0.05)
        self.url = "http://127.0.0.1:" + portfile.read_text().strip()

    def requests(self):
        if not self.log.exists():
            return []
        return [json.loads(l) for l in self.log.read_text().splitlines() if l.strip()]

    def stop(self):
        self.proc.kill()
        self.proc.wait()


def sdk_env(root: Path, server: FakeServer, **extra):
    """Hermetic env for running the real core/ace-cli against the fake server."""
    home = root / "home"
    home.mkdir(exist_ok=True)
    xdg = root / "xdg"
    ace_config(xdg, server.url)
    guard = root / "guard.cjs"
    guard.write_text(GUARD_JS)
    env = dict(os.environ)
    for k in list(env):
        if k.startswith("ACE_"):
            del env[k]
    env.update(HOME=str(home), XDG_CONFIG_HOME=str(xdg), ACE_SERVER_URL=server.url,
               ACE_ORG_ID="org_fake", ACE_PROJECT_ID="prj_fake", NODE_OPTIONS="--require " + str(guard))
    env.update(extra)
    return env


def read_jsonl(p: Path):
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
