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
    t0 = time.time()
    at.redact(big)
    assert time.time() - t0 < 3.0



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
        pytest.skip("bun not installed")
    texts = [t for _, t, _ in SECRETS] + NORMAL
    (tmp_path / "in.json").write_text(json.dumps(texts))
    (tmp_path / "r.ts").write_text("import { redact } from '%s'\nconst t = JSON.parse(require('fs').readFileSync('%s', 'utf8'))\nconsole.log(JSON.stringify(t.map((x: string) => redact(x))))\n"
                                   % (PLUGIN / "mod" / "lib" / "redact.ts", tmp_path / "in.json"))
    p = subprocess.run([bun, str(tmp_path / "r.ts")], capture_output=True, text=True, timeout=120)
    assert p.returncode == 0, p.stderr
    diff = [(x[:40], ts[:60], at.redact(x)[:60]) for x, ts in zip(texts, json.loads(p.stdout)) if at.redact(x) != ts]
    assert diff == []


# ---- round 9 N6: CR-heavy text is linear in both chains (cookie-jar fields stop at CR as JS ^/$ do) ----
def _ts_ms(tmp_path, n):
    import shutil, subprocess
    bun = shutil.which("bun")
    if not bun:
        pytest.skip("bun not installed")
    (tmp_path / "t.ts").write_text("import { redact } from '%s'\nconst t = 'x\\r'.repeat(%d) + '\\tTRUE\\tx'\nconst t0 = performance.now(); redact(t); console.log(performance.now() - t0)\n"
                                   % (PLUGIN / "mod" / "lib" / "redact.ts", n))
    return float(subprocess.run([bun, str(tmp_path / "t.ts")], capture_output=True, text=True, timeout=120).stdout)


def test_round9_cr_heavy_text_is_linear_python():
    t0 = time.time()
    at.redact("x\r" * 1_000_000 + "\tTRUE\tx")   # 2 MB, one CR per 2 chars: quadratic would take minutes
    assert time.time() - t0 < 10


def test_round9_cr_heavy_text_is_linear_ts(tmp_path):
    assert _ts_ms(tmp_path, 1_000_000) < 10_000


# ---- round 9 N7: \s / \S in the env / url-cred / pgpass rules mean JS's whitespace set in both chains ----
WS_EDGE = ["AUTH_SALT=\x85saltvalue-ab12cd", "AUTH_SALT=﻿saltvalue-ab12cd", "AUTH_SALT=\x1csaltvalue-ab12cd",
           "redis at\x1cadmin:pw1234@cache.example.org", "redis at﻿admin:pw1234@cache.example.org", "redis at\x85admin:pw1234@cache.example.org",
           "db\x1cx:5432:app:svc:hunter2pw", "db.example:5432:app:svc:hunter2\x85pw", "db.example:5432:app:svc:hunter2﻿pw",
           "12 AUTH_SALT=saltvalue-ab12cd", "src/x　y:3:AUTH_SALT=saltvalue-ab12cd", "AUTH_SALT= saltvalue-ab12cd"]


def test_round9_whitespace_parity_ts_python(tmp_path):
    import shutil, subprocess
    bun = shutil.which("bun")
    if not bun:
        pytest.skip("bun not installed")
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
        pytest.skip("bun not installed")
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
    t0 = time.time()
    at.redact(pre + unit * n)          # ~2 MB; quadratic took minutes
    assert time.time() - t0 < 15


def test_round10_l3_linear_ts(tmp_path):
    import shutil, subprocess
    bun = shutil.which("bun")
    if not bun:
        pytest.skip("bun not installed")
    (tmp_path / "f.json").write_text(json.dumps(L3_FORMS))
    (tmp_path / "t.ts").write_text("import { redact } from '%s'\nconst f = JSON.parse(require('fs').readFileSync('%s','utf8'))\nconst out: any = {}\n"
                                   "for (const k of Object.keys(f)) { const [p, u, n] = f[k]; const t0 = performance.now(); redact(p + u.repeat(n)); out[k] = performance.now() - t0 }\n"
                                   "console.log(JSON.stringify(out))\n" % (PLUGIN / "mod" / "lib" / "redact.ts", tmp_path / "f.json"))
    p = subprocess.run([bun, str(tmp_path / "t.ts")], capture_output=True, text=True, timeout=150)
    assert p.returncode == 0, p.stderr
    ms = json.loads(p.stdout)
    assert all(v < 15000 for v in ms.values()), ms


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
        pytest.skip("bun not installed")
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
    t0 = time.time()
    r = at.redact(big)
    assert time.time() - t0 < 3.0
    assert r.count("[redacted:name-value]") == 40 and "a" * 1000 not in r


