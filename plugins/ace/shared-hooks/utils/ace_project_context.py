#!/usr/bin/env python3
"""ACE project binding resolver (plugin 8.1.0).

Contract: ACE SDK clients repo, spec/project-context.md @ 9c049a0 (AOP-1361). Mirror: mod/context/resolve.ts.
Pure: no git spawn, no network, no os.getcwd(). All file access goes through `read(path)`:
  returns the text, None when the path does not exist, raises when it is a directory or unreadable.

Precedence: flag > repo_file (.ace/config.json, walk-up to git root, then the main checkout of a
linked worktree) > settings_file (.claude/settings.json, same walk) > env > remote_map > unbound.

Refusals (spec, both chains, no fallback to lower sources, CLI exit 5):
  - apiToken/serverUrl (or snake_case) in a repo file: {bound: False, reason: 'config_refused', source, path,
    warnings: ['repo_file_contains_secret']}
  - broken/unreadable JSON, a non-object, or a non-string id in repo_file or settings_file:
    {bound: False, reason: 'config_invalid', source, path, message?}
"""

import json
import os
import re

SECRET_KEYS = ('apiToken', 'serverUrl', 'api_token', 'server_url')
_ALIAS_RE = re.compile(r'^(.+\.[a-z]+)-[A-Za-z0-9_-]+$')


def read_file(path):
    """Default reader: text, None if missing; directories and permission errors raise."""
    try:
        with open(path, encoding='utf-8') as f:
            return f.read()
    except (FileNotFoundError, NotADirectoryError):
        return None


class _Refused(Exception):
    def __init__(self, reason, source, path, message=None, warning=None):
        super().__init__(reason)
        self.result = {'bound': False, 'reason': reason, 'source': source, 'path': path}
        if message:
            self.result['message'] = message
        if warning:
            self.result['warnings'] = [warning]


def _exists(read, path):
    try:
        return read(path) is not None
    except Exception:
        return True  # a directory (or unreadable entry) still exists


def _quiet(read, path):
    try:
        return read(path)
    except Exception:
        return None


def _git(cwd, read):
    """(root, main_root, config_path) from files only. root None = not inside a git work tree."""
    d = cwd
    while True:
        dotgit = os.path.join(d, '.git')
        try:
            txt = read(dotgit)
        except Exception:
            return d, None, os.path.join(dotgit, 'config')  # .git directory: plain repo
        if txt is not None:
            m = re.match(r'\s*gitdir:\s*(.+?)\s*$', txt)
            if not m:
                return d, None, None
            gitdir = os.path.normpath(os.path.join(d, m.group(1)))
            common = _quiet(read, os.path.join(gitdir, 'commondir'))
            if common is None:
                return d, None, os.path.join(gitdir, 'config')  # submodule: no main-checkout fallback
            common = os.path.normpath(os.path.join(gitdir, common.strip()))
            return d, os.path.dirname(common), os.path.join(common, 'config')
        parent = os.path.dirname(d)
        if parent == d:
            return None, None, None
        d = parent


def origin_url(config_text):
    section = None
    for line in (config_text or '').splitlines():
        s = line.strip()
        if s.startswith('['):
            section = s
            continue
        if section == '[remote "origin"]':
            m = re.match(r'url\s*=\s*(.+)$', s)
            if m:
                return m.group(1).strip()
    return None


def normalize_remote(url):
    """host/owner/repo per spec 1.3, None when not a recognizable remote."""
    if not url:
        return None
    url = url.strip()
    m = re.match(r'^[A-Za-z][A-Za-z0-9+.-]*://(.*)$', url)
    if m:
        hostpart, _, path = m.group(1).partition('/')
        host = hostpart.rpartition('@')[2]
    else:
        m = re.match(r'^(?:[^@/]+@)?([^:/]+):(.+)$', url)
        if not m:
            return None
        host, path = m.group(1), m.group(2)
    host = host.lower()
    a = _ALIAS_RE.match(host)
    if a:
        host = a.group(1)
    path = path.strip('/')
    if path.endswith('.git'):
        path = path[:-4]
    return f'{host}/{path}' if host and path else None


def _parse_json(text, source, path):
    try:
        data = json.loads(text)
    except ValueError as e:
        raise _Refused('config_invalid', source, path, str(e))
    if not isinstance(data, dict):
        raise _Refused('config_invalid', source, path, 'top level is not an object')
    return data


