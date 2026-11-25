"""Round 5 C2: the Python chain sends task/summary uncut, so its redact (utils/redact.py, re-exported by ace_after_task.redact) carries the SAME rules as the mod
(mod/lib/redact.ts + redact_rules.ts): PEM private keys, known prefixes, .env lines (also behind a tool prefix), user:pass@host, high entropy
(length-aware, with the SHA/UUID/object-id exceptions), and the F4 formats (.netrc, .pgpass, docker auth, cookie jar, PHP define).
One shared fixture of RECIPES: tests-fixtures/secret-filter/cases.json (the mod reads a GENERATED copy, guarded here)."""
import json
import os
import re
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "ace"
sys.path.insert(0, str(PLUGIN / "shared-hooks"))
sys.path.insert(0, str(PLUGIN / "shared-hooks" / "utils"))
import ace_after_task as at  # noqa: E402
import redact as rd  # noqa: E402
from timing_util import BUN_LINEAR_JS, LIMIT, assert_linear, prefix  # noqa: E402

FIX = PLUGIN / "tests-fixtures" / "secret-filter" / "cases.json"
CASES = json.loads(FIX.read_text())

M = 0xFFFFFFFF
_x = [2463534242]
def _next():
    x = _x[0]
    x ^= (x << 13) & M
    x ^= x >> 17
    x ^= (x << 5) & M
    _x[0] = x
    return x
def _pick(alpha, n):
    return "".join(alpha[_next() % len(alpha)] for _ in range(n))
B62 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
B36 = "abcdefghijklmnopqrstuvwxyz0123456789"
HEX = "0123456789abcdef"
def _b36s():
    while True:
        v = "cl" + _pick(B36, 28)
        k = sum(1 for i in range(1, len(v)) if v[i].isdigit() != v[i - 1].isdigit())
        if k / (len(v) - 1) >= 0.5 and re.search(r"[0-9]", v):
            return v
GEN = {"r62": lambda n: _pick(B62, n), "r64": lambda n: _pick(B62 + "+/", n), "rUP": lambda n: _pick("ABCDEFGHIJKLMNOPQRSTUVWXYZ234567", n),
       "rlow": lambda n: _pick(B36, n), "rhex": lambda n: _pick(HEX, n), "rHEX": lambda n: _pick(HEX.upper(), n),
       "uuid": lambda n: f"{_pick(HEX, 8)}-{_pick(HEX, 4)}-4{_pick(HEX, 3)}-a{_pick(HEX, 3)}-{_pick(HEX, 12)}", "b36s": lambda n: _b36s(), "rdig": lambda n: _pick("0123456789", n)}
def _build(parts):
    return "".join(p if isinstance(p, str) else GEN[p["g"]](p["n"]) for p in parts)
SECRETS = []
for c in CASES["secrets"]:
    pre, sec, post = _build(c["pre"]), _build(c["secret"]), _build(c["post"])
    SECRETS.append((c["kind"], pre + sec + post, sec))
NORMAL = [_build(p) for p in CASES["normal"]]
# Round 13: PII cases, drawn after NORMAL (the stream above stays as it was)
PII_SECRETS = []
for c in CASES["pii"]["secrets"]:
    pre, sec, post = _build(c["pre"]), _build(c["secret"]), _build(c["post"])
    PII_SECRETS.append((c["kind"], pre + sec + post, sec))
PII_NORMAL = [_build(p) for p in CASES["pii"]["normal"]]
PII_LABEL = re.compile(r"\[redacted:(?:email|phone|iban)\]")


def test_ts_copy_matches_the_shared_fixture():
    ts = (PLUGIN / "mod" / "tests" / "fixtures" / "secret_cases.ts").read_text()
    assert "export const CASES: any = " + json.dumps(CASES, ensure_ascii=False) + "\n" in ts


def test_fixture_size_and_no_token_literals_in_the_json():
    assert len(SECRETS) >= 30 and len(NORMAL) >= 30
    raw = FIX.read_text()
    for lit in ["sk-", "ghp_", "AKIA", "AIza", "glpat-", "sk_live_", "hf_", "-----BEGIN RSA PRIVATE KEY"]:
        assert lit not in raw, lit


@pytest.mark.parametrize("kind,text,secret", SECRETS, ids=[f"{k}:{i}" for i, (k, _, _) in enumerate(SECRETS)])
def test_secret_gone(kind, text, secret):
    r = at.redact(text)
    assert secret not in r and "[redacted" in r


def test_no_false_positive_on_the_normal_fixture():
    assert [x for x in NORMAL if at.redact(x) != x] == []


@pytest.mark.parametrize("kind", ["prefix:aws", "prefix:google", "prefix:gitlab", "prefix:stripe", "prefix:huggingface", "prefix:private-key",
                                  "netrc", "pgpass", "docker-auth", "cookie-jar", "php-define"])
def test_new_rules_label_their_kind(kind):
    cases = [(t, s) for k, t, s in SECRETS if k == kind and (kind != "prefix:aws" or "session" in t)]
    assert cases
    for t, s in cases:
        r = at.redact(t)
        assert "[redacted:%s]" % kind in r and s not in r, (kind, t[:20])


def test_env_lines_behind_a_tool_prefix_and_the_exact_forms():
    pre = [(t, s) for k, t, s in SECRETS if k == "env" and re.match(r"(\s*\d+[\t→]|[^\s:]+:\d+:|\s*- )", t)]
    assert len(pre) == 4
    for t, s in pre:
        assert "[redacted:env]" in at.redact(t) and s not in at.redact(t)
    assert at.redact("AUTH_SALT=abc123xyz") == "AUTH_SALT=[redacted:env]"
    assert at.redact("  12\tAUTHOR=dev team") == "  12\tAUTHOR=dev team"
    assert at.redact("redis at admin:pw1234@cache.example.org") == "redis at admin:[redacted:url-cred]@cache.example.org"
    assert at.redact("-----BEGIN PRIVATE KEY-----\nMHcCAQEE no end") == "[redacted:prefix:private-key]"


def test_the_trace_ids_stay():
    for x in ["df8abbe2-f788-4f32-8e3b-8b39cd5ae322", "70c1624", "844a5f1c3d2e1f00aa11bb22cc33dd44ee55ff66", "ctx-1916239599-9c56"]:
        assert at.redact(f"id {x} done") == f"id {x} done"


def test_entropy_thresholds_match_the_mod():
    ts = (PLUGIN / "mod" / "lib" / "redact_rules.ts").read_text()
    assert "ENTROPY_MIN = 4.0, ENTROPY_LEN_FACTOR = 0.85" in ts and "SWITCH_MIN = 0.35" in ts
    assert (rd.ENTROPY_MIN, rd.ENTROPY_LEN_FACTOR, rd.SWITCH_MIN) == (4.0, 0.85, 0.35)



def test_every_env_segment_redacts_on_its_own():
    """A harmless last segment keeps the line. A literal copy of ENV_SEGS / ENV_HARMLESS on purpose: a dropped row turns this red."""
    assert [x for x in ["SALT", "SIGNING", "DSN", "PRIVATE", "AUTH", "CRED", "CREDS", "CERT", "SEED", "SIG", "SIGNATURE", "HMAC", "ENCRYPTION", "OTP", "PASS", "PWD", "ACCESS", "SESSION"] if "[redacted" not in at.redact("X_%s=abc123" % x)] == []
    assert [x for x in ["TIMEOUT", "MINUTES", "SECONDS", "TTL", "URL", "HOST", "PORT", "NAME", "USER", "ID", "ENABLED", "MODE", "LEVEL", "PATH", "DIR", "FILE", "COUNT", "MAX", "MIN", "LIMIT"] if at.redact("X_AUTH_%s=abc123" % x) != "X_AUTH_%s=abc123" % x] == []


def test_keyword_and_flag_on_different_lines_redact_nothing():
    """A keyword-flag rule (mysql -p, zip -P, openssl -k, curl -u) needs both on ONE line (parity: mod tests/redact.test.ts)."""
    for t in ["mysql x\n -p secret", "zip a\n -P pw", "openssl x\n -k pw", "curl x\n -u a:b"]:
        assert at.redact(t) == t


def test_deep_redact_drops_the_value_under_a_secret_key():
    assert at.deep_redact({"env": {"API_KEY": "plainvalue", "nested": [{"token": "deepsecret"}], "path": "/a"}}) == \
        {"env": {"API_KEY": "[redacted]", "nested": [{"token": "[redacted]"}], "path": "/a"}}

@pytest.mark.parametrize("big", ["A1b2" * 500_000, "user:" * 400_000, "X_AUTH=" * 300_000, "-----BEGIN PRIVATE KEY-----" * 70_000,
                                 "token: abc\n\nplain line here\n" * 20_000 + "x" * 1_000_000, "machine x login y " * 120_000,
                                 "a:1:b:c:" * 250_000, "d\tTRUE\t/\tTRUE\t1\tn\t" * 100_000, "define('A_KEY', '" * 120_000])
