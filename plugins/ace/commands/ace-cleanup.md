---
disable-model-invocation: true
model: claude-haiku-4-5
description: Show ACE log sizes and delete old rotated logs and v7 leftovers
argument-hint: "[--days N] [--status] [--legacy [--yes] [--sessions-db]]"
allowed-tools: Bash(${CLAUDE_PLUGIN_ROOT}/scripts/ace-cli:*), Bash(jq:*), Bash(npm:*), Bash(rm:*), Bash(ls:*), Bash(python3:*), Read
---

# ACE Log Cleanup

v8 writes one metrics log per project, `.claude/data/logs/ace-relevance.jsonl`, rotated by size (50 MB) into
`ace-relevance.1.jsonl` .. `ace-relevance.3.jsonl`, plus the small `ace-eval-request.json` / `ace-review-result.json`.
The hook error log is `<CLAUDE_PLUGIN_DATA>/logs/ace-hook-errors.log` (5 MB, one backup). There is no event logger.

```bash
#!/usr/bin/env bash
set -euo pipefail

DAYS=7
SHOW_STATUS=false
while [[ $# -gt 0 ]]; do
  case $1 in
    --days) DAYS="$2"; shift 2 ;;
    --status) SHOW_STATUS=true; shift ;;
    --legacy) exit 0 ;;  # handled by the "Legacy cleanup" block below
    *) shift ;;
  esac
done

LOG_DIR=".claude/data/logs"
ERR_LOG="${CLAUDE_PLUGIN_DATA:-$HOME/.claude/plugins/data/ace-ce-dot-net-marketplace}/logs/ace-hook-errors.log"

if [ "$SHOW_STATUS" = true ]; then
  echo "ACE Log Status"
  echo ""
  if [ -d "$LOG_DIR" ]; then
    echo "Log Directory: $LOG_DIR ($(du -sh "$LOG_DIR" 2>/dev/null | cut -f1))"
    ls -lhS "$LOG_DIR" 2>/dev/null | grep -E "\.jsonl|\.json" | while read line; do echo "  $line"; done
  else
    echo "Log directory does not exist: $LOG_DIR"
  fi
  [ -f "$ERR_LOG" ] && echo "Hook errors: $ERR_LOG ($(ls -lh "$ERR_LOG" | awk '{print $5}'))" || echo "Hook errors: none"
  exit 0
fi

if [ ! -d "$LOG_DIR" ]; then
  echo "Log directory does not exist: $LOG_DIR"
  exit 0
fi

echo "ACE Log Cleanup: deleting rotated logs and v7 leftovers older than $DAYS days"
BEFORE=$(du -sh "$LOG_DIR" 2>/dev/null | cut -f1)
DELETED=0
# rotated metrics logs (v8) + event/error logs v7 wrote (v8 writes none of these)
for pattern in "ace-relevance.[1-3].jsonl" "ace-posttooluse*.jsonl" "ace-stop*.jsonl" "ace-errors*.jsonl"; do
  for file in "$LOG_DIR"/$pattern; do
    if [ -f "$file" ] && [ ! -L "$file" ] && [ "$(find "$file" -mtime +$DAYS 2>/dev/null)" ]; then
      echo "  Deleting: $(basename "$file") ($(ls -lh "$file" | awk '{print $5}'))"
      rm -f "$file"
      DELETED=$((DELETED + 1))
    fi
  done
done
AFTER=$(du -sh "$LOG_DIR" 2>/dev/null | cut -f1)
if [ $DELETED -eq 0 ]; then echo "No logs older than $DAYS days found."; else echo "Deleted $DELETED file(s), $BEFORE -> $AFTER"; fi
```

## Usage

```bash
# Show log status and sizes
/ace:ace-cleanup --status

# Preview / delete v7 leftovers (dry run unless --yes)
/ace:ace-cleanup --legacy
/ace:ace-cleanup --legacy --yes
/ace:ace-cleanup --legacy --yes --sessions-db

# Delete logs older than 7 days (default)
/ace:ace-cleanup

# Delete logs older than 30 days
/ace:ace-cleanup --days 30
```

## Legacy cleanup (`--legacy`)

v8 keeps its state under `CLAUDE_PLUGIN_DATA` and no longer writes the files below. `--legacy` removes what
v7 left behind. It is a **dry run** by default: it prints the absolute paths and deletes nothing.