# strict (production, the default): every id from a file, the env or a remote map must look like org_... / prj_...,
# so an id can never carry path or argv metacharacters (security review 8.1.0). The SDK spec fixtures use ids like
# proj_a, so ONLY the spec conformance runner passes strict=False. ponytail: a module flag, the resolver is single-threaded.
_STRICT = [True]
_ID_RE = {'org': re.compile(r'^org_[A-Za-z0-9_-]+$'), 'prj': re.compile(r'^prj_[A-Za-z0-9_-]+$')}


def _id(value, source, path, kind='prj'):
    if value is None or value == '':
        return None
    if not isinstance(value, str):
        raise _Refused('config_invalid', source, path, 'id is not a string')
    if _STRICT[0] and not _ID_RE[kind].match(value):
        raise _Refused('config_invalid', source, path, 'id must look like %s_...' % kind)
    return value


def _repo_entry(text, path):
    data = _parse_json(text, 'repo_file', path)
    if any(k in data for k in SECRET_KEYS):
        raise _Refused('config_refused', 'repo_file', path,
                       'repo .ace/config.json contains apiToken/serverUrl; remove them',
                       warning='repo_file_contains_secret')
    org = data.get('orgId', data.get('org_id'))
    prj = data.get('projectId', data.get('project_id'))
    return {'source': 'repo_file', 'path': path,
            'org': _id(org, 'repo_file', path, 'org'), 'prj': _id(prj, 'repo_file', path)}


def _settings_entry(text, path):
    data = _parse_json(text, 'settings_file', path)
    env = data.get('env') if isinstance(data.get('env'), dict) else {}
    return {'source': 'settings_file', 'path': path,
            'org': _id(env.get('ACE_ORG_ID'), 'settings_file', path, 'org'),
            'prj': _id(env.get('ACE_PROJECT_ID'), 'settings_file', path)}


def _search(source, rel, dirs, main_root, home, read, tried, parse, warnings, lenient):
    """Spec 1.1/7: first existing file in the walk ends it; main checkout only if no projectId yet.
    lenient (projectId already decided: a --project flag or a higher source): a refused/invalid file contributes
    nothing and only warns (spec 9500190)."""
    found = []

    def probe(path):
        tried.append({'source': source, 'path': path, 'key': None})
        try:
            try:
                text = read(path)
            except Exception as e:
                raise _Refused('config_invalid', source, path, f'{type(e).__name__}: {e}')
            if text is None:
                return False
            found.append(parse(text, path))
        except _Refused as r:
            if not lenient:
                raise
            w = 'repo_file_contains_secret' if r.result['reason'] == 'config_refused' else 'config_invalid'
            if w not in warnings:
                warnings.append(w)
            found.append({'source': source, 'path': path, 'org': None, 'prj': None})
        return True

    for d in dirs:
        if probe(os.path.join(d, rel)):
            break
    if main_root and main_root != home and not (found and found[0]['prj']):
        probe(os.path.join(main_root, rel))
    return found


def resolve(cwd, env, flags=None, remote_map=None, organizations=None, read=read_file,
            default_org_id=None, global_project_id=None, realpath=None, strict=True):
    """Resolve {orgId, projectId} for an absolute `cwd`. Never falls back to a default project.

    remote_map: global config `projects` ({normalized remote: {orgId?, projectId}}).
    organizations: global config auth.organizations ([{org_id}]); None skips the membership check.
    default_org_id / global_project_id: global config keys (the latter is never used, only warned about).
    """
    _STRICT[0] = strict
    try:
        return _resolve(os.path.normpath(cwd), env or {}, flags or {}, remote_map or {}, organizations,
                        read, default_org_id, global_project_id, realpath or os.path.realpath)
    except _Refused as r:
        return r.result  # spec 9500190: only its own warning
    finally:
        _STRICT[0] = True