def test_linear_on_hostile_inputs(big):
    assert_linear(at.redact, prefix(big), big[:12])



# ---- Shopify (Round 7): shpat_ / shpca_ / shppa_ / shpss_ + >= 32 hex (either case), word boundary before the prefix ----
def test_shopify_round7_no_token_literals_in_the_json():
    raw = FIX.read_text()
    for lit in ["shpat_", "shpca_", "shppa_", "shpss_"]:
        assert lit not in raw, lit


def test_shopify_round7_labels_its_kind_and_leaves_no_rest():
    cases = [(t, s) for k, t, s in SECRETS if k == "prefix:shopify"]
    assert len(cases) == 9  # round 8 I2: + one after a non-ASCII letter
    for t, s in cases:
        r = at.redact(t)
        # a token behind a secret key / header (JSON access_token, X-Shopify-Access-Token) goes by the older key rule ('[redacted]')
        labelled = "access_token" not in t.lower().replace("-", "_")
        assert s not in r and ("[redacted:prefix:shopify]" in r) == labelled and not re.search(r"\[redacted[^\]]*\][0-9a-fA-F]", r), t[:30]


def test_shopify_round7_rule_is_the_same_in_both_chains():
    ts = (PLUGIN / "mod" / "lib" / "redact_rules.ts").read_text()
    assert r"['shopify', /\bshp(?:at|ca|pa|ss)_[0-9a-fA-F]{32,}/g]" in ts
    assert dict(rd.PREFIX_RULES)["shopify"].pattern == r"\bshp(?:at|ca|pa|ss)_[0-9a-fA-F]{32,}"


# ---- round 8 I2: TS and Python give the SAME output on every fixture string (Unicode word boundaries, a lone CR, CRLF) ----
def test_round8_ts_and_python_redact_identically_on_the_whole_fixture(tmp_path):
    import shutil, subprocess
    bun = shutil.which("bun")
    if not bun:
        pytest.skip("bun not installed") if os.environ.get("ACE_ALLOW_NO_BUN") == "1" else pytest.fail("bun missing: the TS/Python parity tests must run (ACE_ALLOW_NO_BUN=1 skips them locally)")
    texts = [t for _, t, _ in SECRETS] + NORMAL
    (tmp_path / "in.json").write_text(json.dumps(texts))
    (tmp_path / "r.ts").write_text("import { redact } from '%s'\nconst t = JSON.parse(require('fs').readFileSync('%s', 'utf8'))\nconsole.log(JSON.stringify(t.map((x: string) => redact(x))))\n"
                                   % (PLUGIN / "mod" / "lib" / "redact.ts", tmp_path / "in.json"))
    p = subprocess.run([bun, str(tmp_path / "r.ts")], capture_output=True, text=True, timeout=120)
    assert p.returncode == 0, p.stderr
    diff = [(x[:40], ts[:60], at.redact(x)[:60]) for x, ts in zip(texts, json.loads(p.stdout)) if at.redact(x) != ts]
    assert diff == []


# ---- round 9 N6: CR-heavy text is linear in both chains (cookie-jar fields stop at CR as JS ^/$ do) ----
def _ts_ratio(tmp_path, n):
    import shutil, subprocess
    bun = shutil.which("bun")
    if not bun:
        pytest.skip("bun not installed") if os.environ.get("ACE_ALLOW_NO_BUN") == "1" else pytest.fail("bun missing: the TS/Python parity tests must run (ACE_ALLOW_NO_BUN=1 skips them locally)")
    (tmp_path / "t.ts").write_text("import { redact } from '%s'\n" % (PLUGIN / "mod" / "lib" / "redact.ts") + BUN_LINEAR_JS +
                                   "console.log(linear(f => 'x\\r'.repeat(Math.floor(%d * f)) + '\\tTRUE\\tx', redact))\n" % n)
    return float(subprocess.run([bun, str(tmp_path / "t.ts")], capture_output=True, text=True, timeout=120).stdout)


def test_round9_cr_heavy_text_is_linear_python():
    assert_linear(at.redact, lambda f: "x\r" * int(1_000_000 * f) + "\tTRUE\tx")   # 2 MB, one CR per 2 chars: quadratic would take minutes


def test_round9_cr_heavy_text_is_linear_ts(tmp_path):
    assert _ts_ratio(tmp_path, 1_000_000) <= LIMIT


# ---- round 9 N7: \s / \S in the env / url-cred / pgpass rules mean JS's whitespace set in both chains ----
WS_EDGE = ["AUTH_SALT=\x85saltvalue-ab12cd", "AUTH_SALT=﻿saltvalue-ab12cd", "AUTH_SALT=\x1csaltvalue-ab12cd",
           "redis at\x1cadmin:pw1234@cache.example.org", "redis at﻿admin:pw1234@cache.example.org", "redis at\x85admin:pw1234@cache.example.org",
           "db\x1cx:5432:app:svc:hunter2pw", "db.example:5432:app:svc:hunter2\x85pw", "db.example:5432:app:svc:hunter2﻿pw",
           "12 AUTH_SALT=saltvalue-ab12cd", "src/x　y:3:AUTH_SALT=saltvalue-ab12cd", "AUTH_SALT= saltvalue-ab12cd"]


def test_round9_whitespace_parity_ts_python(tmp_path):
    import shutil, subprocess
    bun = shutil.which("bun")
    if not bun:
        pytest.skip("bun not installed") if os.environ.get("ACE_ALLOW_NO_BUN") == "1" else pytest.fail("bun missing: the TS/Python parity tests must run (ACE_ALLOW_NO_BUN=1 skips them locally)")
    (tmp_path / "in.json").write_text(json.dumps(WS_EDGE))
    (tmp_path / "r.ts").write_text("import { redact } from '%s'\nconst t = JSON.parse(require('fs').readFileSync('%s', 'utf8'))\nconsole.log(JSON.stringify(t.map((x: string) => redact(x))))\n"
                                   % (PLUGIN / "mod" / "lib" / "redact.ts", tmp_path / "in.json"))
    p = subprocess.run([bun, str(tmp_path / "r.ts")], capture_output=True, text=True, timeout=120)
    assert p.returncode == 0, p.stderr
    diff = [(repr(x), ts, at.redact(x)) for x, ts in zip(WS_EDGE, json.loads(p.stdout)) if at.redact(x) != ts]
    assert diff == []


def test_round9_explicit_whitespace_set_is_the_same_in_both_chains():
    ts = (PLUGIN / "mod" / "lib" / "redact_rules.ts").read_text()
    assert r"const JS_WS = String.raw`\t\n\v\f\r    -     　﻿`" in ts
    assert rd.JS_WS == r"\t\n\x0b\x0c\r    -     　﻿"


# ---- Round 10 / M1: Grep / Glob patterns and Task / Agent descriptions go through redact() in the action (live in 8.3.0) ----
def test_round10_m1_actions_carry_no_secret_python():
    for kind, text, secret in SECRETS:
        for tool, inp in (("Grep", {"pattern": text}), ("Glob", {"pattern": text}), ("Task", {"description": text})):
            a = at.summarize_tool_action(tool, inp)
            assert secret not in a and a.split(": ", 1)[0] in ("Searched for", "Found files matching", "Spawned task"), (tool, kind)


def test_round10_m1_actions_ts_python_parity(tmp_path):
    import shutil, subprocess
    bun = shutil.which("bun")
    if not bun:
        pytest.skip("bun not installed") if os.environ.get("ACE_ALLOW_NO_BUN") == "1" else pytest.fail("bun missing: the TS/Python parity tests must run (ACE_ALLOW_NO_BUN=1 skips them locally)")
    items = [(tool, t) for _, t, _ in SECRETS[:30] for tool in ("Grep", "Glob", "Task")] + [("Task", "short"), ("Grep", "plain words")]
    (tmp_path / "in.json").write_text(json.dumps(items))
    (tmp_path / "a.ts").write_text("import { summarizeAction } from '%s'\nconst it = JSON.parse(require('fs').readFileSync('%s','utf8'))\n"
                                   "console.log(JSON.stringify(it.map(([t, x]: [string, string]) => summarizeAction(t, t === 'Task' ? { description: x } : { pattern: x }))))\n"
                                   % (PLUGIN / "mod" / "lib" / "trace.ts", tmp_path / "in.json"))
    p = subprocess.run([bun, str(tmp_path / "a.ts")], capture_output=True, text=True, timeout=120)
    assert p.returncode == 0, p.stderr
    py = [at.summarize_tool_action(t, {"description": x} if t == "Task" else {"pattern": x}) for t, x in items]
    assert [(i, a, b) for i, (a, b) in enumerate(zip(json.loads(p.stdout), py)) if a != b] == []


