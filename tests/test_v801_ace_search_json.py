"""v8.0.1: /ace:ace-search runs `scripts/ace-cli search ... --json` (the human formatter drops root_cause) and renders
content, domain, section, reward, bandit_rank, evidence and a non-empty root_cause per pattern.
The Step 3 script of the command runs for real against a fake wrapper that prints a search JSON."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

CMD = Path(__file__).resolve().parent.parent / "plugins" / "ace" / "commands" / "ace-search.md"


def _step3():
    text = CMD.read_text()
    sec = text.split("### Step 3", 1)[1]
    return re.search(r"```bash\n(.*?)```", sec, re.S).group(1)


def test_search_goes_through_the_wrapper_with_json():
    script = _step3()
    calls = [l for l in script.splitlines() if "ace-cli search" in l and not l.lstrip().startswith("#")]
    assert calls and all("${CLAUDE_PLUGIN_ROOT}/scripts/ace-cli search" in l and "--json" in l for l in calls)
    assert "root_cause" in script


RESP = {"similar_patterns": [
    {"content": "Use jq -n --arg for hook JSON", "domain": "hooks", "section": "strategies_and_hard_rules",
     "cumulative_v15_reward": 0.7, "match_factors": {"bandit_rank": 1}, "evidence": ["sed broke the JSON"],
     "root_cause": "sed escapes only quotes"},
    {"content": "Pin the CLI exactly", "domain": "release", "section": "apis_to_use", "cumulative_v15_reward": 0,
     "bandit_rank": 2, "evidence": [], "root_cause": ""}], "count": 2, "retrieval_id": "r-1"}


@pytest.mark.skipif(not shutil.which("jq"), reason="jq not installed")
def test_step3_renders_root_cause_only_when_present(tmp_path):
    root = tmp_path / "plugin"
    (root / "scripts").mkdir(parents=True)
    w = root / "scripts" / "ace-cli"
    w.write_text("#!/bin/sh\necho \"$*\" > %s/argv\ncat <<'EOF'\n%s\nEOF\n" % (tmp_path, json.dumps(RESP)))
    w.chmod(0o755)
    real = Path(__file__).resolve().parents[1] / "plugins/ace"
    for n in ("ace-context", "ace-python"):  # the one core, as installed
        shutil.copy(real / "scripts" / n, root / "scripts" / n)
    (root / "shared-hooks").symlink_to(real / "shared-hooks")
    cwd = tmp_path / "repo"
    (cwd / ".claude").mkdir(parents=True)
    (cwd / ".claude" / "settings.json").write_text(json.dumps({"env": {"ACE_PROJECT_ID": "prj_p", "ACE_ORG_ID": "org_o"}}))
    script = _step3().replace("${CLAUDE_PLUGIN_ROOT}", str(root))
    r = subprocess.run(["bash", "-c", script, "bash", "jq", "hook", "json"], cwd=cwd, capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    assert (tmp_path / "argv").read_text().split()[:1] == ["search"] and "--json" in (tmp_path / "argv").read_text()
    out = r.stdout
    for s in ("Use jq -n --arg for hook JSON", "hooks", "strategies_and_hard_rules", "0.7", "sed broke the JSON",
              "sed escapes only quotes", "Pin the CLI exactly", "apis_to_use"):
        assert s in out, (s, out)
    assert out.count("root cause") == 1, out
    assert re.search(r"bandit_rank[^\n]*1", out) and re.search(r"bandit_rank[^\n]*2", out), out