def _resolve(cwd, env, flags, remote_map, organizations, read, default_org_id, global_project_id, realpath):
    warnings = ['global_project_id_ignored'] if isinstance(global_project_id, str) and global_project_id else []
    # spec 9500190: HOME is compared by realpath on both sides, the OS home when unset; reported paths stay unresolved
    home_real = realpath(os.path.normpath(env.get('HOME') or os.path.expanduser('~')))

    def is_home(d):
        return d is not None and realpath(d) == home_real
    home = None
    root, main_root, git_config = _git(cwd, read)

    dirs = []
    d = cwd
    while True:
        if not is_home(d):
            dirs.append(d)
        if root is None or d == root:
            break
        d = os.path.dirname(d)

    tried = []
    entries = [{'source': 'flag', 'path': None, 'org': flags.get('org') or None, 'prj': flags.get('project') or None}]
    if is_home(main_root):
        main_root = None
    entries += _search('repo_file', os.path.join('.ace', 'config.json'), dirs, main_root, home, read, tried,
                       _repo_entry, warnings, any(e['prj'] for e in entries))
    entries += _search('settings_file', os.path.join('.claude', 'settings.json'), dirs, main_root, home, read,
                       tried, _settings_entry, warnings, any(e['prj'] for e in entries))
    def soft(v, kind):  # a malformed env / remote-map id is dropped with a warning (never blocks a file binding)
        try:
            return _id(v, 'env', None, kind)
        except _Refused:
            if 'invalid_id_ignored' not in warnings:
                warnings.append('invalid_id_ignored')
            return None
    entries.append({'source': 'env', 'path': None, 'org': soft(env.get('ACE_ORG_ID'), 'org'), 'prj': soft(env.get('ACE_PROJECT_ID'), 'prj')})
    tried.append({'source': 'env', 'path': None, 'key': None})
    key = normalize_remote(origin_url(_quiet(read, git_config))) if git_config else None
    hit = remote_map.get(key) if key else None
    if isinstance(hit, dict):
        entries.append({'source': 'remote_map', 'path': None,
                        'org': soft(hit.get('orgId'), 'org'), 'prj': soft(hit.get('projectId'), 'prj')})
    tried.append({'source': 'remote_map', 'path': None, 'key': key})

    def done(r):
        if warnings:
            r['warnings'] = warnings + r.get('warnings', [])
        return r

    win = next((e for e in entries if e['prj']), None)
    if win is None:
        return done({'bound': False, 'reason': 'no_binding', 'tried': tried})

    # Spec 1.4: --org > winner's org > first org in order > default_org_id. org_from = where the org came from.
    org_from = None
    if entries[0]['org']:
        org = entries[0]['org']
    elif win['org']:
        org, org_from = win['org'], win
    else:
        org_from = next((e for e in entries if e['org']), None)
        org = org_from['org'] if org_from else default_org_id
    if not org:
        return done({'bound': False, 'reason': 'no_org', 'projectId': win['prj'],
                     'source': win['source'], 'path': win['path']})

    if (org_from and org_from['source'] in ('repo_file', 'settings_file', 'remote_map')
            and organizations is not None
            and org not in {o.get('org_id') for o in organizations if isinstance(o, dict)}):
        return done({'bound': False, 'reason': 'org_not_member', 'orgId': org,
                     'source': org_from['source'], 'path': org_from['path'], 'warnings': ['org_not_member']})

    return done({'bound': True, 'orgId': org, 'projectId': win['prj'], 'source': win['source'], 'path': win['path']})


# ═══════════════════════════════════════════════════════════════════════════
# The one core for the Python chain (8.1.0). Every hook, scripts/ace-context and the markdown commands go
# through context()/get_context(); nothing else reads settings.json or ACE_* binding env. Mirror: mod/context/.
# ═══════════════════════════════════════════════════════════════════════════
import subprocess
import sys
import time

CONTEXT_ENV = 'ACE_CONTEXT'   # the mod's export: {"root","source","path","orgId","projectId","at"} (ms epoch)
MOD_FRESH_S = 900             # the mod re-exports at every marker refresh (60 s); older = the mod is gone
FILE_SOURCES = ('repo_file', 'settings_file')
ADOPT_SOURCES = ('settings_file', 'remote_map')
PROBLEM_STATES = ('unbound', 'not_logged_in', 'expired', 'project_not_found', 'no_access', 'server_error',
                  'cli_missing', 'config_refused', 'config_invalid')
ADOPT_LINE = ('ACE: Bindung als .ace/config.json gespeichert. Bitte committen, dann gilt sie in jedem Clone '
              'und auf jeder Maschine.')
# One line per problem state; the mod shows the same words (mod/context/lines.ts, parity-tested).
LINES = {
    'unbound': 'ACE ▼ Repo nicht verbunden: /ace:ace-configure',
    'not_logged_in': 'ACE ▼ nicht angemeldet: /ace:ace-login',
    'expired': 'ACE ▼ Anmeldung abgelaufen: /ace:ace-login',
    'project_not_found': 'ACE ▼ Projekt nicht gefunden: /ace:ace-configure',
    'no_access': 'ACE ▼ kein Zugriff auf das Projekt: /ace:ace-configure',
    'server_error': 'ACE ▼ Server nicht erreichbar',
    'cli_missing': 'ACE ▼ ace-cli fehlt: /ace:ace-install-cli',
    'config_refused': 'ACE ▼ .ace/config.json enthält apiToken/serverUrl und wird ignoriert: /ace:ace-configure',
    'config_invalid': 'ACE ▼ Bindungsdatei ist kein gültiges JSON: /ace:ace-doctor',
}


