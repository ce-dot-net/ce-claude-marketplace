#!/usr/bin/env python3
"""Secret redaction (8.1.3 + full steps), FAIL-CLOSED: Claude Code does not redact hook inputs, so every text the trace sends or
the task state stores goes through redact(). Rule DATA first (tables), the engine below.

Layers, in this order (each later layer leaves an earlier '[redacted' value alone):
   1. stdin bodies of --password-stdin / --with-token (here-strings, here-docs)    _redact_stdin       '[redacted]'
   2. key / flag / header spans (password=, --token, mysql -p, Bearer ...)          SPAN_RULES          '[redacted]'
   3. echo | --password-stdin, URL userinfo, the 8.1.3 token prefixes / JWTs        SECRET_RULES        '[redacted]'
   4. PEM private keys (to the END line, else to the text end)                     _redact_pem         '[redacted:prefix:private-key]'
   5. known token prefixes (aws, google, gitlab, stripe, huggingface, shopify)      PREFIX_RULES        '[redacted:prefix:<name>]'
   6. .env lines with a secret-like key segment                                    ENV_LINE            '[redacted:env]'
   7. user:password@host without a scheme                                          URL_CRED            '[redacted:url-cred]'
   8. file formats: .netrc, .pgpass, docker auth, cookie jar, PHP define()         FORMAT_RULES        '[redacted:<kind>]'
   9. name / value pairs (K8s env YAML, JSON {name|key, value})                    NV_RULES            '[redacted:name-value]'
  10. personal data: IBAN, e-mail, phone (+CC, national after a keyword), PII keys  PII_RULES           '[redacted:email|phone|iban]'
  11. high entropy runs                                                            _redact_entropy     '[redacted:entropy]'
deep_redact applies redact() to every string of a structured value and drops the whole value under a secret-named key.
A new token class (like Shopify) is ONE table row here and in mod/lib/redact_rules.ts plus ONE case in
tests-fixtures/secret-filter/cases.json. ponytail: over-redacts on purpose (a key span takes the rest of the line), never under-redacts.
KNOWN LIMITS (README): bare secrets with no key word and no known format (a lowercase or hex token, anything under 20 chars, an
unlabelled value in prose), hex-only key material (SHAs and UUIDs must stay readable), a .netrc password on its own line.
Parity TS<->Python: mod/lib/redact.ts (engine) + mod/lib/redact_rules.ts (rules), rule for rule. The regexes spell JS semantics for
Python: re.A (ASCII \\b and classes), JS_WS (JS's \\s), _BOL / _EOL (JS multiline ^ / $ also at a lone CR and U+2028/9).
Fixture tests-fixtures/secret-filter/cases.json (tests/test_secret_filter_py.py, which also compares both chains' outputs, and mod
tests/redact.test.ts); tests/test_redact_parity.py compares the tables. Linear: no backtracking regex, find() scans, cached matches.
"""
import math
import re

# ======================= RULES =======================

# ---- layer 2: key / flag / header spans (8.1.3, write '[redacted]') ----
# (name, rule, block): the value runs from the match end to the end of the line; block = on to the next blank line (at most
# REDACT_BLOCK chars). Inside a scheme:// token (a URL query) the value ends at '&', '#' or whitespace. A rule (keyword, flag)
# (Round 10 / L3) is a keyword plus a flag on the same line, searched in two linear steps (_lazy_search).
REDACT_BLOCK = 500
SPAN_RULES = (
    ('key', re.compile(r'''(?:password|passwd|passphrase|pwd|secret|token|credential|authorization|cookie|api[-_]?key|_key(?![a-z0-9])|pass(?![a-z]))[A-Za-z0-9_-]*["']?[ \t]*[:=][ \t]*''', re.I | re.A), True),
    ('flag', re.compile(r'''--[A-Za-z0-9-]*(?:token|password|passwd|secret|api[-_]?key|credential)[A-Za-z0-9-]*(?:=|[ \t]+)''', re.I | re.A), False),
    ('mysql-p', (re.compile(r'''\b(?:mysql(?:dump|admin|sh)?|sshpass|7z[a-z]?)\b''', re.A), re.compile(r'''[ \t]-p[ \t]*''', re.A)), False),  # Round 10 / L3
    ('zip-P', (re.compile(r'''\b(?:unzip|zip)\b''', re.A), re.compile(r'''[ \t]-P[ \t]*''', re.A)), False),  # Round 10 / L3
    ('ssh-keygen-N', (re.compile(r'''\bssh-keygen\b''', re.A), re.compile(r'''[ \t]-N[ \t]*''', re.A)), False),  # Round 10 / L3
    ('openssl-pass', (re.compile(r'''\bopenssl\b''', re.A), re.compile(r'''[ \t]-(?:k|pass|passin|passout)[ \t]+''', re.A)), False),  # Round 10 / L3
    ('htpasswd', re.compile(r'''\bhtpasswd\b[ \t]*''', re.A), False),
    ('curl-user', (re.compile(r'''\b(?:curl|wget)\b''', re.A), re.compile(r'''[ \t](?:-u|--user)(?:=|[ \t]+)?(?=["']?[^ \t\n\r"']*:)''', re.A)), False),  # Round 10 / L3
    ('bearer', re.compile(r'''\bBearer[ \t]+''', re.I | re.A), False),
)

