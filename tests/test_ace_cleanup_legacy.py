"""WP-I (v8.0.0 round 2) — /ace:ace-cleanup --legacy (DESIGN §10 P-14, §11 A5, MECHANICS P-15).

Contract for plugins/ace/commands/ace-cleanup.md:
- It embeds ONE stdlib-only Python 3.9 block that starts with the line `# ace-cleanup: legacy`
  (run by the command as `python3 - --legacy [--yes] [--sessions-db] <<'PY' ... PY`, the block
  ends at a line that is exactly `PY` or a closing code fence).
- Without `--legacy` it does nothing. With `--legacy` alone it is a DRY RUN: prints `DRY RUN`, lists
  every candidate's absolute path, deletes nothing. `--legacy --yes` deletes:
    * `~/.claude/logs/ace-background-*`: zero-byte files always, non-empty ones only if older than 30 days
    * user-owned `ace-*` files in the temp dir (`$ACE_LEGACY_TMPDIR`, default the system `/tmp`)
    * `<cwd>/.claude/data/logs/ace-patterns-used-*`
  `~/.ace-cache/sessions.db{,-wal,-shm}` is listed only when sessions.db > 100 MB and deleted only
  with the extra confirmation flag `--sessions-db` (A5: 24 h-TTL local cache, lock storms).
- Never touches `ace-relevance.jsonl`, non-`ace-` temp files, or fresh non-empty background logs.
"""
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest

CLEANUP = Path(__file__).resolve().parent.parent / "plugins" / "ace" / "commands" / "ace-cleanup.md"
MARKER = "# ace-cleanup: legacy"
MB = 1024 * 1024


def _text():
    return CLEANUP.read_text(encoding="utf-8")


def _block():
    text = _text()
    i = text.find(MARKER)
    assert i >= 0, "ace-cleanup.md has no embedded python block starting with %r" % MARKER
    out = []
    for line in text[text.rfind("\n", 0, i) + 1:].splitlines():
        if line.strip() in ("PY", "```"):
            break
        out.append(line)
    return "\n".join(out) + "\n"


@pytest.fixture
def world(tmp_path):
    home = tmp_path / "home"
    proj = tmp_path / "proj"
    tmpd = tmp_path / "systmp"
    logs = home / ".claude" / "logs"
    plogs = proj / ".claude" / "data" / "logs"
    cache = home / ".ace-cache"
    for d in (logs, plogs, tmpd, cache):
        d.mkdir(parents=True)
    old = time.time() - 40 * 86400
    f = {}
    f["bg_empty"] = logs / "ace-background-1.log"
    f["bg_empty"].write_text("")
    f["bg_old"] = logs / "ace-background-2.log"
    f["bg_old"].write_text("x")
    os.utime(f["bg_old"], (old, old))
    f["bg_fresh"] = logs / "ace-background-3.log"
    f["bg_fresh"].write_text("keep me")
    f["other_log"] = logs / "other.log"
    f["other_log"].write_text("")
    f["tmp_ace"] = tmpd / "ace-domain-abc.txt"
    f["tmp_ace"].write_text("x")
    f["tmp_other"] = tmpd / "unrelated.txt"
    f["tmp_other"].write_text("x")
    f["pu"] = plogs / "ace-patterns-used-main.json"
    f["pu"].write_text("{}")
    f["relevance"] = plogs / "ace-relevance.jsonl"
    f["relevance"].write_text("{}\n")
    f["sdb"] = cache / "sessions.db"
    f["sdb_wal"] = cache / "sessions.db-wal"
    f["sdb_shm"] = cache / "sessions.db-shm"
    for k in ("sdb", "sdb_wal", "sdb_shm"):
        f[k].write_bytes(b"")
    return {"home": home, "proj": proj, "tmpd": tmpd, "tmp_path": tmp_path, "f": f}


def _big_sessions_db(world):
    with open(world["f"]["sdb"], "wb") as fh:
        fh.truncate(101 * MB)  # sparse: cheap on disk


