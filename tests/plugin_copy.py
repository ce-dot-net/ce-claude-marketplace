"""A plugin root the suite can trust to be hermetic.

`plugins/ace/node_modules` appears as soon as a developer runs `npm ci` (release-manager pin bump, DESIGN §17).
The hooks then find the REAL ace-cli next to their own code and the fakes on PATH are bypassed. So whenever the
repo plugin has node_modules, tests run the hooks from a throw-away copy without it; otherwise from the repo itself.
"""
import atexit
import shutil
import tempfile
from pathlib import Path

REPO_PLUGIN = Path(__file__).resolve().parent.parent / "plugins" / "ace"
_copies = {}


def hermetic_root(src=None) -> Path:
    src = Path(src or REPO_PLUGIN)
    if not (src / "node_modules").exists():
        return src
    key = str(src)
    if key not in _copies:
        d = Path(tempfile.mkdtemp(prefix="ace-plugin-copy-"))
        atexit.register(shutil.rmtree, str(d), True)
        dst = d / "ace"
        shutil.copytree(str(src), str(dst), ignore=shutil.ignore_patterns("node_modules", "__pycache__", ".pytest_cache"))
        _copies[key] = dst
    return _copies[key]