def _env_map(env):
    return dict(os.environ if env is None else env)


def global_config_path(env=None):
    env = _env_map(env)
    if env.get('ACE_CONFIG_PATH'):
        return env['ACE_CONFIG_PATH']
    base = env.get('XDG_CONFIG_HOME') or os.path.join(env.get('HOME') or os.path.expanduser('~'), '.config')
    return os.path.join(base, 'ace', 'config.json')


def load_global(env=None):
    """The ace-cli global config, read-only. {} when missing or broken (the CLI reports that itself)."""
    try:
        with open(global_config_path(env), encoding='utf-8') as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _data_root():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import plugin_data_dir
    return plugin_data_dir.data_root()


def machine_map_path():
    return os.path.join(str(_data_root()), 'remote-map.json')


def load_machine_map():
    try:
        with open(machine_map_path(), encoding='utf-8') as f:
            d = json.load(f)
        return {k: v for k, v in d.items() if isinstance(v, dict)} if isinstance(d, dict) else {}
    except Exception:
        return {}


def repo_roots(cwd, read=read_file):
    """(git root or None, main checkout root or None) from files only."""
    root, main_root, _ = _git(os.path.normpath(cwd), read)
    return root, main_root


def log_root(cwd=None):
    """Where logs and per-repo state live: the main checkout of a worktree, else the git root, else cwd."""
    cwd = os.path.abspath(cwd or os.getcwd())
    root, main_root = repo_roots(cwd)
    return main_root or root or cwd


def logs_dir(cwd=None):
    return os.path.join(log_root(cwd), '.claude', 'data', 'logs')


def remote_key(cwd, read=read_file):
    _, _, cfg = _git(os.path.normpath(cwd), read)
    return normalize_remote(origin_url(_quiet(read, cfg))) if cfg else None


def _mod_export(env):
    try:
        m = json.loads(env.get(CONTEXT_ENV) or '')
        return m if isinstance(m, dict) else None
    except ValueError:
        return None


_CACHE = {}


def context(cwd=None, env=None, flags=None, now=None):
    """The resolver result for `cwd` plus `root` (log root) and `via` ('mod' | 'resolver').

    A fresh mod export for the same root is taken as is. A stale or foreign one never leaks: its ACE_ORG_ID /
    ACE_PROJECT_ID (the mod's own values) are dropped before the resolver sees the env."""
    env = _env_map(env)
    cwd = os.path.abspath(cwd or os.getcwd())
    root = log_root(cwd)
    key = (cwd, json.dumps(flags or {}, sort_keys=True),
           tuple(env.get(k) for k in (CONTEXT_ENV, 'ACE_ORG_ID', 'ACE_PROJECT_ID', 'ACE_CONFIG_PATH', 'HOME')))
    if now is None and key in _CACHE:
        return dict(_CACHE[key])
    t = time.time() if now is None else now
    m = _mod_export(env)
    if m and not flags and m.get('root') == root and m.get('projectId') and m.get('projectId') == env.get('ACE_PROJECT_ID') \
            and isinstance(m.get('at'), (int, float)) and t - m['at'] / 1000.0 < MOD_FRESH_S:
        r = {'bound': True, 'orgId': m.get('orgId'), 'projectId': m['projectId'], 'source': m.get('source'),
             'path': m.get('path'), 'root': root, 'via': 'mod'}
    else:
        if m and env.get('ACE_PROJECT_ID') == m.get('projectId'):
            env.pop('ACE_PROJECT_ID', None)
            if env.get('ACE_ORG_ID') == m.get('orgId'):
                env.pop('ACE_ORG_ID', None)
        gc = load_global(env)
        remote = dict(load_machine_map())
        if isinstance(gc.get('projects'), dict):
            remote.update(gc['projects'])  # the CLI's own map wins over ours
        auth = gc.get('auth') if isinstance(gc.get('auth'), dict) else {}
        orgs = auth.get('organizations') if isinstance(auth.get('organizations'), list) else None
        r = resolve(cwd, env, flags=flags, remote_map=remote, organizations=orgs,
                    default_org_id=gc.get('default_org_id') or gc.get('defaultOrgId'),
                    global_project_id=gc.get('projectId'))
        r['root'] = root
        r['via'] = 'resolver'
    if now is None:
        _CACHE[key] = dict(r)
    return r


