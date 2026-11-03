#!/usr/bin/env python3
"""ACE project binding resolver (plugin 8.1.0).

Contract: ACE SDK clients repo, spec/project-context.md @ b42a020 (AOP-1361). Mirror: mod/context/resolve.ts.
Pure: no git spawn, no network, no os.getcwd(). All file access goes through `read(path)`:
  returns the text, None when the path does not exist, raises when it is a directory or unreadable.

Precedence: flag > repo_file (.ace/config.json, walk-up to git root, then the main checkout of a
linked worktree) > settings_file (.claude/settings.json, same walk) > env > remote_map > unbound.

Beyond the spec, `strict=True` (the default, what the hooks use):
  - a repo file with apiToken/serverUrl (or snake_case) is refused instead of warned about,
  - ids must match ^org_ / ^prj_.
  The spec fixtures use ids like proj_a and expect a warning for secrets, so the conformance runner passes strict=False.
Bad JSON and unreadable config files are refused in both modes. Result shapes: spec 1.5, plus
  {bound: False, reason: 'config_refused', detail, source, path, message?}.
"""

import json
import os
import re

SECRET_KEYS = ('apiToken', 'serverUrl', 'api_token', 'server_url')
ORG_RE = re.compile(r'^org_[A-Za-z0-9_-]+$')
PRJ_RE = re.compile(r'^prj_[A-Za-z0-9_-]+$')
_ALIAS_RE = re.compile(r'^(.+\.[a-z]+)-[A-Za-z0-9_-]+$')


def read_file(path):
    """Default reader: text, None if missing; directories and permission errors raise."""
    try:
        with open(path, encoding='utf-8') as f:
            return f.read()
    except (FileNotFoundError, NotADirectoryError):
        return None


class _Refused(Exception):
    def __init__(self, detail, source, path, message=None):
        super().__init__(detail)
        self.result = {'bound': False, 'reason': 'config_refused', 'detail': detail, 'source': source, 'path': path}
        if message:
            self.result['message'] = message


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
        raise _Refused('invalid_json', source, path, str(e))
    if not isinstance(data, dict):
        raise _Refused('invalid_json', source, path, 'top level is not an object')
    return data


def _id(value, source, path):
    if value is None or value == '':
        return None
    if not isinstance(value, str):
        raise _Refused('invalid_id', source, path, 'id is not a string')
    return value


def _repo_entry(text, path, strict, warnings):
    data = _parse_json(text, 'repo_file', path)
    if any(k in data for k in SECRET_KEYS):
        if strict:
            raise _Refused('repo_file_contains_secret', 'repo_file', path,
                           'repo .ace/config.json contains apiToken/serverUrl; remove them')
        if 'repo_file_contains_secret' not in warnings:
            warnings.append('repo_file_contains_secret')
    org = data.get('orgId', data.get('org_id'))
    prj = data.get('projectId', data.get('project_id'))
    return {'source': 'repo_file', 'path': path,
            'org': _id(org, 'repo_file', path), 'prj': _id(prj, 'repo_file', path)}


def _settings_entry(text, path, strict, warnings):
    data = _parse_json(text, 'settings_file', path)
    env = data.get('env') if isinstance(data.get('env'), dict) else {}
    return {'source': 'settings_file', 'path': path,
            'org': _id(env.get('ACE_ORG_ID'), 'settings_file', path),
            'prj': _id(env.get('ACE_PROJECT_ID'), 'settings_file', path)}


def _search(source, rel, dirs, main_root, home, read, tried, parse, strict, warnings):
    """Spec 1.1/7: first existing file in the walk ends it; main checkout only if no projectId yet."""
    found = []
    for d in dirs:
        path = os.path.join(d, rel)
        tried.append({'source': source, 'path': path, 'key': None})
        try:
            text = read(path)
        except Exception as e:
            raise _Refused('unreadable', source, path, f'{type(e).__name__}: {e}')
        if text is not None:
            found.append(parse(text, path, strict, warnings))
            break
    if main_root and main_root != home and not (found and found[0]['prj']):
        path = os.path.join(main_root, rel)
        tried.append({'source': source, 'path': path, 'key': None})
        try:
            text = read(path)
        except Exception as e:
            raise _Refused('unreadable', source, path, f'{type(e).__name__}: {e}')
        if text is not None:
            found.append(parse(text, path, strict, warnings))
    return found


def resolve(cwd, env, flags=None, remote_map=None, organizations=None, read=read_file,
            default_org_id=None, global_project_id=None, strict=True):
    """Resolve {orgId, projectId} for an absolute `cwd`. Never falls back to a default project.

    remote_map: global config `projects` ({normalized remote: {orgId?, projectId}}).
    organizations: global config auth.organizations ([{org_id}]); None skips the membership check.
    default_org_id / global_project_id: global config keys (the latter is never used, only warned about).
    """
    try:
        return _resolve(os.path.normpath(cwd), env or {}, flags or {}, remote_map or {}, organizations,
                        read, default_org_id, global_project_id, strict)
    except _Refused as r:
        return r.result


def _resolve(cwd, env, flags, remote_map, organizations, read, default_org_id, global_project_id, strict):
    warnings = ['global_project_id_ignored'] if global_project_id else []
    home = os.path.normpath(env['HOME']) if env.get('HOME') else None
    root, main_root, git_config = _git(cwd, read)

    dirs = []
    d = cwd
    while True:
        if d != home:
            dirs.append(d)
        if root is None or d == root:
            break
        d = os.path.dirname(d)

    tried = []
    entries = [{'source': 'flag', 'path': None, 'org': flags.get('org') or None, 'prj': flags.get('project') or None}]
    entries += _search('repo_file', os.path.join('.ace', 'config.json'), dirs, main_root, home, read, tried,
                       _repo_entry, strict, warnings)
    entries += _search('settings_file', os.path.join('.claude', 'settings.json'), dirs, main_root, home, read,
                       tried, _settings_entry, strict, warnings)
    entries.append({'source': 'env', 'path': None,
                    'org': env.get('ACE_ORG_ID') or None, 'prj': env.get('ACE_PROJECT_ID') or None})
    tried.append({'source': 'env', 'path': None, 'key': None})
    key = normalize_remote(origin_url(_quiet(read, git_config))) if git_config else None
    hit = remote_map.get(key) if key else None
    if isinstance(hit, dict):
        entries.append({'source': 'remote_map', 'path': None,
                        'org': hit.get('orgId') or None, 'prj': hit.get('projectId') or None})
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

    if strict and not (isinstance(org, str) and ORG_RE.match(org) and PRJ_RE.match(win['prj'])):
        bad = org_from if (org_from and not ORG_RE.match(str(org))) else win
        return done({'bound': False, 'reason': 'config_refused', 'detail': 'invalid_id',
                     'orgId': org, 'projectId': win['prj'], 'source': bad['source'], 'path': bad['path'],
                     'message': 'ids must look like org_... / prj_...'})

    if (org_from and org_from['source'] in ('repo_file', 'settings_file', 'remote_map')
            and organizations is not None
            and org not in {o.get('org_id') for o in organizations if isinstance(o, dict)}):
        return done({'bound': False, 'reason': 'org_not_member', 'orgId': org,
                     'source': org_from['source'], 'path': org_from['path'], 'warnings': ['org_not_member']})

    return done({'bound': True, 'orgId': org, 'projectId': win['prj'], 'source': win['source'], 'path': win['path']})
