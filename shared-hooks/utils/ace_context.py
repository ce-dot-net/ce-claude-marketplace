#!/usr/bin/env python3
"""ACE Context Resolution - Reads .claude/settings.json for orgId/projectId"""

import json
from pathlib import Path
from typing import Optional, Dict


def get_context() -> Optional[Dict[str, str]]:
    """
    Read orgId and projectId from .claude/settings.json

    Supports two formats:
    1. Direct: {"orgId": "...", "projectId": "..."}
    2. Env wrapper: {"env": {"ACE_ORG_ID": "...", "ACE_PROJECT_ID": "..."}}

    Returns:
        Dict with 'org' and 'project' keys, or None if not found
    """
    settings_file = Path('.claude/settings.json')

    if not settings_file.exists():
        return None

    try:
        settings = json.loads(settings_file.read_text())

        # Try direct format first
        org_id = settings.get('orgId')
        project_id = settings.get('projectId')

        # If not found, try env wrapper format
        if not org_id or not project_id:
            env = settings.get('env', {})
            org_id = env.get('ACE_ORG_ID')
            project_id = env.get('ACE_PROJECT_ID')

        # For single-org mode, orgId is optional but projectId is required
        if not project_id:
            return None

        return {
            'org': org_id,
            'project': project_id
        }

    except (json.JSONDecodeError, IOError):
        return None