def get_context(base_dir=None):
    """{'org', 'project', 'source', 'path', 'root'} when bound, else None. The hooks' only binding lookup."""
    r = context(base_dir)
    if not r.get('bound'):
        return None
    return {'org': r['orgId'], 'project': r['projectId'], 'source': r['source'], 'path': r['path'], 'root': r['root']}


def local_state(r):
    """State without the network: None when bound (verify decides), else the problem state."""
    if r.get('bound'):
        return None
    return {'config_refused': 'config_refused', 'config_invalid': 'config_invalid'}.get(r.get('reason'), 'unbound')


def cli_ids(r):
    """--org/--project for every CLI spawn: the CLI must never pick its own binding (4.3.4 reads settings.json)."""
    out = []
    if r and r.get('orgId'):
        out += ['--org', r['orgId']]
    if r and r.get('projectId'):
        out += ['--project', r['projectId']]
    return out


_HTTP = re.compile(r'Server error \((\d{3})\)')
_CODES = {3: 'not_logged_in', 4: 'expired', 5: 'unbound', 6: 'project_not_found', 7: 'no_access',
          8: 'server_error', 9: 'not_logged_in'}
_NAMES = {'not_logged_in': 'not_logged_in', 'token_expired': 'expired', 'unbound': 'unbound',
          'project_not_found': 'project_not_found', 'no_access': 'no_access', 'server_error': 'server_error',
          'device_limit_exceeded': 'not_logged_in'}


def classify(exit_code, stderr, spawn_error=False, timeout=False):
    """ace-cli exit code + stderr -> state. stdout is never read (pattern text may say anything)."""
    if spawn_error:
        return 'cli_missing'
    if timeout:
        return 'server_error'
    if exit_code == 0:
        return 'ok'
    err = stderr or ''
    if exit_code in _CODES:
        return _CODES[exit_code]
    for line in err.splitlines():  # the new CLI: {"error":{"code","status","message"}}
        try:
            e = json.loads(line)
        except ValueError:
            continue
        code = e.get('error', {}).get('code') if isinstance(e, dict) and isinstance(e.get('error'), dict) else None
        if code in _NAMES:
            return _NAMES[code]
    if re.search(r'Cannot find module|MODULE_NOT_FOUND|ace-cli not found', err):
        return 'cli_missing'
    if re.search(r'No API token found|Please login first|Not logged in|not_logged_in', err, re.I):
        return 'not_logged_in'
    m = _HTTP.search(err)
    code = int(m.group(1)) if m else 0
    return {401: 'expired', 403: 'no_access', 404: 'project_not_found'}.get(code, 'server_error')


def verify(r, timeout=20):
    """One `status --json` with explicit --org/--project -> state (or the local state when not bound)."""
    st = local_state(r)
    if st:
        return st
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import ace_cli
    try:
        argv = ace_cli._cmd('status', '--json', *cli_ids(r))
    except FileNotFoundError:
        return 'cli_missing'
    env = dict(os.environ)
    env['ACE_ORG_ID'], env['ACE_PROJECT_ID'] = r['orgId'], r['projectId']
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, env=env, cwd=r.get('root') or None)
    except FileNotFoundError:
        return 'cli_missing'
    except subprocess.TimeoutExpired:
        return 'server_error'
    return classify(p.returncode, p.stderr)


def remember(r, cwd, now=None):
    """Per-machine remote map: a file-bound repo teaches its origin, so a fresh clone binds by itself."""
    if not r.get('bound') or r.get('source') not in FILE_SOURCES:
        return False
    key = remote_key(cwd)
    if not key:
        return False
    m = load_machine_map()
    entry = {'orgId': r['orgId'], 'projectId': r['projectId']}
    if {k: m.get(key, {}).get(k) for k in entry} == entry:
        return False
    m[key] = dict(entry, at=int(time.time() if now is None else now))
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import plugin_data_dir
    plugin_data_dir.private_write(machine_map_path(), json.dumps(m, indent=2, sort_keys=True) + '\n')
    return True


