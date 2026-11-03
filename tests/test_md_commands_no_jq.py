"""8.1.0 review: no markdown command may need jq (ace-configure exited 1 without it, ace-doctor read the global
config through it). JSON fields come from `scripts/ace-context --get/--rows` (the plugin's Python core) instead."""
import json
import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
CMDS = sorted((REPO / 'plugins/ace/commands').glob('*.md'))
CTX = str(REPO / 'plugins/ace/scripts/ace-context')


@pytest.mark.parametrize('md', CMDS, ids=[p.name for p in CMDS])
def test_no_md_command_requires_jq(md):
    """jq only behind a `command -v jq` guard with a fallback; none of ours needs it at all, so: no jq anywhere."""
    hits = [f'{i}: {l.strip()}' for i, l in enumerate(md.read_text().splitlines(), 1) if re.search(r'\bjq\b', l)]
    assert not hits, f'{md.name} uses jq:\n' + '\n'.join(hits)


def get(doc, *args, stdin=None):
    p = subprocess.run([CTX, *args], input=stdin if stdin is not None else json.dumps(doc), capture_output=True, text=True)
    return p.returncode, p.stdout


def test_get_fields_defaults_lengths_and_exit_codes():
    d = {'authenticated': True, 'count': 0, 'user': {'email': 'a@b', 'organizations': [1, 2]},
         'organizations': [{'org_id': 'org_1', 'org_name': 'One', 'role': 'owner'}], 'apiToken': None}
    assert get(d, '--get', 'authenticated') == (0, 'true\n')
    assert get(d, '--get', 'count', '0') == (0, '0\n')
    assert get(d, '--get', 'user.email') == (0, 'a@b\n')
    assert get(d, '--get', 'user.organizations.#') == (0, '2\n')
    assert get(d, '--get', 'organizations.0.org_id') == (0, 'org_1\n')
    assert get(d, '--get', 'missing.deep', 'none') == (0, 'none\n')
    assert get(d, '--get', 'missing') == (1, '')            # like jq -e: absent -> exit 1, nothing printed
    assert get(d, '--get', 'apiToken') == (1, '')           # null counts as absent
    assert get(d, '--get', 'user') == (0, '{"email": "a@b", "organizations": [1, 2]}\n')
    assert get(d, '--get', '.') [0] == 0                    # the whole document: a JSON validity check
    assert get(None, '--get', '.', stdin='not json')[0] == 2
    assert get(None, '--get', 'count', '0', stdin='Error: not logged in') == (0, '0\n')
    assert get(d, '--rows', 'organizations', 'org_id,org_name,role') == (0, 'org_1|One|owner\n')
    assert get({'projects': []}, '--rows', 'projects', 'project_id') == (0, '')
