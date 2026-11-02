#!/usr/bin/env python3
"""DESIGN §27 + merge item 7: ace-cli-watch artifact poisoning.

The test job runs freshly published npm code (npm ci, rebuild, the suite). Anything it can write after that is
untrusted, so: the bump patch is uploaded BEFORE any package code runs, the pr job verifies at JSON level that the
patch changes only the pinned version and @ace-sdk lock entries (registry tarballs), the test outcome comes from the
runner (job output), and the log tails are display text with fences and mentions neutralised. Actions pinned by SHA.
"""
import copy
import importlib.util
import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
WATCH = REPO / ".github" / "workflows" / "ace-cli-watch.yml"
VERIFY = REPO / ".github" / "scripts" / "verify_bump.py"


def _jobs():
    t = WATCH.read_text()
    head, rest = t.split("\n  test:\n", 1)
    test_job, pr_job = rest.split("\n  pr:\n", 1)
    return head, test_job, pr_job


def _steps(job):
    return ["- name:" + s if not s.lstrip().startswith("- uses") else s for s in re.split(r"\n\s+- name:", job)]


# ── static: order and trust ─────────────────────────────────────────────────────────────

def test_patch_is_uploaded_before_any_package_code_runs():
    _h, test_job, _p = _jobs()
    up = test_job.index("name: ace-cli-bump-patch")
    for cmd in ("npm ci", "npm rebuild", "pytest"):
        assert test_job.index(cmd) > up, cmd + " runs before the patch is uploaded"


def test_logs_travel_in_their_own_artifact_and_the_pr_job_takes_the_patch_from_the_early_one():
    _h, test_job, pr_job = _jobs()
    assert "name: ace-cli-bump-logs" in test_job
    patch_dl = pr_job.split("name: ace-cli-bump-patch", 1)[1].split("path:", 1)[1].split("\n", 1)[0]
    logs_dl = pr_job.split("name: ace-cli-bump-logs", 1)[1].split("path:", 1)[1].split("\n", 1)[0]
    assert patch_dl.strip() != logs_dl.strip(), "logs must not land where the patch is read from"
    assert "bump.patch" not in test_job.split("name: ace-cli-bump-logs", 1)[0].rsplit("upload-artifact", 1)[1]


def test_pr_job_verifies_the_patch_before_commit_and_push():
    _h, _t, pr_job = _jobs()
    i_apply, i_verify = pr_job.index("git apply \"$PATCH/bump.patch\""), pr_job.index("verify_bump.py")
    assert i_apply < i_verify < pr_job.index("git commit") < pr_job.index("git push")


def test_outcome_comes_from_the_runner_not_from_an_artifact():
    _h, test_job, pr_job = _jobs()
    assert re.search(r"outcome: \$\{\{ steps\.tests\.outcome \}\}", test_job)
    assert "needs.test.outputs.outcome" in pr_job
    assert "outcome.txt" not in pr_job


def test_log_tails_are_neutralised_display_text():
    _h, _t, pr_job = _jobs()
    body = pr_job.split("name: Open the pull request", 1)[1]
    for f in ("contract.txt", "suite.txt"):
        line = next(l for l in body.splitlines() if f in l)
        assert "sed" in line and "`" in line and "@" in line, line


def test_every_action_is_pinned_by_sha():
    uses = re.findall(r"uses:\s*(\S+)", WATCH.read_text())
    assert uses and all(re.search(r"@[0-9a-f]{40}$", u) for u in uses), uses


# ── verify_bump: JSON-level allow-list ──────────────────────────────────────────────────

def _verify():
    spec = importlib.util.spec_from_file_location("verify_bump", VERIFY)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.verify


