"""Parity TS<->Python of the secret-redaction RULE TABLES: mod/lib/redact_rules.ts and shared-hooks/utils/redact.py keep the same
rows in the same order (name, pattern, i-flag, options). A row added or changed in one language only fails here; the shared fixture
tests-fixtures/secret-filter/cases.json checks the outputs (tests/test_secret_filter_py.py, mod tests/redact.test.ts).
The rules stay one table per language (no generated code): the mod may not read files at run time, and the two regex dialects
differ in spelling, which this test normalizes: \\d vs [0-9], \\/ vs /, \\v \\f vs \\x0b \\x0c, ${CONST} vs ' + CONST + ', and JS's
multiline ^ / $ vs Python's _BOL / _EOL (re.A, which only makes Python's classes ASCII as in JS, is not compared)."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "ace"
sys.path.insert(0, str(PLUGIN / "shared-hooks" / "utils"))
import redact as rd  # noqa: E402

TS = (PLUGIN / "mod" / "lib" / "redact_rules.ts").read_text()
RAW = {m.group(1): m.group(2) for m in re.finditer(r"(?:export )?const (\w+) = String\.raw`([^`]*)`", TS)}


def _expand(src):
    while '${' in src:
        src = re.sub(r"\$\{(\w+)\}", lambda x: RAW[x.group(1)], src)
    return src


def _regex_literal(s, i):
    """(source, flags, end) of the JS regex literal starting at s[i] == '/'."""
    j, cls = i + 1, False
    while True:
        c = s[j]
        if c == '\\':
            j += 2
            continue
        if c == '[':
            cls = True
        elif c == ']':
            cls = False
        elif c == '/' and not cls:
            break
        j += 1
    k = j + 1
    while s[k].isalpha():
        k += 1
    return s[i + 1:j], s[j + 1:k], k


_NEW_RE = re.compile(r"new RegExp\(String\.raw`([^`]*)`(?:, '(\w*)')?\)")


def _regex_at(s, i):
    """(source, flags, end) of the regex at s[i]: a /literal/ or new RegExp(String.raw`...${C}...`, 'flags')."""
    if s[i] == '/':
        return _regex_literal(s, i)
    m = _NEW_RE.match(s, i)
    assert m, s[i:i + 60]
    return _expand(m.group(1)), m.group(2) or '', m.end()


def _norm(src):
    for a, b in (('\\/', '/'), ('\\d', '[0-9]'), ("\\'", "'"), ('\\"', '"'), ('\\v', '\\x0b'), ('\\f', '\\x0c')):
        src = src.replace(a, b)
    return src


def _ts_flags(f):
    return 'i' if 'i' in f else ''


def _ts_rule(line, i):
    """(normalized rule, end): one regex, or a [keyword, flag] pair (Round 10 / L3) as a 2-tuple."""
    if line[i] == '[':
        a, fa, j = _regex_at(line, i + 1)
        assert line[j:j + 2] == ', '
        b, fb, k = _regex_at(line, j + 2)
        assert line[k] == ']'
        return ((_norm(a), _ts_flags(fa)), (_norm(b), _ts_flags(fb))), k + 1
    src, flags, end = _regex_at(line, i)
    return (_norm(src), _ts_flags(flags)), end


def _table(name):
    """Rows of `export const NAME: [...][] = [ ... ]` as (row name, rule, rest-of-row text)."""
    m = re.search(r"export const %s: [^=]+= \[\n(.*?)\n\]" % name, TS, re.S)
    assert m, name
    rows = []
    for line in m.group(1).split('\n'):
        line = line.strip()
        if not line.startswith("['"):
            continue
        n = re.match(r"\['([^']+)', ", line)
        rule, end = _ts_rule(line, n.end())
        rows.append((n.group(1), rule, re.sub(r'\],?(?:[ \t]*//.*)?$', '', line[end:]).strip(', ')))
    return rows


def _py(rx):
    if isinstance(rx, tuple):
        return tuple(_py(x) for x in rx)
    return _norm(rx.pattern.replace(rd._BOL, '^').replace(rd._EOL, '$')), ('i' if rx.flags & re.I else '')


def test_span_rules_match():
    assert [(n, r, rest) for n, r, rest in _table('SPAN_RULES')] == \
        [(n, _py(rx), 'true' if b else 'false') for n, rx, b in rd.SPAN_RULES]


def test_secret_rules_match():
    assert [(n, r, rest.strip("'").replace('$1', '\\1')) for n, r, rest in _table('SECRET_RULES')] == \
        [(n, _py(rx), rep) for n, rx, rep in rd.SECRET_RULES]


def test_prefix_rules_match():
    assert [(n, r) for n, r, _ in _table('PREFIX_RULES')] == [(n, _py(rx)) for n, rx in rd.PREFIX_RULES]


def test_format_rules_match():
    assert [(n, r, rest.replace(' ', '')) for n, r, rest in _table('FORMAT_RULES')] == \
        [(n, _py(rx), '%d,%d' % (vg, tg)) for n, rx, vg, tg in rd.FORMAT_RULES]


def test_name_value_rules_match():
    assert [(n, r, rest) for n, r, rest in _table('NV_RULES')] == [(n, _py(rx), str(tg)) for n, rx, tg in rd.NV_RULES]


def _single(name):
    i = TS.index('export const %s = ' % name) + len('export const %s = ' % name)
    src, flags, _ = _regex_at(TS, i)
    return _norm(src), _ts_flags(flags)


def test_single_rules_match():
    for name, rx in [('ENV_LINE', rd.ENV_LINE), ('ENV_STRIP', rd.ENV_STRIP), ('URL_CRED', rd.URL_CRED),
                     ('ENTROPY_RUN', rd.ENTROPY_RUN), ('OBJECT_ID', rd.OBJECT_ID)]:
        assert _single(name) == _py(rx), name


def _set(name):
    m = re.search(r"export const %s = new Set\(\[([^\]]*)\]\)" % name, TS)
    return set(re.findall(r"'([^']*)'", m.group(1)))


def test_sets_and_constants_match():
    assert _set('ENV_SEGS') == rd.ENV_SEGS and _set('ENV_HARMLESS') == rd.ENV_HARMLESS
    assert _norm(RAW['JS_WS']) == rd.JS_WS
    assert 'export const REDACT_BLOCK = %d' % rd.REDACT_BLOCK in TS
    assert 'ENTROPY_MIN = %s, ENTROPY_LEN_FACTOR = %s' % (rd.ENTROPY_MIN, rd.ENTROPY_LEN_FACTOR) in TS
    assert 'SWITCH_MIN = %s' % rd.SWITCH_MIN in TS


def _record(name):
    m = re.search(r"export const %s: Record<string, (?:string|number)> = \{(.*?)\}\n" % name, TS, re.S)
    assert m, name
    out = {}
    for k, v in re.findall(r"'?([A-Za-z-]+)'?: ('[^']*'|\d+)", m.group(1)):
        out[k] = v.strip("'") if v.startswith("'") else int(v)
    return out


def test_pii_tables_match():
    """Round 13: the PII layer's data (example domains, E.164 country codes, IBAN lengths, PII key kinds, DOMAIN_MAX)."""
    assert _set('EXAMPLE_DOMAINS') == rd.EXAMPLE_DOMAINS and _set('EXAMPLE_TLDS') == rd.EXAMPLE_TLDS
    assert _set('PHONE_CC') == rd.PHONE_CC and len(rd.PHONE_CC) > 200
    assert _record('IBAN_LEN') == rd.IBAN_LEN and _record('PII_KEY_KIND') == rd.PII_KEY_KIND
    assert 'export const DOMAIN_MAX = %d' % rd.DOMAIN_MAX in TS


