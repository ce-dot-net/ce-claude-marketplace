"""Differential test (Round 17): the current redaction against the FROZEN base 36159e0 (tests/fixtures/redact-base-36159e0), both chains.
Release criterion: no regression against 36159e0. A regression is a stretch of input that the base redacted and that the current chain
leaves visible (the label may change, the stretch must stay covered). Stretches with fewer than 4 alnum chars are not compared.
Corpus (fixed seeds): the secret-filter fixture, the Opus probe cases (tests/fixtures/redact_probes.json), the Opus IBAN generator of
round 16 (iban16, seed 1616; its two-IBAN and lead blocks in full, every 40th case of the main block), the round 17 IBAN cases and a
mixed generator (seed 17), keyed cases (seed 171) and meta-text contexts (seed 1818: the call / exception forms inside lists, quotes,
brackets and long prose). The generated IBANs are also checked absolutely: none may survive in the current output (Opus leak rule).
Exceptions: EXCEPTIONS below, one predicate per FORM of an intentionally removed false alarm, each with its reason."""
import importlib.util
import json
import os
import random
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "ace"
BASE = ROOT / "tests" / "fixtures" / "redact-base-36159e0"
sys.path.insert(0, str(ROOT / "tests"))
import test_secret_filter_py as sf  # noqa: E402  (fixture recipes + round 17 IBAN cases)


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


base_py = _load(BASE / "redact.py", "redact_base_36159e0")
new_py = sf.rd

# ---------------- corpus ----------------


def _iban16_cases():
    """Port of the Opus round 16 generator (iban16.py, random.Random(1616)): (text, [ibans]); the same draws in the same order."""
    rng = random.Random(1616)
    LEN = dict(new_py.IBAN_LEN)

    def num(s):
        return int("".join(str(int(ch, 36)) for ch in s))

    def make(cc, bban):
        return "%s%02d%s" % (cc, 98 - num(bban + cc + "00") % 97, bban)

    def bbans(cc):
        n = LEN[cc] - 4
        D, A, U = "0123456789", "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        return ["".join(rng.choice(D) for _ in range(n)), "".join(rng.choice(A) for _ in range(4)) + "".join(rng.choice(D) for _ in range(n - 4)),
                "".join(rng.choice(U) for _ in range(n)), "".join(rng.choice(D) for _ in range(n - 3)) + "".join(rng.choice(A) for _ in range(3))]

    def render(iban, sep, case):
        t = iban if sep is None else sep.join(iban[i:i + 4] for i in range(0, len(iban), 4))
        if case == "lower":
            t = t.lower()
        elif case == "mixed":
            t = "".join(ch.lower() if rng.random() < 0.5 else ch for ch in t)
        return t

    SEPS = [" ", "\t", "\u00a0", "\u202f", "\u2009"]
    PRE = ["", "IBAN ", "an ", "Konto: ", "(", "IBAN: ", "\n"]
    FOL = ["", " bis Freitag", " und BIC", " a", " zu", " bis", " oder", " Bank", " BIC", " BANK", " 2024", " 1", " 12", " 123", " 1234",
           " 12345678", ".", ",", ")", ";", "\n", " ü", " überweisen", "-", "/", " IBAN", " EUR", " für Max", " ab", " ok"]
    main, pairs, leads = [], [], []
    for cc in sorted(LEN):
        for b in bbans(cc):
            iban = make(cc, b)
            for sep in [None] + SEPS:
                for case in ("upper", "lower", "mixed"):
                    body = render(iban, sep, case)
                    for p in PRE:
                        for f in FOL:
                            if rng.random() < 0.25 or (p == "" and case == "upper"):
                                main.append((p + body + f, [iban]))
    for _ in range(3000):
        a, b = rng.sample(sorted(LEN), 2)
        i1, i2 = make(a, rng.choice(bbans(a))), make(b, rng.choice(bbans(b)))
        sep = rng.choice([None, " ", " ", "\t"])
        mid = rng.choice([" ", " oder ", " und ", " bzw ", " alt ", " neu ", " IBAN ", "\t", ", ", " / ", " or ", " plus ", " Bank "])
        pairs.append(("IBAN " + render(i1, sep, rng.choice(["upper", "lower"])) + mid + render(i2, sep, rng.choice(["upper", "lower"])), [i1, i2]))
    for _ in range(2000):
        cc = rng.choice(sorted(LEN))
        i1 = make(cc, rng.choice(bbans(cc)))
        sep = rng.choice([None, " "])
        lead = rng.choice(["KW47", "kw48", "AB12", "Re24", "ID42", "DE00", "AT12", "Nr12", "DE12 3456", "Q324", "v1.2 RC12", "KW47:"])
        leads.append(("Zahlung " + lead + " " + render(i1, sep, "upper") + " danke", [i1]))
    return main[::40] + pairs + leads


