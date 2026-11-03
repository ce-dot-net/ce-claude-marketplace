"""Hermetic harness for the round 3d tests (DESIGN §23 CLI delivery). Not a test module.

A throw-away COPY of the plugin (so package.json, node_modules and the version can differ per
test, whichever way the code locates its root), PATH = one bin dir holding only fake node / npm /
ace-cli / python3. Never the real npm, never the network, never the developer's plugin data.
Both fake CLIs log to the same file with their `source`.
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PLUGIN = REPO / "plugins" / "ace"
PROJECT_ID, ORG_ID = "prj_r3d", "org_r3d"
BASH = shutil.which("bash")

# ace-cli 4.2.2 dist/utils/version-checker.js:100-122, verbatim (both variants).
NOTIFIER = ("\n💡 Update available: v9.9.9 (current: v4.2.2)\n"
            "   Run: npm install -g @ace-sdk/cli@latest\n\n"
            "\n💡 Update available: v9.9.9 → Run: npm install -g @ace-sdk/cli@latest\n\n")

SEARCH = {"count": 1, "retrieval_id": "r-r3d", "similar_patterns": [
    {"id": "11111111-2222-4333-8444-555555555555", "content": "auth tip", "domain": "auth",
     "section": "strategies_and_hard_rules", "bandit_rank": 1, "cumulative_v15_reward": 1.0,
     "isAtRisk": False, "retrieval_log_id": 7}]}

_RESPOND = r'''
import json, os, sys
def respond(argv, source, version):
    rec = {"source": source, "argv": argv}
    if "--transcript" in argv:
        try:
            rec["trace"] = json.load(open(argv[argv.index("--transcript") + 1]))
        except Exception as e:
            rec["trace_error"] = str(e)
    with open(os.environ["FAKE_CLI_LOG"], "a") as f:
        f.write(json.dumps(rec) + "\n")
    if os.environ.get("FAKE_CLI_NOTIFY"):
        sys.stderr.write(%(notifier)r)
    if os.environ.get("FAKE_CLI_STDERR"):
        sys.stderr.write(os.environ["FAKE_CLI_STDERR"] + "\n")
    if os.environ.get("FAKE_CLI_RC"):
        sys.exit(int(os.environ["FAKE_CLI_RC"]))
    if "--version" in argv:
        print(version)
    elif argv[:1] == ["search"]:
        print(%(search)r)
    elif argv[:1] == ["whoami"]:
        print(json.dumps({"authenticated": True}))
    else:
        print("{}")
''' % {"notifier": NOTIFIER, "search": json.dumps(SEARCH)}

_FAKE_GLOBAL = "#!%s\n" + _RESPOND + "\nrespond(sys.argv[1:], 'global', %r)\n"

_FAKE_NODE = "#!%s\n" + _RESPOND + r'''
argv = sys.argv[1:]
if argv[:1] in (["-e"], ["-p"], ["--eval"], ["--print"]):
    with open(os.environ["FAKE_NODE_LOG"], "a") as f:
        f.write(json.dumps({"argv": argv, "cwd": os.getcwd()}) + "\n")
    # the load probe: FAKE_NODE_REQUIRE_RC forces a result; else it passes once a (fake) `npm rebuild` has run
    rc = os.environ.get("FAKE_NODE_REQUIRE_RC")
    sys.exit(int(rc) if rc is not None else (0 if os.path.exists(os.environ["FAKE_BUILT"]) else 1))
script = argv[0] if argv else ""
pkg = os.path.join(os.path.dirname(os.path.dirname(script)), "package.json")
respond(argv[1:], "plugin-local", json.load(open(pkg)).get("version", "0.0.0"))
'''

_FAKE_NPM = "#!%s\n" + r'''
import json, os, sys
with open(os.environ["FAKE_NPM_LOG"], "a") as f:
    f.write(json.dumps({"argv": sys.argv[1:], "cwd": os.getcwd(),
                        "ignore_scripts": os.environ.get("npm_config_ignore_scripts")}) + "\n")
rc = int(os.environ.get("FAKE_NPM_RC", "0"))
if rc == 0 and sys.argv[1:2] == ["rebuild"]:
    open(os.environ["FAKE_BUILT"], "w").close()
sys.exit(rc)
'''


class Box3d:
    def __init__(self, tmp, pin="4.3.0", local=False, global_version=None, node=True, npm=True):
        self.tmp = Path(tmp)
        self.root = self.tmp / "ace-plugin"
        self.data = self.tmp / "ace-data"
        self.home = self.tmp / "home"
        self.proj = self.tmp / "proj"
        self.bin = self.tmp / "bin"
        self.xdg = self.tmp / "xdg"
        self.cli_log, self.npm_log, self.node_log = (self.tmp / n for n in ("cli.jsonl", "npm.jsonl", "node.jsonl"))
        for d in (self.home, self.data, self.proj / ".claude", self.bin, self.xdg / "ace"):
            d.mkdir(parents=True, exist_ok=True)
        (self.xdg / "ace" / "config.json").write_text(json.dumps({"apiToken": "x"}))
        (self.proj / ".claude" / "settings.json").write_text(json.dumps({"projectId": PROJECT_ID, "orgId": ORG_ID}))
        ignore = shutil.ignore_patterns("__pycache__", "node_modules", ".pytest_cache", ".ace-cache", "tests", "engine", "mod")
        for sub in ("shared-hooks", "scripts", "hooks", ".claude-plugin", "utils"):
            if (PLUGIN / sub).is_dir():
                shutil.copytree(str(PLUGIN / sub), str(self.root / sub), ignore=ignore)
        self.pin = pin
        (self.root / "package.json").write_text(json.dumps(
            {"private": True, "dependencies": {"@ace-sdk/cli": pin}}))
        (self.bin / "python3").symlink_to(sys.executable)
        self.node = self.bin / "node"
        if node:
            self._exe(self.node, _FAKE_NODE % sys.executable)
        if npm:
            self._exe(self.bin / "npm", _FAKE_NPM % sys.executable)
        if global_version:
            self.install_global(global_version)
        if local:
            self.install_local()

    @staticmethod
    def _exe(path, body):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)
        path.chmod(0o755)

    def install_global(self, version):
        self._exe(self.bin / "ace-cli", _FAKE_GLOBAL % (sys.executable, version))

    @property
    def cli_js(self):
        return self.root / "node_modules" / "@ace-sdk" / "cli" / "dist" / "cli.js"

    def install_local(self, version=None):
        """What CC's `npm ci --ignore-scripts` leaves behind (P8 report)."""
        self.cli_js.parent.mkdir(parents=True)
        self.cli_js.write_text("// fake\n")
        (self.cli_js.parent.parent / "package.json").write_text(json.dumps({"version": version or self.pin}))
        self._exe(self.root / "node_modules" / ".bin" / "ace-cli",
                  '#!/bin/sh\nexec node "%s" "$@"\n' % self.cli_js)
        (self.root / "node_modules" / "better-sqlite3").mkdir(parents=True)

    def env(self, **extra):
        e = {"HOME": str(self.home), "PATH": str(self.bin), "CLAUDE_PLUGIN_ROOT": str(self.root),
             "CLAUDE_PLUGIN_DATA": str(self.data), "XDG_CONFIG_HOME": str(self.xdg),
             "CLAUDE_PROJECT_DIR": str(self.proj), "LANG": "en_US.UTF-8", "ACE_LEARN_INLINE": "1",
             "FAKE_CLI_LOG": str(self.cli_log), "FAKE_NPM_LOG": str(self.npm_log), "FAKE_NODE_LOG": str(self.node_log),
             "FAKE_BUILT": str(self.tmp / "sqlite-built")}
        for k, v in extra.items():
            if v is None:
                e.pop(k, None)
            else:
                e[k] = str(v)
        return e

    def run(self, script, event, args=(), **env):
        return subprocess.run([BASH, str(self.root / "scripts" / script)] + list(args), input=json.dumps(event),
                              capture_output=True, text=True, timeout=60, cwd=str(self.proj), env=self.env(**env))

    def py(self, code, **env):
        """Run python inside the copied plugin; returns the JSON it prints."""
        prog = ("import json, sys; sys.path.insert(0, %r); sys.path.insert(0, %r)\n" %
                (str(self.root / "shared-hooks"), str(self.root / "shared-hooks" / "utils"))) + code
        p = subprocess.run([sys.executable, "-c", prog], capture_output=True, text=True, timeout=60,
                           cwd=str(self.proj), env=self.env(**env))
        assert p.returncode == 0, p.stderr
        return json.loads(p.stdout)

    def resolve(self, **env):
        """(argv prefix, source) from the one Python helper."""
        return tuple(self.py("import ace_cli; print(json.dumps([ace_cli.cli_argv(), ace_cli.cli_source()]))", **env))

    def _jsonl(self, p):
        return [json.loads(l) for l in p.read_text().splitlines() if l.strip()] if p.exists() else []

    def cli_calls(self, verb=None):
        return [c for c in self._jsonl(self.cli_log) if verb is None or c["argv"][:1] == [verb]]

    def npm_calls(self):
        return self._jsonl(self.npm_log)

    def node_evals(self):
        return self._jsonl(self.node_log)

    def relevance(self):
        return self._jsonl(self.proj / ".claude" / "data" / "logs" / "ace-relevance.jsonl")

    def session_dir(self, sid):
        return self.data / "projects" / PROJECT_ID / "sessions" / sid

    def flags(self):
        return [str(p) for p in self.data.rglob("disabled.flag")]

    def session_start(self, sid="s3d", source="startup", **env):
        return self.run("ace_install_cli.sh", {"session_id": sid, "hook_event_name": "SessionStart", "source": source,
                                               "cwd": str(self.proj), "transcript_path": ""}, **env)

    def async_row_args(self):
        """args of the async SessionStart row, as hooks.json routes them (the row keeps the sweep + sqlite rebuild)."""
        hooks = json.loads((self.root / "hooks" / "hooks.json").read_text())["hooks"]["SessionStart"]
        rows = [h for g in hooks for h in g["hooks"] if h.get("async")]
        assert len(rows) == 1, rows
        return tuple(rows[0].get("args") or ())

    def session_start_async(self, sid="s3d", **env):
        return self.run("ace_install_cli.sh", {"session_id": sid, "hook_event_name": "SessionStart", "source": "startup",
                                               "cwd": str(self.proj), "transcript_path": ""},
                        args=self.async_row_args(), **env)

    def ups(self, sid="s3d", prompt="refactor the authentication middleware to use JSON web tokens", **env):
        return self.run("ace_before_task_wrapper.sh", {
            "session_id": sid, "hook_event_name": "UserPromptSubmit", "cwd": str(self.proj), "prompt": prompt,
            "prompt_id": "f486434d-1111-4222-8333-944455556666", "transcript_path": str(self.tmp / "t.jsonl")}, **env)


def system_message(proc):
    return json.loads(proc.stdout).get("systemMessage", "") if proc.stdout.strip() else ""