# ---- layer 3: substitutions (8.1.3, write '[redacted]') ----
# (name, rule, replacement). 'stdin-echo' is applied per line by the linear _echo_stdin (Round 11 / W2), 'url-userinfo' by the linear
# _url_userinfo (Round 13: the regex is quadratic on a long run of scheme chars without '://'); both give exactly their regex's result,
# the regexes stay as their specification.
SECRET_RULES = (
    # the echo/printf stage that pipes a secret into --password-stdin / --with-token
    ('stdin-echo', re.compile(r'''\b(echo|printf)\b[^\n]*\|(?=[^|\n]*--(?:password-stdin|with-token))''', re.A | re.I), r'\1 [redacted] |'),
    ('url-userinfo', re.compile(r'''(\b[A-Za-z][A-Za-z0-9+.-]*://)[^ \t\n\r\x0b\x0c"']*@''', re.A), r'\1[redacted]@'),
    ('token-8.1.3', re.compile(r'''\b(?:ghp_|gho_|ghu_|ghs_|ghr_|github_pat_|xox[abprs]-|ace_user_|sk-)[A-Za-z0-9_-]{8,}|\bnpm_[A-Za-z0-9]{20,}|\bAKIA[0-9A-Z]{12,}|\beyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}(?:\.[A-Za-z0-9_-]+)?''', re.A), '[redacted]'),
)

# ---- layer 5: known token prefixes (write '[redacted:prefix:<name>]') ----
# round 8 I2: re.A on these prefix rules and on the netrc / php-define rules: \b and classes are ASCII as in JS (an 'ä' before a token is a boundary)
PREFIX_RULES = (
    ('aws', re.compile(r'\b(?:AKIA|ASIA)[0-9A-Z]{16}\b', re.A)),
    ('google', re.compile(r'\bAIza[0-9A-Za-z_-]{35}', re.A)),
    ('gitlab', re.compile(r'\bglpat-[0-9A-Za-z_-]{20,}', re.A)),
    ('stripe', re.compile(r'\b[rs]k_(?:live|test)_[0-9A-Za-z]{16,}', re.A)),
    ('huggingface', re.compile(r'\bhf_[A-Za-z0-9]{30,}', re.A)),
    # Shopify (Round 7): = mod lib/redact_rules.ts PREFIX_RULES 'shopify'
    ('shopify', re.compile(r'\bshp(?:at|ca|pa|ss)_[0-9a-fA-F]{32,}', re.A)),
)

# ---- layer 6: .env lines (write '[redacted:env]') ----
# KEY=value whose key has a secret-like SEGMENT (split at '_'; AUTHOR or SESSION_TIMEOUT stay). Optional tool prefix before the key:
# Read / cat -n line numbers, grep -n, grep context, single-file grep, a YAML item ('- '), a diff line ('+', '-').
# round 9 N7: JS's \s written out (= mod JS_WS); Python's \s differs (\x1c-\x1f and \x85 in, U+FEFF out)
JS_WS = r'\t\n\x0b\x0c\r    -     　﻿'
_TOOL_PREFIX = r'(?:[ \t]*[0-9]+[\t→]|[^' + JS_WS + r':]{1,256}:[0-9]+:)?'
_ENV_HEAD = r'(?:[ \t]*[0-9]+[\t→]|[^' + JS_WS + r':]{1,256}:[0-9]+:|[^' + JS_WS + r':]{1,256}-[0-9]+-|[0-9]+[:-]|[ \t]*-[ \t]+|[+-])?'  # = mod ENV_LINE (round 6: grep context, single-file grep, diff)
# round 8 I2: JS multiline ^ / $ also hold at a lone CR (and U+2028/9); Python's only at \n: these two keep the line rules identical
_BOL = r'(?:^|(?<=[\r  ]))'
_EOL = r'(?=[\r\n  ]|\Z)'
ENV_LINE = re.compile(_BOL + r'(' + _ENV_HEAD + r'[ \t]*(?:export[ \t]+)?[A-Za-z_][A-Za-z0-9_]*[ \t]*=[ \t]*)([^' + JS_WS + r'][^\n]*)' + _EOL, re.M)
ENV_STRIP = re.compile(r'^' + _ENV_HEAD + r'[ \t]*(?:export[ \t]+)?')
ENV_SEGS = {'SALT', 'SIGNING', 'DSN', 'PRIVATE', 'AUTH', 'CRED', 'CREDS', 'CERT', 'SEED', 'SIG', 'SIGNATURE', 'HMAC', 'ENCRYPTION', 'OTP',
            'PASS', 'PWD', 'ACCESS', 'SESSION'}
ENV_HARMLESS = {'TIMEOUT', 'MINUTES', 'SECONDS', 'TTL', 'URL', 'HOST', 'PORT', 'NAME', 'USER', 'ID', 'ENABLED', 'MODE', 'LEVEL', 'PATH',
                'DIR', 'FILE', 'COUNT', 'MAX', 'MIN', 'LIMIT'}