def _mixed_cases():
    """Random combinations of PII / key / number fragments (random.Random(17))."""
    rng = random.Random(17)
    low = "abcdefghijklmnopqrstuvwxyz"
    dig = lambda n: "".join(rng.choice("0123456789") for _ in range(n))
    word = lambda n: "".join(rng.choice(low) for _ in range(n))
    vals = [lambda: word(5) + "@" + word(7) + rng.choice([".com", ".de", ".io", ".org", ".net", ".berlin", ".co.uk", ".gz", ".png"]),
            lambda: word(4) + "." + word(5) + "@" + word(6) + ".com",
            lambda: "+49 30 " + dig(7), lambda: "+1 415 555 " + dig(4), lambda: "030 " + dig(7), lambda: "0151 " + dig(8),
            lambda: "(030) 123 45 " + dig(2), lambda: "089/" + dig(7), lambda: "DE89 3704 0044 0532 0130 00", lambda: "AT611904300234573201",
            lambda: "GB82 WEST 1234 5698 7654 32", lambda: "2026-11-" + dig(2), lambda: "+" + dig(1) + "." + dig(3), lambda: dig(9),
            lambda: "v" + dig(1) + "." + dig(2) + "." + dig(1), lambda: "192.168." + dig(1) + "." + dig(2)]
    pres = ["", "Kontakt: ", "Tel ", "Telefon: ", "iban: ", "IBAN ", "mail: ", "Fax: ", "Mobil: ", "see ", "call ", "phone=", '"email": "',
            "Handy ", "WhatsApp ", "Durchwahl ", "E-Mail: ", "Rufnummer ", "tel: ", "cell: ", "phone_number: "]
    sufs = ["", " bitte", ".", ")", " (privat)", "\n", " 2024", '"', ", danke"]
    out = []
    for _ in range(3000):
        out.append(" ".join(rng.choice(pres) + rng.choice(vals)() + rng.choice(sufs) for _ in range(rng.randint(1, 3))))
    return out


def _keyed_cases():
    """A phone number / address behind a key or keyword the current rules know (random.Random(171)): (text, [value]); the value must go."""
    rng = random.Random(171)
    dig = lambda n: "".join(rng.choice("0123456789") for _ in range(n))
    word = lambda n: "".join(rng.choice("abcdefghijklmnopqrstuvwxyz") for _ in range(n))
    phones = [lambda: "+49 30 " + dig(7), lambda: "030 " + dig(7), lambda: "0151 " + dig(8), lambda: "(030) 123 45 " + dig(2), lambda: "089/" + dig(7)]
    phone_keys = ["Telefon: ", "phone=", "phone_number: ", "tel: ", "workPhone: ", "home_phone: ", "Fax: ", "Mobil: ", "Telefax: ", "Durchwahl: ",
                  "Fon: ", "phone_2: ", "Handynummer: ", "Mobiltelefon: ", "Tel.-Nr. "]
    mail_keys = ["mail: ", "E-Mail: ", "email=", "Kontakt: ", ""]
    sufs = ["", " bitte", ".", ", danke", "\n"]
    out = []
    for _ in range(1500):
        if rng.random() < 0.6:
            v = rng.choice(phones)()
            out.append((rng.choice(phone_keys) + v + rng.choice(sufs), [v]))
        else:
            v = word(5) + rng.choice(["", "."]) + word(3) + "@" + word(7) + rng.choice([".com", ".de", ".io", ".org", ".net"])
            out.append((rng.choice(mail_keys) + v + rng.choice(sufs), [v]))
    return out


