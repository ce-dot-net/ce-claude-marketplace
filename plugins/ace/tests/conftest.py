"""These plugin-local tests mock subprocess.run; they must not depend on an ace-cli being installed.
Pin the resolver to the global-name argv so the mocked spawn is reached on any machine (CI has no ace-cli)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'shared-hooks' / 'utils'))
import ace_cli  # noqa: E402


@pytest.fixture(autouse=True)
def _resolved_cli(monkeypatch):
    monkeypatch.setattr(ace_cli, '_resolve', lambda: (['ace-cli'], 'global'))
