#!/usr/bin/env python3
"""8.2.0: engine/backfill.js sends the bootstrap backfill through the core client (fake core + stubbed fetch).

`post` (stdin body) -> POST /traces/backfill, `get --job J` -> GET /traces/backfill/J. stdout = ONE line
{status, body}; exit 0 = any HTTP answer, 3 = gate failed (nothing sent), 1 = transport failure, 2 = bad args.
"""
import json
import os
import subprocess

import pytest

import engine_harness as E

pytestmark = pytest.mark.skipif(E.node_bin() is None, reason="node not installed")
TOKEN = "ace_user_FAKE"
BODY = {"source": "bootstrap", "items": [{"idempotency_key": "k1", "task": "t"}]}


def _stub(tmp_path):
    p = tmp_path / "stub.cjs"
    p.write_text(r"""
const fs = require('fs');
globalThis.fetch = async (url, init) => {
  fs.appendFileSync(process.env.STUB_LOG, JSON.stringify({ url: String(url), method: init.method, body: init.body || null }) + '\n');
  if (process.env.STUB_STATUS === 'net') throw new TypeError('fetch failed');
  return new Response(process.env.STUB_BODY, { status: Number(process.env.STUB_STATUS), headers: { 'Content-Type': 'application/json' } });
};
""")
    return p


def _run(tmp_path, args, stdin="", status=202, body='{"job_id":"j1"}', bin_dir=None, **env):
    bin_dir = bin_dir or E.make_prefix(tmp_path)
    stub = _stub(tmp_path)
    e = dict(os.environ, PATH=E.path_with(bin_dir), NODE_OPTIONS="--require " + str(stub), STUB_STATUS=str(status),
             STUB_BODY=body, STUB_LOG=str(tmp_path / "fetch.log"), ACE_FAKE_CORE_LOG=str(tmp_path / "core.log"))
    e.update(env)
    r = subprocess.run([E.node_bin(), str(E.ENGINE / "backfill.js")] + args, input=stdin, capture_output=True,
                       text=True, env=e, timeout=30)
    return r, E.read_jsonl(tmp_path / "core.log"), E.read_jsonl(tmp_path / "fetch.log")


POST = ["post", "--org", "o", "--project", "p"]


def test_post_sends_json_body_via_request(tmp_path):
    r, core, fetch = _run(tmp_path, POST, json.dumps(BODY))
    assert r.returncode == 0, r.stderr
    bf = [x for x in core if x["op"] == "backfill"]
    assert len(bf) == 1 and bf[0]["method"] == "POST" and bf[0]["endpoint"] == "/traces/backfill" and bf[0]["body"] == BODY
    assert [x for x in core if x["op"] == "context"][0]["project"] == "p"
    assert len(r.stdout.strip().splitlines()) == 1
    assert json.loads(r.stdout) == {"status": 202, "body": {"job_id": "j1"}}


def test_get_hits_the_job_path(tmp_path):
    r, core, fetch = _run(tmp_path, ["get", "--org", "o", "--project", "p", "--job", "job_9"], status=200,
                          body='{"state":"done"}')
    assert r.returncode == 0, r.stderr
    assert fetch[0]["method"] == "GET" and fetch[0]["url"].endswith("/traces/backfill/job_9")
    assert json.loads(r.stdout) == {"status": 200, "body": {"state": "done"}}


@pytest.mark.parametrize("status,body", [(413, '{"error_code":"too_large"}'), (429, '{"retry_after":5}'),
                                         (422, '{"message":"bad item"}'), (503, '{"message":"busy"}')])
def test_error_answers_come_back_with_exit_0(tmp_path, status, body):
    r, core, fetch = _run(tmp_path, POST, json.dumps(BODY), status=status, body=body)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout) == {"status": status, "body": json.loads(body)}
    assert len(fetch) == 1  # never retried


def test_non_json_answer_has_null_body(tmp_path):
    r, _, _ = _run(tmp_path, POST, json.dumps(BODY), status=502, body="<html>")
    assert r.returncode == 0 and json.loads(r.stdout) == {"status": 502, "body": None}


def test_transport_failure_exits_1_with_empty_stdout(tmp_path):
    r, _, _ = _run(tmp_path, POST, json.dumps(BODY), status="net")
    assert r.returncode == 1 and not r.stdout.strip()


def test_gate_failure_exits_3_and_sends_nothing(tmp_path):
    r, core, fetch = _run(tmp_path, POST, json.dumps(BODY), bin_dir=E.make_prefix(tmp_path, no_export=True))
    assert r.returncode == 3 and not fetch and not r.stdout.strip()


def test_missing_request_method_exits_3(tmp_path):
    r, core, fetch = _run(tmp_path, POST, json.dumps(BODY), ACE_FAKE_CORE_NO_REQUEST="1")
    assert r.returncode == 3 and "gate: request_missing" in r.stderr and not fetch


def test_token_never_printed(tmp_path):
    for status in (202, 429, "net"):
        tmp_path = tmp_path / str(status)
        tmp_path.mkdir()
        r, _, _ = _run(tmp_path, POST, json.dumps(BODY), status=status)
        assert TOKEN not in r.stdout + r.stderr and "Authorization" not in r.stdout + r.stderr


@pytest.mark.parametrize("args,stdin", [
    ([], ""), (["bogus", "--org", "o", "--project", "p"], ""), (["post", "--project", "p"], "{}"),
    (["post", "--org", "o"], "{}"), (["get", "--org", "o", "--project", "p"], ""),
    (["post", "--org", "o", "--project", "p"], "not json"), (["post", "--org", "o", "--project", "p"], "[1]")])
def test_bad_args_exit_2_no_network(tmp_path, args, stdin):
    r, core, fetch = _run(tmp_path, args, stdin)
    assert r.returncode == 2 and r.stderr.strip() and not fetch and not r.stdout.strip()
    assert not [x for x in core if x["op"] == "backfill"]


def test_learn_and_search_gate_unchanged_without_request(tmp_path):
    """learn.js/search.js do not need request(): their gate must stay as it was."""
    bin_dir = E.make_prefix(tmp_path)
    e = dict(os.environ, PATH=E.path_with(bin_dir), ACE_FAKE_CORE_NO_REQUEST="1")
    r = subprocess.run([E.node_bin(), str(E.ENGINE / "search.js")], input=json.dumps({"query": "q", "org": "o", "project": "p"}),
                       capture_output=True, text=True, env=e, timeout=30)
    assert r.returncode == 0, r.stderr