# ---- layer 7: user:password@host without a scheme (write '[redacted:url-cred]'; 'git@github.com' has no ':' before '@') ----
URL_CRED = re.compile(r'(^|[' + JS_WS + r'"\'(=,;])([A-Za-z0-9._~%-]{1,64}):([^' + JS_WS + r'@/:"\']{1,128})@([A-Za-z0-9-]{1,63}(?:\.[A-Za-z0-9-]{1,63})+)')

# ---- layer 8: well-known file formats without the usual key word (write '[redacted:<kind>]') ----
# (kind, rule, value group, tail group (0 = none)): the match becomes group 1 + label + tail group; a value that is empty or already
# starts with '[redacted' stays. .netrc: '[machine M] login L password X' on one line; .pgpass: host:port:db:user:password;
# docker config.json "auth" / "identitytoken"; Netscape cookie jar (value = the 7th tab field; round 9 N6: the fields stop at CR too);
# PHP define('…KEY|SECRET|…', '…').
FORMAT_RULES = (
    ('netrc', re.compile(r'\b((?:machine[ \t]+[^ \t\n]+[ \t]+)?login[ \t]+[^ \t\n]+[ \t]+password[ \t]+)([^ \t\n]+)', re.A), 2, 0),
    ('pgpass', re.compile(_BOL + r'(' + _TOOL_PREFIX + r'[^' + JS_WS + r':]{1,253}:(?:[0-9]{1,5}|\*):[^' + JS_WS + r':]{1,128}:[^' + JS_WS + r':]{1,128}:)([^' + JS_WS + r']+)' + _EOL, re.M), 2, 0),
    ('docker-auth', re.compile(r'("(?:auth|identitytoken)"[ \t]*:[ \t]*")([^"\n]{4,})(")'), 2, 3),
    ('cookie-jar', re.compile(_BOL + r'(' + _TOOL_PREFIX + r'(?:#HttpOnly_)?[^\t\n\r]+\t(?:TRUE|FALSE)\t[^\t\n\r]*\t(?:TRUE|FALSE)\t[0-9]+\t[^\t\n\r]*\t)([^\n\r]+)' + _EOL, re.M), 2, 0),
    ('php-define', re.compile(r'(\bdefine\([ \t]*([\'"])[A-Za-z0-9_]*(?:KEY|SECRET|PASSWORD|PASS|TOKEN|SALT|AUTH)[A-Za-z0-9_]*\2[ \t]*,[ \t]*([\'"]))([^\'"\n]*)(\3)', re.I | re.A), 4, 5),
)

# ---- layer 9: name / value pairs (Round 10 / M3, write '[redacted:name-value]') ----
# (kind, rule, tail group): group 2 = the name, group 4 = the value; when the name is a secret name (secret_name) the match becomes
# groups 1-3 + label + tail group. K8s env YAML 'name: X' + next line 'value: Y'; JSON {"name"|"key": "X", "value": "Y"} (Round 11 /
# I3.1: the JSON value runs over escaped characters; Round 12: as an unrolled loop, = mod).
NV_RULES = (
    ('yaml', re.compile(_BOL + r'''([ \t]*(?:-[ \t]+)?name:[ \t]*["']?)([A-Za-z_][A-Za-z0-9_.-]{0,127})(["']?[ \t]*\r?\n[ \t]*(?:-[ \t]+)?value:[ \t]*)([^ \t\r\n\u2028\u2029][^\r\n\u2028\u2029]*)''', re.M), 0),
    ('json', re.compile(r'("(?:name|key)"[ \t]*:[ \t]*")([^"\n]{1,128})("[ \t]*,[ \t]*"value"[ \t]*:[ \t]*")([^"\\\n]*(?:\\[^\n][^"\\\n]*)*)(")'), 5),
)

# ---- layer 10: personal data (Round 13, write '[redacted:email]' / '[redacted:phone]' / '[redacted:iban]'); = mod lib/redact_rules.ts ----
# (name, label, prefilter, rule) in this order; _PII_HANDLERS checks each candidate (IBAN length + mod 97, example domains, country code
# and the diff rule, the keyword gap, the PII key value). Reasons and known limits: mod/lib/redact_rules.ts layer 10.
DOMAIN_MAX = 253
EXAMPLE_DOMAINS = {'example.com', 'example.org', 'example.net'}
EXAMPLE_TLDS = {'test', 'example', 'invalid', 'localhost'}
# ITU E.164 assigned country codes (= mod PHONE_CC)
PHONE_CC = {'1', '7', '20', '27', '30', '31', '32', '33', '34', '36', '39', '40', '41', '43', '44', '45', '46', '47',
            '48', '49', '51', '52', '53', '54', '55', '56', '57', '58', '60', '61', '62', '63', '64', '65', '66', '81',
            '82', '84', '86', '90', '91', '92', '93', '94', '95', '98', '211', '212', '213', '216', '218', '220', '221', '222',
            '223', '224', '225', '226', '227', '228', '229', '230', '231', '232', '233', '234', '235', '236', '237', '238', '239', '240',
            '241', '242', '243', '244', '245', '246', '247', '248', '249', '250', '251', '252', '253', '254', '255', '256', '257', '258',
            '260', '261', '262', '263', '264', '265', '266', '267', '268', '269', '290', '291', '297', '298', '299', '350', '351', '352',
            '353', '354', '355', '356', '357', '358', '359', '370', '371', '372', '373', '374', '375', '376', '377', '378', '379', '380',
            '381', '382', '383', '385', '386', '387', '388', '389', '420', '421', '423', '500', '501', '502', '503', '504', '505', '506',
            '507', '508', '509', '590', '591', '592', '593', '594', '595', '596', '597', '598', '599', '670', '672', '673', '674', '675',
            '676', '677', '678', '679', '680', '681', '682', '683', '685', '686', '687', '688', '689', '690', '691', '692', '800', '808',
            '850', '852', '853', '855', '856', '870', '880', '881', '882', '883', '886', '888', '960', '961', '962', '963', '964', '965',
            '966', '967', '968', '970', '971', '972', '973', '974', '975', '976', '977', '979', '991', '992', '993', '994', '995', '996',
            '998'}