def fix_gitignore(text):
    """(new text, changed): a bare `.ace/` rule becomes `.ace/*` (a dir rule blocks the negation), then
    `!.ace/config.json` is added. Same semantics as `ace-cli init --fix-gitignore`."""
    lines = (text or '').splitlines()
    out, changed = [], False
    for line in lines:
        s = line.strip()
        if s in ('.ace', '.ace/', '/.ace', '/.ace/', '.ace/**', '/.ace/**'):
            new = ('/' if s.startswith('/') else '') + '.ace/*'
            changed |= new != line
            out.append(new)
        else:
            out.append(line)
    if not any(l.strip() in ('!.ace/config.json', '!/.ace/config.json') for l in out):
        if not any(l.strip() in ('.ace/*', '/.ace/*') for l in out):
            out.append('.ace/*')
        out.append('!.ace/config.json')
        changed = True
    return ('\n'.join(out) + '\n') if changed else (text or ''), changed


def _git_rc(root, *args):
    try:
        return subprocess.run(['git', '-C', root, *args], capture_output=True, text=True, timeout=5).returncode
    except Exception:
        return -1


def ignored(main):
    return _git_rc(main, 'check-ignore', '-q', '.ace/config.json') == 0


def untracked(main):
    return _git_rc(main, 'ls-files', '--error-unmatch', '.ace/config.json') != 0


class WriteRefused(Exception):
    """A repo write that could leave the main checkout (symlinked component, path outside it)."""


def safe_repo_write(main, rel, text, mode=0o644):
    """Write <main>/<rel> atomically without ever following a symlink out of the repo (security review 8.1.0):
    every component below main must be a real directory/file (no symlink), realpath(dir) must stay under
    realpath(main), the temp file is O_CREAT|O_EXCL|O_NOFOLLOW with a random name, then os.replace."""
    import secrets
    main = os.path.abspath(main)
    parts = [p for p in rel.split('/') if p]
    if not parts or any(p in ('.', '..') for p in parts):
        raise WriteRefused('bad relative path: %s' % rel)
    cur = main
    for p in parts:
        cur = os.path.join(cur, p)
        if os.path.islink(cur):
            raise WriteRefused('symlink: %s' % cur)
    d = os.path.dirname(os.path.join(main, *parts))
    os.makedirs(d, exist_ok=True)
    if os.path.islink(d):
        raise WriteRefused('symlink: %s' % d)
    real_main = os.path.realpath(main)
    if os.path.commonpath([os.path.realpath(d), real_main]) != real_main:
        raise WriteRefused('outside the main checkout: %s' % d)
    target = os.path.join(d, parts[-1])
    tmp = os.path.join(d, '.ace-w-%s.tmp' % secrets.token_hex(8))
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), mode)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(text)
        if os.path.islink(target):
            raise WriteRefused('symlink: %s' % target)
        os.replace(tmp, target)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return target


def _log_refused(main, what, reason):
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from ace_relevance_logger import ACERelevanceLogger
        from datetime import datetime, timezone
        d = os.path.join(main, '.claude', 'data', 'logs')
        lg = ACERelevanceLogger(d)
        lg.base = main
        lg._write_log({'timestamp': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
                       'event': 'write_refused', 'what': what, 'reason': reason, 'chain': 'python'})
    except Exception:
        pass


def write_binding(main, org, project):
    """Write <main>/.ace/config.json {orgId, projectId} (never anything else) and un-ignore it. Raises WriteRefused."""
    if not (ORG_ID.match(org or '') and PRJ_ID.match(project or '')):
        raise ValueError('ids must look like org_... / prj_...')
    try:
        path = safe_repo_write(main, '.ace/config.json', json.dumps({'orgId': org, 'projectId': project}, indent=2) + '\n')
    except WriteRefused as e:
        _log_refused(main, '.ace/config.json', str(e))
        raise
    gi = 'ok'
    gpath = os.path.join(main, '.gitignore')
    if os.path.islink(gpath):  # never read or rewrite through it (git itself does not follow it either)
        _log_refused(main, '.gitignore', 'symlink: %s' % gpath)
        return {'path': path, 'gitignore': 'refused'}
    if ignored(main):
        new, changed = fix_gitignore(read_file(gpath) or '')
        if changed:
            try:
                safe_repo_write(main, '.gitignore', new)
            except WriteRefused as e:
                _log_refused(main, '.gitignore', str(e))
                return {'path': path, 'gitignore': 'refused'}
        gi = 'still_ignored' if ignored(main) else 'fixed'
    return {'path': path, 'gitignore': gi}