- `/ace:ace-cleanup --legacy` lists the candidates (DRY RUN).
- `/ace:ace-cleanup --legacy --yes` deletes them.
- `/ace:ace-cleanup --legacy --yes --sessions-db` also deletes `~/.ace-cache/sessions.db{,-wal,-shm}`, but only
  when sessions.db is over 100 MB (it is a 24 h-TTL local cache; stop running `ace-cli` processes first).

Candidates: `~/.claude/logs/ace-background-*` (zero-byte, or non-empty and older than 30 days), your own
v7 temp files in `/tmp` (`ace-session-*`, `ace-domain-*`, `ace-domains-*`, `ace-update-check-*`,
`ace-patterns-precompact-*`, `ace-learn-inflight-*`, `ace-disabled-*`, `ace-eval-requested-*`; override the
directory with `ACE_LEGACY_TMPDIR`), and
`.claude/data/logs/ace-patterns-used-*` in the current project.

Run the block with the flags you were given (`$ARGUMENTS`); without `--legacy` it does nothing:

```bash
python3 - $ARGUMENTS <<'PY'
# ace-cleanup: legacy
import os, sys, glob, time

args = sys.argv[1:]
if "--legacy" not in args:
    sys.exit(0)
yes = "--yes" in args
sdb_ok = "--sessions-db" in args
home = os.path.expanduser("~")
MB = 1024 * 1024
cands = []
cutoff = time.time() - 30 * 86400
for p in glob.glob(os.path.join(home, ".claude", "logs", "ace-background-*")):
    try:
        st = os.stat(p)
    except OSError:
        continue
    if st.st_size == 0 or st.st_mtime < cutoff:
        cands.append(p)
# v7 hardcoded the literal /tmp (not $TMPDIR, which differs on macOS)
tmpd = os.environ.get("ACE_LEGACY_TMPDIR") or os.path.join(os.sep, "tmp")
V7_PREFIXES = ("session", "domain", "domains", "update-check", "patterns-precompact",
               "learn-inflight", "disabled", "eval-requested")
for pre in V7_PREFIXES:
    for p in glob.glob(os.path.join(tmpd, "ace-%s-*" % pre)):
        try:
            if os.path.isfile(p) and os.stat(p).st_uid == os.getuid():
                cands.append(p)
        except OSError:
            pass
cands += glob.glob(os.path.join(os.getcwd(), ".claude", "data", "logs", "ace-patterns-used-*"))
sdb = os.path.join(home, ".ace-cache", "sessions.db")
sdb_files = []
if os.path.isfile(sdb) and os.path.getsize(sdb) > 100 * MB:
    sdb_files = [f for f in (sdb, sdb + "-wal", sdb + "-shm") if os.path.exists(f)]

print("ACE legacy cleanup" + ("" if yes else " - DRY RUN (nothing deleted)"))
for p in cands:
    print("  " + os.path.abspath(p))
for p in sdb_files:
    print("  " + p + ("" if sdb_ok else "   (needs --sessions-db)"))
if not cands and not sdb_files:
    print("  nothing to clean")
if not yes:
    print("Re-run with --yes to delete" + (" (add --sessions-db for sessions.db)" if sdb_files else "") + ".")
    sys.exit(0)
targets = cands + (sdb_files if sdb_ok else [])
n = 0
for p in targets:
    try:
        os.remove(p)
        n += 1
    except OSError as e:
        print("  skip %s: %s" % (p, e))
print("Deleted %d file(s)" % n)
PY
```

## What Gets Cleaned

**Deleted** (older than `--days`, default 7):
- `ace-relevance.1.jsonl` .. `ace-relevance.3.jsonl` - rotated metrics logs
- `ace-posttooluse*.jsonl`, `ace-stop*.jsonl`, `ace-errors*.jsonl` - v7 event/error logs (v8 does not write them)

**Preserved**:
- `ace-relevance.jsonl` - the current metrics log (`/ace:ace-insights` reads it)
- `<CLAUDE_PLUGIN_DATA>/logs/ace-hook-errors.log` - hook errors (size-capped by the hooks; see `/ace:ace-doctor`)

v8 plugin state (task state, tool records) lives under `CLAUDE_PLUGIN_DATA` and is removed by SessionEnd.