# ---- Round 10 / M2: nested error / stderr values are redacted before they are stringified (live in 8.3.0) ----
@pytest.mark.parametrize("shape", ["error_obj", "error_list", "stderr_list", "data_nested"])
def test_round10_m2_nested_values_redacted(shape):
    for _, text, secret in SECRETS:
        r = {"error_obj": {"error": {"message": text}}, "error_list": {"error": [text]}, "stderr_list": {"stderr": [text]},
             "data_nested": {"result": {"items": [{"note": text}]}}}[shape]
        out = at.summarize_tool_response("mcp__x__y", r)
        assert secret not in out, (shape, text[:30], out[:80])


def _tok():
    import random
    return "gh" + "p_" + "".join(random.Random(7).choice("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789") for _ in range(36))


def test_round10_reproduction_cases_from_8_3_0():
    tok = _tok()
    assert at.summarize_tool_action("Grep", {"pattern": "x " + tok}).startswith("Searched for: x [redacted")
    for tool, inp in (("Grep", {"pattern": "x " + tok}), ("Glob", {"pattern": tok}), ("Task", {"description": "deploy with " + tok})):
        assert tok not in at.summarize_tool_action(tool, inp)
    assert tok not in at.summarize_tool_response("mcp__x__y", {"error": {"message": "bad " + tok}})
    assert "hunter22xx" not in at.summarize_tool_response("Bash", {"stderr": ["password=hunter22xx"]})
    assert "hunter22xx" not in at.redact("- name: DB_PASSWORD\n  value: hunter22xx\n")
    assert "hunter22xx" not in at.redact("DB_PASSWORD=hunter22xx")


# ---- Round 10 golden: on the 8.3.0 fixture corpus (tests-fixtures/task-outcome) only outputs that M1 / M2 / M3 explain change ----
def _corpus_strings():
    base = PLUGIN / "tests-fixtures" / "task-outcome"
    out = []
    def walk(v):
        if isinstance(v, str):
            out.append(v)
        elif isinstance(v, list):
            for x in v: walk(x)
        elif isinstance(v, dict):
            for k, x in v.items():
                if k not in ("name", "_doc", "expect"): walk(x)
    for f in ("cases.json", "random_cases.json", "secret_pairs.json"):
        walk(json.loads((base / f).read_text()))
    return sorted(set(out))


def _old_response(tool_name, tool_response):  # 8.3.0's summarize_tool_response head (top-level strings only)
    if isinstance(tool_response, dict):
        tool_response = {k: at.redact(v) if isinstance(v, str) else v for k, v in tool_response.items()}
    return tool_response


def test_round10_golden_8_3_0_corpus(monkeypatch, capsys):
    texts = _corpus_strings()
    new_red = [at.redact(x) for x in texts]
    monkeypatch.setattr(rd, "_redact_name_value", lambda s: s)
    old_red = [at.redact(x) for x in texts]
    monkeypatch.undo()
    red_changed = [x for x, a, b in zip(texts, old_red, new_red) if a != b]
    assert all(any(rx.search(x) for _, rx, _ in rd.NV_RULES) for x in red_changed)          # M3 only
    act_changed, act_other = 0, 0
    for x in texts:
        for tool, inp, label in (("Grep", {"pattern": x}, "Searched for: "), ("Glob", {"pattern": x}, "Found files matching: "),
                                 ("Task", {"description": x}, "Spawned task: ")):
            new = at.summarize_tool_action(tool, inp)
            raw = x if tool != "Task" or len(x) <= 60 else x[:60] + "..."
            old = label + (raw[:100] + "..." if tool != "Task" and len(raw) > 100 else raw) if tool != "Task" else label + raw
            if new != old:
                act_changed += 1
                exp = label + (lambda r: (r[:100] + "..." if len(r) > 100 else r) if tool != "Task" else (r[:60] + "..." if len(r) > 60 else r))(at.redact(x))
                act_other += new != exp                                               # every change = M1 (redact, then the cut)
    flat = [r for x in texts for r in ({"stdout": x, "stderr": "", "exit_code": 0}, {"stderr": x}, {"error": x})]
    new_resp = [at.summarize_tool_response("Bash", dict(r)) for r in flat]
    monkeypatch.setattr(at, "deep_redact", lambda v, depth=0: _old_response("Bash", v) if isinstance(v, dict) else v)  # 8.3.0 head
    old_resp = [at.summarize_tool_response("Bash", dict(r)) for r in flat]
    monkeypatch.undo()
    resp_same = sum(a == b for a, b in zip(old_resp, new_resp))
    assert resp_same == len(flat)  # flat responses (all 8.3.0 produced for Bash) are byte-identical: M2 acts only on nested values
    assert act_other == 0
    print("GOLDEN inputs=%d redact_changed=%d(M3) action_labels=%d changed=%d(M1) flat_responses=%d identical" % (len(texts), len(red_changed), len(texts) * 3, act_changed, resp_same))


def test_round10_m3_python_deep_redact_name_value():
    r = at.deep_redact({"env": [{"name": "DB_PASSWORD", "value": "hunter22xx"}, {"key": "client_secret", "value": "cs-1"}, {"name": "LOG_LEVEL", "value": "debug"}]})
    assert r == {"env": [{"name": "DB_PASSWORD", "value": "[redacted]"}, {"key": "client_secret", "value": "[redacted]"}, {"name": "LOG_LEVEL", "value": "debug"}]}
    assert "hunter22xx" not in at.summarize_tool_response("mcp__http__request", {"headers": [{"name": "Authorization", "value": "Basic hunter22xx"}]})


# ---- Round 10 / L3: the 8.1.3 span rules stay linear on 2 MB hostile input (keyword runs, one long URL token, no blank line, echo |) ----
# sizes: ~2 MB each; pwline ~6 MB and url ~4.8 MB, where a per-match re-search still finished in ~9 s at 2 MB
L3_FORMS = {"curl": ("", " curl -u ", 220_000), "mysql": ("", "mysql ", 330_000), "url": ("https://h/?", "token=a&", 600_000),
            "pwline": ("", "password:x\n", 540_000), "echo": ("", "echo |", 330_000),
            # Round 11 / W1: a keyword whose flag follows at once, many times on one line; W2: echo stages on a line that holds the flag
            "w1_mysql_url": ("", "a://mysql -p x ", 420_000), "w2_echo_flag": ("x '--password-stdin' ", "echo |", 330_000)}


@pytest.mark.parametrize("form", sorted(L3_FORMS))
def test_round10_l3_linear_python(form):
    pre, unit, n = L3_FORMS[form]
    assert_linear(at.redact, lambda f: pre + unit * int(n * f), form)          # ~2 MB; quadratic took minutes


def test_round10_l3_linear_ts(tmp_path):
    import shutil, subprocess
    bun = shutil.which("bun")
    if not bun:
        pytest.skip("bun not installed") if os.environ.get("ACE_ALLOW_NO_BUN") == "1" else pytest.fail("bun missing: the TS/Python parity tests must run (ACE_ALLOW_NO_BUN=1 skips them locally)")
    (tmp_path / "f.json").write_text(json.dumps(L3_FORMS))
    (tmp_path / "t.ts").write_text("import { redact } from '%s'\nconst f = JSON.parse(require('fs').readFileSync('%s','utf8'))\nconst out: any = {}\n" % (PLUGIN / "mod" / "lib" / "redact.ts", tmp_path / "f.json") + BUN_LINEAR_JS +
                                   "for (const k of Object.keys(f)) { const [p, u, n] = f[k]; out[k] = linear(g => p + u.repeat(Math.floor(n * g)), redact) }\n"
                                   "console.log(JSON.stringify(out))\n")
    p = subprocess.run([bun, str(tmp_path / "t.ts")], capture_output=True, text=True, timeout=150)
    assert p.returncode == 0, p.stderr
    ratios = json.loads(p.stdout)
    assert all(v <= LIMIT for v in ratios.values()), ratios


# ---- Round 10 / T1: in CI the bun-based cross-chain tests must run, never skip silently ----
def test_round10_t1_bun_present_in_ci():
    import shutil
    if os.environ.get("GITHUB_ACTIONS") != "true":
        pytest.skip("only enforced on GitHub Actions (.github/workflows/tests.yml installs bun)")
    assert shutil.which("bun"), "bun missing: the TS/Python parity tests would be skipped"



# ---- Round 11 / W2: the linear echo/printf rule gives exactly the old regex's result ----
def test_round11_w2_echo_stdin_equals_the_regex():
    import random
    _, rx, rep = rd.SECRET_RULES[0]
    parts = ["echo", "printf", "ECHO", "|", " ", "x", "--password-stdin", "--with-token", "'", "secret", "docker login", "echos", "-"]
    rnd = random.Random(11)
    for _ in range(3000):
        l = "".join(rnd.choice(parts) for _ in range(rnd.randint(1, 14)))
        assert rd._echo_stdin(l) == rx.sub(rep, l), l