# ISO 13616 IBAN register: total length per country (= mod IBAN_LEN)
IBAN_LEN = {'AD': 24, 'AE': 23, 'AL': 28, 'AT': 20, 'AZ': 28, 'BA': 20, 'BE': 16, 'BG': 22, 'BH': 22, 'BI': 27, 'BR': 29, 'BY': 28,
            'CH': 21, 'CR': 22, 'CY': 28, 'CZ': 24, 'DE': 22, 'DJ': 27, 'DK': 18, 'DO': 28, 'EE': 20, 'EG': 29, 'ES': 24, 'FI': 18,
            'FK': 18, 'FO': 18, 'FR': 27, 'GB': 22, 'GE': 22, 'GI': 23, 'GL': 18, 'GR': 27, 'GT': 28, 'HN': 28, 'HR': 21, 'HU': 28,
            'IE': 22, 'IL': 23, 'IQ': 23, 'IS': 26, 'IT': 27, 'JO': 30, 'KW': 30, 'KZ': 20, 'LB': 28, 'LC': 32, 'LI': 21, 'LT': 20,
            'LU': 20, 'LV': 21, 'LY': 25, 'MC': 27, 'MD': 24, 'ME': 22, 'MK': 19, 'MN': 20, 'MR': 27, 'MT': 31, 'MU': 30, 'NI': 28,
            'NL': 18, 'NO': 15, 'OM': 23, 'PK': 24, 'PL': 28, 'PS': 29, 'PT': 25, 'QA': 29, 'RO': 24, 'RS': 22, 'RU': 33, 'SA': 24,
            'SC': 31, 'SD': 18, 'SE': 24, 'SI': 19, 'SK': 24, 'SM': 27, 'SO': 23, 'ST': 25, 'SV': 28, 'TL': 23, 'TN': 24, 'TR': 26,
            'UA': 29, 'VA': 22, 'VG': 24, 'XK': 20, 'YE': 30}
PII_KEY_KIND = {'e-mail': 'email', 'email': 'email', 'mail': 'email', 'iban': 'iban', 'telephone': 'phone', 'phone': 'phone',
                'tel': 'phone', 'mobile': 'phone', 'handy': 'phone', 'fax': 'phone'}
PII_RULES = (
    ('iban', 'iban', re.compile(r'[A-Z]{2}[0-9]{2}', re.A), re.compile(r'(?<![A-Za-z0-9])[A-Z]{2}[0-9]{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,3})?(?![A-Za-z0-9])', re.A)),
    ('email', 'email', re.compile(r'@', re.A), re.compile(r'(?<![A-Za-z0-9._%+\-])(?<!//)[A-Za-z0-9._%+-]{1,64}@((?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.){1,8}[A-Za-z]{2,24})(?![A-Za-z0-9-]|\.[A-Za-z0-9])(?!:[A-Za-z0-9._/~-])', re.A)),
    ('phone-intl', 'phone', re.compile(r'\+', re.A), re.compile(r'(?<![A-Za-z0-9+])\+([0-9](?:[ ()./-]{0,2}[0-9]){5,16})(?![0-9])', re.A)),
    ('phone-kw', 'phone', re.compile(r'tel|phone|mobil|handy|fax|whatsapp|call|rufnummer', re.I | re.A),
     re.compile(r'\b(telefon|tel|phone|mobile|mobil|handy|fax|whatsapp|call|rufnummer)\b([^\n0-9]{0,20})([0-9](?:[ ()./-]{0,2}[0-9]){5,14})(?![0-9])', re.I | re.A)),
    ('pii-key', '', re.compile(r'mail|iban|phone|tel|mobile|handy|fax', re.I | re.A),
     re.compile(r'''(?<![A-Za-z0-9_.\-])(["']?)(e-mail|email|mail|iban|telephone|phone|tel|mobile|handy|fax)\1[ \t]*[:=](?!=)[ \t]*(?:"([^"\n]{1,256})"|'([^'\n]{1,256})'|([^''' + JS_WS + r'''"',;}\]]{1,256}))''', re.I | re.A)),
)

