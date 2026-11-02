---
disable-model-invocation: true
model: claude-haiku-4-5
description: Manage ACE log files and event logging toggle
argument-hint: "[--days N] [--status] [--enable-logging] [--disable-logging] [--legacy [--yes] [--sessions-db]]"
allowed-tools: Bash(ace-cli:*), Bash(jq:*), Bash(npm:*), Bash(rm:*), Bash(ls:*), Bash(python3:*), Read
---

# ACE Log Cleanup & Event Logging Toggle

```bash
#!/usr/bin/env bash
set -euo pipefail

# Parse arguments
DAYS=7
SHOW_STATUS=false
ENABLE_LOGGING=""

while [[ $# -gt 0 ]]; do
  case $1 in
    --days)
      DAYS="$2"
      shift 2
      ;;
    --status)
      SHOW_STATUS=true
      shift
      ;;
    --enable-logging)
      ENABLE_LOGGING="enable"
      shift
      ;;
    --disable-logging)
      ENABLE_LOGGING="disable"
      shift
      ;;
    --legacy)
      # handled by the separate "Legacy cleanup" block below; never run the default cleanup
      exit 0
      ;;
    *)
      shift
      ;;
  esac
done

LOG_DIR=".claude/data/logs"

# Handle logging toggle
if [ -n "$ENABLE_LOGGING" ]; then
  if [ "$ENABLE_LOGGING" = "enable" ]; then
    echo "To enable event logging, add to your shell profile:"
    echo ""
    echo "  export ACE_EVENT_LOGGING=1"
    echo ""
    echo "Or run Claude Code with:"
    echo ""
    echo "  ACE_EVENT_LOGGING=1 claude"
    echo ""
    echo "Note: Event logging writes full tool responses to .claude/data/logs/"
    echo "This can cause 42GB+ log growth over time. Only enable for debugging."
  else
    echo "To disable event logging, remove from your shell profile:"
    echo ""
    echo "  unset ACE_EVENT_LOGGING"
    echo ""
    echo "Or simply don't set the variable (disabled by default since v5.4.5)."
  fi
  exit 0
fi

# Show status
if [ "$SHOW_STATUS" = true ]; then
  echo "ACE Log Status"
  echo ""

  # Check event logging status
  if [ "${ACE_EVENT_LOGGING:-0}" = "1" ]; then
    echo "Event Logging: ENABLED (ACE_EVENT_LOGGING=1)"
    echo "  Warning: Full tool responses are being logged!"
  else
    echo "Event Logging: DISABLED (default since v5.4.5)"
  fi
  echo ""

  # Show log sizes
  if [ -d "$LOG_DIR" ]; then
    echo "Log Directory: $LOG_DIR"
    echo ""
    TOTAL=$(du -sh "$LOG_DIR" 2>/dev/null | cut -f1)
    echo "Total Size: $TOTAL"
    echo ""
    echo "Files:"
    ls -lhS "$LOG_DIR" 2>/dev/null | grep -E "\.jsonl|\.db" | while read line; do
      echo "  $line"
    done
  else
    echo "Log directory does not exist: $LOG_DIR"
  fi
  exit 0
fi

# Cleanup old logs
if [ ! -d "$LOG_DIR" ]; then
  echo "Log directory does not exist: $LOG_DIR"
  exit 0
fi

echo "ACE Log Cleanup"
echo ""
echo "Deleting logs older than $DAYS days..."
echo ""

# Calculate size before
BEFORE=$(du -sh "$LOG_DIR" 2>/dev/null | cut -f1)

# Find and delete old log files
# Note: We keep ace-relevance.jsonl (metrics) but delete event logs
DELETED=0

# Delete old event logs (the 42GB culprits)
for pattern in "ace-posttooluse*.jsonl" "ace-stop*.jsonl"; do
  for file in "$LOG_DIR"/$pattern; do
    if [ -f "$file" ]; then
      # Check if file is older than N days
      if [ "$(find "$file" -mtime +$DAYS 2>/dev/null)" ]; then
        SIZE=$(ls -lh "$file" | awk '{print $5}')
        echo "  Deleting: $(basename "$file") ($SIZE)"
        rm -f "$file"
        DELETED=$((DELETED + 1))
      fi
    fi
  done
done

# Delete old error logs
for file in "$LOG_DIR"/ace-errors*.jsonl; do
  if [ -f "$file" ]; then
    if [ "$(find "$file" -mtime +$DAYS 2>/dev/null)" ]; then
      SIZE=$(ls -lh "$file" | awk '{print $5}')
      echo "  Deleting: $(basename "$file") ($SIZE)"
      rm -f "$file"
      DELETED=$((DELETED + 1))
    fi
  fi
done

# Calculate size after
AFTER=$(du -sh "$LOG_DIR" 2>/dev/null | cut -f1)

echo ""
if [ $DELETED -eq 0 ]; then
  echo "No logs older than $DAYS days found."
else
  echo "Deleted $DELETED file(s)"
  echo "Space: $BEFORE -> $AFTER"
fi

echo ""
echo "Remaining files:"
ls -lhS "$LOG_DIR" 2>/dev/null | grep -E "\.jsonl|\.db" | head -10 | while read line; do
  echo "  $line"
done
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

# Show how to enable event logging (for debugging)
/ace:ace-cleanup --enable-logging

# Show how to disable event logging
/ace:ace-cleanup --disable-logging
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

**Deleted** (event logs - the 42GB culprits):
- `ace-posttooluse*.jsonl` - Full tool input/output logs
- `ace-stop*.jsonl` - Stop hook event logs
- `ace-errors*.jsonl` - Error logs

**Preserved** (useful for analysis):
- `ace-relevance.jsonl` - Pattern metrics
- `ace-tools.db` - SQLite (auto-cleaned after each task)

v8 plugin state and the hook error log live under `CLAUDE_PLUGIN_DATA` (see `/ace:ace-doctor`).

## Event Logging

Since v5.4.5, event logging is **disabled by default** to prevent 42GB log growth.

To enable for debugging:
```bash
export ACE_EVENT_LOGGING=1
```

To disable (default):
```bash
unset ACE_EVENT_LOGGING
```
