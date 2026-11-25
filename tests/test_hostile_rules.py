"""A hostile input per redaction rule, derived from the rule tables (tests/hostile_gen.py): the fitted scaling exponent (tests/timing_util.py,
load-proof) of redact() on it must stay linear in BOTH chains: Python (process_time) and TS under bun (process.cpuUsage). A rule without a
registry entry fails test_every_rule_is_registered. The mod-sandbox twin is plugins/ace/mod/tests/redact_hostile.test.ts."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "ace"
sys.path.insert(0, str(PLUGIN / "shared-hooks"))
sys.path.insert(0, str(PLUGIN / "shared-hooks" / "utils"))
import redact as rd  # noqa: E402
from hostile_gen import REGISTRY, build, hostile_cases, registry, table_rules  # noqa: E402
from timing_util import BUN_LINEAR_JS, LIMIT, assert_linear  # noqa: E402

FULL_PY = 128 * 1024
FULL_TS = 256 * 1024
CASES = hostile_cases(rd)
RULES = sorted({r for r, _ in CASES})


def test_every_rule_is_registered():
    ids = [i for i, _ in table_rules(rd)]
    reg = registry()
    assert [i for i in ids if i not in reg] == [], "a rule without a hostile-registry entry: add it to hostile_rules.json (derived / units / linear + reason)"
    assert [i for i in reg if i not in ids and not i.startswith("engine:")] == [], "stale registry entries"
    assert all(isinstance(d["linear"], str) and d["linear"] for d in reg.values() if "linear" in d)


def test_mod_registry_is_in_sync():
    ts = (PLUGIN / "mod" / "tests" / "fixtures" / "hostile_rules.ts").read_text()
    assert ts.split("export const HOSTILE: any = ", 1)[1].strip() == json.dumps(json.loads(REGISTRY.read_text()), ensure_ascii=False), \
        "regenerate mod/tests/fixtures/hostile_rules.ts from hostile_rules.json"


@pytest.mark.parametrize("rule", RULES)
def test_hostile_python_scales_linearly(rule):
    for rid, u in CASES:
        if rid == rule:
            assert_linear(rd.redact, lambda f: build(u, int(FULL_PY * f)), "%s %r" % (rule, u[:20]))


def test_hostile_ts_under_bun_scales_linearly(tmp_path):
    bun = shutil.which("bun")
    if not bun:
        pytest.skip("bun not installed") if os.environ.get("ACE_ALLOW_NO_BUN") == "1" else pytest.fail("bun missing: the TS/Python parity tests must run (ACE_ALLOW_NO_BUN=1 skips them locally)")
    (tmp_path / "t.ts").write_text(
        "import { redact } from '%s'\nimport { build, hostileCases } from '%s'\n" % (PLUGIN / "mod" / "lib" / "redact.ts", PLUGIN / "mod" / "tests" / "hostile_gen.ts")
        + BUN_LINEAR_JS + "const out: any[] = []\nfor (const [id, u] of hostileCases()) out.push([id, u.slice(0, 20), linear(f => build(u, Math.floor(%d * f)), redact)])\n"
        "console.log(JSON.stringify(out))\n" % FULL_TS)
    p = subprocess.run([bun, str(tmp_path / "t.ts")], capture_output=True, text=True, timeout=900)
    assert p.returncode == 0, p.stderr[-2000:]
    out = json.loads(p.stdout)
    bad = [(r, u, round(s, 2)) for r, u, s in out if s > LIMIT]
    assert bad == [], "TS chain not linear (slope > %s): %s" % (LIMIT, bad)
