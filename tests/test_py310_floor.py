"""8.1.0: the Python hook chain supports Python >= 3.10. Every shared-hooks module must parse with 3.10 grammar
(ast feature_version) and use no 3.11+ stdlib or syntax. CI's 3.10 job additionally py_compiles them for real."""
import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1] / 'plugins/ace'
FILES = sorted(p for d in ('shared-hooks', 'utils') for p in (ROOT / d).rglob('*.py') if '__pycache__' not in p.parts)
BANNED = [(r'^\s*except\s*\*', 'except* (3.11)'), (r'\bimport\s+tomllib\b|\bfrom\s+tomllib\b', 'tomllib (3.11)'),
          (r'\btyping\.Self\b|from typing import[^\n]*\bSelf\b', 'typing.Self (3.11)'),
          (r'^\s*type\s+\w+\s*(\[[^\]]*\])?\s*=', 'PEP 695 type alias (3.12)'), (r'^\s*(def|class)\s+\w+\[', 'PEP 695 type params (3.12)'),
          (r'\bExceptionGroup\b', 'ExceptionGroup (3.11)'), (r'\btaskgroup|TaskGroup\b', 'asyncio.TaskGroup (3.11)')]


def test_there_are_files():
    assert len(FILES) > 20


@pytest.mark.parametrize('p', FILES, ids=lambda p: str(p.relative_to(ROOT)))
def test_parses_with_python_3_10_grammar(p):
    ast.parse(p.read_text(), filename=str(p), feature_version=(3, 10))


@pytest.mark.parametrize('p', FILES, ids=lambda p: str(p.relative_to(ROOT)))
def test_no_3_11_plus_constructs(p):
    text = p.read_text()
    hits = [why for pat, why in BANNED if re.search(pat, text, re.M)]
    assert not hits, '%s: %s' % (p.name, hits)
