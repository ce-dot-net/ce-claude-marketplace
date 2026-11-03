# ACE Plugin Troubleshooting (v8)

Start with `/ace:ace-doctor`. It checks the Claude Code version (>= 2.1.311), the CLI source and version, the plugin-data layout, hook scripts,
server connectivity and the local session cache.

## Plugin data and logs

All plugin state lives under `CLAUDE_PLUGIN_DATA` (default `~/.claude/plugins/data/ace-ce-dot-net-marketplace`):

- `python_path`, `cli_version.json` - cached by SessionStart (`cli_version.json` is the version of a global ace-cli, the fallback only). Delete them to force a re-probe.
- `ace-hook-errors.log` - every hook failure is appended here. `tail -20` it first.
- `projects/<project_id>/sessions/<session_id>/` - per-session state, removed by SessionEnd.

Per-project metrics: `.claude/data/logs/ace-relevance.jsonl` (what the statusline, insights and doctor read).

## No patterns injected

1. `/ace:ace-doctor` - which ace-cli is used (plugin-local pin or global), and is it logged in (`/ace:ace-login`)? No CLI at all: `/ace:ace-install-cli` (ACE starts working by itself once it exists).
2. Look for `"search_skipped"` rows in `ace-relevance.jsonl`: trivial prompts (below `ACE_MIN_PROMPT_CHARS`) and
   machine prompts such as `<task-notification>` skip the search on purpose.
3. A `disabled.flag` turns ACE hooks off: `<plugin-data>/projects/<project>/disabled.flag` (whole project) or
   `<plugin-data>/projects/<project>/sessions/<session>/disabled.flag` (one session; SessionStart writes it only when Claude Code is older than 2.1.311). Remove it to re-enable. A missing ace-cli never writes it.
4. `tail ace-hook-errors.log` in the plugin data root.

## Older Claude Code

ACE 8 needs Claude Code >= 2.1.311. The hooks reference does not say what an older Claude Code does with hooks.json entries it does
not know, so ACE does not rely on it: SessionStart exists in every version, compares `CLAUDE_CODE_VERSION` with the floor and, when it is
lower, prints one message ("ACE hooks are paused") and writes the session `disabled.flag`, so every other ACE hook exits silently.
Update Claude Code and start a new session. Windows is not supported (macOS, Linux and WSL2 only).

## "database is locked" / hooks timing out

`ace-cli` keeps a 24 h-TTL local cache at `~/.ace-cache/sessions.db`. A large file plus many concurrent `ace-cli`
processes causes `database is locked` errors and hook timeouts.

1. `/ace:ace-doctor` warns when sessions.db is over 100 MB or a locked error was logged in the last 24 h.
2. Stop running `ace-cli` processes, then remove `sessions.db`, `sessions.db-wal` and `sessions.db-shm`
   (`/ace:ace-cleanup --legacy --yes --sessions-db` does exactly this, only above 100 MB).

## Leftovers from v7

`/ace:ace-cleanup --legacy` lists (dry run) old `ace-background-*` logs, `ace-*` temp files and
`ace-patterns-used-*` state files; add `--yes` to delete them.

## Learning does not show up

Stop/SubagentStop learn in a detached process, so the session can end before the result lands. Check
`ace-hook-errors.log` and run `/ace:ace-status`. Denials by deny rules are not learned (only auto-mode denials are).

## Statusline looks stale

`~/.claude/ace_statusline.sh` is a user copy; refresh it with `/ace:ace-statusline-setup update`.

## Hooks not firing

Run `claude plugin validate <plugin dir> --strict`, restart Claude Code, then `/ace:ace-test`.