def test_round12_i31_nv_json_600k_value_redacted_python():
    r = at.redact(_nv_pair("x" * 600_000))
    assert "[redacted:name-value]" in r and "x" * 1000 not in r


def test_round12_i31_nv_json_ts_python(tmp_path):
    import shutil, subprocess
    bun = shutil.which("bun")
    if not bun:
        pytest.skip("bun not installed")
    items = ["[" + ", ".join(_nv_pair("a" * 100_000) for _ in range(40)) + "]", _nv_pair("x" * 600_000)]
    (tmp_path / "in.json").write_text(json.dumps(items))
    (tmp_path / "r.ts").write_text("import { redact } from '%s'\nconst t = JSON.parse(require('fs').readFileSync('%s', 'utf8'))\n"
                                   "const out: any[] = []\nfor (const x of t) { const t0 = performance.now(); const r = redact(x); out.push([r, performance.now() - t0]) }\n"
                                   "console.log(JSON.stringify(out))\n" % (PLUGIN / "mod" / "lib" / "redact.ts", tmp_path / "in.json"))
    p = subprocess.run([bun, str(tmp_path / "r.ts")], capture_output=True, text=True, timeout=120)
    assert p.returncode == 0, p.stderr
    out = json.loads(p.stdout)
    assert [r for r, _ in out] == [at.redact(x) for x in items]
    assert all(ms < 2000 for _, ms in out), [ms for _, ms in out]


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


R13_HOSTILE = {"dot_chain": "a@" + "a." * 100_000 + "1", "long_local": "a@" + "a" * 1_000_000, "many_at": "a@b." * 1_000_000,
               "many_plus": "+1 " * 1_300_000, "digit_run": "+" + "1" * 4_000_000, "upper_run": "AB12" + "C" * 4_000_000,
               "kw_spam": "tel " * 1_000_000, "key_spam": "phone: " * 570_000, "real_emails": "x@acme-corp.io " * 280_000,
               "iban_spam": "DE89 3704 0044 0532 0130 00 " * 140_000}


@pytest.mark.parametrize("form", sorted(R13_HOSTILE))
def test_round13_pii_linear_python(form):
    t0 = time.time()
    at.redact(R13_HOSTILE[form])
    assert time.time() - t0 < 15, form


def test_round13_pii_ts_python(tmp_path):
    import shutil, subprocess
    bun = shutil.which("bun")
    if not bun:
        pytest.skip("bun not installed")
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
        pytest.skip("bun not installed")
    (tmp_path / "f.json").write_text(json.dumps(R13_HOSTILE))
    (tmp_path / "t.ts").write_text("import { redact } from '%s'\nconst f = JSON.parse(require('fs').readFileSync('%s','utf8'))\nconst out: any = {}\n"
                                   "for (const k of Object.keys(f)) { const t0 = performance.now(); redact(f[k]); out[k] = performance.now() - t0 }\n"
                                   "console.log(JSON.stringify(out))\n" % (PLUGIN / "mod" / "lib" / "redact.ts", tmp_path / "f.json"))
    p = subprocess.run([bun, str(tmp_path / "t.ts")], capture_output=True, text=True, timeout=300)
    assert p.returncode == 0, p.stderr
    ms = json.loads(p.stdout)
    assert all(v < 15000 for v in ms.values()), ms


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
        pytest.skip("bun not installed")
    lines = _ui_lines()
    (tmp_path / "in.json").write_text(json.dumps(lines))
    (tmp_path / "r.ts").write_text("import { redact } from '%s'\nconsole.log(JSON.stringify(JSON.parse(require('fs').readFileSync('%s','utf8')).map((x: string) => redact(x))))\n"
                                   % (PLUGIN / "mod" / "lib" / "redact.ts", tmp_path / "in.json"))
    p = subprocess.run([bun, str(tmp_path / "r.ts")], capture_output=True, text=True, timeout=120)
    assert p.returncode == 0, p.stderr
    assert [(l, t) for l, t in zip(lines, json.loads(p.stdout)) if at.redact(l) != t] == []