def _call_form_cases():
    """Code / log text after 'call' that the base redacted as a phone number and the current rules keep (one per exception form)."""
    out = []
    for i, (name, ext) in enumerate([("redact", "py"), ("trace", "ts"), ("main", "go"), ("lib", "rs"), ("index", "js"), ("Makefile", "mk")]):
        for a, b in [("123", "456"), ("1234", "5678"), ("12345", "12399"), ("1234567", "1234599")]:
            out += ["tool call: %s.%s:%s-%s" % (name, ext, a, b), "call in src/%s.%s:%s-%s" % (name, ext, a, b)]
    for a, b in [("123", "456"), ("999", "999"), ("1234", "5678"), ("100", "1000")]:
        out += ["call ratio %s/%s done" % (a, b), "api call progress %s/%s" % (a, b)]
    out += ["call timeout 123456789", "tool call took 1234567890 ns", "call settled 987654321", "call ratio 123456789012"]
    for d in ("123456", "1234567", "12345678"):
        out += ["call timeout %s" % d, "call(timeout=%s)" % d, "call with timeout: %s ms" % d, "tool call took %s ns" % d, "call took %s us" % d,
                "call took %s ms, ok" % d, "API call %s ok" % d, "call(%s)" % d,
                "function call used %s bytes" % d]
    return out


# genuine PII shapes that no exception may excuse (span, context): an over-wide predicate turns this check red
# Known limit (Round 18 / N5): shapes here cover the call / quoted-rest / decimal forms; date, ipv4, file-tld, asset-scale, code-call,
# diffstat, dd-mm-prefix and app-version have no counter shape yet (they are guarded only by being used and by their narrow form).
COUNTER = [("015112345678", "call 015112345678"), ("030.1234567", "call 030.1234567"), ("5550123", "call or fax 5550123"), ("91234567", "Call or WhatsApp 91234567"),
           ("299839", "Call (mobil): 299839"), ("0301234567", "call Tel.Nr:0301234567"), ("0301234567", "call(0301234567)"), ("5550123", "call  me 5550123"), ("0301234567,0301234568", 'telephone: "0301234567,0301234568"'), ("4155550123", "call 4155550123"), ("+49 30 1234-5678", "call +49 30 1234-5678"), ("1234-5678", "call Tel 1234-5678"), ("030 1234-5678", "call 030 1234-5678"),
           ("089/1234567", "call 089/1234567"), ("12345/678901", "call 12345/678901"), ("030 1234567", "call timeout 030 1234567"),
           ("0151 12345678", "call timeout 0151 12345678"), ("0301234567", "call took 0301234567 ns"),
           ("030 1234567", "call took 030 1234567 ns"), ("1234-5678", "call x.py 1234-5678"), ("0301234567", "call used 0301234567 bytes"), ("030 1234567", "call used 030 1234567 bytes"),
           ("030 12345678", "call 030 12345678")]


def _meta_cases():
    """Round 18c: the call / exception forms embedded in meta text (lists, quotes, brackets, review notes, long prose before them;
    random.Random(1818)), so a context-dependent miss is caught: (text, [secret values that must go])."""
    rng = random.Random(1818)
    secret = list(sf.R18B_REDACT) + [("call 030.1234567", "030.1234567"), ("Please call 030 1234567 tomorrow", "030 1234567")]
    stay = sf.R18B_STAY + _call_form_cases()[::7] + ["+2026-11-24 10:00:00 deploy", "logo@2x.png", "q@k.transpose(x)", "3 files changed, +13989/-4568"]
    st = " ".join(_strip(x) for x in stay)
    secret = [(x, v) for x, v in secret if _strip(v) not in st and _strip(v)[-8:] not in st]  # the leak check is by value: no value a stay form also holds
    words = "the of and redact phone keyword COUNTER exception case review round regex test differential base form chain".split()
    prose = lambda n: " ".join(rng.choice(words) for _ in range(n))
    wraps = ["COUNTER + ('x', '{t}')", "`{t}`, ", '("x", "{t}"),', "- {t}\n", "({t})", "'{t}' -> ", "{t}; ", "[{t}] ", "Fixes: '{t}' stay readable. "]
    out = []
    for _ in range(160):
        parts, sec = [prose(rng.randint(0, 40))], []
        for _ in range(rng.randint(1, 12)):
            if rng.random() < 0.5:
                t, v = rng.choice(secret)
                sec.append(v)
            else:
                t, v = rng.choice(stay), "x"
            parts.append(rng.choice(wraps).format(t=t))
        if rng.random() < 0.25:
            parts.insert(0, prose(rng.randint(600, 1200)))  # 4-8 KB
        out.append((" ".join(parts), sec))
    return out