ORG_ID = re.compile(r'^org_[A-Za-z0-9_-]+$')
PRJ_ID = re.compile(r'^prj_[A-Za-z0-9_-]+$')


def adopt(r, cwd, env=None):
    """Automatic adoption: a legacy settings_file or remote_map binding becomes a tracked .ace/config.json in the
    main checkout. Only in git, only if the file is missing, never for flag/env, opt-out ACE_AUTO_ADOPT=0."""
    env = _env_map(env)
    if env.get('ACE_AUTO_ADOPT') == '0' or not r.get('bound') or r.get('source') not in ADOPT_SOURCES:
        return None
    root, main_root = repo_roots(os.path.abspath(cwd))
    main = main_root or root
    if not main or os.path.exists(os.path.join(main, '.ace', 'config.json')):
        return None
    try:
        return write_binding(main, r['orgId'], r['projectId'])
    except (OSError, ValueError, WriteRefused):
        return None


def context_row(r, state, hook, now_iso=None, sid=None):
    from datetime import datetime, timezone
    row = {'timestamp': now_iso or datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
           'event': 'context', 'hook': hook, 'session_id': sid, 'state': state, 'source': r.get('source'), 'path': r.get('path'),
           'reason': None if r.get('bound') else r.get('reason'), 'org_id': r.get('orgId'),
           'project_id': r.get('projectId'), 'root': r.get('root'), 'via': r.get('via'), 'chain': 'python'}
    if r.get('warnings'):
        row['warnings'] = r['warnings']
    return row


def log_context(r, state, hook='UserPromptSubmit', sid=None):
    """One `context` row in <log root>/.claude/data/logs. An unbound unrelated repo gets no new log dir."""
    d = os.path.join(r.get('root') or log_root(), '.claude', 'data', 'logs')
    if state == 'unbound' and not os.path.isdir(d):
        return False
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from ace_relevance_logger import ACERelevanceLogger
    ACERelevanceLogger(d)._write_log(context_row(r, state, hook, sid=sid))
    return True


def _state_path(sid, project):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import plugin_data_dir
    return plugin_data_dir.session_dir(project, sid) / 'context.json'


def _load(p):
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def _save(p, d):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import plugin_data_dir
    plugin_data_dir.private_write(p, json.dumps(d))


def session_notice(sid, cwd=None, env=None, spawn_verify=True, bound=None):
    """The Python chain's once-per-session context step (first UserPromptSubmit while the mod is not running):
    resolve, remember, adopt, log once, verify in the background; returns at most one line to show, once.
    bound: the hook's own get_context() result, when it has one (one lookup per hook)."""
    cwd = os.path.abspath(cwd or os.getcwd())
    e = _env_map(env)
    m = _mod_export(e)
    if m and m.get('bound') is False and m.get('root') == log_root(cwd) and isinstance(m.get('at'), (int, float)) \
            and time.time() - m['at'] / 1000.0 < MOD_FRESH_S:
        return None  # the mod resolved this root unbound: its band and its one context row, not ours
    r = context(cwd, env)
    if bound and not r.get('bound'):
        r = {'bound': True, 'orgId': bound.get('org'), 'projectId': bound.get('project'), 'source': bound.get('source'),
             'path': bound.get('path'), 'root': bound.get('root') or r.get('root'), 'via': 'hook'}
    p = _state_path(sid, r.get('projectId'))
    st = _load(p)
    if st is None:
        st = {'state': local_state(r), 'shown': False, 'adopted': None, 'adopt_shown': False}
        remember(r, cwd)
        a = adopt(r, cwd, env)
        if a:
            st['adopted'] = a['path']
        _save(p, st)
        if st['state']:
            log_context(r, st['state'], sid=sid)
        elif spawn_verify:
            try:
                subprocess.Popen([sys.executable, os.path.abspath(__file__), '--verify-session', sid, '--cwd', cwd],
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 start_new_session=True)
            except OSError:
                pass
    line = None
    if st.get('state') in PROBLEM_STATES and not st.get('shown'):
        line, st['shown'] = LINES[st['state']], True
    elif st.get('adopted') and not st.get('adopt_shown') and untracked(os.path.dirname(os.path.dirname(st['adopted']))):
        line, st['adopt_shown'] = ADOPT_LINE, True
    if line:
        _save(p, st)
    return line