def _run(world, *args):
    script = world["tmp_path"] / "legacy_block.py"
    script.write_text(_block(), encoding="utf-8")
    env = dict(os.environ, HOME=str(world["home"]), ACE_LEGACY_TMPDIR=str(world["tmpd"]))
    r = subprocess.run([sys.executable, str(script)] + list(args), cwd=str(world["proj"]),
                       env=env, capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    return r.stdout


def _exists(world):
    return {k: p.exists() for k, p in world["f"].items()}


def test_command_documents_legacy_flag():
    text = _text()
    fm = text.split("\n---", 1)[0]
    assert "--legacy" in fm, "argument-hint must list --legacy"
    assert "/ace:ace-cleanup --legacy" in text, "Usage must show `/ace:ace-cleanup --legacy`"
    assert "--sessions-db" in text


def test_command_allows_python3():
    fm = _text().split("\n---", 1)[0]
    assert "Bash(python3:*)" in fm, "allowed-tools must include Bash(python3:*) to run the embedded block"


def test_block_is_stdlib_python39():
    src = _block()
    compile(src, "legacy_block.py", "exec")
    imports = set(re.findall(r"^\s*(?:import|from)\s+([A-Za-z_][\w]*)", src, re.M))
    stdlib = {"os", "sys", "time", "glob", "pathlib", "argparse", "stat", "json", "datetime", "shutil", "tempfile"}
    assert imports <= stdlib, "non-stdlib imports: %s" % (imports - stdlib)
    py39 = "/usr/bin/python3"
    if os.path.exists(py39):
        r = subprocess.run([py39, "-c", "import sys;compile(sys.stdin.read(),'b','exec')"],
                           input=src, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr


def test_no_flag_deletes_nothing(world):
    _big_sessions_db(world)
    before = _exists(world)
    _run(world, "--yes", "--sessions-db")  # no --legacy -> must be a no-op
    assert _exists(world) == before


def test_dry_run_lists_candidates_and_deletes_nothing(world):
    before = _exists(world)
    out = _run(world, "--legacy")
    assert "DRY RUN" in out
    f = world["f"]
    for k in ("bg_empty", "bg_old", "tmp_ace", "pu"):
        assert str(f[k]) in out, "dry run must list %s" % f[k]
    for k in ("bg_fresh", "other_log", "tmp_other", "relevance", "sdb"):
        assert str(f[k]) not in out, "dry run must not list %s" % f[k]
    assert "--yes" in out, "dry run must say how to actually delete"
    assert _exists(world) == before


def test_yes_deletes_exactly_the_legacy_files(world):
    _run(world, "--legacy", "--yes")
    e = _exists(world)
    assert not e["bg_empty"] and not e["bg_old"] and not e["tmp_ace"] and not e["pu"]
    assert e["bg_fresh"] and e["other_log"] and e["tmp_other"] and e["relevance"]
    assert e["sdb"] and e["sdb_wal"] and e["sdb_shm"]


def test_small_sessions_db_never_offered(world):
    out = _run(world, "--legacy", "--yes", "--sessions-db")
    assert str(world["f"]["sdb"]) not in out
    assert world["f"]["sdb"].exists()


def test_big_sessions_db_listed_but_needs_confirmation(world):
    _big_sessions_db(world)
    out = _run(world, "--legacy")
    assert str(world["f"]["sdb"]) in out
    assert "--sessions-db" in out
    _run(world, "--legacy", "--yes")
    assert world["f"]["sdb"].exists(), "sessions.db needs --sessions-db confirmation"


def test_big_sessions_db_deleted_with_confirmation(world):
    _big_sessions_db(world)
    _run(world, "--legacy", "--yes", "--sessions-db")
    f = world["f"]
    assert not f["sdb"].exists() and not f["sdb_wal"].exists() and not f["sdb_shm"].exists()


def test_cleanup_doc_has_no_v7_vocabulary():
    """MECHANICS P-15: no `.prev` relevance archive, no pretooluse/precompact event logs; mention plugin data."""
    text = _text()
    assert "ace-relevance.prev" not in text
    assert "ace-pretooluse" not in text and "ace-precompact" not in text
    assert "CLAUDE_PLUGIN_DATA" in text


def test_default_tmpdir_is_literal_tmp_and_prefixes_narrow(world, monkeypatch):
    """ACE_LEGACY_TMPDIR unset + TMPDIR elsewhere: block must scan the literal /tmp, not $TMPDIR."""
    src = _block()
    assert 'os.path.join(os.sep, "tmp")' in src and "gettempdir" not in src
    script = world["tmp_path"] / "legacy_default.py"
    # run the block with the literal /tmp swapped for the fixture dir, to prove the default branch is used
    script.write_text(src.replace('os.path.join(os.sep, "tmp")', repr(str(world["tmpd"]))), encoding="utf-8")
    other = world["tmp_path"] / "elsewhere"
    other.mkdir()
    (other / "ace-domain-zzz.txt").write_text("x")
    (world["tmpd"] / "ace-agile-1.txt").write_text("x")  # unrelated ace-* tool: must not be listed
    env = {k: v for k, v in os.environ.items() if k != "ACE_LEGACY_TMPDIR"}
    env.update(HOME=str(world["home"]), TMPDIR=str(other))
    r = subprocess.run([sys.executable, str(script), "--legacy"], cwd=str(world["proj"]),
                       env=env, capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    assert str(world["f"]["tmp_ace"]) in r.stdout
    assert "ace-domain-zzz" not in r.stdout and "ace-agile" not in r.stdout


def test_main_block_with_legacy_deletes_nothing(world):
    """The default-cleanup bash block must exit early on --legacy (dry run promise)."""
    text = _text()
    i = text.index("```bash")
    blk = text[i + len("```bash"):text.index("\n```", i)]
    old = world["proj"] / ".claude" / "data" / "logs" / "ace-posttooluse-x.jsonl"
    old.write_text("{}\n")
    t = time.time() - 30 * 86400
    os.utime(old, (t, t))
    r = subprocess.run(["bash", "-c", blk, "bash", "--legacy"], cwd=str(world["proj"]),
                       env=dict(os.environ, HOME=str(world["home"])), capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    assert old.exists() and "Deleted" not in r.stdout
