"""The 422 trap: the server requires GitContext.commit_hash; a trace with `git` but no commit_hash is rejected whole.
Python chain: git_utils.get_git_context returns a context only with commit_hash; ace_after_task hangs session_commits only
onto an existing git context (never a git object made of session_commits alone). The other trace builders (permission
denied, backfill) never build a git object at all. Mod twin: plugins/ace/mod/tests/git_context.test.ts."""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "plugins" / "ace" / "shared-hooks" / "utils"))
sys.path.insert(0, str(REPO / "plugins" / "ace" / "shared-hooks"))
import git_utils  # noqa: E402

GIT_ENV = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid", GIT_COMMITTER_NAME="t",
               GIT_COMMITTER_EMAIL="t@example.invalid", GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1")


def _git(d, *a):
    subprocess.run(["git", *a], cwd=d, env=GIT_ENV, check=True, capture_output=True)


def test_no_repo_is_none(tmp_path):
    assert git_utils.get_git_context(str(tmp_path)) is None


def test_repo_without_a_commit_is_none(tmp_path):
    _git(tmp_path, "init", "-q")
    assert git_utils.get_git_context(str(tmp_path)) is None


def test_failed_rev_parse_head_is_none(tmp_path, monkeypatch):
    _git(tmp_path, "init", "-q")
    (tmp_path / "f").write_text("x")
    _git(tmp_path, "add", "f")
    _git(tmp_path, "commit", "-qm", "c")
    real = subprocess.run

    def run(argv, *a, **k):
        if argv[:3] == ["git", "rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(argv, 128, "", "fatal")
        return real(argv, *a, **k)
    monkeypatch.setattr(git_utils.subprocess, "run", run)
    assert git_utils.get_git_context(str(tmp_path)) is None


def test_repo_with_a_commit_has_commit_hash(tmp_path):
    _git(tmp_path, "init", "-q")
    (tmp_path / "f").write_text("x")
    _git(tmp_path, "add", "f")
    _git(tmp_path, "commit", "-qm", "c")
    ctx = git_utils.get_git_context(str(tmp_path))
    assert re.fullmatch(r"[0-9a-f]{40}", ctx["commit_hash"])


def _after_task_trace(tmp_path, init_repo):
    from test_stop_v8 import ORG_ID, PROJECT_ID, Box
    box = Box(tmp_path)
    if init_repo:
        _git(box.project, "init", "-q")  # a repo without any commit: no HEAD
    sid = "s-git"
    box.write_state(sid, "main", task_session_id="own", user_prompt="refactor the parser module")
    box.seed_tools(sid, [("Edit", {"file_path": "src/app.py", "old_string": "a", "new_string": "b"}, {"success": True}),
                         ("Bash", {"command": "git commit -m x"}, {"stdout": "[main abc1234f] x\n 1 file changed", "stderr": ""})])
    p = box.run_after_task(box.stop_event(sid), ACE_PROJECT_ID=PROJECT_ID, ACE_ORG_ID=ORG_ID)
    assert p.returncode == 0, p.stderr
    (learn,) = box.cli_calls("learn")
    return learn["trace"]


@pytest.mark.parametrize("init_repo", [False, True], ids=["no_repo", "repo_without_commit"])
def test_after_task_no_git_context_plus_session_commits_sends_no_git(tmp_path, init_repo):
    assert "git" not in _after_task_trace(tmp_path, init_repo)


def test_permission_denied_trace_has_no_git():
    import ace_permission_denied as m
    assert "git" not in m._build_trace({"session_id": "c", "tool_name": "Bash", "tool_input": {"command": "git commit -m x"}})


def test_backfill_never_builds_a_git_object():
    for f in ("backfill.ts", "backfill_git.ts", "backfill_send.ts", "backfill_run.ts"):
        src = (REPO / "plugins/ace/mod/lib" / f).read_text()
        assert not re.search(r"\bgit\s*:\s*\{|\.git\s*=|commit_hash", src), f
    assert "commit_hash" not in (REPO / "plugins/ace/engine/backfill.js").read_text()


# ---- git minimisation (DSGVO): only commit_hash, timestamp, files_changed, insertions, deletions, commit_is_fix ----
ALLOWED = {"commit_hash", "commit_is_fix", "deletions", "files_changed", "insertions", "timestamp"}
SUBJECTS = [("Fix login bug", True), ("fix(8.2.7): x", True), ('Revert "x"', True), ("hotfix: y", True), ("FIXES #12", True), ("bugfix", True),
            ("prefix handling", False), ("fixture update", False), ("suffix", False), ("affix", False), ("Add feature", False), ("", False),
            ("äfix things", True)]


def test_minimised_git_context_has_only_the_allowed_keys(tmp_path):
    _git(tmp_path, "init", "-q")
    (tmp_path / "f").write_text("x")
    _git(tmp_path, "add", "f")
    _git(tmp_path, "commit", "-qm", "Fix login for ACME customer")
    ctx = git_utils.get_git_context(str(tmp_path))
    assert set(ctx) == ALLOWED and ctx["commit_is_fix"] is True
    assert "ACME" not in json.dumps(ctx) and "t@example.invalid" not in json.dumps(ctx)


@pytest.mark.parametrize("subject,want", SUBJECTS)
def test_commit_is_fix_python(subject, want):
    assert git_utils.commit_is_fix(subject) is want


def test_commit_is_fix_ts_python_parity(tmp_path):
    import shutil
    bun = shutil.which("bun")
    if not bun:
        pytest.skip("bun not installed")
    (tmp_path / "in.json").write_text(json.dumps([s for s, _ in SUBJECTS]))
    (tmp_path / "f.ts").write_text("import { commitIsFix } from '%s'\nconsole.log(JSON.stringify(JSON.parse(require('fs').readFileSync('%s','utf8')).map((s: string) => commitIsFix(s))))\n"
                                   % (REPO / "plugins/ace/mod/io/spawn.ts", tmp_path / "in.json"))
    p = subprocess.run([bun, str(tmp_path / "f.ts")], capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout) == [git_utils.commit_is_fix(s) for s, _ in SUBJECTS] == [w for _, w in SUBJECTS]


def test_sent_trace_git_is_minimised(tmp_path):
    from test_stop_v8 import ORG_ID, PROJECT_ID, Box
    box = Box(tmp_path)
    _git(box.project, "init", "-q")
    (box.project / "f").write_text("x")
    _git(box.project, "add", "f")
    _git(box.project, "commit", "-qm", "hotfix: secret customer ACME")
    sid = "s-min"
    box.write_state(sid, "main", task_session_id="own", user_prompt="refactor the parser module")
    box.seed_tools(sid, [("Edit", {"file_path": "src/app.py", "old_string": "a", "new_string": "b"}, {"success": True})])
    p = box.run_after_task(box.stop_event(sid), ACE_PROJECT_ID=PROJECT_ID, ACE_ORG_ID=ORG_ID)
    assert p.returncode == 0, p.stderr
    (learn,) = box.cli_calls("learn")
    g = learn["trace"]["git"]
    assert set(g) <= ALLOWED | {"session_commits"} and g["commit_is_fix"] is True and "ACME" not in json.dumps(learn["trace"]["git"])