# ---- layer 11: high entropy (write '[redacted:entropy]'); thresholds and reasons: mod/lib/redact_rules.ts ----
ENTROPY_MIN, ENTROPY_LEN_FACTOR, SWITCH_MIN = 4.0, 0.85, 0.35
ENTROPY_RUN = re.compile(r'[A-Za-z0-9+/_=-]{20,}')
# Object ids with a base62 body, never key material (Claude / ACE / Stripe object prefixes)
OBJECT_ID = re.compile(r'^(?:toolu|srvtoolu|msg|req|session|file|batch|org|prj|cus|pi|ch|sub|price|prod|acct|evt|in|call|run)_[A-Za-z0-9]{8,}$')

# ======================= ENGINE =======================

# ---- layer 1: stdin bodies ----
# Run BEFORE the span rules (which cut the line at the flag): the stdin value of --password-stdin / --with-token that they
# cannot see. A LOGICAL line is the physical lines joined over an unescaped trailing backslash (and, below, over a
# multi-line quoted here-string word). On a logical line holding the flag (any case, left or right of the value, behind a
# pipe): every shell word after a '<<<' (quotes, $'..', backslashes; a word starting $( ` ${ runs to the end of the logical
# line; an open quote runs to the closing quote on a later line, else to the TEXT END) and the body of every here-doc
# ('<<[-]DELIM', quoted or \DELIM; case-sensitive; '<<-' allows leading tabs) on the lines below, up to the terminator line, or
# to the TEXT END when there is none or the delimiter cannot be parsed. Fail closed, a heuristic, not a shell parser. Linear:
# one cheap flag test first, no backtracking regex. Parity: mod/lib/redact.ts redactStdin.
_STDIN_FLAG = re.compile(r'--(?:password-stdin|with-token)', re.A | re.I)
_WORD_END = ' \t\n;&|)'
_DELIM_END = ' \t\n;&|)<>\'"\\('
_DELIM_MAX = 256


def _stdin_word_end(t, i):
    """The end of the shell word starting at i in t (an open quote runs to the closing quote on a later line, else to the end)."""
    n = len(t)
    while i < n and t[i] not in _WORD_END:
        c = t[i]
        if c == '\\':
            i += 2
        elif c in '\'"' or (c == '$' and t[i + 1:i + 2] == "'"):
            q = "'" if c == '$' else c
            esc = q == '"' or c == '$'
            j = i + 2 if c == '$' else i + 1
            while j < n and t[j] != q:
                j += 2 if esc and t[j] == '\\' else 1
            if j >= n:
                return n
            i = j + 1
        else:
            i += 1
    return min(i, n)


def _logical_end(t, p):
    """The end (index of the '\\n' or text end) of the logical line that holds index p."""
    e = t.find('\n', p)
    while e >= 0:
        b = 0
        while e - 1 - b >= p and t[e - 1 - b] == '\\':
            b += 1
        if b % 2 == 0:
            return e
        e = t.find('\n', e + 1)
    return len(t)


def _here_docs(l):
    """The delimiters of the here-docs on one logical line: [(delimiter, dash)], or None when one cannot be parsed."""
    out, k = [], 0
    while True:
        k = l.find('<<', k)
        if k < 0:
            return out
        if l[k + 2:k + 3] == '<':
            k += 1
            continue
        if k > 0 and l[k - 1] == '<':
            k += 2
            continue
        i = k + 2
        dash = l[i:i + 1] == '-'
        if dash:
            i += 1
        while l[i:i + 1] in (' ', '\t'):
            i += 1
        if l[i:i + 1] in ("'", '"'):
            e = l.find(l[i], i + 1)
            if e < 0:
                return None
            d, i = l[i + 1:e], e + 1
        else:
            if l[i:i + 1] == '\\':
                i += 1
            e = i
            while e < len(l) and l[e] not in _DELIM_END:
                e += 1
            d, i = l[i:e], e
        if not d or len(d) > _DELIM_MAX:
            return None
        out.append((d, dash))
        k = i


def _redact_stdin(t):
    if not _STDIN_FLAG.search(t):
        return t
    n, out, p, next_k = len(t), [], 0, -2
    while p <= n:
        e = _logical_end(t, p)
        flag = bool(_STDIN_FLAG.search(t[p:e]))
        words, pos = [], p
        while True:
            if next_k != -1 and next_k < pos:
                next_k = t.find('<<<', pos)
            if next_k < 0 or next_k >= e:
                break
            s = next_k + 3
            while t[s:s + 1] in (' ', '\t') or (t[s:s + 1] == '\\' and t[s + 1:s + 2] == '\n'):
                s += 2 if t[s] == '\\' else 1
            subst = t[s:s + 1] == '`' or (t[s:s + 1] == '$' and t[s + 1:s + 2] in ('(', '{'))
            w = e if subst else _stdin_word_end(t, s)
            words.append((s, w))
            if w > e:
                e2 = _logical_end(t, w)
                flag = flag or bool(_STDIN_FLAG.search(t[e:e2]))
                e = e2
            pos = max(w, next_k + 3)
        if not flag:
            out.append(t[p:e])
            p = e + 1
            continue
        line, q = [], p
        for s, w in words:
            line.append(t[q:s] + ('[redacted]' if w > s else ''))
            q = w
        out.append(''.join(line) + t[q:e])
        docs = _here_docs(t[p:e])
        ls = e + 1
        if docs is None:
            if ls <= n:
                out.append('[redacted]')
            break
        done = False
        for d, dash in docs:
            if ls > n:
                break
            b, found = ls, False
            while b <= n:
                le = t.find('\n', b)
                if le < 0:
                    le = n
                ln = t[b:le]
                if (ln.lstrip('\t') if dash else ln) == d:
                    found = True
                    if b > ls:
                        out.append('[redacted]')
                    out.append(ln)
                    ls = le + 1
                    break
                b = le + 1
            if not found:
                out.append('[redacted]')
                done = True
                break
        if done:
            break
        p = ls
    return '\n'.join(out)


