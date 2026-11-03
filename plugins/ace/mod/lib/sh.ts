// The shell programs behind the mod's private (0600, atomic) writes and symlink-safe relevance-log appends.
// Pure strings: io/fs.ts and io/log.ts run them; the learn child (lib/trace.ts) appends through APPEND_SH too.

// O_APPEND through the shell: safe beside the Python hooks writing the same jsonl; size rotation as ace_relevance_logger.
// §24: <cwd>/.claude/data/logs is repo-controlled: a symlinked component or target is refused (row dropped).
// $1 = log file, $2 = cwd, stdin = rows.
export const APPEND_SH = 'umask 077; for p in "$2/.claude" "$2/.claude/data" "$(dirname "$1")" "$1"; do [ -L "$p" ] && exit 0; done; '
  + 'mkdir -p "$(dirname "$1")" || exit 0; [ -L "$1" ] && exit 0; '
  + 'if [ "$(wc -c <"$1" 2>/dev/null || echo 0)" -gt 52428800 ]; then b="${1%.jsonl}"; '
  // same chain as ace_relevance_logger (.1-.3): a repo-planted symlink or directory in the chain drops the row, nothing is moved
  + 'for i in 1 2 3; do if [ -L "$b.$i.jsonl" ] || [ -d "$b.$i.jsonl" ]; then exit 0; fi; done; '
  + 'mv -f "$b.2.jsonl" "$b.3.jsonl" 2>/dev/null; mv -f "$b.1.jsonl" "$b.2.jsonl" 2>/dev/null; mv -f "$1" "$b.1.jsonl"; fi; cat >> "$1"'

// §24: files holding prompts, tool records or traces: umask 077 (file 0600), the dir chmod 700, atomic create+rename.
// $1 = target path, stdin = content.
export const PRIVATE_WRITE_SH = 'umask 077; d=$(dirname "$1"); mkdir -p "$d" && chmod 700 "$d" && t="$d/.w$$.tmp" && cat > "$t" && mv -f "$t" "$1"'