def _probes():
    d = json.loads((ROOT / "tests" / "fixtures" / "redact_probes.json").read_text())
    objs = json.loads(json.dumps(d["objects"]).replace("@@GHP@@", "gh" + "p_"))
    return d["texts"], objs


def corpus():
    """(texts, objects, truth): truth = [(text index, [secret values])] for the absolute check (generated IBANs, keyed numbers / addresses)."""
    texts = [t for _, t, _ in sf.SECRETS] + sf.NORMAL + [t for _, t, _ in sf.PII_SECRETS] + sf.PII_NORMAL
    ptexts, objs = _probes()
    texts += ptexts
    truth = []
    for t, ibans in _iban16_cases() + [(t, i) for t, i, _ in sf._r17_cases()] + _keyed_cases() + [(t, [s]) for t, s in sf.R18B_REDACT] + _meta_cases():
        truth.append((len(texts), ibans))
        texts.append(t)
    texts += _mixed_cases() + _call_form_cases() + [
        k % v for k in ('x telephone: "%s" bitte', "telephone: '%s'", '{"telephone": "%s"}') for v in ("0301234567,next", "1234567;rest", "089123456;privat")]
    return texts, objs, truth


# ---------------- comparison ----------------
MARK = re.compile(r"\[redacted(?::[A-Za-z0-9:._-]+)?\]")
_strip = lambda s: re.sub(r"[^A-Za-z0-9]", "", s).upper()


def _kept(inp, out):
    """The input ranges an output keeps verbatim: the text between labels, matched in order (first piece = prefix, last = suffix)."""
    pieces = MARK.split(out)
    if len(pieces) == 1:
        return [(0, len(inp))] if out == inp else []
    res, pos = [], 0
    for k, p in enumerate(pieces):
        if not p:
            continue
        if k == 0:
            i = 0 if inp.startswith(p) else -1
        elif k == len(pieces) - 1:
            i = len(inp) - len(p) if inp.endswith(p) and len(inp) - len(p) >= pos else -1
        else:
            i = inp.find(p, pos)
        if i < 0:
            continue  # a rewritten piece ('echo [redacted] |'): not counted as kept
        res.append((i, i + len(p)))
        pos = i + len(p)
    return res


def _redacted_spans(inp, out, with_pos=False):
    """The maximal input stretches an output does not keep, with >= 4 alnum chars."""
    keep = bytearray(len(inp))
    for a, b in _kept(inp, out):
        keep[a:b] = b"\x01" * (b - a)
    spans, i = [], 0
    while i < len(inp):
        if keep[i]:
            i += 1
            continue
        j = i
        while j < len(inp) and not keep[j]:
            j += 1
        if len(_strip(inp[i:j])) >= 4:
            spans.append((i, j) if with_pos else inp[i:j])
        i = j
    return spans


def text_regressions(inp, base_out, new_out, with_ctx=False):
    """Stretches the base redacted of which the new output keeps >= 4 alnum chars in place (full or partial disclosure). The new
    output's kept chars come from the same in-order piece match as the base's (_kept), so a number that occurs twice is judged
    where it stands (Round 18c: the global count and difflib could pin a kept number on another occurrence in a long text)."""
    if base_out == inp or new_out == base_out:
        return []
    nk = bytearray(len(inp))
    for a, b in _kept(inp, new_out):
        nk[a:b] = b"\x01" * (b - a)
    out = []
    for i, j in _redacted_spans(inp, base_out, True):
        if sum(1 for k in range(i, j) if nk[k] and inp[k].isascii() and inp[k].isalnum()) >= 4:
            sp, s = inp[i:j], max(0, i - 80)
            while inp.find(sp, s) != i:  # a context in which the span's first occurrence is this one (the predicates look it up)
                s += 1
            out.append((sp, inp[s:j + 80]) if with_ctx else sp)
    return out


