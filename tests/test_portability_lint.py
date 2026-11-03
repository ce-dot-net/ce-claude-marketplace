#!/usr/bin/env python3
"""DESIGN §18: nothing may depend on the author's machine (300 users on Linux + macOS).

Stock macOS: /bin/bash 3.2, no flock/timeout, BSD date/sed/stat, `readlink -f` only on >= 12.3.
Linux: GNU tools, no Homebrew. Realpath/locking/timeouts live in Python or Node.
"""
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
PLUGIN = REPO / "plugins" / "ace"

MACHINE_PATHS = ["/Users/ptsafaridis", ".nvm/versions", "/opt/homebrew"]

# Forbidden in anything bash runs: scripts and the bash blocks of commands.
IDIOMS = {
    "flock": r"\bflock\b",
    "timeout": r"(?:^|[;&|(]\s*|\s)timeout\s+\d",
    "readlink -f": r"\breadlink\s+-f\b",
    "date -d": r"\bdate\s+(?:-\w+\s+)*-d\b",
    "stat -c": r"\bstat\s+-c\b",
    "sed -i": r"\bsed\s+(?:-\w+\s+)*-i\b",
    "grep -P": r"\bgrep\s+(?:-\w+\s+)*-\w*P\w*\b",
    "/proc": r"(?<![\w.-])/proc/",
    "sort -V": r"\bsort\s+(?:-\w+\s+)*-\w*V",
}

FENCE = re.compile(r"```(?:bash|sh|shell)\n(.*?)```", re.S)


def _shipped_text_files():
    skip_dirs = {"node_modules", "__pycache__", ".pytest_cache", ".ace-cache", "tests"}
    for p in sorted(PLUGIN.rglob("*")):
        if not p.is_file() or skip_dirs & set(p.relative_to(PLUGIN).parts):
            continue
        if p.name in ("CHANGELOG.md", "package-lock.json", ".DS_Store") or p.suffix in (".pyc", ".png", ".db"):
            continue
        yield p


def _code_lines(text):
    for line in text.splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            yield line


def _bash_sources():
    for p in sorted((PLUGIN / "scripts").glob("*")):
        if p.is_file():
            yield p, p.read_text(errors="replace")
    for p in sorted((PLUGIN / "commands").glob("*.md")):
        yield p, "\n".join(FENCE.findall(p.read_text(errors="replace")))


@pytest.mark.parametrize("needle", MACHINE_PATHS)
def test_no_machine_paths_shipped(needle):
    hits = ["%s:%d" % (p.relative_to(PLUGIN), i)
            for p in _shipped_text_files()
            for i, l in enumerate(p.read_text(errors="replace").splitlines(), 1) if needle in l]
    assert hits == [], "%s in: %s" % (needle, hits[:10])


@pytest.mark.parametrize("label", sorted(IDIOMS))
def test_no_forbidden_shell_idiom(label):
    rx = re.compile(IDIOMS[label])
    hits = []
    for p, text in _bash_sources():
        for line in _code_lines(text):
            if rx.search(line):
                hits.append("%s: %s" % (p.relative_to(PLUGIN), line.strip()[:80]))
    assert hits == [], "%s is not portable: %s" % (label, hits[:10])


def test_no_gnu_only_flock_or_proc_in_python_hooks():
    hits = [p.name for p in (PLUGIN / "shared-hooks").rglob("*.py")
            if re.search(r"""['"]/proc/|['"](flock|readlink)['"]""", p.read_text())]
    assert hits == []


def test_tests_ci_workflow_has_both_oses_and_python_floor():
    wf = (REPO / ".github" / "workflows" / "tests.yml").read_text()
    assert "ubuntu-latest" in wf and "macos-latest" in wf and '"3.10"' in wf and '"3.15"' in wf  # 8.1.0: floor + latest


def test_lint_scan_covers_the_expected_files():
    names = {p.name for p in _shipped_text_files()}
    assert {"ace_install_cli.sh", "ace_cli.py", "ace-doctor.md", "hooks.json"} <= names
    assert {"ace_statusline.sh"} <= {p.name for p, _ in _bash_sources()}