PKG = {"private": True, "dependencies": {"@ace-sdk/cli": "4.2.2"}}
LOCK = {"name": "ace", "lockfileVersion": 3, "requires": True, "packages": {
    "": {"dependencies": {"@ace-sdk/cli": "4.2.2"}},
    "node_modules/@ace-sdk/cli": {"version": "4.2.2", "resolved": "https://registry.npmjs.org/@ace-sdk/cli/-/cli-4.2.2.tgz",
                                  "integrity": "sha512-old", "dependencies": {"@ace-sdk/core": "^3.3.2"}},
    "node_modules/@ace-sdk/core": {"version": "3.3.2", "resolved": "https://registry.npmjs.org/@ace-sdk/core/-/core-3.3.2.tgz",
                                   "integrity": "sha512-oldc"},
    "node_modules/chalk": {"version": "5.6.2", "resolved": "https://registry.npmjs.org/chalk/-/chalk-5.6.2.tgz",
                           "integrity": "sha512-ch"}}}
MAN = '{"description": "Requires: ace-cli >= 4.2.2"}'


def _files(pkg=PKG, lock=LOCK, man=MAN):
    return {"plugins/ace/package.json": json.dumps(pkg), "plugins/ace/package-lock.json": json.dumps(lock),
            "plugins/ace/.claude-plugin/plugin.json": man}


def _good():
    pkg, lock = copy.deepcopy(PKG), copy.deepcopy(LOCK)
    pkg["dependencies"]["@ace-sdk/cli"] = "4.3.0"
    lock["packages"][""]["dependencies"]["@ace-sdk/cli"] = "4.3.0"
    cli = lock["packages"]["node_modules/@ace-sdk/cli"]
    cli.update(version="4.3.0", resolved="https://registry.npmjs.org/@ace-sdk/cli/-/cli-4.3.0.tgz", integrity="sha512-new")
    lock["packages"]["node_modules/@ace-sdk/core"].update(
        version="3.4.0", resolved="https://registry.npmjs.org/@ace-sdk/core/-/core-3.4.0.tgz", integrity="sha512-newc")
    return pkg, lock, MAN.replace("4.2.2", "4.3.0")


def test_a_clean_bump_passes():
    assert _verify()(_files(), _files(*_good()), "4.2.2", "4.3.0") == []


def test_extra_dependency_in_package_json_fails():
    pkg, lock, man = _good()
    pkg["dependencies"]["evil"] = "1.0.0"
    assert _verify()(_files(), _files(pkg, lock, man), "4.2.2", "4.3.0")


def test_a_script_in_package_json_fails():
    pkg, lock, man = _good()
    pkg["scripts"] = {"postinstall": "curl x | sh"}
    assert _verify()(_files(), _files(pkg, lock, man), "4.2.2", "4.3.0")


def test_lock_entry_outside_ace_sdk_fails():
    pkg, lock, man = _good()
    lock["packages"]["node_modules/chalk"]["version"] = "9.9.9"
    assert _verify()(_files(), _files(pkg, lock, man), "4.2.2", "4.3.0")


@pytest.mark.parametrize("url", ["https://evil.example/cli.tgz", "http://registry.npmjs.org/@ace-sdk/cli/-/cli-4.3.0.tgz",
                                 "git+ssh://git@github.com/x/y.git"])
def test_lock_tarball_off_the_registry_fails(url):
    pkg, lock, man = _good()
    lock["packages"]["node_modules/@ace-sdk/cli"]["resolved"] = url
    assert _verify()(_files(), _files(pkg, lock, man), "4.2.2", "4.3.0")


def test_lock_install_script_flag_fails():
    pkg, lock, man = _good()
    lock["packages"]["node_modules/@ace-sdk/cli"]["hasInstallScript"] = True
    assert _verify()(_files(), _files(pkg, lock, man), "4.2.2", "4.3.0")


def test_manifest_change_beyond_the_version_fails():
    pkg, lock, _m = _good()
    assert _verify()(_files(), _files(pkg, lock, MAN.replace("4.2.2", "4.3.0") + " "), "4.2.2", "4.3.0")


def test_a_file_outside_the_allow_list_fails():
    new = _files(*_good())
    new["plugins/ace/hooks/hooks.json"] = "{}"
    assert _verify()(_files(), new, "4.2.2", "4.3.0")