# ---- layer 2: key / flag / header spans ----
_BLANK_LINE = re.compile(r'\n[ \t\r]*\n')
_URL_VALUE_END = re.compile(r'''[&# \t\n\r\x0b\x0c"']''')
_TOKEN_SEP = ' \t\n\r\x0b\x0c"\''


class _LazyMatch:
    __slots__ = ("_s", "_e")

    def __init__(self, s, e):
        self._s, self._e = s, e

    def start(self):
        return self._s

    def end(self):
        return self._e


def _lazy_search(rule, text, pos, cache):
    """Round 10 / L3: = mod lazySearch (keyword, then the flag on the rest of its line; a line without the flag is skipped)."""
    kw, flag = rule
    while True:
        m = kw.search(text, pos)
        if not m:
            return None
        if cache.get('eol', -1) < m.end():  # Round 11 / W1: the end of the line cached (= mod)
            e = text.find('\n', m.end())
            cache['eol'] = len(text) if e < 0 else e
        eol = cache['eol']
        f = flag.search(text, m.end(), eol)  # Round 11 / W1: pos/endpos, no copy of the rest of the line
        if f:
            return _LazyMatch(m.start(), f.end())
        pos = eol


def _redact_spans(text):
    out, pos = [], 0
    # round 5 C2: each rule's next match is cached and searched again only once pos has passed it (the same matches as a fresh
    # search from pos; mod parity lib/redact.ts redactSpans). Linear on long outputs, which the Python chain now sends uncut.
    nxt = [False] * len(SPAN_RULES)  # False = not searched yet, None = no further match
    scanned, last_sep, scheme_at, blank = 0, -1, -1, False
    caches = [{} for _ in SPAN_RULES]
    while True:
        best = None
        for k, (_name, rx, block) in enumerate(SPAN_RULES):
            m = nxt[k]
            if m is False or (m is not None and m.start() < pos):
                m = nxt[k] = _lazy_search(rx, text, pos, caches[k]) if isinstance(rx, tuple) else rx.search(text, pos)
            if m and (best is None or m.start() < best[0].start()):
                best = (m, block)
        if best is None:
            break
        m, block = best
        start = m.end()
        while scanned < m.start():  # Round 10 / L3: the token start remembered forward (= mod)
            if text[scanned] in _TOKEN_SEP:
                last_sep = scanned
            elif scheme_at <= last_sep and text.startswith('://', scanned):
                scheme_at = scanned  # the token's first '://'
            scanned += 1
        k = last_sep
        if scheme_at > k and scheme_at + 3 <= m.start():  # a URL query value ends at '&', '#' or whitespace
            e = _URL_VALUE_END.search(text, start)
            end = e.start() if e else len(text)
        else:
            end = text.find('\n', start)
            end = len(text) if end < 0 else end
            if block:  # Round 10 / L3: the next blank line cached (= mod)
                if blank is False or (blank is not None and blank.start() < start):
                    blank = _BLANK_LINE.search(text, start)
                end = max(end, min(blank.start() if blank else len(text), start + REDACT_BLOCK))
        out.append(text[pos:start] + '[redacted]')
        pos = end
    out.append(text[pos:])
    return ''.join(out)


# ---- layer 3: echo | --password-stdin ----
_ECHO_WORD = re.compile(r'\b(echo|printf)\b', re.A | re.I)


def _echo_stdin(l):
    """Round 11 / W2: = mod echoStdin (the echo/printf rule on one line, linear, same result as the regex)."""
    q, p = -1, l.find('|')
    while p >= 0:
        nx = l.find('|', p + 1)
        if _STDIN_FLAG.search(l, p + 1, len(l) if nx < 0 else nx):
            q = p
        p = nx
    if q < 0:
        return l
    m = _ECHO_WORD.search(l)
    if not m or m.end() > q:
        return l
    return l[:m.start()] + m.group(1) + ' [redacted] |' + l[q + 1:]


_USERINFO_END = re.compile(r'''[ \t\n\r\x0b\x0c"']''')