def _leaves(x):
    if isinstance(x, dict):
        for v in x.values():
            yield from _leaves(v)
    elif isinstance(x, list):
        for v in x:
            yield from _leaves(v)
    elif isinstance(x, (str, int, float)) and not isinstance(x, bool):
        yield str(x)


def object_regressions(inp, base_out, new_out):
    sb, sn = _strip(json.dumps(base_out, ensure_ascii=False)), _strip(json.dumps(new_out, ensure_ascii=False))
    return [v for v in _leaves(inp) if len(_strip(v)) >= 4 and sn.count(_strip(v)) > sb.count(_strip(v))]


# ---------------- exceptions: intentionally removed false alarms, by form ----------------
# each: (name, reason, predicate(span, new_output, context) -> bool); span = the stretch the base redacted, context = the whole input
_DATE = re.compile(r"(?<![\d.])(?:\d{4}-\d{2}-\d{2}|\d{1,2}\.\d{1,2}\.\d{2,4}|\d{4}[./]\d{2}[./]\d{2}|\d{1,2}/\d{1,2}/\d{4})(?![\d.])")
def _before(sp, ctx):
    i = ctx.find(sp)
    return ctx[:i] if i > 0 else ""


def _after_call(sp, ctx):
    """The base's 'call' keyword rule: 'call' (not 'call me' / 'call us') and up to 20 non-digit chars right before the span."""
    g = re.search(r"\bcall\b(?![ \t]+(?:me|us)\b)([^\n0-9]{0,20})$", _before(sp, ctx), re.I)
    # Round 18b / B1': a gap holding another phone keyword ('call or fax 5550123') is that keyword's number, never a call exception
    return bool(g) and not re.search(r"tel|phone|mobil|handy|fax|whatsapp|fon|cell|rufnummer|festnetz|durchwahl", g.group(1), re.I)


