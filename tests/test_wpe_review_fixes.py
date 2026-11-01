"""WP-E review fixes."""
import re, subprocess, json, os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "plugins" / "ace"
DOC = (ROOT / "commands" / "ace-doctor.md").read_text()
SL = (ROOT / "commands" / "ace-statusline-setup.md").read_text()
SCRIPT = ROOT / "scripts" / "ace_statusline.sh"


def test_doctor_data_token_and_real_fallback():
    # cc_hooks_reference.md:480 / plugins_components.md:643: only exact ${CLAUDE_PLUGIN_DATA} is substituted
    assert 'DATA="${CLAUDE_PLUGIN_DATA}"' in DOC
    assert "plugins/data/ace-ce-dot-net-marketplace" in DOC
    assert ":-$HOME/.claude/plugins/data/ace}" not in DOC


def test_statusline_setup_uses_braced_root():
    assert "$CLAUDE_PLUGIN_ROOT" not in SL.replace("${CLAUDE_PLUGIN_ROOT}", "")


def test_doctor_allowed_tools_cover_check0():
    line = re.search(r"^allowed-tools:.*$", DOC, re.M).group(0)
    for t in ("claude", "cat", "tail", "sort"):
        assert "Bash(%s:*)" % t in line


def test_doctor_plugin_json_path_and_stale_samples():
    assert '"$PLUGIN_ROOT/plugin.json"' not in DOC
    assert ".claude-plugin/plugin.json" in DOC
    for s in ("--log --chat", "--notify", "Permission telemetry"):
        assert s not in DOC


def test_statusline_bounded_tail_and_zero_quality(tmp_path):
    logs = tmp_path / ".claude" / "data" / "logs"
    logs.mkdir(parents=True)
    pad = json.dumps({"event": "search", "patterns_injected": 999, "avg_confidence": 0.1}) + "\n"
    with open(logs / "ace-relevance.jsonl", "w") as f:
        for _ in range(60000):  # > 2MB
            f.write(pad)
        f.write(json.dumps({"event": "search", "patterns_injected": 3, "avg_confidence": 0.5}) + "\n")
    (logs / "ace-review-result.json").write_text(json.dumps({"quality_pct": 0, "helpful_pct": 80}))
    r = subprocess.run(["bash", str(SCRIPT)], input=json.dumps({"cwd": str(tmp_path)}),
                       capture_output=True, text=True, timeout=30)
    assert "80%" not in r.stdout
