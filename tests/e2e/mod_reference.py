"""Python reference for the v8 production mod (DESIGN §13.1, §9 G9, §4/C1, §12).

The mod (plugins/ace/mod, TypeScript) must produce exactly what these functions
produce. They are built ONLY on the shipped Python modules (render_patterns_dict,
append_patterns_used), so "mod == reference" means "mod == the Python chain".

Also generates the committed fixtures (synthetic: no real server data in the repo):
    python3 tests/e2e/mod_reference.py --write
writes tests/e2e/fixtures/mod/*.json and their TS twins under
plugins/ace/mod/tests/fixtures/*.ts (the `claude plugin test` kit imports .ts).
test_mod_shared_state.py fails when the committed files drift from this generator.
"""
import hashlib
import html
import json
import random
import sys
import tempfile
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PLUGIN = REPO / "plugins" / "ace"
MOD = PLUGIN / "mod"
FIX_JSON = Path(__file__).resolve().parent / "fixtures" / "mod"
FIX_TS = MOD / "tests" / "fixtures"
for _p in (PLUGIN / "shared-hooks" / "utils", PLUGIN / "utils"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from ace_pattern_render import render_patterns_dict  # noqa: E402

HUMAN_PROMPT = "please fix the domain shift hook so it injects patterns when reading plugin files"
TSID_PLACEHOLDER = "__TSID__"
FULL_CAP = 95000          # §13.1 100K guard: drop tail patterns until <= 95,000 chars
STATE_RENDER_CAP = 10000  # C1 rendered_context cap (patterns_used_state.RENDERED_CONTEXT_MAX)
DOMAIN_CAP = 10000        # ace_domain_shift._CAP

DOMAINS = ["ace-cli", "claude-plugins", "ace-plugin-release-management", "system-validation-and-testing"]
SECTIONS = ["strategies_and_hard_rules", "troubleshooting_and_pitfalls", "apis_to_use", "useful_code_snippets"]
FILLER = ("Use `ace-cli search --stdin` and keep the \"quoted\" path C:\\tmp\\x; "
          "naïve café ☃ — résumé → ok.\nSecond line\twith tab. ")


def _uuid(rng):
    return str(uuid.UUID(int=rng.getrandbits(128), version=4))


def make_search_response(n, seed, content_len=300):
    """Deterministic synthetic `ace-cli search --json` response with the edge cases the
    renderer must survive: shuffled/None bandit_rank, float reprs, bool/float log ids,
    invalid + ctx- ids, unicode, a lone surrogate escape (seed-dependent position)."""
    rng = random.Random(seed)
    ranks = list(range(1, n + 1))
    rng.shuffle(ranks)
    floats = [0.30000000000000004, 1e-05, 1e16, 2.5e-07, 1.5e300, -0.0, 1.0, 0.7, 2.4000000000000004, 123456789012345.67]
    pats = []
    for i in range(n):
        content = (FILLER * (content_len // len(FILLER) + 1))[:content_len] + " #%d" % i
        mf = {"bandit_rank": ranks[i] if i % 11 != 5 else None,
              "semantic_score": round(rng.random(), 4) if i % 7 != 3 else None,
              "retrieval_log_id": 1000 + i}
        if i % 13 == 4:
            mf["retrieval_log_id"] = True     # bool is never a log id
        if i % 17 == 8:
            mf["retrieval_log_id"] = 5.0      # float is never a log id
        p = {
            "id": _uuid(rng) if i % 9 else "ctx-%d-%s" % (3000000000 + i, "ab%02d" % i),
            "name": "", "domain": DOMAINS[i % len(DOMAINS)], "content": content,
            "confidence": floats[i % len(floats)], "observations": i, "helpful": round(rng.random() * 10, 1),
            "harmful": floats[(i + 3) % len(floats)], "section": SECTIONS[i % len(SECTIONS)],
            "created_at": "2026-11-02T06:18:25.904544Z",
            "evidence": ["evidence %d ü" % k for k in range(i % 4)] if i % 5 else "string evidence",
            "root_cause": "" if i % 3 else "root cause %d" % i, "error_context": "ec" if i % 6 == 1 else "",
            "cumulative_v15_reward": [0.7, 1.1, -0.7, 0, 5.4][i % 5], "isAtRisk": [False, True, None][i % 3],
            "n_hot_pos": i % 3, "n_hot_neg": (i + 1) % 2, "match_factors": mf,
            "extra_internal": {"x": i},
        }
        if i == n - 2 and n > 3:
            p["id"] = "BAD id"
        if i == n - 1 and n > 3:
            del p["id"]
        pats.append(p)
    dsum = {}
    for p in pats:
        dsum[p["domain"]] = dsum.get(p["domain"], 0) + 1
    resp = {"similar_patterns": pats, "count": n, "threshold": 0.5, "domains_summary": dsum,
            "retrieval_id": _uuid(rng), "expanded": [], "zz_extra": 0.1}
    text = json.dumps(resp)
    if n > 3:  # a lone surrogate escape the way a buggy server could send one
        text = text.replace(" #2\"", " #2 \\ud800 end\"", 1)
    return text


def sanitize(obj):
    """ace_before_task.sanitize_response (copied: importing the hook pulls the whole module)."""
    if isinstance(obj, str):
        return obj.encode("utf-8", errors="surrogatepass").decode("utf-8", errors="replace")
    if isinstance(obj, dict):
        return {k: sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize(x) for x in obj]
    return obj


def load_response(text):
    return sanitize(json.loads(text))


def _body(d, patterns):
    base = [(k, v) for k, v in d.items() if k not in ("similar_patterns", "count")]
    parts = ["%s: %s" % (json.dumps(k), json.dumps(v)) for k, v in base]
    parts.append('"similar_patterns": [' + ", ".join(json.dumps(p, sort_keys=True) for p in patterns) + "]")
    parts.append('"count": %d' % len(patterns))
    return "{" + ", ".join(parts) + "}"


def render_full(resp, tag, attrs, cap=FULL_CAP):
    """The mod's injection: ALL patterns in the render_patterns envelope, per-pattern keys
    SORTED (Python's own order is PYTHONHASHSEED-dependent), whole tail patterns dropped
    until the string is <= cap (never raw-truncated). Returns (context, ids, rlog, shown, total)."""
    d, ids, rlog = render_patterns_dict(resp)
    pats = list(d["similar_patterns"])
    total = len(pats)
    while True:
        n = len(pats)
        opn = '<%s shown="%d" of="%d"%s>' % (tag, n, total, (" " + attrs) if attrs else "")
        ctx = "%s\n%s\n</%s>" % (opn, _body(d, pats), tag)
        if len(ctx) <= cap or not pats:
            break
        pats = pats[:-1]
    shown_ids = [p["id"] for p in pats if p.get("id") in ids]
    return ctx, shown_ids, {k: v for k, v in rlog.items() if k in shown_ids}, len(pats), total


def render_domain_shift(resp, domain):
    """ace_domain_shift._context with sorted per-pattern keys (m1 renderDomainShift)."""
    d, ids, rlog = render_patterns_dict(resp)
    pats = list(d["similar_patterns"])
    attr = html.escape(domain, quote=True)
    while True:
        body = "{" + ", ".join(
            "%s: %s" % (json.dumps(k), ("[" + ", ".join(json.dumps(p, sort_keys=True) for p in pats) + "]")
                        if k == "similar_patterns" else json.dumps(len(pats) if k == "count" else v))
            for k, v in d.items()) + "}"
        ctx = '<ace-patterns-domain-shift domain="%s">%s</ace-patterns-domain-shift>' % (attr, body)
        if len(ctx) <= DOMAIN_CAP or not pats:
            return ctx
        pats = pats[:-1]


def eval_injection(req):
    """ace_before_task.check_eval_request_and_review text for one request dict."""
    return ("<!-- ACE Self-Eval Request: Previous task used %s patterns (%s%% relevance, %s domains, %s tools). "
            "As a human developer, how much time did these patterns save? "
            "Without ACE, a developer would search docs, explore codebases, ask colleagues, or trial-and-error. "
            "Rate from a HUMAN DEVELOPER perspective, not AI perspective. "
            "Include in your response: ACE_REVIEW: N%% | Xm saved | one-line reason -->"
            % (req.get("patterns_injected", 0), req.get("avg_relevance", 0), req.get("domains", 0),
               req.get("tools_executed", 0)))


def render_bucket(session_id):
    """render_cohort's salted bucket (ace_pattern_render.render_cohort)."""
    return int(hashlib.sha256(("render:" + session_id).encode()).hexdigest()[:8], 16) % 100


def mod_render_cohort(session_id, env):
    """The mod's cohort (§13.1): render_cohort's salted bucket and ACE_AB_* knobs (same validation as
    ace_pattern_render._read_ab_pcts) plus ACE_RENDER_FULL_PCT (default 100, invalid -> 100), clamped
    to what control+compact leave. Arms in bucket order: control, compact, full, budget.
    No anchor -> 'full' (the default arm; never experiment without one)."""
    try:
        ctrl, comp = int(env.get("ACE_AB_CONTROL_PCT", "0")), int(env.get("ACE_AB_COMPACT_PCT", "0"))
        if ctrl < 0 or comp < 0 or min(ctrl, 100) + min(comp, 100) > 100:
            raise ValueError
        ctrl, comp = min(ctrl, 100), min(comp, 100)
    except (TypeError, ValueError):
        ctrl, comp = 0, 0
    try:
        full = int(env.get("ACE_RENDER_FULL_PCT", "100"))
        if full < 0:
            raise ValueError
    except (TypeError, ValueError):
        full = 100
    full = min(full, 100 - ctrl - comp)
    if not session_id:
        return "full"
    b = render_bucket(session_id)
    return ("control" if b < ctrl else "compact" if b < ctrl + comp
            else "full" if b < ctrl + comp + full else "budget")


def expected_main_state(search_text, prompt=HUMAN_PROMPT, tsid=TSID_PLACEHOLDER):
    """The exact bytes patterns_used_state.append_patterns_used writes for a main-agent
    UPS of `prompt` whose search returned `search_text` (the mod must write the same)."""
    import patterns_used_state as pus
    resp = load_response(search_text)
    _ctx, ids, rlog, _n, _t = render_full(resp, "ace-patterns", 'agent-type="main"')
    rendered = render_full(resp, "ace-patterns", 'agent-type="main"', cap=STATE_RENDER_CAP)[0]
    with tempfile.TemporaryDirectory() as d:
        pus.append_patterns_used("s", None, ids, state_dir=d, retrieval_id=resp.get("retrieval_id"),
                                 retrieval_log_ids=rlog, task_session_id=tsid, user_prompt=prompt,
                                 rendered_context=rendered, hook_event_name="UserPromptSubmit", reset=True,
                                 render_variant="full")  # §28: the mod renders the full arm by default
        return (Path(d) / "patterns-used-main.json").read_text()


def generated_files():
    """{path: text} of every committed generated fixture."""
    s100, s8, sbig = make_search_response(100, 1), make_search_response(8, 2), make_search_response(120, 3, 1000)
    edge = make_search_response(6, 4, 40)
    r8, redge = load_response(s8), load_response(edge)
    out = {}
    for name, text in (("search_100", s100), ("search_8", s8), ("search_120_big", sbig), ("search_edge", edge)):
        out[FIX_JSON / (name + ".json")] = text
        if name != "search_120_big":  # the TS suite builds its own oversized response
            out[FIX_TS / (name + ".ts")] = "export default " + json.dumps(text) + "\n"
    goldens = {
        "full_main_8": render_full(r8, "ace-patterns", 'agent-type="main"')[0],
        "full_main_edge": render_full(redge, "ace-patterns", 'agent-type="main"')[0],
        "full_sub_8": render_full(r8, "ace-patterns-subagent", 'agent-type="general-purpose"')[0],
        "domain_shift_8": render_domain_shift(r8, "ace-cli"),
        "state_main_8": expected_main_state(s8),
        "eval_injection": eval_injection({"patterns_injected": 100, "avg_relevance": 0, "domains": 0,
                                          "tools_executed": 2, "success": True}),
    }
    out[FIX_JSON / "golden.json"] = json.dumps(goldens, indent=1, sort_keys=True) + "\n"
    out[FIX_TS / "golden.ts"] = "export default " + json.dumps(goldens, sort_keys=True) + " as Record<string, string>\n"
    return out


if __name__ == "__main__":
    if "--write" in sys.argv:
        for path, text in generated_files().items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
            print(path.relative_to(REPO), len(text))
