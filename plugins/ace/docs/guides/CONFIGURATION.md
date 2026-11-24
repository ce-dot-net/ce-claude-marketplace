# ACE Plugin Configuration (8.1.0)

Two things are configured, in two places:

| What | Where | Who writes it |
|---|---|---|
| Login (device-code token) | ace-cli global config `~/.config/ace/config.json` (`ACE_CONFIG_PATH` overrides) | `/ace:ace-login` (ace-cli) |
| Binding: which org/project a repo is | tracked `.ace/config.json` at the repo's main checkout root | `/ace:ace-configure`, or the automatic adoption |

## The binding

```json
{"orgId": "org_xxxxx", "projectId": "prj_xxxxx"}
```

Nothing else may be in it: a file with `apiToken`, `serverUrl` (or `api_token`, `server_url`) is refused
(`config_refused`, warning `repo_file_contains_secret`) and nothing is sent; broken JSON is `config_invalid`. Ids must
look like `org_...` / `prj_...`. Commit the file: every clone, worktree and subfolder is then bound.

### Precedence (one core for every hook, command and the statusline)

1. `--org` / `--project` (what the commands pass to ace-cli)
2. `.ace/config.json`, from the current directory up to the git root; in a linked worktree then the main checkout's
3. `.claude/settings.json` `env.ACE_ORG_ID` / `env.ACE_PROJECT_ID`, same walk (legacy; adopted, see below)
4. `ACE_ORG_ID` / `ACE_PROJECT_ID` in the environment
5. the remote map: global config `projects`, then this machine's map (`<plugin data>/remote-map.json`), keyed by the
   normalized `origin` URL
6. unbound. There is never a default project; a top-level `projectId` in the global config is ignored and
   `/ace:ace-doctor` warns about it (`global_project_id_ignored`).

`$HOME/.ace/config.json` and `$HOME/.claude/settings.json` are never bindings. The org comes from `--org`, else the
source that gave the project, else the first org found down the list, else the global `default_org_id`.

Check any directory: `${CLAUDE_PLUGIN_ROOT}/scripts/ace-context --json` (exit 0 bound, 5 not; `tried` lists every
path), `--verify` adds the state from one `ace-cli status` call.

### .gitignore

The file must not be ignored. The rule that works:

```gitignore
.ace/*
!.ace/config.json
```

A bare `.ace/` (or `.ace`) rule ignores the directory, and git then never looks at the negation. `/ace:ace-configure`
shows this diff and applies it only after you confirm; the automatic adoption applies it itself (same semantics as
`ace-cli init --fix-gitignore`). Nothing is ever staged or committed by the plugin.

### Automatic adoption and the remote map

- A repo bound only by the legacy `.claude/settings.json` (or by the remote map) gets `.ace/config.json` written at the
  main checkout root on the next session, once, if the file does not exist; one line says so while it is untracked.
  Never for a flag or env binding, never outside git. Opt out: `ACE_AUTO_ADOPT=0`.
- Every session bound by a file records `origin URL -> {orgId, projectId}` in this machine's remote map, so a fresh
  clone of the same remote binds without a click.
- Writes never follow a symlink out of the repo (`.ace`, the file and `.gitignore` are checked; a refusal is logged as
  `write_refused` in the relevance log).

### herdr, remote boxes, no git

Outside a git repo only `<cwd>/.ace/config.json` counts (no walk-up). On a remote machine or in a herdr workspace bind
through the environment of the Claude Code process:

```bash
export ACE_ORG_ID=org_xxxxx
export ACE_PROJECT_ID=prj_xxxxx
```

The env loses to a tracked `.ace/config.json`, so a leaked foreign env never rebinds a repo. Where the mod runs it
re-exports the resolved ids (and `ACE_CONTEXT`) to every process it starts.

## States you can see

Nothing is shown when everything is ok. Otherwise `ACE ▼ <state>` in the status area and one band above the prompt:

| State | Means | The band's one action |
|---|---|---|
| `unbound` | no binding found | [Verbinden: <project matching the repo name>] or [Projekt wählen] |
| `not_logged_in` / `expired` | no or expired login | [Anmelden] (device login, only on the press) |
| `project_not_found` / `no_access` | the server refuses the project | [Anderes wählen] |
| `config_refused` | `.ace/config.json` holds a secret | [Bereinigt neu schreiben] (then revoke the token) |
| `config_invalid` | a binding file is not valid JSON or has bad ids | none: fix the file |
| `cli_missing` | no ace-cli | [ace-cli installieren] |
| `server_error` | server down or 5xx | none (shown in the status only) |

