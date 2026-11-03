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

