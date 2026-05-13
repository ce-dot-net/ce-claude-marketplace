#!/usr/bin/env python3
"""Item #2 (Phase 1 partial) — ${CLAUDE_PLUGIN_DATA} path resolution + project hash.

Returns the per-project data directory under ${CLAUDE_PLUGIN_DATA}/projects/<id>/.
Project ID resolution order:
    1. Explicit `project_id` argument
    2. $ACE_PROJECT_ID env var
    3. sha1(git_remote_origin + ":" + git_repo_root)[:12]  ← preferred fallback
    4. sha1(realpath(cwd))[:12]  ← last-resort fallback

The full lazy-migration logic (Phase 4) builds on top of this. Phase 1 ships the
helper module without rewiring any callers — callers are migrated in Phase 4 with
backward-compat shim (try new path → fall back to old path).

SDK-team confirmed (Q1): ace-cli does not read/write any of these paths, so the
migration is plugin-internal.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional


def _run_git(args: list[str], cwd: Optional[str] = None) -> str:
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=cwd or os.getcwd(),
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return ""


def _git_remote_origin(cwd: Optional[str] = None) -> str:
    return _run_git(["remote", "get-url", "origin"], cwd=cwd)


def _git_repo_root(cwd: Optional[str] = None) -> str:
    return _run_git(["rev-parse", "--show-toplevel"], cwd=cwd)


def get_project_hash(cwd: Optional[str] = None) -> str:
    """sha1 hex digest, first 12 chars.

    Prefers git remote + repo root (stable across machines, symlinks, worktrees).
    Falls back to realpath(cwd) if not in a git repository.
    """
    remote = _git_remote_origin(cwd)
    root = _git_repo_root(cwd)
    if remote and root:
        raw = f"{remote}:{root}"
    else:
        raw = os.path.realpath(cwd or os.getcwd())
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def get_project_id(cwd: Optional[str] = None) -> str:
    """Resolve project ID via priority chain."""
    pid = os.environ.get("ACE_PROJECT_ID")
    if pid:
        return pid
    return get_project_hash(cwd)


def get_plugin_data_base() -> Path:
    """Base directory for plugin-persistent state.

    Priority:
      1. $CLAUDE_PLUGIN_DATA (set by CC 2.1.78+ when plugin is installed)
      2. $XDG_DATA_HOME/ace
      3. ~/.local/share/ace
    """
    explicit = os.environ.get("CLAUDE_PLUGIN_DATA")
    if explicit:
        return Path(explicit)
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg) / "ace"
    return Path.home() / ".local/share/ace"


def get_project_data_dir(
    project_id: Optional[str] = None,
    cwd: Optional[str] = None,
    create: bool = True,
) -> Path:
    """Returns ${CLAUDE_PLUGIN_DATA}/projects/<id>/ — main per-project data root."""
    pid = project_id or get_project_id(cwd)
    path = get_plugin_data_base() / "projects" / pid
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def get_session_data_dir(
    session_id: str,
    project_id: Optional[str] = None,
    cwd: Optional[str] = None,
    create: bool = True,
) -> Path:
    """Per-session subfolder for ephemeral state (debounce timestamps, etc.)."""
    base = get_project_data_dir(project_id=project_id, cwd=cwd, create=create)
    path = base / "sessions" / session_id
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def write_metadata(project_id: str, cwd: Optional[str] = None, extra: Optional[dict] = None) -> None:
    """Write/update .metadata.json describing this project's data folder."""
    import json
    base = get_project_data_dir(project_id=project_id, cwd=cwd, create=True)
    meta_path = base / ".metadata.json"
    existing: dict = {}
    if meta_path.exists():
        try:
            existing = json.loads(meta_path.read_text())
        except (OSError, json.JSONDecodeError):
            existing = {}
    payload = {
        "ace_project_id": project_id,
        "cwd": os.path.realpath(cwd or os.getcwd()),
        "ace_org_id": os.environ.get("ACE_ORG_ID", ""),
        "first_seen_at": existing.get("first_seen_at") or datetime.utcnow().isoformat() + "Z",
        "last_updated_at": datetime.utcnow().isoformat() + "Z",
    }
    if extra:
        payload.update(extra)
    meta_path.write_text(json.dumps(payload, indent=2))


def lazy_migrate(old_path: Path, new_path: Path) -> bool:
    """Move old_path → new_path if new doesn't exist. Returns True on migration.

    Uses copy2 + unlink (NOT rename) to handle cross-filesystem moves safely
    (Risk Mitigation #2 from architect plan).
    """
    if new_path.exists() or not old_path.exists():
        return False
    new_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        if old_path.is_dir():
            shutil.copytree(old_path, new_path)
            shutil.rmtree(old_path)
        else:
            shutil.copy2(old_path, new_path)
            old_path.unlink()
        return True
    except (OSError, shutil.Error):
        # Best-effort: leave old in place, caller falls back to old path
        return False


def archive_on_id_change(old_project_id: str, new_project_id: str, cwd: Optional[str] = None) -> Optional[Path]:
    """When ACE_PROJECT_ID changes, archive the old folder. Returns archived path."""
    if old_project_id == new_project_id:
        return None
    base = get_plugin_data_base() / "projects"
    old_dir = base / old_project_id
    if not old_dir.exists():
        return None
    archive_name = f"{old_project_id}-archived-{datetime.utcnow().strftime('%Y%m%d')}"
    archive_dir = base / archive_name
    if archive_dir.exists():
        # Suffix with HHMMSS if same-day archive
        archive_name = f"{old_project_id}-archived-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"
        archive_dir = base / archive_name
    old_dir.rename(archive_dir)
    return archive_dir