def test_round11_w2_echo_lines_ts_python_parity(tmp_path):
    import random, shutil, subprocess
    bun = shutil.which("bun")
    if not bun:
        pytest.skip("bun not installed") if os.environ.get("ACE_ALLOW_NO_BUN") == "1" else pytest.fail("bun missing: the TS/Python parity tests must run (ACE_ALLOW_NO_BUN=1 skips them locally)")
    parts = ["echo", "printf", "ECHO", "|", " ", "x", "--password-stdin", "--with-token", "'", "secret", "docker login", "echos", "-"]
    rnd = random.Random(11)
    lines = ["".join(rnd.choice(parts) for _ in range(rnd.randint(1, 14))) for _ in range(3000)]
    (tmp_path / "in.json").write_text(json.dumps(lines))
    (tmp_path / "r.ts").write_text("import { redact } from '%s'\nconsole.log(JSON.stringify(JSON.parse(require('fs').readFileSync('%s','utf8')).map((x: string) => redact(x))))\n"
                                   % (PLUGIN / "mod" / "lib" / "redact.ts", tmp_path / "in.json"))
    p = subprocess.run([bun, str(tmp_path / "r.ts")], capture_output=True, text=True, timeout=120)
    assert p.returncode == 0, p.stderr
    assert [(l, t) for l, t in zip(lines, json.loads(p.stdout)) if at.redact(l) != t] == []


# ---- Round 12 / I3.1: the JSON name/value rule on long one-line JSON (unrolled value group; fail-open above ~540k in JSC before) ----
def _nv_pair(v):
    return '{"name": "API_KEY", "value": "' + v + '"}'


def test_round12_i31_nv_json_4mb_40_pairs_linear_python():
    big = "[" + ", ".join(_nv_pair("a" * 100_000) for _ in range(40)) + "]"
    r = at.redact(big)
    assert_linear(at.redact, lambda f: "[" + ", ".join(_nv_pair("a" * 100_000) for _ in range(int(40 * f))) + "]")
    assert r.count("[redacted:name-value]") == 40 and "a" * 1000 not in r


def test_round12_i31_nv_json_600k_value_redacted_python():
    r = at.redact(_nv_pair("x" * 600_000))
    assert "[redacted:name-value]" in r and "x" * 1000 not in r


def test_round12_i31_nv_json_ts_python(tmp_path):
    import shutil, subprocess
    bun = shutil.which("bun")
    if not bun:
        pytest.skip("bun not installed") if os.environ.get("ACE_ALLOW_NO_BUN") == "1" else pytest.fail("bun missing: the TS/Python parity tests must run (ACE_ALLOW_NO_BUN=1 skips them locally)")
    items = ["[" + ", ".join(_nv_pair("a" * 100_000) for _ in range(40)) + "]", _nv_pair("x" * 600_000)]
    (tmp_path / "in.json").write_text(json.dumps(items))
    (tmp_path / "r.ts").write_text("import { redact } from '%s'\nconst t = JSON.parse(require('fs').readFileSync('%s', 'utf8'))\n" % (PLUGIN / "mod" / "lib" / "redact.ts", tmp_path / "in.json") + BUN_LINEAR_JS +
                                   "const out: any[] = []\nfor (const x of t) { const r = redact(x); out.push([r, linear(f => x.slice(0, Math.floor(x.length * f)), redact)]) }\n"
                                   "console.log(JSON.stringify(out))\n")
    p = subprocess.run([bun, str(tmp_path / "r.ts")], capture_output=True, text=True, timeout=120)
    assert p.returncode == 0, p.stderr
    out = json.loads(p.stdout)
    assert [r for r, _ in out] == [at.redact(x) for x in items]
    assert all(ratio <= LIMIT for _, ratio in out), [ratio for _, ratio in out]


# ---- Round 13: PII layer (email, phone, IBAN, key context); labels [redacted:email|phone|iban]; after the secret / url-cred / name-value
# rules, before entropy. Fixture: cases.json "pii" (recipes; random or reserved domains; the only IBAN is the official example) ----
@pytest.mark.parametrize("i", range(len(PII_SECRETS)))
def test_round13_pii_secret_gone_and_labelled(i):
    kind, text, secret = PII_SECRETS[i]
    r = at.redact(text)
    assert secret not in r and "[redacted:%s]" % kind.split(":")[1] in r, (kind, text, r)


def test_round13_pii_normal_carries_no_pii_label():
    assert [(x, at.redact(x)) for x in PII_NORMAL if PII_LABEL.search(at.redact(x))] == []


def test_round13_pii_exceptions_and_limits():
    assert at.redact("ssh ubuntu@host.example.net") == "ssh ubuntu@host.example.net"            # reserved example domain
    assert at.redact("ssh ubuntu@host.acme-corp.io") == "ssh [redacted:email]"                 # ssh target without a path = an e-mail
    assert at.redact("user@host.acme-corp.io:/srv/x") == "user@host.acme-corp.io:/srv/x"       # SCP form with a path stays
    assert at.redact("x //bob@acme-corp.io") == "x //bob@acme-corp.io"                         # URL userinfo position stays
    # the diff-constant limit, documented: '+' + 11-15 digits with a valid country code and no separator IS redacted (a false alarm on
    # such diff lines); 8-10 digits without a separator are not
    assert at.redact("+123456789012") == "[redacted:phone]"
    assert at.redact("+1234567890") == "+1234567890"
    assert at.redact("+28 123 456 789") == "+28 123 456 789"      # neither 2, 28 nor 281 is a country code (ITU E.164)
    assert at.redact("+422 123 456 789") == "+422 123 456 789"    # 422 is spare
    assert at.redact("+423 123 456 789") == "[redacted:phone]"    # Liechtenstein
    assert at.redact("030 1234567") == "030 1234567"              # a bare national number without context: known limit


def _iban(cc, bban):
    n = "".join(str(int(ch, 36)) for ch in bban + cc + "00")
    return cc + "%02d" % (98 - int(n) % 97) + bban


def test_round13_iban_checksum_and_length():
    assert _iban("DE", "370400440532013000") == "DE89370400440532013000"   # the official example, checksum computed here
    assert at.redact("x " + _iban("DE", "370400440532013000") + " y") == "x [redacted:iban] y"
    assert at.redact("x " + _iban("DE", "3704004405320130001") + " y").count("[redacted:iban]") == 0   # valid checksum, DE needs 22
    assert at.redact("x " + _iban("NL", "ABNA0417164300") + " y") == "x [redacted:iban] y"            # NL 18
    assert at.redact("x DE89370400440532013001 y") == "x DE89370400440532013001 y"                 # wrong checksum


def test_round13_deep_redact_pii_keys():
    r = at.deep_redact({"email": "dev at host", "Mail": "ops@intranet", "phone": 491701234567, "Tel": "+49 30 1234 5678",
                        "iban": "XX12 3456", "fax": True, "mobile": "n/a", "note": "x"})
    assert r == {"email": "dev at host", "Mail": "[redacted:email]", "phone": "[redacted:phone]", "Tel": "[redacted:phone]",
                 "iban": "[redacted:iban]", "fax": True, "mobile": "n/a", "note": "x"}


# Round 18b / B2: key values that made the IBAN-shaped value alternative backtrack (Opus hostile18 seeds, 1 MB each)
R18_KEY_SEEDS = {"run40": "iban: DE12" + "A" * 40 + " ", "run33": "iban: DE12" + "A" * 33 + " ", "run33_x": "iban=DE12" + "AB1" * 11 + "Z\n",
                 "mixed": "iban: DE12" + "A1B2" * 10 + "/x ", "short": "iban: DE12ABCDABCDABCD-x ", "sp": "iban: DE12 ABCD ABCD ABCD ABCD ABCD ABCD ABCD ABCDX ",
                 "mail": "mail=AB12" + "C" * 40 + " ", "tel": "tel: AB12" + "C1" * 20 + ";x "}