def verify_session(sid, cwd):
    """The detached half of session_notice: status once, the state for the next prompt, the one log row."""
    r = context(cwd)
    p = _state_path(sid, r.get('projectId'))
    st = _load(p) or {'shown': False, 'adopted': None, 'adopt_shown': False}
    st['state'] = None if (s := verify(r)) == 'ok' else s
    _save(p, st)
    log_context(r, s, sid=sid)
    return s


def _shell(r):
    import shlex
    if not r.get('bound'):
        return ''
    return ''.join('export %s=%s\n' % (k, shlex.quote(str(v or ''))) for k, v in (
        ('ACE_ORG_ID', r['orgId']), ('ACE_PROJECT_ID', r['projectId']), ('ACE_CONTEXT_SOURCE', r['source']),
        ('ACE_CONTEXT_ROOT', r['root'])))


def _bind_cli(cwd, org, prj, yes):
    root, main_root = repo_roots(cwd)
    main = main_root or root
    if not main:
        print('Not a git repo: there is no tracked file to write. Set ACE_ORG_ID / ACE_PROJECT_ID in the env instead.')
        return 1
    if not (ORG_ID.match(org) and PRJ_ID.match(prj)):
        print('ids must look like org_... / prj_...')
        return 1
    path = os.path.join(main, '.ace', 'config.json')
    if not yes:
        print('Would write %s:\n%s' % (path, json.dumps({'orgId': org, 'projectId': prj}, indent=2)))
        if ignored(main):
            before = read_file(os.path.join(main, '.gitignore')) or ''
            after, _ = fix_gitignore(before)
            b, n = set(before.splitlines()), set(after.splitlines())
            print('.gitignore ignores it; this change makes it trackable:')
            print('\n'.join(['- ' + l for l in before.splitlines() if l and l not in n] + ['+ ' + l for l in after.splitlines() if l and l not in b]))
        print('Nothing written. Re-run with --yes after the user confirmed.')
        return 0
    try:
        r = write_binding(main, org, prj)
    except WriteRefused as e:
        print('Refused: %s' % e)
        return 1
    print('Wrote %s (gitignore: %s). Nothing staged or committed: commit it to bind every clone.' % (r['path'], r['gitignore']))
    return 0


def main(argv=None):
    """scripts/ace-context: the markdown commands' only binding lookup.
      ace-context [--cwd DIR] [--json]   the result as JSON (exit 0 bound, 5 not)
      ace-context --shell                export lines for eval (nothing printed when not bound; exit 5)
      ace-context --verify               plus `state` from one status call
      ace-context --line                 the one problem line, empty when ok
      ace-context --logs                 <log root>/.claude/data/logs (main checkout of a worktree, git root, else cwd)
      ace-context --bind ORG PRJ [--yes] the tracked <main checkout>/.ace/config.json: a preview (with the .gitignore
                                         diff when the file is ignored); written only with --yes. Never settings.json.
    """
    import argparse
    ap = argparse.ArgumentParser(prog='ace-context')
    ap.add_argument('--cwd')
    ap.add_argument('--org')
    ap.add_argument('--project')
    g = ap.add_mutually_exclusive_group()
    g.add_argument('--json', action='store_true')
    g.add_argument('--shell', action='store_true')
    g.add_argument('--line', action='store_true')
    g.add_argument('--logs', action='store_true')
    ap.add_argument('--verify', action='store_true')
    ap.add_argument('--verify-session')
    ap.add_argument('--bind', nargs=2, metavar=('ORG', 'PRJ'))
    ap.add_argument('--yes', action='store_true')
    a = ap.parse_args(argv)
    cwd = os.path.abspath(a.cwd or os.getcwd())
    if a.bind:
        return _bind_cli(cwd, a.bind[0], a.bind[1], a.yes)
    if a.logs:  # the repo root's log dir (worktrees and subfolders share it)
        print(logs_dir(cwd))
        return 0
    if a.verify_session:
        verify_session(a.verify_session, cwd)
        return 0
    flags = {k: v for k, v in (('org', a.org), ('project', a.project)) if v} or None
    r = context(cwd, flags=flags)
    if a.verify or a.line:
        r['state'] = verify(r)
    else:
        r['state'] = local_state(r) or 'bound'
    if a.shell:
        sys.stdout.write(_shell(r))
        if not r.get('bound'):
            sys.stderr.write(LINES[r['state']] + '\n')
    elif a.line:
        if r['state'] in LINES:
            print(LINES[r['state']])
    else:
        print(json.dumps(r, indent=2))
    return 0 if r.get('bound') else 5


if __name__ == '__main__':
    sys.exit(main())