def test_pii_rules_match():
    """Round 13: [name, label, prefilter, rule] rows in the same order."""
    m = re.search(r"export const PII_RULES: [^=]+= \[\n(.*?)\n\]", TS, re.S)
    rows = []
    for line in m.group(1).split('\n'):
        line = line.strip()
        if not line.startswith("['"):
            continue
        n = re.match(r"\['([^']+)', '([^']*)', ", line)
        pre, i = _ts_rule(line, n.end())
        assert line[i:i + 2] == ', '
        rule, _ = _ts_rule(line, i + 2)
        rows.append((n.group(1), n.group(2), pre, rule))
    assert rows == [(n, label, _py(pre), _py(rx)) for n, label, pre, rx in rd.PII_RULES]


def test_every_table_is_checked():
    """A new rule table or constant in redact_rules.ts needs a parity check here."""
    tables = set(re.findall(r"export const (\w+)", TS))
    assert tables == {'REDACT_BLOCK', 'SPAN_RULES', 'SECRET_RULES', 'PREFIX_RULES', 'JS_WS', 'ENV_LINE', 'ENV_STRIP', 'ENV_SEGS', 'ENV_HARMLESS',
                      'URL_CRED', 'FORMAT_RULES', 'NV_RULES', 'DOMAIN_MAX', 'EXAMPLE_DOMAINS', 'EXAMPLE_TLDS', 'PHONE_CC', 'IBAN_LEN',
                      'PII_KEY_KIND', 'PII_RULES', 'ENTROPY_MIN', 'SWITCH_MIN', 'ENTROPY_RUN', 'OBJECT_ID'}