R13_HOSTILE = {"dot_chain": "a@" + "a." * 100_000 + "1", "long_local": "a@" + "a" * 1_000_000, "many_at": "a@b." * 1_000_000,
               "many_plus": "+1 " * 1_300_000, "digit_run": "+" + "1" * 4_000_000, "upper_run": "AB12" + "C" * 4_000_000,
               "kw_spam": "tel " * 1_000_000, "key_spam": "phone: " * 570_000, "real_emails": "x@acme-corp.io " * 280_000,
               "iban_spam": "DE89 3704 0044 0532 0130 00 " * 140_000, "iban_lc_starts": "LC55 " * 800_000,
               **{"key_" + k: (s * (1_000_000 // len(s) + 1))[:1_000_000] for k, s in R18_KEY_SEEDS.items()}}


@pytest.mark.parametrize("form", sorted(R13_HOSTILE))
def test_round13_pii_linear_python(form):
    assert_linear(at.redact, prefix(R13_HOSTILE[form]), form)


def test_round13_pii_ts_python(tmp_path):
    import shutil, subprocess
    bun = shutil.which("bun")
    if not bun:
        pytest.skip("bun not installed") if os.environ.get("ACE_ALLOW_NO_BUN") == "1" else pytest.fail("bun missing: the TS/Python parity tests must run (ACE_ALLOW_NO_BUN=1 skips them locally)")
    texts = [t for _, t, _ in PII_SECRETS] + PII_NORMAL + [v[:5000] for v in R13_HOSTILE.values()] + [
        "ssh ubuntu@host.acme-corp.io", "+123456789012", "+422 123 456 789", "Tel: (030) 1234567", '"email": "a@b.example.com"']
    (tmp_path / "in.json").write_text(json.dumps(texts))
    (tmp_path / "r.ts").write_text("import { redact } from '%s'\nconst t = JSON.parse(require('fs').readFileSync('%s', 'utf8'))\nconsole.log(JSON.stringify(t.map((x: string) => redact(x))))\n"
                                   % (PLUGIN / "mod" / "lib" / "redact.ts", tmp_path / "in.json"))
    p = subprocess.run([bun, str(tmp_path / "r.ts")], capture_output=True, text=True, timeout=120)
    assert p.returncode == 0, p.stderr
    assert [(x[:60], ts[:80], at.redact(x)[:80]) for x, ts in zip(texts, json.loads(p.stdout)) if at.redact(x) != ts] == []


def test_round13_pii_timing_ts(tmp_path):
    import shutil, subprocess
    bun = shutil.which("bun")
    if not bun:
        pytest.skip("bun not installed") if os.environ.get("ACE_ALLOW_NO_BUN") == "1" else pytest.fail("bun missing: the TS/Python parity tests must run (ACE_ALLOW_NO_BUN=1 skips them locally)")
    (tmp_path / "f.json").write_text(json.dumps(R13_HOSTILE))
    (tmp_path / "t.ts").write_text("import { redact } from '%s'\nconst f = JSON.parse(require('fs').readFileSync('%s','utf8'))\nconst out: any = {}\n" % (PLUGIN / "mod" / "lib" / "redact.ts", tmp_path / "f.json") + BUN_LINEAR_JS +
                                   "for (const k of Object.keys(f)) out[k] = linear(g => f[k].slice(0, Math.floor(f[k].length * g)), redact)\n"
                                   "console.log(JSON.stringify(out))\n")
    p = subprocess.run([bun, str(tmp_path / "t.ts")], capture_output=True, text=True, timeout=300)
    assert p.returncode == 0, p.stderr
    ratios = json.loads(p.stdout)
    assert all(v <= LIMIT for v in ratios.values()), ratios


# ---- Round 13: the url-userinfo rule runs linear (the regex was quadratic on 'a.a.a.…') and gives exactly the regex's result ----
_UI_PARTS = ["a", "Z", "1", "+", ".", "-", "_", ":", "/", "://", "@", " ", '"', "x", "\n"]


def _ui_lines():
    import random
    rnd = random.Random(13)
    return ["".join(rnd.choice(_UI_PARTS) for _ in range(rnd.randint(1, 18))) for _ in range(4000)]


def test_round13_url_userinfo_equals_the_regex():
    _, rx, rep = rd.SECRET_RULES[1]
    assert rd.SECRET_RULES[1][0] == "url-userinfo"
    for l in _ui_lines():
        assert rd._url_userinfo(l) == rx.sub(rep, l), repr(l)


def test_round13_url_userinfo_lines_ts_python(tmp_path):
    import shutil, subprocess
    bun = shutil.which("bun")
    if not bun:
        pytest.skip("bun not installed") if os.environ.get("ACE_ALLOW_NO_BUN") == "1" else pytest.fail("bun missing: the TS/Python parity tests must run (ACE_ALLOW_NO_BUN=1 skips them locally)")
    lines = _ui_lines()
    (tmp_path / "in.json").write_text(json.dumps(lines))
    (tmp_path / "r.ts").write_text("import { redact } from '%s'\nconsole.log(JSON.stringify(JSON.parse(require('fs').readFileSync('%s','utf8')).map((x: string) => redact(x))))\n"
                                   % (PLUGIN / "mod" / "lib" / "redact.ts", tmp_path / "in.json"))
    p = subprocess.run([bun, str(tmp_path / "r.ts")], capture_output=True, text=True, timeout=120)
    assert p.returncode == 0, p.stderr
    assert [(l, t) for l, t in zip(lines, json.loads(p.stdout)) if at.redact(l) != t] == []


# ---- Round 14 (review of the PII layer): suffix keys, spaced values behind a key, file-name / date / IP / decimal false alarms,
# no 'call' keyword, prototype-safe lookups, float parity. Fixture cases: cases.json "pii" (appended) ----
def test_round14_prototype_keys_and_float_parity():
    d = {"__proto__": "1234567", "constructor": "abc", "toString": "x", "hasOwnProperty": "0301234567"}
    assert at.deep_redact(d) == d
    assert at.deep_redact({"phone": 12345.0}) == {"phone": 12345.0}                      # JS String(12345.0) == "12345": 5 digits
    assert at.deep_redact({"phone": 1234567.0, "Phone_Number": 30123456}) == {"phone": "[redacted:phone]", "Phone_Number": "[redacted:phone]"}
    assert at.deep_redact({"phoneNumber": "030 1234567", "mobile_no": "0151 1234 5678", "telNr": "x"}) == \
        {"phoneNumber": "[redacted:phone]", "mobile_no": "[redacted:phone]", "telNr": "x"}


def test_round14_limits_stay_documented():
    assert at.redact("0049 30 1234567") == "0049 30 1234567"          # 00-prefix without a keyword: known limit
    assert at.redact("user@host.acme-corp.io:8080") == "user@host.acme-corp.io:8080"   # host:port reads as the SCP form: known limit
    assert at.redact("+49\u00a030\u00a01234567") == "[redacted:phone]"               # NBSP as a separator (optional fix 8)
    assert at.redact("Tel.:\u00a0030\u00a01234567") == "Tel.:\u00a0[redacted:phone]"


R14_HOSTILE = {"suffix_spam": "Telefonnummer " * 300_000, "spaced_key": "iban: de89 " * 360_000, "spaced_key2": "phone_number: 1 2 3 4 5 6 7 8 9 " * 125_000,
               "file_at": "logo@2x.png " * 330_000, "date_plus": "+2026-11-24 10:00:00 " * 190_000}


@pytest.mark.parametrize("form", sorted(R14_HOSTILE))
def test_round14_linear_python(form):
    assert_linear(at.redact, prefix(R14_HOSTILE[form]), form)


def test_round14_ts_python(tmp_path):
    import shutil, subprocess
    bun = shutil.which("bun")
    if not bun:
        pytest.skip("bun not installed") if os.environ.get("ACE_ALLOW_NO_BUN") == "1" else pytest.fail("bun missing: the TS/Python parity tests must run (ACE_ALLOW_NO_BUN=1 skips them locally)")
    texts = [v[:6000] for v in R14_HOSTILE.values()] + ["Tel.-Nr.: 030 1234567", "iban: de89 3704 0044 0532 0130 00 and more", "img@1.5x.jpg"]
    objs = [{"phone": 12345.0}, {"phone": 1234567.0}, {"constructor": "abc", "toString": "0301234567"}, {"phoneNumber": "030 1234567"}]
    (tmp_path / "in.json").write_text(json.dumps([texts, objs]))
    (tmp_path / "r.ts").write_text("import { redact, deepRedact } from '%s'\nconst [t, o] = JSON.parse(require('fs').readFileSync('%s', 'utf8'))\n"
                                   "console.log(JSON.stringify([t.map((x: string) => redact(x)), o.map((x: any) => deepRedact(x))]))\n"
                                   % (PLUGIN / "mod" / "lib" / "redact.ts", tmp_path / "in.json"))
    p = subprocess.run([bun, str(tmp_path / "r.ts")], capture_output=True, text=True, timeout=120)
    assert p.returncode == 0, p.stderr
    ts_t, ts_o = json.loads(p.stdout)
    assert ts_t == [at.redact(x) for x in texts]
    assert ts_o == json.loads(json.dumps([at.deep_redact(x) for x in objs]))


# ---- Round 15 (review of round 14): IBAN groups without a digit and lower case, German deepRedact keys and arrays under a PII key,
# German compound keywords, JS float text, more date / CIDR rejects, narrow spaces, no silent bun skip. Fixture: cases.json "pii" ----
def test_round15_keyed_iban_stops_at_its_country_length():
    assert at.redact("iban: gb00 west 1234 5698 7654 32 and more") == "iban: [redacted:iban] and more"   # bad checksum: the key rule
    assert at.redact("iban: gb82 west 1234 5698 7654 32 and more") == "iban: [redacted:iban] and more"   # valid: the IBAN rule
    assert at.redact("iban: xq12 abcd efgh and more") == "iban: [redacted:iban] and more"       # Round 16 / I1: unknown country: all groups


def test_round15_deep_redact_german_keys_and_arrays():
    r = at.deep_redact({"telefon": "030 1234567", "Telefonnummer": "030 1234567", "handynummer": "0151 12345678", "mobil": "0151 12345678",
                        "rufnummer": "030 1234567", "whatsapp": "0151 12345678", "mobilnummer": "0151 12345678", "handy-nr": "0151 1234567",
                        "phone": ["030 1234567", ["0151 2345678", {"n": 301234567}], "n/a"], "iban": ["de89 3704 0044 0532 0130 00"],
                        "fax": {"n": "0301234567"}, "mobile": [1234567, True, None]})
    P = "[redacted:phone]"
    assert r == {"telefon": P, "Telefonnummer": P, "handynummer": P, "mobil": P, "rufnummer": P, "whatsapp": P, "mobilnummer": P, "handy-nr": P,
                 "phone": [P, [P, {"n": P}], "n/a"], "iban": ["[redacted:iban]"], "fax": {"n": P}, "mobile": [P, True, None]}


def test_round15_js_float_text():
    for x, want in [(1e-6, "0.000001"), (1.234e-05, "0.00001234"), (1.5e-07, "1.5e-7"), (0.0001234, "0.0001234"), (12345.0, "12345"),
                    (1e21, "1e+21"), (1.2345678901234566e+17, "123456789012345660"), (123456.789, "123456.789"), (-1234567.0, "-1234567"), (2.5e-10, "2.5e-10")]:
        assert rd._js_num(x) == want, (x, rd._js_num(x), want)


R15_HOSTILE = {"prefix_spam": "Mobiltelefonnummer " * 220_000, "prefix_nostem": "Firmenhandyxyzabcde " * 200_000, "iban_lower": "gb82 west " * 400_000,
               "iban_key_words": "iban: gb00 west 1234 and more " * 130_000, "dates_plus": "+24.11.2026 10:00:00 " * 190_000}


@pytest.mark.parametrize("form", sorted(R15_HOSTILE))
def test_round15_linear_python(form):
    assert_linear(at.redact, prefix(R15_HOSTILE[form]), form)


def test_round15_deep_array_linear_python():
    assert_linear(at.deep_redact, lambda f: {"phone": ["030 1234567"] * int(100_000 * f), "x": [{"tel": "0301234567"}] * int(50_000 * f)})


def test_round15_ts_python(tmp_path):
    import shutil, subprocess
    bun = shutil.which("bun")
    if not bun:
        pytest.skip("bun not installed") if os.environ.get("ACE_ALLOW_NO_BUN") == "1" else pytest.fail("bun missing: the TS/Python parity tests must run (ACE_ALLOW_NO_BUN=1 skips them locally)")
    texts = [v[:6000] for v in R15_HOSTILE.values()] + ["iban: gb00 west 1234 5698 7654 32 and more", "iban: xq12 abcd efgh and more",
             "meine iban ist de89 3704 0044 0532 0130 00", "+44.20.794.609", "+49\u202f30\u202f1234567", "Hotel 1234567"]
    objs = [{"phone": x} for x in (1e-6, 1.234e-05, 1.5e-07, 0.0001234, 1e21, 1.2345678901234566e+17, 123456.789, -1234567.0, 2.5e-10, 12345678901234567890)] + [
        {"Telefonnummer": "030 1234567", "phone": ["030 1234567", ["0151 2345678", {"n": 301234567}], "n/a"], "fax": {"n": "0301234567"}}]
    (tmp_path / "in.json").write_text(json.dumps([texts, objs]))
    (tmp_path / "r.ts").write_text("import { redact, deepRedact } from '%s'\nconst [t, o] = JSON.parse(require('fs').readFileSync('%s', 'utf8'))\n"
                                   "console.log(JSON.stringify([t.map((x: string) => redact(x)), o.map((x: any) => deepRedact(x))]))\n"
                                   % (PLUGIN / "mod" / "lib" / "redact.ts", tmp_path / "in.json"))
    p = subprocess.run([bun, str(tmp_path / "r.ts")], capture_output=True, text=True, timeout=120)
    assert p.returncode == 0, p.stderr
    ts_t, ts_o = json.loads(p.stdout)
    assert ts_t == [at.redact(x) for x in texts]
    assert ts_o == json.loads(json.dumps([at.deep_redact(json.loads(json.dumps(x))) for x in objs]))


# ---- Round 16 (review of round 15): an unkeyed IBAN is cut to its country length before the checks (a following short word no
# longer hides it), NBSP / tab inside an IBAN, keyword keys in deepRedact, English '...phone' keys, dotted numbers behind 'Tel/', 'cell'
# only with ':' / '#' / 'no', a keyed IBAN that does not validate loses all its groups, an address with a real TLD before '(' / '[' ----
def _iban16(cc, n):
    bban = "".join(str((i * 7 + 3) % 10) for i in range(n - 4))
    num = "".join(str(int(ch, 36)) for ch in bban + cc + "00")
    return cc + "%02d" % (98 - int(num) % 97) + bban


R16_FOLLOW = [" bis", " BANK", " 1", ".", ", ok", " und mehr"]


def _r16_iban_texts():
    out = []
    for cc, n in sorted(rd.IBAN_LEN.items()):
        iban = _iban16(cc, n)
        spaced = " ".join(iban[i:i + 4] for i in range(0, len(iban), 4))
        for form in (iban, spaced):
            for follow in R16_FOLLOW:
                out.append((form, "Konto " + form + follow, follow))
    return out


def test_round16_every_iban_country_with_a_following_word():
    leaks = [(t, at.redact(t)) for form, t, follow in _r16_iban_texts() if at.redact(t) != "Konto [redacted:iban]" + follow]
    assert leaks == []


def test_round16_words_after_an_iban_stay():
    assert at.redact("Bitte ueberweisen an AT61 1904 3002 3457 3201 bis Freitag") == "Bitte ueberweisen an [redacted:iban] bis Freitag"
    assert at.redact("IBAN AT611904300234573201 und BIC") == "IBAN [redacted:iban] und BIC"
    assert at.redact("iban: GB82 WEST 1234 5698 7654 3 and more") == "iban: [redacted:iban] and more"     # does not validate: all groups
    assert at.redact("iban: xyz and more") == "iban: xyz and more"
    assert at.redact("iban: xq12 abcd efgh and more") == "iban: [redacted:iban] and more"


def test_round16_keys_and_cell():
    P = "[redacted:phone]"
    r = at.deep_redact({"festnetz": "030 1234567", "Mobiltelefon": "0151 12345678", "Diensthandy": "0151 12345678", "Firmenhandy": "0151 12345678",
                        "Mobilfunknummer": "0151 12345678", "cell": "415 555 0123", "cellphone": "415 555 0123", "MobilePhone": "0151 12345678",
                        "HomePhone": "030 1234567", "phoneNumbers": ["030 1234567"], "home_phone": "030 1234567", "phone2": "030 1234567",
                        "phones": [{"value": "030 1234567"}], "iPhone": "15 Pro", "cells": "030 1234567"})
    assert r == {"festnetz": P, "Mobiltelefon": P, "Diensthandy": P, "Firmenhandy": P, "Mobilfunknummer": P, "cell": P, "cellphone": P, "MobilePhone": P,
                 "HomePhone": P, "phoneNumbers": [P], "home_phone": P, "phone2": P, "phones": [{"value": P}], "iPhone": "15 Pro", "cells": "030 1234567"}
    assert at.redact("cell size 1000000 bytes") == "cell size 1000000 bytes"
    assert at.redact("Cell: 415 555 0123") == "Cell: " + P
    assert at.redact("Tel/089.1234.5678") == "Tel/" + P and at.redact("WhatsApp/2.23.20.0 Android") == "WhatsApp/2.23.20.0 Android"
    assert at.redact("jane.doe@firma.de(Vertrieb)") == "[redacted:email](Vertrieb)" and at.redact("q@k.transpose(-1)") == "q@k.transpose(-1)"
    assert at.redact("x@y.name(arg)") == "x@y.name(arg)"


def test_round16_ts_python(tmp_path):
    import shutil, subprocess
    bun = shutil.which("bun")
    if not bun:
        pytest.skip("bun not installed") if os.environ.get("ACE_ALLOW_NO_BUN") == "1" else pytest.fail("bun missing: the TS/Python parity tests must run (ACE_ALLOW_NO_BUN=1 skips them locally)")
    texts = [t for _, t, _ in _r16_iban_texts()] + ["iban: GB82 WEST 1234 5698 7654 3 and more", "iban: xq12 abcd efgh and more", "cell size 1000000 bytes",
             "Tel/089.1234.5678", "jane.doe@firma.de(Vertrieb)", "q@k.transpose(-1)", "IBAN DE89\t3704\t0044\t0532\t0130\t00", "MobilePhone: 0151 12345678"]
    objs = [{"festnetz": "030 1234567", "cell": "415 555 0123", "MobilePhone": "0151 12345678", "phones": [{"value": "030 1234567"}], "iPhone": "15 Pro"}]
    (tmp_path / "in.json").write_text(json.dumps([texts, objs]))
    (tmp_path / "r.ts").write_text("import { redact, deepRedact } from '%s'\nconst [t, o] = JSON.parse(require('fs').readFileSync('%s', 'utf8'))\n"
                                   "console.log(JSON.stringify([t.map((x: string) => redact(x)), o.map((x: any) => deepRedact(x))]))\n"
                                   % (PLUGIN / "mod" / "lib" / "redact.ts", tmp_path / "in.json"))
    p = subprocess.run([bun, str(tmp_path / "r.ts")], capture_output=True, text=True, timeout=120)
    assert p.returncode == 0, p.stderr
    ts_t, ts_o = json.loads(p.stdout)
    assert [(x, a) for x, a in zip(texts, ts_t) if a != at.redact(x)] == []
    assert ts_o == json.loads(json.dumps([at.deep_redact(json.loads(json.dumps(x))) for x in objs]))


# ---- Round 17 (review of round 16 / C1'): an unkeyed IBAN is found by a scan over start candidates that walks exactly the country
# length (no group regex): two IBANs in a row, a 'CC+2 digits' token before it (KW47, Re24), tab-separated columns. Telefax / Fon /
# Durchwahl as phone words, a digit suffix on phone keys (phone_2, telefon2, fax2; not cell) ----
def _iban17(cc, n, k):
    bban = "".join(("ABCDEFGHJK"[(i * 3 + k) % 10] if k and i < 4 else str((i * (5 + k) + 3 + k) % 10)) for i in range(n - 4))
    num = "".join(str(int(ch, 36)) for ch in bban + cc + "00")
    return cc + "%02d" % (98 - int(num) % 97) + bban


R17_SEPS = [None, " ", "\t", "\u00a0"]
R17_MIDS = [" ", "\t", " oder ", " IBAN ", ", ", " / ", " neue "]
R17_LEADS = ["", "KW47 ", "Re24 ", "AB12 ", "DE00 ", "Nr12 ", "IBAN ", "Zahlung KW47: "]
R17_FOLLOWS = ["", " bis", " 1234", ".", " BANK", "\tBerlin"]


def _r17_render(iban, sep, lower):
    t = iban if sep is None else sep.join(iban[i:i + 4] for i in range(0, len(iban), 4))
    return t.lower() if lower else t


def _r17_cases():
    """(text, [ibans], expected): every country, two IBANs in a row (each separator x middle word) and one IBAN behind every lead /
    before every follow form; deterministic."""
    ccs, out = sorted(rd.IBAN_LEN), []
    for x, cc in enumerate(ccs):
        b = ccs[(x * 7 + 1) % len(ccs)]
        for y, sep in enumerate(R17_SEPS):
            for z, mid in enumerate(R17_MIDS):
                i1, i2 = _iban17(cc, rd.IBAN_LEN[cc], (y + z) % 2), _iban17(b, rd.IBAN_LEN[b], (y + z + 1) % 2)
                lead, follow = R17_LEADS[(x + y + z) % len(R17_LEADS)], R17_FOLLOWS[(x + z) % len(R17_FOLLOWS)]
                t = lead + _r17_render(i1, sep, z % 3 == 1) + mid + _r17_render(i2, sep, z % 3 == 2) + follow
                out.append((t, [i1, i2], lead + "[redacted:iban]" + mid + "[redacted:iban]" + follow))
        for y, lead in enumerate(R17_LEADS):
            for z, follow in enumerate(R17_FOLLOWS):
                i1 = _iban17(cc, rd.IBAN_LEN[cc], z % 2)
                t = lead + _r17_render(i1, R17_SEPS[(y + z) % 4], False) + follow
                out.append((t, [i1], lead + "[redacted:iban]" + follow))
    return out


def _r17_leaks(cases, outs):
    strip = lambda s: re.sub(r"[^A-Za-z0-9]", "", s).upper()
    return [(t, o) for (t, ibans, _), o in zip(cases, outs) if any(i in strip(o) or i[-8:] in strip(o) for i in ibans)]


def test_round17_two_ibans_leads_follows_every_country():
    cases = _r17_cases()
    outs = [at.redact(t) for t, _, _ in cases]
    assert len(cases) == 89 * (4 * 7 + 8 * 6)
    assert _r17_leaks(cases, outs) == []
    # an exact output except where a lead plus the IBAN's first groups happen to form a valid IBAN of the lead's country (1 in 97)
    off = [(t, o) for (t, _, e), o in zip(cases, outs) if o != e]
    assert all(o.startswith("[redacted:iban]") for _, o in off) and len(off) <= len(cases) // 97, off


def test_round17_review_examples():
    I = "[redacted:iban]"
    AT, DE = "AT61 1904 3002 3457 3201", "DE89 3704 0044 0532 0130 00"
    assert at.redact("Max\t" + AT + "\t" + DE + "\tBerlin") == "Max\t" + I + "\t" + I + "\tBerlin"
    assert at.redact("Bitte auf " + AT + " oder " + DE + " ueberweisen") == "Bitte auf " + I + " oder " + I + " ueberweisen"
    assert at.redact("IBAN alt " + AT + " neue " + DE) == "IBAN alt " + I + " neue " + I
    assert at.redact("iban: " + AT + " oder " + DE) == "iban: " + I + " oder " + I
    assert at.redact("Zahlung KW47 " + DE + " danke") == "Zahlung KW47 " + I + " danke"
    assert at.redact("Re24 " + AT.replace(" ", "")) == "Re24 " + I
    assert at.redact(AT + " oder 12345") == I + " oder 12345"
    assert at.redact("AE41 ABCD NO93 8601 1117 947 x") == I + " x"     # a valid IBAN inside a found one: the scan goes on after the end
    assert at.redact("AB12" + AT.replace(" ", "")) == "AB12" + AT.replace(" ", "")                    # no boundary before the start
    assert at.redact(AT.replace(" ", "") + "X") == AT.replace(" ", "") + "X"                          # no boundary after the end
    assert at.redact("AT61  1904 3002 3457 3201") == "AT61  1904 3002 3457 3201"                      # limit: a double space
    P = "[redacted:phone]"
    for t in ("Telefax: 089 1234567", "Telefax 089/1234567", "Fon: 089 1234567", "Fon 089 1234567", "Durchwahl: 089 1234-567"):
        assert at.redact(t) == t[:t.index("0")] + P, t
    assert at.redact("Fonds 1234567") == "Fonds 1234567" and at.redact("cell_2 = 1234567") == "cell_2 = 1234567"
    assert at.redact("phone_2: 0151 12345678") == "phone_2: " + P and at.redact("telefon2: 0151 12345678") == "telefon2: " + P
    assert at.redact("fax2: 089 1234567") == "fax2: " + P and at.redact("phone12: 0151 12345678") == "phone12: " + P
    r = at.deep_redact({"Telefax": "089 1234567", "fon": "089 1234567", "Durchwahl": "1234567", "phone_2": "030 1234567", "telefon2": "030 1234567",
                        "fax2": "030 1234567", "cell_2": "1234567", "font": "1234567"})
    assert r == {"Telefax": P, "fon": P, "Durchwahl": P, "phone_2": P, "telefon2": P, "fax2": P, "cell_2": "1234567", "font": "1234567"}


def test_round17_ts_python(tmp_path):
    import shutil, subprocess
    bun = shutil.which("bun")
    if not bun:
        pytest.skip("bun not installed") if os.environ.get("ACE_ALLOW_NO_BUN") == "1" else pytest.fail("bun missing: the TS/Python parity tests must run (ACE_ALLOW_NO_BUN=1 skips them locally)")
    texts = [t for t, _, _ in _r17_cases()] + ["Telefax: 089 1234567", "Fon 089 1234567", "Durchwahl: 089 1234-567", "phone_2: 0151 12345678", "cell_2 = 1234567"]
    objs = [{"Telefax": "089 1234567", "fon": "089 1234567", "phone_2": "030 1234567", "cell_2": "1234567"}]
    (tmp_path / "in.json").write_text(json.dumps([texts, objs]))
    (tmp_path / "r.ts").write_text("import { redact, deepRedact } from '%s'\nconst [t, o] = JSON.parse(require('fs').readFileSync('%s', 'utf8'))\n"
                                   "console.log(JSON.stringify([t.map((x: string) => redact(x)), o.map((x: any) => deepRedact(x))]))\n"
                                   % (PLUGIN / "mod" / "lib" / "redact.ts", tmp_path / "in.json"))
    p = subprocess.run([bun, str(tmp_path / "r.ts")], capture_output=True, text=True, timeout=120)
    assert p.returncode == 0, p.stderr
    ts_t, ts_o = json.loads(p.stdout)
    assert len(texts) == 6769 and [(x, a) for x, a in zip(texts, ts_t) if a != at.redact(x)] == []
    assert ts_o == json.loads(json.dumps([at.deep_redact(json.loads(json.dumps(x))) for x in objs]))


# ---- Round 18 (review of round 17): a phone number behind a bare 'call' (B1, a regression against the base: 'call' + up to 3 words /
# ':' / '(' and a number that looks like a phone number: leading 0, a space, '(' before it or 2+ separators; code numbers stay), digit
# suffix on every PII key stem (N2: iban2, email2, mail1 resolve their kind), an IBAN-shaped key value must end at a value end (N3) ----
def test_round18_call_and_key_suffix():
    P, I, E = "[redacted:phone]", "[redacted:iban]", "[redacted:email]"
    assert at.redact("Please call 030 1234567 tomorrow") == "Please call " + P + " tomorrow"
    assert at.redact("Call: (415) 555-0123") == "Call: (" + P
    assert at.redact("call our hotline 0800 1234567") == "call our hotline " + P
    assert at.redact("call the customer at 0151 23456789") == "call the customer at " + P
    assert at.redact("call 015112345678") == "call " + P and at.redact("call 1-800-555-0123") == "call " + P
    assert at.redact("call 4155550123") == "call " + P and at.redact("API call 12345678 ok") == "API call 12345678 ok"
    for t in ("call(123456)", "call timeout 123456", "call(timeout=123456)", "tool call took 1234567 ns", "API call 1234567 ok",
              "call used 1234567 bytes", "call ratio 123/456", "tool call: redact.py:1234-5678", "call with timeout: 12345678 ms"):
        assert at.redact(t) == t, t
    assert at.redact("iban2: DE89 3704 0044 0532 0130 00") == "iban2: " + I and at.redact("email2: max.mustermann@firma.de") == "email2: " + E
    assert at.redact("IBAN10: XX12 3456") == "IBAN10: " + I and at.redact("mail1=0301234567") == "mail1=0301234567"
    assert at.redact("iban: DE893704.0044.0532.0130.00") == "iban: " + I and at.redact("iban: Re24089.1234.5678") == "iban: " + I
    assert at.redact("iban: AT61 1904 3002 3457 3201 oder 12") == "iban: " + I + " oder 12"
    assert at.deep_redact({"iban2": "DE89 3704 0044 0532 0130 00", "email_1": "max@firma.de"}) == {"iban2": I, "email_1": E}


def test_round18_ts_python(tmp_path):
    import shutil, subprocess
    bun = shutil.which("bun")
    if not bun:
        pytest.skip("bun not installed") if os.environ.get("ACE_ALLOW_NO_BUN") == "1" else pytest.fail("bun missing: the TS/Python parity tests must run (ACE_ALLOW_NO_BUN=1 skips them locally)")
    texts = ["Please call 030 1234567 tomorrow", "Call: (415) 555-0123", "call our hotline 0800 1234567", "call(123456)", "tool call took 1234567 ns",
             "iban2: DE89 3704 0044 0532 0130 01", "iban_2=XX12 3456 7890", "mail1=0301234567", "IBAN10: 1234", "email2: \"max\"",
             "iban: DE893704.0044.0532.0130.00", "iban: Re24089.1234.5678", "iban: AB12 3.456.789", "call me0151 23456789"]
    objs = [{"iban2": "DE89 3704 0044 0532 0130 00", "email_1": "max@firma.de", "mail1": "0301234567"}]
    (tmp_path / "in.json").write_text(json.dumps([texts, objs]))
    (tmp_path / "r.ts").write_text("import { redact, deepRedact } from '%s'\nconst [t, o] = JSON.parse(require('fs').readFileSync('%s', 'utf8'))\n"
                                   "console.log(JSON.stringify([t.map((x: string) => redact(x)), o.map((x: any) => deepRedact(x))]))\n"
                                   % (PLUGIN / "mod" / "lib" / "redact.ts", tmp_path / "in.json"))
    p = subprocess.run([bun, str(tmp_path / "r.ts")], capture_output=True, text=True, timeout=120)
    assert p.returncode == 0, p.stderr
    ts_t, ts_o = json.loads(p.stdout)
    assert [(x, a) for x, a in zip(texts, ts_t) if a != at.redact(x)] == []
    assert not any("None" in a or "undefined" in a for a in ts_t)
    assert ts_o == json.loads(json.dumps([at.deep_redact(json.loads(json.dumps(x))) for x in objs]))


# ---- Round 18b (review of round 18): a bare 'call' no longer swallows a following phone keyword (the gap is scanned again), the
# file-name exception only for a line range, dates / IPv4 / decimals and code words (timeout, took, settled, used, ratio) after 'call',
# 'call  me'; the IBAN-shaped key value alternative is linear again (B2) ----
R18B_REDACT = [("Call or WhatsApp 91234567", "91234567"), ("call/whatsapp 91234567", "91234567"), ("call or fax 5550123", "5550123"),
               ("Please call my phone number 5550123", "5550123"), ("call mobile 87654321", "87654321"), ("call Fax 1234567", "1234567"),
               ("Call Anna (mobile): 5550123", "5550123"), ("Call/Tel. 5550123", "5550123"), ("Call (mobil): 299839", "299839"),
               ("call Tel.Nr:0301234567", "0301234567"), ("call Mobil.Nr:0151234567", "0151234567"), ("call me 5550123", "5550123"),
               ("call  me 5550123", "5550123"), ("Call:555-0123", "555-0123"), ("call 030 1234567", "030 1234567"), ("call 015112345678", "015112345678"),
               ("Call: (415) 555-0123", "555-0123"), ("call timeout 030 1234567", "030 1234567"), ("call(0301234567)", "0301234567"),
               ("Call Dr.Meier:0301234567", "0301234567"), ("call 0123456", "0123456"), ("call 123456789", "123456789"),
               ("call or tel. 5550123", "5550123"), ("call timeout 0301234567", "0301234567"), ("Call/Fax: 5550123", "5550123")]
R18B_STAY = ["per call (2026-11-24)", "call on 24.11.2026", "first call 2026-11-24T10:00", "call settled in 12.5 ms", "call timeout 123456789",
             "call(123456)", "call x.py:1234-5678", "tool call took 1234567 ns", "call 1234567", "call 192.168.10.20 failed"]


def test_round18b_call():
    assert [(t, at.redact(t)) for t, s in R18B_REDACT if s in at.redact(t) or "[redacted:phone]" not in at.redact(t)] == []
    assert [(t, at.redact(t)) for t in R18B_STAY if at.redact(t) != t] == []


def test_round18b_key_value_linear_and_unchanged():
    assert at.redact("iban: DE12" + "A" * 40 + " x") == "iban: [redacted:iban] x"
    assert at.redact("iban: GB82 WEST 1234 5698 7654 32.") == at.redact("iban: GB82 WEST 1234 5698 7654 32.")  # (pinned below by TS == Py)
    assert_linear(at.redact, lambda f: ("iban: DE12" + "A" * 40 + " ") * int(2000 * f))


def test_round18b_ts_python(tmp_path):
    import shutil, subprocess
    bun = shutil.which("bun")
    if not bun:
        pytest.skip("bun not installed") if os.environ.get("ACE_ALLOW_NO_BUN") == "1" else pytest.fail("bun missing: the TS/Python parity tests must run (ACE_ALLOW_NO_BUN=1 skips them locally)")
    texts = [t for t, _ in R18B_REDACT] + R18B_STAY + ["iban2: DE89370400440532013000", "email_1=max@firma.de", "iban: DE89 3704 0044 0532 0130 00/x",
             "iban=DE89370400440532013000xyz", "iban: DE12ABCDEFGH", "iban: GB82 WEST 1234 5698 7654 32.", "iban: XX12 3456 7890 1234 bitte",
             "tel: ab12 3456 7890;", "Tel: AB12-3456", "iban: DE12" + "A" * 40 + " x", "iban: DE12 ABCD ABCD ABCD ABCD ABCD ABCD ABCD ABCDX x"]
    (tmp_path / "in.json").write_text(json.dumps(texts))
    (tmp_path / "r.ts").write_text("import { redact } from '%s'\nconsole.log(JSON.stringify(JSON.parse(require('fs').readFileSync('%s', 'utf8')).map((x: string) => redact(x))))\n"
                                   % (PLUGIN / "mod" / "lib" / "redact.ts", tmp_path / "in.json"))
    p = subprocess.run([bun, str(tmp_path / "r.ts")], capture_output=True, text=True, timeout=120)
    assert p.returncode == 0, p.stderr
    assert [(x, a) for x, a in zip(texts, json.loads(p.stdout)) if a != at.redact(x)] == []


# ---- Round 18c (NB1): a number with a leading 0 and one '.' behind 'call' is a phone number, not a decimal ----
def test_round18c_leading_zero_dot():
    P = "[redacted:phone]"
    assert at.redact("call 030.1234567") == "call " + P and at.redact("Call (030.1234567)") == "Call (" + P + ")"
    for t in ("call settled in 12.5 ms", "call 0.5", "call 09.30 am", "+49.301234567", "+4930.1234567", "+0.123456789"):
        assert at.redact(t) == t, t