# frozen here (not read from the rules under test, so a widened rule table cannot widen its own exception)
FILE_TLDS = {"png", "jpg", "jpeg", "gif", "svg", "webp", "ico", "gz", "tgz", "zip", "js", "mjs", "cjs", "ts", "tsx", "jsx", "json", "css", "map"}
EXCEPTIONS = [
    ("date", "a date or ISO date behind '+' is no phone number (Round 14, PHONE_REJECT)",
     lambda sp, out, ctx: bool(_DATE.search(sp)) and len(re.sub(r"\D", "", sp)) <= 14),
    ("diffstat", "a diffstat '+N/-N' is no phone number (Round 14)", lambda sp, out, ctx: bool(re.search(r"\d{1,6}/-\d{1,6}", sp))),
    # the base read 'call' + up to 20 non-digit chars + 6-15 digits as a phone number. Round 18 / B1: behind 'call' only a phone-shaped
    # number counts (KW_CALL_PHONE); the forms below are the code / log numbers that stay, each defined narrowly.
    ("call-compact", "a compact number of 6-8 digits without a leading 0 after 'call' (call(123456), API call 20261124, call took 1234567 ns, "
     "call timeout 123456, call used 1234567 bytes) is code or a log; 9+ digits, a leading 0, a space, '-', '.' or ')' are a phone number",
     lambda sp, out, ctx: _after_call(sp, ctx) and bool(re.fullmatch(r"[1-9]\d{5,7}", sp.strip()))
     or bool(re.search(r"\bcall\($", _before(sp, ctx), re.I)) and bool(re.fullmatch(r"[1-9]\d{5,14}", sp.strip()))),
    ("call-codeword", "a compact number after a code word behind 'call' ('call timeout 123456789', took, settled, used, ratio) is a log value (Round 18b)",
     lambda sp, out, ctx: _after_call(sp, ctx) and bool(re.fullmatch(r"[1-9]\d{5,14}", sp.strip()))
     and bool(re.search(r"(?:^|[^A-Za-z])(?:timeout|took|settled|used|ratio)[ \t:=]*$", _before(sp, ctx), re.I))),
    ("call-line-range", "a line range behind a file name ('tool call: redact.py:1234-5678') is no phone number",
     lambda sp, out, ctx: _after_call(sp, ctx) and bool(re.fullmatch(r"\d{1,7}-\d{1,7}", sp.strip()))
     and bool(re.search(r"[A-Za-z0-9_]\.[A-Za-z0-9]{1,5}:$", _before(sp, ctx)))),
    ("call-fraction", "a fraction / progress 'NNN/NNN' of at most 4 digits per side ('call ratio 123/456') is no phone number",
     lambda sp, out, ctx: _after_call(sp, ctx) and bool(re.fullmatch(r"\d{3,4}/\d{3,4}", sp.strip()))),
    ("quoted-rest", "a word after ',' / ';' behind a phone number inside a quoted key value ('telephone: \"0301234567,next\"'): the phone "
     "keyword rule takes the number, the base took the whole value; the word is no phone number",
     lambda sp, out, ctx: bool(re.fullmatch(r"([0-9]{6,15})([,;][A-Za-z]{1,16})", sp))
     and "[redacted:phone]" + sp[len(re.match(r"[0-9]+", sp).group()):] in out),
    ("decimal", "a decimal number, also behind '+', is no phone number (Round 14)", lambda sp, out, ctx: bool(re.fullmatch(r"\+?(?!0\d)\d{1,6}[.,]\d+", sp.strip()))),
    ("ipv4", "an IPv4 address / CIDR, also behind '+', is no phone number (Round 14)",
     lambda sp, out, ctx: bool(re.search(r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}", sp))),
    ("app-version", "a version behind 'WhatsApp/' or another keyword and '/' is no phone number (Round 15, KW_VERSION)",
     lambda sp, out, ctx: bool(re.search(r"/" + re.escape(sp.strip()), ctx)) and bool(re.fullmatch(r"\d{1,4}(?:\.\d{1,4}){1,4}", sp.strip()))),
    ("dd-mm-prefix", "a 'DD.MM.' date prefix is no phone number", lambda sp, out, ctx: bool(re.match(r"\s*\+?\d{1,2}\.\d{1,2}\.", sp))),
    ("asset-scale", "an asset file name 'logo@2x.png' is no e-mail (EMAIL_SCALE)", lambda sp, out, ctx: bool(re.search(r"@\d+(?:\.\d+)?x\.", sp))),
    ("file-tld", "an address whose TLD is a file extension (.gz, .zip, .png ...) is no e-mail (EMAIL_FILE_TLDS)",
     lambda sp, out, ctx: "@" in sp and sp.strip().rsplit(".", 1)[-1].lower() in FILE_TLDS),
    ("code-call", "x@y.name( / x@y.name[ with a TLD of more than 3 letters is code (a decorator, a method call), no e-mail (Round 16)",
     lambda sp, out, ctx: "@" in sp and bool(re.search(re.escape(sp.strip()) + r"[(\[]", ctx))
     and len(sp.strip().rsplit(".", 1)[-1]) > 3),
    ("prototype-key", "a key named like an Object.prototype member (__proto__, constructor, toString ...) is no PII key; the base's TS lookup "
     "read the inherited member and labelled its value (Round 14: own keys only)",
     lambda sp, out, ctx: bool(re.search(r'"(?:__proto__|constructor|toString|valueOf|hasOwnProperty)": "?' + re.escape(sp) + r'(?![0-9])', ctx))),
]


def unexpected(regs):
    """(case, span, context) regressions that no exception covers."""
    return [r for r in regs if not any(p(r[1], r[2], r[3]) for _, _, p in EXCEPTIONS)]


def check_exceptions(regs, unused_ok=()):
    """Every exception is used by at least one regression, and none excuses a COUNTER shape."""
    used = {n for r in regs for n, _, p in EXCEPTIONS if p(r[1], r[2], r[3])}
    assert {n for n, _, _ in EXCEPTIONS} - used - set(unused_ok) == set()
    assert [(n, c) for c in COUNTER for n, _, p in EXCEPTIONS if p(c[0], "", c[1])] == []


def _ts_outputs(texts, objs, tmp_path):
    bun = shutil.which("bun")
    if not bun:
        pytest.skip("bun not installed") if os.environ.get("ACE_ALLOW_NO_BUN") == "1" else pytest.fail("bun missing: the TS/Python parity tests must run (ACE_ALLOW_NO_BUN=1 skips them locally)")
    (tmp_path / "in.json").write_text(json.dumps([texts, objs]))
    (tmp_path / "d.ts").write_text(
        "import * as B from '%s'\nimport * as N from '%s'\nconst [t, o] = JSON.parse(require('fs').readFileSync('%s', 'utf8'))\n"
        "const run = (M: any) => [t.map((x: string) => M.redact(x)), o.map((x: any) => M.deepRedact(x))]\n"
        "require('fs').writeFileSync('%s', JSON.stringify([run(B), run(N)]))\n"
        % (BASE / "redact.ts", PLUGIN / "mod" / "lib" / "redact.ts", tmp_path / "in.json", tmp_path / "out.json"))
    p = subprocess.run([bun, str(tmp_path / "d.ts")], capture_output=True, text=True, timeout=300)
    assert p.returncode == 0, p.stderr
    return json.loads((tmp_path / "out.json").read_text())


def regressions(texts, objs, base, new):
    (bt, bo), (nt, no) = base, new
    regs = [("text", sp, nt[i], ctx) for i in range(len(texts)) for sp, ctx in text_regressions(texts[i], bt[i], nt[i], True)]
    regs += [("object", v, json.dumps(no[i], ensure_ascii=False), json.dumps(objs[i], ensure_ascii=False)) for i in range(len(objs))
             for v in object_regressions(objs[i], bo[i], no[i])]
    return regs


def truth_leaks(texts, truth, outs):
    """Opus leak rule: a secret value (separators stripped, upper case) or its last 8 chars survive in the stripped output."""
    return [(texts[i], outs[i]) for i, xs in truth if any(_strip(x) in _strip(outs[i]) or _strip(x)[-8:] in _strip(outs[i]) for x in xs)]


# a lead token plus the first groups of the IBAN that happen to form a valid IBAN of the lead's country (1 in 97): the real IBAN loses
# only its head; proven per case by the mod-97 of the swallowing walk
def _random_hit(text):
    for m in re.finditer(r"(?<![A-Za-z0-9])[A-Za-z]{2}[0-9]{2}", text):
        e = new_py._iban_walk(text, m.start())
        if e >= 0 and re.search(r"(?<![A-Za-z0-9])[A-Za-z]{2}[0-9]{2}", text[m.end():e]):
            return True
    return False


def _py_outputs(mod, texts, objs):
    return [mod.redact(t) for t in texts], [mod.deep_redact(json.loads(json.dumps(o))) for o in objs]


def test_differential_python(tmp_path):
    texts, objs, truth = corpus()
    assert len(texts) >= 15000
    base, new = _py_outputs(base_py, texts, objs), _py_outputs(new_py, texts, objs)
    regs = regressions(texts, objs, base, new)
    left = unexpected(regs)
    check_exceptions(regs, unused_ok=("prototype-key",))  # the Python base read own keys already
    if os.environ.get("ACE_DIFF_DUMP"):
        Path(os.environ["ACE_DIFF_DUMP"]).write_text(json.dumps({"cases": len(texts) + len(objs), "regressions": len(regs), "left": left}, ensure_ascii=False, indent=1))
    assert left == []
    assert [x for x in truth_leaks(texts, truth, new[0]) if not _random_hit(x[0])] == []
    assert [o for o in new[0] if "[redacted:None]" in o or "[redacted:undefined]" in o] == []  # Round 18b: every PII key resolves its kind


def test_differential_typescript(tmp_path):
    texts, objs, truth = corpus()
    base, new = _ts_outputs(texts, objs, tmp_path)
    regs = regressions(texts, objs, base, new)
    check_exceptions(regs)
    assert unexpected(regs) == []
    assert [x for x in truth_leaks(texts, truth, new[0]) if not _random_hit(x[0])] == []
    assert [o for o in new[0] if "[redacted:None]" in o or "[redacted:undefined]" in o] == []  # Round 18b: every PII key resolves its kind