The Python fallback chain shows the same words once per session as a single line.

## Environment knobs

- `ACE_AUTO_ADOPT=0`: no automatic `.ace/config.json`.
- `ACE_CONTEXT_ENGINE=resolver|cli`: force the plugin's resolver, or the SDK's `ace-cli context --json` (the default
  feature-detects the CLI).
- `ACE_MIN_PROMPT_CHARS`: prompts shorter than this skip the pattern search (default 12).
- `ACE_PIN_BACKOFF_MIN`: minutes to back off pinning a task session after a pin failure (default 5).
- `ACE_RENDER_FULL_PCT`, `ACE_ENGINE=cli`: see the README.

### More switches the code reads

Each row was taken from the code (the Where column). All are read from the environment of the Claude Code process.

| Variable | Default | Effect | Where |
|---|---|---|---|
| `ACE_AB_CONTROL_PCT`, `ACE_AB_COMPACT_PCT` | 0 / 0 (dormant, local only) | Percent of conversations that render no patterns (control) or all patterns compact. Each 0..100, sum <= 100, else both 0; the rest splits into full/budget by `ACE_RENDER_FULL_PCT`. Bucket = sha256(`render:` + conversation id) % 100. Nothing is sent to a server; the arm is only stamped on the trace and the relevance log. | `mod/lib/cohort.ts` `renderCohort`, `shared-hooks/utils/ace_pattern_render.py` |
| `ACE_FEEDBACK_DOWNVOTE` | unset: the server's stored switch (`feedback-downvote.json` in the data root, global: the last search of any project wins; valid < 7 days, else off) | `1` forces the rejection downvote on, `0` forces it off. | `mod/io/state.ts` `downvoteEnabled`, `utils/ace_feedback.py` `downvote_enabled` |
| `ACE_LOCAL_REUSE` | `domain,subagent` | Comma list of the searches that may reuse a local cached result (same project and query, < 15 min). Kinds: `domain`, `subagent`; the main prompt search never reuses. Empty string = none. | `mod/lib/state.ts` `reuseEnabled`, `utils/ace_search_cache.py` |
| `ACE_MACHINE_PROMPT_PREFIXES` | empty | Comma list of extra prompt prefixes (lower-cased) treated as machine prompts from local daemons, so they skip pattern search; added to the built-in list. | `mod/io/state.ts`, `utils/machine_prompts.py` |
| `ACE_SUBAGENT_INJECT_FORKS` | unset (forks get no second search) | `1` makes a forked subagent search and inject its own patterns although it inherits the parent's context. | `mod/handlers/agent.ts`, `ace_subagent_start.py` |
| `ACE_SELF_EVAL` | on | `0` skips the Haiku self-review before the learn; the used ids then come from the token evidence only. | `mod/handlers/turn.ts` |
| `ACE_REJECTION_MODEL` | on | `0` turns off the model that classifies a rejecting prompt; only the phrase list can queue a downvote. | `mod/handlers/prompt.ts` |
| `ACE_REJECTION_MIN_CONF` | 0.8 | Minimum model confidence (0..1) to accept a rejection; a value outside 0..1 or not a number falls back to 0.8. | `mod/handlers/prompt.ts`, `mod/lib/rejection.ts` |
| `ACE_VERBOSITY` | `detailed` | Passed as `--verbosity` to `ace-cli learn`. It acts only on the CLI fallback: the engine (`engine/learn.js`) accepts it and ignores it. | `mod/handlers/turn.ts`, `shared-hooks/ace_after_task.py` |
| `ACE_LEARN_INLINE` | unset | FOR TESTS ONLY: any non-empty value runs the learn inline instead of the detached child. Never set it in normal use. | `shared-hooks/ace_after_task.py` `dispatch_learn` |

## Timeout settings

`timeout` values in `hooks.json` are **seconds** (not milliseconds). To adjust, edit `plugins/ace/hooks/hooks.json`:

```json
{
  "UserPromptSubmit": [{
    "hooks": [{
      "timeout": 30
    }]
  }]
}
```

**Defaults (seconds):**

- SessionStart: 30
- UserPromptSubmit: 30 (pattern retrieval)
- PostToolUse domain shift: 20
- SubagentStart: 30
- PreToolUse (Agent prompt stash): 5
- Stop / SubagentStop: async, detached learning

---