def _url_userinfo(t):
    """Round 13: = mod urlUserinfo, SECRET_RULES 'url-userinfo' in linear time with the same result."""
    p = t.find('://')
    if p < 0:
        return t
    out, pos, span_end, last_at = [], 0, -1, -1
    while p >= 0:
        r = p
        while r > pos and (t[r - 1].isascii() and (t[r - 1].isalnum() or t[r - 1] in '+.-')):
            r -= 1
        ok = any(('A' <= t[s] <= 'Z' or 'a' <= t[s] <= 'z') and not (s > 0 and t[s - 1].isascii() and (t[s - 1].isalnum() or t[s - 1] == '_'))
                 for s in range(r, p))
        if ok:
            if span_end < p + 3:  # a new span: its end and its last '@'
                e = _USERINFO_END.search(t, p + 3)
                span_end = e.start() if e else len(t)
                last_at = t.rfind('@', p + 3, span_end)
            if last_at >= p + 3:
                out.append(t[pos:p + 3] + '[redacted]@')
                pos = last_at + 1
        p = t.find('://', max(p + 1, pos))
    out.append(t[pos:])
    return ''.join(out)


# ---- layer 4: PEM private keys ----
def _redact_pem(t):
    out, pos = [], 0
    while True:
        b = t.find('-----BEGIN ', pos)
        if b < 0:
            break
        h_end = t.find('-----', b + 11)
        if h_end < 0 or h_end - b > 80 or not t[b:h_end].endswith('PRIVATE KEY'):
            out.append(t[pos:b + 11])
            pos = b + 11
            continue
        e = t.find('-----END ', h_end + 5)
        e_end = -1 if e < 0 else t.find('-----', e + 9)
        out.append(t[pos:b] + '[redacted:prefix:private-key]')
        pos = len(t) if e_end < 0 else e_end + 5
    out.append(t[pos:])
    return ''.join(out)


# ---- layer 6: .env lines ----
def _env_line(m):
    head, value = m.group(1), m.group(2)
    segs = re.sub(r'[ \t]*=[ \t]*$', '', ENV_STRIP.sub('', head, count=1)).upper().split('_')
    if value.startswith('[redacted') or not any(x in ENV_SEGS for x in segs) or segs[-1] in ENV_HARMLESS:
        return m.group(0)
    return head + '[redacted:env]'


# ---- layer 8: file formats ----
def _redact_formats(s):
    for kind, rx, vg, tg in FORMAT_RULES:
        def one(m, kind=kind, vg=vg, tg=tg):
            v = m.group(vg)
            return m.group(0) if not v or v.startswith('[redacted') else m.group(1) + '[redacted:%s]' % kind + (m.group(tg) if tg else '')
        s = rx.sub(one, s)
    return s


# ---- layer 9: name / value pairs ----
def _redact_name_value(s):
    for _kind, rx, tg in NV_RULES:
        s = rx.sub(lambda m, tg=tg: m.group(0) if not m.group(4) or m.group(4).startswith('[redacted') or not secret_name(m.group(2))
                   else m.group(1) + m.group(2) + m.group(3) + '[redacted:name-value]' + (m.group(tg) if tg else ''), s)
    return s


# ---- layer 10: personal data ----
def _is_example_domain(d):
    l = d.lower()
    return any(l == x or l.endswith('.' + x) for x in EXAMPLE_DOMAINS) or l[l.rfind('.') + 1:] in EXAMPLE_TLDS


def _iban_mod97(c):
    m = 0
    for ch in c[4:] + c[:4]:
        v = int(ch, 36)
        m = (m * 10 + v if v < 10 else m * 100 + v) % 97
    return m


def _digits(x):
    return ''.join(ch for ch in x if '0' <= ch <= '9')


def _pii_value(kind, v):
    """Whether a value behind a PII key looks like its kind (= mod piiValue)."""
    if v.startswith('[redacted'):
        return False
    if kind == 'email':
        return '@' in v and not _is_example_domain(v[v.rfind('@') + 1:])
    if kind == 'phone':
        return len(_digits(v)) >= 6
    return any('0' <= ch <= '9' for ch in v)


def _pii_iban(s, rx, label):
    def one(m):
        c = m.group(0).replace(' ', '')
        return '[redacted:%s]' % label if IBAN_LEN.get(c[:2]) == len(c) and _iban_mod97(c) == 1 else m.group(0)
    return rx.sub(one, s)


def _pii_email(s, rx, label):
    return rx.sub(lambda m: m.group(0) if len(m.group(1)) > DOMAIN_MAX or _is_example_domain(m.group(1)) else '[redacted:%s]' % label, s)


def _pii_phone_intl(s, rx, label):
    def one(m):
        body = m.group(1)
        dg = _digits(body)
        if len(dg) < 8 or len(dg) > 15 or not (dg[:1] in PHONE_CC or dg[:2] in PHONE_CC or dg[:3] in PHONE_CC):
            return m.group(0)
        return '[redacted:%s]' % label if len(dg) != len(body) or len(dg) >= 11 else m.group(0)  # no separator: only 11-15 digits
    return rx.sub(one, s)


def _pii_phone_kw(s, rx, label):
    return rx.sub(lambda m: m.group(1) + m.group(2) + '[redacted:%s]' % label, s)


