"""Per-rule hostile inputs, derived from the rule tables (shared-hooks/utils/redact.py) so that a NEW rule gets a hostile test automatically.
Registry: plugins/ace/tests-fixtures/secret-filter/hostile_rules.json. Every rule is listed there (its inputs derived from the regex source),
with extra hand-picked units, or marked 'linear' with a reason. TS twin: plugins/ace/mod/tests/hostile_gen.ts (same derivation)."""
import json
import re
from pathlib import Path

REGISTRY = Path(__file__).resolve().parent.parent / "plugins" / "ace" / "tests-fixtures" / "secret-filter" / "hostile_rules.json"


def registry():
    return json.loads(REGISTRY.read_text())["rules"]


def table_rules(rd):
    out = []
    for n, r, _b in rd.SPAN_RULES:
        out.append(("span:" + n, [x.pattern for x in (r if isinstance(r, tuple) else (r,))]))
    for n, r, _rep in rd.SECRET_RULES:
        out.append(("secret:" + n, [r.pattern]))
    for n, r in rd.PREFIX_RULES:
        out.append(("prefix:" + n, [r.pattern]))
    for row in rd.FORMAT_RULES:
        out.append(("format:" + row[0], [row[1].pattern]))
    for row in rd.NV_RULES:
        out.append(("nv:" + row[0], [row[1].pattern]))
    for row in rd.PII_RULES:
        out.append(("pii:" + row[0], [row[3].pattern]))
    out += [("env-line", [rd.ENV_LINE.pattern]), ("url-cred", [rd.URL_CRED.pattern]), ("entropy-run", [rd.ENTROPY_RUN.pattern])]
    return out


def derive_units(sources):
    words, fillers = set(), []

    def add(c):
        if c not in fillers:
            fillers.append(c)

    for src in sources:
        cls, cur, i = False, "", 0

        def flush():
            nonlocal cur
            if len(cur) >= 3 and re.search("[A-Za-z]", cur):
                words.add(cur)
            cur = ""
        while i < len(src):
            c = src[i]
            if c == "\\":
                flush()
                i += 1
                n = src[i] if i < len(src) else ""
                if n == "d":
                    add("1")
                elif n == "s":
                    add(" ")
                elif n == "w":
                    add("a")
                i += 1
                continue
            if cls:
                if c == "]":
                    cls = False
                i += 1
                continue
            if c == "[":
                flush()
                cls = True
                n = src[i + 1] if i + 1 < len(src) else ""
                if n not in ("^", "\\", "]", "") and " " <= n <= "~":
                    add(n)
                i += 1
                continue
            if re.match("[A-Za-z0-9_-]", c):
                cur += c
            else:
                flush()
            i += 1
        flush()
    add("a")
    ws = sorted(words, key=lambda w: (-len(w), w))[:2]
    f = next((x for x in fillers if x not in ("a", " ")), "a") * 8
    return [ws[0] + " ", ws[0] + f + " ", (ws[1] if len(ws) > 1 else ws[0]) + ":"] if ws else [f, f + "@", f + " "]


def hostile_cases(rd):
    reg, out = registry(), []
    for rid, srcs in table_rules(rd):
        d = reg.get(rid)
        if d and d.get("linear"):
            continue
        for u in dict.fromkeys(derive_units(srcs) + (d or {}).get("units", [])):
            out.append((rid, u))
    for rid, d in reg.items():
        if rid.startswith("engine:"):
            out += [(rid, u) for u in d.get("units", [])]
    return out


def build(unit, size):
    return unit * max(1, -(-size // len(unit))) + "\x01"