def _pii_key(s, rx, _label):
    def one(m):
        v = next(x for x in (m.group(3), m.group(4), m.group(5)) if x is not None)
        kind, close = PII_KEY_KIND[m.group(2).lower()], 0 if m.group(5) is not None else 1
        t = m.group(0)
        return t[:len(t) - len(v) - close] + '[redacted:%s]' % kind + t[len(t) - close:] if _pii_value(kind, v) else t
    return rx.sub(one, s)


_PII_HANDLERS = {'iban': _pii_iban, 'email': _pii_email, 'phone-intl': _pii_phone_intl, 'phone-kw': _pii_phone_kw, 'pii-key': _pii_key}


def _redact_pii(s):
    for name, label, pre, rx in PII_RULES:
        if pre.search(s):
            s = _PII_HANDLERS[name](s, rx, label)
    return s


# ---- layer 11: high entropy ----
_SHA_INTEGRITY = re.compile(r'sha(?:256|384|512)-')
_NOT_ENTROPY = re.compile(r'[-_=+]')


def shannon(x):
    f = {}
    for c in x:
        f[c] = f.get(c, 0) + 1
    h = 0.0
    for n in f.values():
        p = n / len(x)
        h -= p * math.log2(p)
    return round(h * 1e6) / 1e6


def _cls(c):
    return 1 if 'a' <= c <= 'z' else 2 if 'A' <= c <= 'Z' else 3


def class_switches(x):
    if len(x) < 2:
        return 0
    return sum(1 for i in range(1, len(x)) if _cls(x[i]) != _cls(x[i - 1])) / (len(x) - 1)


def _redact_entropy(t):
    def one(m):
        run, at = m.group(0), m.start()
        if t[max(0, at - 7):at] == 'base64,' or _SHA_INTEGRITY.match(run):
            return run
        for piece in run.split('/'):
            if OBJECT_ID.match(piece):
                continue
            core = _NOT_ENTROPY.sub('', piece)
            if (len(core) >= 20 and any('A' <= c <= 'Z' for c in core) and any('a' <= c <= 'z' for c in core) and any('0' <= c <= '9' for c in core)
                    and shannon(core) >= min(ENTROPY_MIN, ENTROPY_LEN_FACTOR * math.log2(len(core))) and class_switches(core) >= SWITCH_MIN):
                return '[redacted:entropy]'
        return run
    return ENTROPY_RUN.sub(one, t)


# ======================= PUBLIC API =======================

def redact(text):
    """Fail-closed secret redaction, the layers of the module docstring in order. Parity: mod/lib/redact.ts redact."""
    if not isinstance(text, str) or not text:
        return text
    text = _redact_spans(_redact_stdin(text))
    for name, rx, rep in SECRET_RULES:  # Round 10 / L3: the echo/printf rule only on lines holding the stdin flag (= mod)
        text = '\n'.join(_echo_stdin(l) if _STDIN_FLAG.search(l) else l for l in text.split('\n')) if name == 'stdin-echo' else _url_userinfo(text) if name == 'url-userinfo' else rx.sub(rep, text)
    text = _redact_pem(text)
    for name, rx in PREFIX_RULES:
        text = rx.sub('[redacted:prefix:%s]' % name, text)
    text = ENV_LINE.sub(_env_line, text)
    # Round 13: 'mailto:local@domain' is an e-mail (layer 10), not user:password@host
    text = URL_CRED.sub(lambda m: m.group(0) if m.group(2).lower() == 'mailto' else '%s%s:[redacted:url-cred]@%s' % (m.group(1), m.group(2), m.group(4)), text)
    text = _redact_formats(text)
    text = _redact_name_value(text)  # Round 10 / M3
    text = _redact_pii(text)  # Round 13
    return _redact_entropy(text)


def secret_name(n):
    return redact(n + '=x') != n + '=x'  # = mod secretKey


def deep_redact(v, depth=0):
    """Round 10 / M2+M3: = mod deepRedact. Every string at any depth through redact(); the whole value under a secret-named key
    and the value of a {name|key: <secret name>, value: x} object become '[redacted]'. Linear; depth > 50 is dropped."""
    if isinstance(v, str):
        return redact(v)
    if depth > 50:
        return '[redacted]'  # ponytail: absurd nesting is dropped, never sent unchecked
    if isinstance(v, list):
        return [deep_redact(x, depth + 1) for x in v]
    if isinstance(v, dict):
        nm = v.get('name') if isinstance(v.get('name'), str) else v.get('key') if isinstance(v.get('key'), str) else None
        nv = nm is not None and 'value' in v and secret_name(nm)
        return {k: _deep_value(k, x, nv, depth) for k, x in v.items()}
    return v


def _deep_value(k, x, nv, depth):
    if (isinstance(k, str) and secret_name(k)) or (nv and k == 'value'):
        return '[redacted]'
    kind = PII_KEY_KIND.get(k.lower()) if isinstance(k, str) else None  # Round 13: a PII key whose value looks like its kind
    if kind and (isinstance(x, str) or (isinstance(x, (int, float)) and not isinstance(x, bool))) and _pii_value(kind, str(x)):
        return '[redacted:%s]' % kind
    return deep_redact(x, depth + 1)
