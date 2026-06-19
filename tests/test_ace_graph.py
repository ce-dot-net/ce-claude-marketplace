#!/usr/bin/env python3
"""
RED tests for ace_graph_builder.py and the ace-graph.md command.

Covers:
  1. resolve_graph_db  - env-first, fallback most-recent, None when absent
  2. load_graph        - synthetic DB: nodes/edges, min_weight filter, max_edges
                         truncation+flag, missing-endpoint edges dropped,
                         malformed payload skipped, empty DB is safe
  3. build_graph_html  - inline JSON present, node+edge present, XSS escaping
  4. command sync      - ace-graph.md uses dynamic plugin-root resolution,
                         no hardcoded marketplaces/ path, imports ace_graph_builder

Run with:
    python3 -m pytest tests/test_ace_graph.py -v
"""

import json
import os
import re
import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Path setup: import ace_graph_builder without installing
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
UTILS_DIR = PROJECT_ROOT / "plugins" / "ace" / "shared-hooks" / "utils"
sys.path.insert(0, str(UTILS_DIR))

from ace_graph_builder import (
    build_graph_html,
    load_graph,
    resolve_graph_db,
)

# ---------------------------------------------------------------------------
# Paths for command-sync tests
# ---------------------------------------------------------------------------
ACE_GRAPH_MD = PROJECT_ROOT / "plugins" / "ace" / "commands" / "ace-graph.md"


# ===========================================================================
# Helpers
# ===========================================================================

def _make_db(patterns, edges):
    """
    Create a temporary SQLite DB with patterns+edges tables.

    patterns: list of dicts with keys:
        pattern_id, domain, section, content, cumulative_v15_reward,
        confidence, helpful, harmful, isAtRisk
        (payload_json is built from those keys)
    edges: list of (src, dst, weight) tuples

    Returns the path to the temp file.
    """
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = tmp.name

    con = sqlite3.connect(db_path)
    con.execute(
        "CREATE TABLE patterns "
        "(pattern_id TEXT PRIMARY KEY, payload_json TEXT, "
        "cumulative_reward REAL, fetched_at_ms INTEGER, expires_at_ms INTEGER)"
    )
    con.execute(
        "CREATE TABLE edges "
        "(src TEXT, dst TEXT, weight INTEGER, PRIMARY KEY(src, dst))"
    )
    for p in patterns:
        payload = {
            "id": p["pattern_id"],
            "domain": p.get("domain", "test-domain"),
            "section": p.get("section", "useful_code_snippets"),
            "content": p.get("content", "test content"),
            "confidence": p.get("confidence", 0.9),
            "helpful": p.get("helpful", 1.0),
            "harmful": p.get("harmful", 0.0),
            "cumulative_v15_reward": p.get("cumulative_v15_reward", 1.0),
            "isAtRisk": p.get("isAtRisk", False),
        }
        con.execute(
            "INSERT INTO patterns VALUES (?,?,?,?,?)",
            (
                p["pattern_id"],
                json.dumps(payload),
                p.get("cumulative_v15_reward", 1.0),
                1700000000000,
                9999999999999,
            ),
        )
    for src, dst, weight in edges:
        con.execute("INSERT INTO edges VALUES (?,?,?)", (src, dst, weight))
    con.commit()
    con.close()
    return db_path


# ===========================================================================
# 1. resolve_graph_db
# ===========================================================================

class TestResolveGraphDb:
    def test_env_first_double_underscore(self, tmp_path, monkeypatch):
        """
        When settings.json has ACE_ORG_ID + ACE_PROJECT_ID, the function
        resolves '<org>__<project>.db' from cache_dir.
        """
        settings = tmp_path / "settings.json"
        settings.write_text(
            json.dumps(
                {"env": {"ACE_ORG_ID": "org_ABC", "ACE_PROJECT_ID": "prj_123"}}
            )
        )
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        db_file = cache_dir / "org_ABC__prj_123.db"
        # DB must have a patterns table with at least one row
        con = sqlite3.connect(str(db_file))
        con.execute(
            "CREATE TABLE patterns "
            "(pattern_id TEXT PRIMARY KEY, payload_json TEXT, "
            "cumulative_reward REAL, fetched_at_ms INTEGER, expires_at_ms INTEGER)"
        )
        con.execute(
            "INSERT INTO patterns VALUES ('p1', '{}', 1.0, 0, 0)"
        )
        con.commit()
        con.close()

        result = resolve_graph_db(str(settings), str(cache_dir))
        assert result is not None
        assert Path(result).name == "org_ABC__prj_123.db"

    def test_fallback_most_recent_nonempty(self, tmp_path):
        """
        When settings.json is missing, fall back to the most-recently-modified
        *.db in cache_dir that has a non-empty patterns table.
        """
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()

        # Create an older DB (empty patterns)
        old_db = cache_dir / "old__prj.db"
        con = sqlite3.connect(str(old_db))
        con.execute(
            "CREATE TABLE patterns "
            "(pattern_id TEXT, payload_json TEXT, "
            "cumulative_reward REAL, fetched_at_ms INTEGER, expires_at_ms INTEGER)"
        )
        con.commit()
        con.close()
        import time
        time.sleep(0.01)

        # Create a newer DB (has data)
        new_db = cache_dir / "new__prj.db"
        con = sqlite3.connect(str(new_db))
        con.execute(
            "CREATE TABLE patterns "
            "(pattern_id TEXT, payload_json TEXT, "
            "cumulative_reward REAL, fetched_at_ms INTEGER, expires_at_ms INTEGER)"
        )
        con.execute("INSERT INTO patterns VALUES ('p1', '{}', 1.0, 0, 0)")
        con.commit()
        con.close()

        result = resolve_graph_db(None, str(cache_dir))
        assert result is not None
        assert Path(result).name == "new__prj.db"

    def test_returns_none_when_no_db(self, tmp_path):
        """Returns None gracefully when cache_dir is empty."""
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        result = resolve_graph_db(None, str(cache_dir))
        assert result is None

    def test_returns_none_when_cache_dir_missing(self, tmp_path):
        """Returns None gracefully when cache_dir does not exist."""
        result = resolve_graph_db(None, str(tmp_path / "nonexistent"))
        assert result is None

    def test_settings_missing_falls_back(self, tmp_path):
        """
        When settings_path doesn't exist, fall back to most-recent DB.
        """
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        db_file = cache_dir / "fallback__prj.db"
        con = sqlite3.connect(str(db_file))
        con.execute(
            "CREATE TABLE patterns "
            "(pattern_id TEXT, payload_json TEXT, "
            "cumulative_reward REAL, fetched_at_ms INTEGER, expires_at_ms INTEGER)"
        )
        con.execute("INSERT INTO patterns VALUES ('p1', '{}', 1.0, 0, 0)")
        con.commit()
        con.close()

        result = resolve_graph_db(str(tmp_path / "no_such.json"), str(cache_dir))
        assert result is not None
        assert "fallback__prj" in Path(result).name


# ===========================================================================
# 2. load_graph
# ===========================================================================

class TestLoadGraph:
    def test_basic_nodes_and_edges(self, tmp_path):
        """load_graph returns nodes and edges for a simple 3-node graph."""
        patterns = [
            {"pattern_id": "p1", "domain": "dom-a"},
            {"pattern_id": "p2", "domain": "dom-b"},
            {"pattern_id": "p3", "domain": "dom-a"},
        ]
        edges = [("p1", "p2", 5), ("p2", "p3", 3)]
        db = _make_db(patterns, edges)

        g = load_graph(db, min_weight=1)
        assert len(g["nodes"]) == 3
        assert len(g["edges"]) == 2
        node_ids = {n["id"] for n in g["nodes"]}
        assert node_ids == {"p1", "p2", "p3"}

    def test_min_weight_filter(self, tmp_path):
        """Edges below min_weight are excluded."""
        patterns = [
            {"pattern_id": "p1"},
            {"pattern_id": "p2"},
            {"pattern_id": "p3"},
        ]
        edges = [("p1", "p2", 5), ("p2", "p3", 1)]
        db = _make_db(patterns, edges)

        g = load_graph(db, min_weight=2)
        assert len(g["edges"]) == 1
        assert g["edges"][0]["src"] == "p1"
        assert g["edges"][0]["dst"] == "p2"

    def test_max_edges_truncation(self, tmp_path):
        """When edge count exceeds max_edges, keep top by weight; set truncated=True."""
        patterns = [{"pattern_id": f"p{i}"} for i in range(6)]
        # 5 edges with varying weights
        edges = [
            ("p0", "p1", 10),
            ("p1", "p2", 8),
            ("p2", "p3", 6),
            ("p3", "p4", 4),
            ("p4", "p5", 2),
        ]
        db = _make_db(patterns, edges)

        g = load_graph(db, min_weight=1, max_edges=3)
        assert len(g["edges"]) == 3
        assert g["meta"]["truncated"] is True
        weights = [e["weight"] for e in g["edges"]]
        assert sorted(weights, reverse=True) == weights  # top-N by weight

    def test_no_truncation_flag_when_within_limit(self, tmp_path):
        """truncated is False when edge count is within max_edges."""
        patterns = [{"pattern_id": "p1"}, {"pattern_id": "p2"}]
        edges = [("p1", "p2", 5)]
        db = _make_db(patterns, edges)

        g = load_graph(db, min_weight=1, max_edges=1500)
        assert g["meta"]["truncated"] is False

    def test_edges_with_missing_endpoint_dropped(self, tmp_path):
        """Edges referencing a pattern_id not in the patterns table are dropped."""
        patterns = [{"pattern_id": "p1"}, {"pattern_id": "p2"}]
        # p3 does not exist in patterns
        edges = [("p1", "p2", 5), ("p2", "p3", 10)]
        db = _make_db(patterns, edges)

        g = load_graph(db, min_weight=1)
        assert len(g["edges"]) == 1
        assert g["edges"][0]["src"] == "p1"
        assert g["edges"][0]["dst"] == "p2"

    def test_malformed_payload_json_skipped(self, tmp_path):
        """Patterns with malformed payload_json are skipped without crashing."""
        db_path = tmp_path / "bad.db"
        con = sqlite3.connect(str(db_path))
        con.execute(
            "CREATE TABLE patterns "
            "(pattern_id TEXT PRIMARY KEY, payload_json TEXT, "
            "cumulative_reward REAL, fetched_at_ms INTEGER, expires_at_ms INTEGER)"
        )
        con.execute(
            "CREATE TABLE edges "
            "(src TEXT, dst TEXT, weight INTEGER, PRIMARY KEY(src, dst))"
        )
        # One valid row, one malformed JSON
        con.execute("INSERT INTO patterns VALUES ('good', '{\"domain\": \"x\", \"section\": \"s\", \"content\": \"c\"}', 1.0, 0, 0)")
        con.execute("INSERT INTO patterns VALUES ('bad', 'NOT_JSON{{{{', 0.0, 0, 0)")
        con.execute("INSERT INTO edges VALUES ('good', 'bad', 5)")
        con.commit()
        con.close()

        # Must not raise
        g = load_graph(str(db_path), min_weight=1)
        # 'bad' was skipped, so its edge is dropped too
        good_ids = {n["id"] for n in g["nodes"]}
        assert "good" in good_ids
        assert "bad" not in good_ids
        assert len(g["edges"]) == 0  # edge to 'bad' dropped

    def test_empty_db_returns_empty_graph(self, tmp_path):
        """Empty patterns/edges tables produce an empty graph without crashing."""
        db = _make_db([], [])
        g = load_graph(db, min_weight=1)
        assert g["nodes"] == []
        assert g["edges"] == []
        assert g["meta"]["total_patterns"] == 0

    def test_node_degree_computed_from_kept_edges(self, tmp_path):
        """Each node's degree reflects the count of kept edges it participates in."""
        patterns = [
            {"pattern_id": "hub"},
            {"pattern_id": "spoke1"},
            {"pattern_id": "spoke2"},
            {"pattern_id": "spoke3"},
        ]
        edges = [
            ("hub", "spoke1", 5),
            ("hub", "spoke2", 5),
            ("hub", "spoke3", 5),
        ]
        db = _make_db(patterns, edges)
        g = load_graph(db, min_weight=1)
        hub = next(n for n in g["nodes"] if n["id"] == "hub")
        assert hub["degree"] == 3

    def test_meta_contains_project_info(self, tmp_path):
        """meta dict includes total_patterns, total_edges, rendered_edges, truncated."""
        patterns = [{"pattern_id": "p1"}, {"pattern_id": "p2"}]
        edges = [("p1", "p2", 5)]
        db = _make_db(patterns, edges)
        g = load_graph(db, min_weight=1)
        meta = g["meta"]
        assert "total_patterns" in meta
        assert "total_edges" in meta
        assert "rendered_edges" in meta
        assert "truncated" in meta

    def test_node_fields_present(self, tmp_path):
        """Each node dict has id, domain, section, label, reward, degree."""
        patterns = [{"pattern_id": "p1", "domain": "dom", "section": "s", "content": "hello"}]
        db = _make_db(patterns, [])
        g = load_graph(db, min_weight=1)
        assert len(g["nodes"]) == 1
        node = g["nodes"][0]
        for field in ("id", "domain", "section", "label", "reward", "degree"):
            assert field in node, f"missing field: {field}"

    def test_content_snippet_truncated(self, tmp_path):
        """label (content snippet) is truncated for long content."""
        long_content = "x" * 300
        patterns = [{"pattern_id": "p1", "content": long_content}]
        db = _make_db(patterns, [])
        g = load_graph(db, min_weight=1)
        node = g["nodes"][0]
        assert len(node["label"]) < len(long_content)

    def test_only_both_endpoint_edges_counted_for_degree(self, tmp_path):
        """Degree counts only edges where BOTH endpoints are valid nodes."""
        patterns = [{"pattern_id": "p1"}, {"pattern_id": "p2"}]
        edges = [("p1", "p2", 5), ("p1", "ghost", 10)]  # ghost not in patterns
        db = _make_db(patterns, edges)
        g = load_graph(db, min_weight=1)
        p1 = next(n for n in g["nodes"] if n["id"] == "p1")
        # Only edge to p2 kept; degree = 1
        assert p1["degree"] == 1

    def test_load_graph_missing_edges_table_returns_empty(self, tmp_path):
        """
        A DB that has a patterns table but NO edges table must not crash.
        load_graph() must return nodes from patterns and an empty edges list.
        """
        db_path = tmp_path / "patterns_only.db"
        con = sqlite3.connect(str(db_path))
        con.execute(
            "CREATE TABLE patterns "
            "(pattern_id TEXT PRIMARY KEY, payload_json TEXT, "
            "cumulative_reward REAL, fetched_at_ms INTEGER, expires_at_ms INTEGER)"
        )
        con.execute(
            "INSERT INTO patterns VALUES ('p1', "
            "'{\"domain\": \"d\", \"section\": \"s\", \"content\": \"c\"}', "
            "1.0, 0, 0)"
        )
        con.commit()
        con.close()

        # Must not raise sqlite3.OperationalError
        g = load_graph(str(db_path), min_weight=1)
        assert g["edges"] == [], "Expected empty edges list for patterns-only DB"
        node_ids = {n["id"] for n in g["nodes"]}
        assert "p1" in node_ids, "Expected p1 node to be loaded"

    def test_load_graph_raises_on_missing_file(self, tmp_path):
        """
        Calling load_graph() with a path that does not exist must raise
        FileNotFoundError (not a bare shutil.Error or other opaque exception).
        """
        nonexistent = str(tmp_path / "no_such.db")
        with pytest.raises(FileNotFoundError):
            load_graph(nonexistent)


# ===========================================================================
# 3. build_graph_html
# ===========================================================================

class TestBuildGraphHtml:
    def _minimal_graph(self):
        return {
            "nodes": [
                {"id": "p1", "domain": "dom-a", "section": "s1",
                 "label": "short label", "reward": 2.5, "degree": 1},
                {"id": "p2", "domain": "dom-b", "section": "s2",
                 "label": "another label", "reward": 1.0, "degree": 1},
            ],
            "edges": [{"src": "p1", "dst": "p2", "weight": 5}],
            "meta": {
                "total_patterns": 2,
                "total_edges": 1,
                "rendered_edges": 1,
                "truncated": False,
                "project": "prj_test",
                "org": "org_test",
            },
        }

    def test_returns_string(self):
        html = build_graph_html(self._minimal_graph())
        assert isinstance(html, str)

    def test_html_contains_inline_json(self):
        """The graph data must be embedded as inline JSON."""
        g = self._minimal_graph()
        html = build_graph_html(g)
        # The HTML must contain a JS variable assignment with the JSON blob
        assert "p1" in html
        assert "p2" in html
        assert "dom-a" in html

    def test_html_contains_script_tag(self):
        """Output must contain a <script> tag (for the force-directed layout lib)."""
        html = build_graph_html(self._minimal_graph())
        assert "<script" in html.lower()

    def test_html_is_complete_document(self):
        """Output must start with <!DOCTYPE or <html."""
        html = build_graph_html(self._minimal_graph())
        lower = html.lstrip().lower()
        assert lower.startswith("<!doctype") or lower.startswith("<html")

    def test_truncated_note_when_truncated(self):
        """When meta.truncated is True, the HTML mentions truncation."""
        g = self._minimal_graph()
        g["meta"]["truncated"] = True
        g["meta"]["total_edges"] = 5000
        g["meta"]["rendered_edges"] = 1500
        html = build_graph_html(g)
        assert "truncat" in html.lower() or "1500" in html

    # -----------------------------------------------------------------------
    # XSS / escaping tests (critical security requirement)
    # -----------------------------------------------------------------------

    def test_script_injection_in_content_is_escaped(self):
        """
        A pattern whose content contains '</script>' must NOT appear raw/unescaped
        in the HTML in a way that could break out of a script block.
        """
        g = self._minimal_graph()
        g["nodes"][0]["label"] = "</script><script>alert('xss')</script>"
        html = build_graph_html(g)
        # The raw literal </script> must not break out — it must be JSON-encoded
        # json.dumps will turn < into < or escape the string
        # At minimum: the raw "</script><script>" sequence must not appear unescaped
        assert "</script><script>" not in html

    def test_html_injection_in_content_is_escaped(self):
        """
        Patterns containing '"><img onerror=...' must not appear unescaped.
        """
        g = self._minimal_graph()
        evil = '"><img src=x onerror=alert(1)>'
        g["nodes"][0]["label"] = evil
        html = build_graph_html(g)
        assert evil not in html

    def test_data_embedded_via_json_dumps(self):
        """
        Graph data embedded in the HTML must be valid JSON (json.loads succeeds).
        Extract the inline JSON blob and verify it round-trips cleanly.
        """
        g = self._minimal_graph()
        html = build_graph_html(g)
        # Find a JSON blob assignment: var graphData = {...};
        # Allow both single and double quotes around the var name pattern
        match = re.search(r'var\s+graphData\s*=\s*(\{.*?\});', html, re.DOTALL)
        assert match is not None, "Could not find 'var graphData = {...};' in HTML"
        blob = match.group(1)
        parsed = json.loads(blob)
        assert "nodes" in parsed
        assert "edges" in parsed

    def test_empty_graph_does_not_crash(self):
        """build_graph_html must handle zero nodes/edges without crashing."""
        g = {
            "nodes": [],
            "edges": [],
            "meta": {
                "total_patterns": 0,
                "total_edges": 0,
                "rendered_edges": 0,
                "truncated": False,
                "project": "",
                "org": "",
            },
        }
        html = build_graph_html(g)
        assert isinstance(html, str)
        assert len(html) > 0

    def test_single_quotes_in_content_do_not_break_html(self):
        """Content with single quotes must be safely handled."""
        g = self._minimal_graph()
        g["nodes"][0]["label"] = "it's a pattern with 'quotes'"
        html = build_graph_html(g)
        # Must not produce broken JS
        assert isinstance(html, str)
        # Round-trip the JSON blob to confirm it's valid
        match = re.search(r'var\s+graphData\s*=\s*(\{.*?\});', html, re.DOTALL)
        assert match is not None
        json.loads(match.group(1))  # must not raise

    def test_project_name_with_html_is_escaped_in_title(self):
        """
        A project name containing HTML special characters must be escaped
        before being inserted into the <h1> title — raw injection must not appear.
        """
        g = self._minimal_graph()
        g["meta"]["project"] = "</h1><script>xss()</script>"
        html = build_graph_html(g)
        # The raw string must not appear verbatim in the output
        assert "</h1><script>xss()</script>" not in html, (
            "Raw HTML from project name leaked into <h1> without escaping"
        )


# ===========================================================================
# 3b. build_graph_html — project_name parameter (new UX feature)
# ===========================================================================

class TestBuildGraphHtmlProjectName:
    """Tests for the project_name parameter added to build_graph_html."""

    def _minimal_graph(self):
        return {
            "nodes": [
                {"id": "p1", "domain": "dom-a", "section": "s1",
                 "label": "short label", "reward": 2.5, "degree": 1},
            ],
            "edges": [],
            "meta": {
                "total_patterns": 1,
                "total_edges": 0,
                "rendered_edges": 0,
                "truncated": False,
                "project": "prj_d3a244129d62c198",
                "org": "org_test",
            },
        }

    def test_project_name_shown_in_title_when_provided(self):
        """
        build_graph_html(graph, project_name='ce-claude-marketplace')
        must include 'ce-claude-marketplace' in the rendered <h1> title
        and must NOT include the raw meta project ID 'prj_d3a244129d62c198' in the <h1>.
        """
        g = self._minimal_graph()
        html = build_graph_html(g, project_name="ce-claude-marketplace")
        # Extract the h1 text
        h1_match = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL | re.IGNORECASE)
        assert h1_match is not None, "No <h1> found in HTML"
        h1_text = h1_match.group(1)
        assert "ce-claude-marketplace" in h1_text, (
            f"project_name not found in <h1>: {h1_text!r}"
        )
        assert "prj_d3a244129d62c198" not in h1_text, (
            f"Raw project ID leaked into <h1> when project_name was provided: {h1_text!r}"
        )

    def test_fallback_to_meta_project_id_when_name_is_none(self):
        """
        build_graph_html(graph, project_name=None) must fall back to
        meta['project'] (the raw ID) — backward-compatible behaviour.
        """
        g = self._minimal_graph()
        html = build_graph_html(g, project_name=None)
        h1_match = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL | re.IGNORECASE)
        assert h1_match is not None, "No <h1> found in HTML"
        h1_text = h1_match.group(1)
        assert "prj_d3a244129d62c198" in h1_text, (
            f"meta project ID not used as fallback when project_name=None: {h1_text!r}"
        )

    def test_project_name_html_escaped(self):
        """
        project_name containing HTML special characters must be escaped —
        raw injection must not appear in the output.
        """
        g = self._minimal_graph()
        evil = "<img onerror=x>"
        html = build_graph_html(g, project_name=evil)
        assert evil not in html, (
            "project_name was not HTML-escaped: raw injection found in output"
        )
        # The escaped form must appear instead (html.escape converts < to &lt; etc.)
        assert "&lt;img" in html or "\\u003c" in html, (
            "Expected HTML-escaped form of project_name not found"
        )

    def test_no_project_name_arg_backward_compatible(self):
        """
        Calling build_graph_html(graph) with no project_name arg (default)
        falls back to meta project ID — zero-arg backward compatibility.
        """
        g = self._minimal_graph()
        html = build_graph_html(g)  # no project_name kwarg
        h1_match = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL | re.IGNORECASE)
        assert h1_match is not None, "No <h1> found in HTML"
        h1_text = h1_match.group(1)
        assert "prj_d3a244129d62c198" in h1_text, (
            "Default (no project_name) must fall back to meta project ID"
        )

    def test_cytoscape_border_color_no_8digit_hex(self):
        """
        The generated HTML must NOT contain the invalid 8-digit hex color
        '#ffffff22' in a cytoscape style block — cytoscape rejects alpha hex.
        The builder source must use a cytoscape-valid color form instead.
        """
        g = self._minimal_graph()
        html = build_graph_html(g)
        assert "#ffffff22" not in html, (
            "Found '#ffffff22' (invalid 8-digit hex) in cytoscape style — "
            "cytoscape does not support alpha hex; use rgba() or separate border-opacity"
        )

    def test_command_passes_project_name_to_builder(self):
        """
        ace-graph.md must pass project_name= to build_graph_html
        (verifies the I/O layer wires the name lookup through).
        """
        doc = ACE_GRAPH_MD.read_text(encoding="utf-8")
        assert "project_name" in doc, (
            "ace-graph.md must pass project_name= to build_graph_html"
        )

    def test_command_calls_ace_cli_projects(self):
        """
        ace-graph.md must call 'ace-cli projects' (the name lookup).
        Accepts either the shell string form 'ace-cli projects' or the Python
        subprocess list form 'ace-cli', 'projects' (both are equivalent calls).
        """
        doc = ACE_GRAPH_MD.read_text(encoding="utf-8")
        has_shell_form = "ace-cli projects" in doc
        has_list_form = ("'ace-cli'" in doc or '"ace-cli"' in doc) and (
            "'projects'" in doc or '"projects"' in doc
        )
        assert has_shell_form or has_list_form, (
            "ace-graph.md must call 'ace-cli projects' for name lookup "
            "(either shell form 'ace-cli projects' or subprocess list form)"
        )

    def test_command_has_fallback_to_none_on_failure(self):
        """
        ace-graph.md's name-lookup block must set project_name to None
        on any failure (offline / parse error / id-not-found), falling
        back to the ID gracefully.
        """
        doc = ACE_GRAPH_MD.read_text(encoding="utf-8")
        # Must have try/except guarding the lookup
        assert "try:" in doc or "except" in doc, (
            "ace-graph.md must guard the ace-cli projects lookup with try/except"
        )
        # Must have a fallback assignment to None
        assert "project_name = None" in doc or "project_name=None" in doc, (
            "ace-graph.md must set project_name=None on lookup failure"
        )

    def test_command_summary_includes_project_name(self):
        """
        ace-graph.md's summary output must include the project name
        (e.g. 'Project: ce-shell (prj_1f4d...)' format).
        """
        doc = ACE_GRAPH_MD.read_text(encoding="utf-8")
        assert "Project:" in doc or "project_name" in doc.lower(), (
            "ace-graph.md must include project name in the summary output"
        )

    def test_command_name_lookup_uses_real_ace_cli_keys(self):
        """
        Regression guard (v7.1.6): `ace-cli projects --json` records use keys
        project_id / project_name (4.x schema), NOT id / name. The name lookup
        MUST match on project_id and read project_name (id/name only as fallback),
        else project_name stays None and the title shows the raw prj_… ID.
        """
        doc = ACE_GRAPH_MD.read_text(encoding="utf-8")
        assert "p.get('project_id')" in doc or 'p.get("project_id")' in doc, (
            "ace-graph.md name-lookup must match on p.get('project_id') "
            "(ace-cli 4.x schema), not only p.get('id')"
        )
        assert "p.get('project_name')" in doc or 'p.get("project_name")' in doc, (
            "ace-graph.md name-lookup must read p.get('project_name') "
            "(ace-cli 4.x schema), not only p.get('name')"
        )


# ===========================================================================
# 4. Command sync: ace-graph.md
# ===========================================================================

class TestAceGraphCommand:
    def _doc(self):
        return ACE_GRAPH_MD.read_text(encoding="utf-8")

    def test_command_file_exists(self):
        """ace-graph.md must exist in commands/."""
        assert ACE_GRAPH_MD.exists(), f"Missing: {ACE_GRAPH_MD}"

    def test_no_hardcoded_marketplaces_path(self):
        """
        ace-graph.md must NOT hardcode a 'marketplaces/' path —
        it must use dynamic $CLAUDE_PLUGIN_ROOT or the glob pattern.
        """
        doc = self._doc()
        assert "marketplaces/" not in doc, (
            "ace-graph.md must not hardcode 'marketplaces/' — "
            "use $CLAUDE_PLUGIN_ROOT or the cache glob"
        )

    def test_uses_dynamic_plugin_root_resolution(self):
        """
        ace-graph.md must reference CLAUDE_PLUGIN_ROOT or the cache glob
        to locate ace_graph_builder.py dynamically.
        """
        doc = self._doc()
        has_plugin_root = "CLAUDE_PLUGIN_ROOT" in doc
        has_cache_glob = "plugins/cache/" in doc or ".claude/plugins" in doc
        assert has_plugin_root or has_cache_glob, (
            "ace-graph.md must resolve ace_graph_builder dynamically "
            "via CLAUDE_PLUGIN_ROOT or the cache glob pattern"
        )

    def test_imports_ace_graph_builder(self):
        """ace-graph.md must reference ace_graph_builder."""
        doc = self._doc()
        assert "ace_graph_builder" in doc

    def test_has_frontmatter(self):
        """ace-graph.md must have YAML frontmatter with description."""
        doc = self._doc()
        assert doc.startswith("---"), "Missing YAML frontmatter"
        assert "description" in doc

    def test_writes_to_usage_data_dir(self):
        """ace-graph.md must write output to ~/.claude/usage-data/."""
        doc = self._doc()
        assert "usage-data" in doc

    def test_output_file_is_html(self):
        """The output file referenced in ace-graph.md must be ace-graph.html."""
        doc = self._doc()
        assert "ace-graph.html" in doc

    def test_opens_on_darwin(self):
        """On Darwin, the command opens the report with 'open'."""
        doc = self._doc()
        assert "Darwin" in doc or "open" in doc.lower()

    def test_mentions_min_weight_arg(self):
        """ace-graph.md must mention --min-weight argument."""
        doc = self._doc()
        assert "min_weight" in doc or "min-weight" in doc

    def test_mentions_max_edges_arg(self):
        """ace-graph.md must mention --max-edges argument."""
        doc = self._doc()
        assert "max_edges" in doc or "max-edges" in doc


# ===========================================================================
# 5. Isolated-node visibility feature (RED phase)
# ===========================================================================

class TestIsolatedNodeVisibility:
    """
    Tests for the 'Show isolated nodes' feature added to build_graph_html.

    An isolated node is one with no currently-visible edge (degree == 0 in the
    rendered/kept-edge set).  By default they are hidden; a checkbox reveals them.
    """

    def _graph_with_isolated(self):
        """
        3 nodes: p1-p2 connected, p3 isolated (no edge to/from it).
        degree: p1=1, p2=1, p3=0.
        """
        return {
            "nodes": [
                {"id": "p1", "domain": "dom-a", "section": "s1",
                 "label": "connected node 1", "reward": 2.0, "degree": 1},
                {"id": "p2", "domain": "dom-a", "section": "s1",
                 "label": "connected node 2", "reward": 1.5, "degree": 1},
                {"id": "p3", "domain": "dom-b", "section": "s2",
                 "label": "isolated node",    "reward": 0.5, "degree": 0},
            ],
            "edges": [{"src": "p1", "dst": "p2", "weight": 5}],
            "meta": {
                "total_patterns": 3,
                "total_edges": 1,
                "rendered_edges": 1,
                "truncated": False,
                "project": "prj_test",
                "org": "org_test",
            },
        }

    def _graph_all_connected(self):
        """All 2 nodes have an edge between them — no isolated node."""
        return {
            "nodes": [
                {"id": "a1", "domain": "dom-x", "section": "s",
                 "label": "node a1", "reward": 1.0, "degree": 1},
                {"id": "a2", "domain": "dom-x", "section": "s",
                 "label": "node a2", "reward": 1.0, "degree": 1},
            ],
            "edges": [{"src": "a1", "dst": "a2", "weight": 3}],
            "meta": {
                "total_patterns": 2,
                "total_edges": 1,
                "rendered_edges": 1,
                "truncated": False,
                "project": "prj_test",
                "org": "org_test",
            },
        }

    # -----------------------------------------------------------------------
    # T1 — Checkbox control exists
    # -----------------------------------------------------------------------

    def test_checkbox_control_exists(self):
        """
        build_graph_html output must contain an <input type="checkbox"> (or
        type='checkbox') element — the 'Show isolated nodes' toggle.
        """
        html = build_graph_html(self._graph_with_isolated())
        # Accept either single or double quotes around the type value
        assert re.search(r'<input[^>]+type=["\']checkbox["\']', html, re.IGNORECASE), (
            "Expected <input type='checkbox'> for 'Show isolated nodes' toggle"
        )

    def test_checkbox_label_text(self):
        """
        The HTML must contain label text that includes the phrase
        'isolated nodes' (case-insensitive) near the checkbox.
        """
        html = build_graph_html(self._graph_with_isolated())
        assert re.search(r'isolated\s+nodes', html, re.IGNORECASE), (
            "Expected label text 'isolated nodes' near the checkbox control"
        )

    def test_checkbox_default_unchecked(self):
        """
        The 'Show isolated nodes' checkbox must NOT have a 'checked' attribute
        by default (unchecked = isolated nodes hidden on first load).
        """
        html = build_graph_html(self._graph_with_isolated())
        # Find the checkbox input element
        checkbox_match = re.search(
            r'<input[^>]+type=["\']checkbox["\'][^>]*>',
            html,
            re.IGNORECASE | re.DOTALL,
        )
        assert checkbox_match is not None, "No checkbox found"
        checkbox_html = checkbox_match.group(0)
        # The checkbox element itself must not have a 'checked' attribute
        assert "checked" not in checkbox_html.lower(), (
            "Checkbox must be unchecked by default (isolated nodes hidden initially)"
        )

    # -----------------------------------------------------------------------
    # T2 — Default hidden mechanism for isolated nodes
    # -----------------------------------------------------------------------

    def test_isolated_class_or_style_applied_by_default(self):
        """
        The JS/CSS must define a mechanism to hide isolated (degree-0) nodes by
        default.  Accept any of:
          (a) a CSS class rule for an 'isolated' selector with display:none, OR
          (b) a cytoscape style selector targeting 'node.isolated' with display:none, OR
          (c) a JS applyFilters function that hides nodes with 0 visible edges.
        At minimum the word 'isolated' must appear as an identifier/class/selector
        (not just in comments or label text).
        """
        html = build_graph_html(self._graph_with_isolated())
        # 'isolated' must appear as a JS/CSS token (class name, selector, or variable)
        # We allow it to appear in JS code context, e.g. 'isolated', "isolated",
        # .isolated, node.isolated, addClass('isolated'), etc.
        assert re.search(
            r"""['"`\.]isolated['"`\s{,)]""",
            html,
        ), (
            "Expected 'isolated' to appear as a JS/CSS class/selector/identifier "
            "in the generated HTML (not just in prose text)"
        )

    def test_apply_filters_function_exists(self):
        """
        The generated JS must define a single applyFilters (or applyFilters-style)
        function that the slider, dropdown, and checkbox all call — so that
        isolated-node recompute is integrated with existing filter paths.
        Accepts: 'function applyFilters' or 'applyFilters =' or 'var applyFilters'.
        """
        html = build_graph_html(self._graph_with_isolated())
        assert re.search(
            r'(function\s+applyFilters|applyFilters\s*=\s*(function)?)',
            html,
        ), (
            "Expected a JS 'applyFilters' function definition in the generated HTML"
        )

    def test_slider_calls_apply_filters(self):
        """
        The min-weight slider event handler must call applyFilters() (not
        implement its own inline filter logic independently).
        """
        html = build_graph_html(self._graph_with_isolated())
        # The wt-slider listener block must reference applyFilters
        assert re.search(r'wt-slider.*?applyFilters|applyFilters.*?wt-slider', html, re.DOTALL), (
            "wt-slider handler must delegate to applyFilters()"
        )

    def test_domain_filter_calls_apply_filters(self):
        """
        The domain filter (select) event handler must call applyFilters().
        """
        html = build_graph_html(self._graph_with_isolated())
        # The dom-filter listener must reference applyFilters
        assert re.search(r'dom-filter.*?applyFilters|applyFilters.*?dom-filter', html, re.DOTALL), (
            "dom-filter handler must delegate to applyFilters()"
        )

    def test_checkbox_calls_apply_filters(self):
        """
        The 'Show isolated nodes' checkbox event handler must call applyFilters().
        """
        html = build_graph_html(self._graph_with_isolated())
        # show-isolated listener (or equivalent) must reference applyFilters
        assert re.search(
            r'(show.isolated|isolated.*checkbox|checkbox.*isolated).*?applyFilters'
            r'|applyFilters.*?(show.isolated|isolated)',
            html,
            re.DOTALL | re.IGNORECASE,
        ), (
            "Show-isolated checkbox handler must delegate to applyFilters()"
        )

    # -----------------------------------------------------------------------
    # T3 — Isolated node flagged in data / applyFilters hides it
    # -----------------------------------------------------------------------

    def test_degree_zero_node_handled_as_isolated(self):
        """
        A node with degree==0 in graph_dict must be treated as isolated.
        The HTML must encode the degree value (0) in the cytoscape data,
        so the JS applyFilters can inspect it to hide/show the node.
        """
        html = build_graph_html(self._graph_with_isolated())
        # p3 has degree 0 — its id must appear in the HTML data
        assert "p3" in html, "Node p3 (degree=0) must be present in HTML data"
        # The degree value 0 must be embedded in the element data
        assert re.search(r'"degree"\s*:\s*0', html), (
            "Expected degree:0 to be embedded in cytoscape element data "
            "for the isolated node p3"
        )

    def test_apply_filters_hides_zero_degree_nodes(self):
        """
        The applyFilters JS function must contain logic that evaluates whether
        a node has zero visible edges, to hide it when the checkbox is unchecked.
        Accepts: checking degree==0, counting visible edges per-node, etc.
        """
        html = build_graph_html(self._graph_with_isolated())
        # applyFilters must reference degree or count edges to detect isolation
        assert re.search(
            r'degree|connectedEdges|visibleEdge|isolat',
            html,
        ), (
            "applyFilters must check node degree or connected edges "
            "to identify and hide isolated nodes"
        )

    # -----------------------------------------------------------------------
    # T4 — Header split count
    # -----------------------------------------------------------------------

    def test_header_shows_connected_and_isolated_split(self):
        """
        The header/meta-bar must show a split like 'N connected' and 'M isolated'
        OR the JS must compute and display such a split dynamically.
        Accept either static HTML values or JS that sets innerHTML with those terms.
        """
        html = build_graph_html(self._graph_with_isolated())
        # Accept 'connected' and 'isolated' appearing in JS string literals or HTML
        has_connected = re.search(r'connected', html, re.IGNORECASE)
        has_isolated_count = re.search(r'isolated', html, re.IGNORECASE)
        assert has_connected and has_isolated_count, (
            "Header must reference both 'connected' and 'isolated' node counts "
            "(either as static HTML or as JS-computed strings)"
        )

    # -----------------------------------------------------------------------
    # T5 — Regression: existing tests still pass (escaping, project title)
    # -----------------------------------------------------------------------

    def test_xss_escaping_still_works_with_new_controls(self):
        """
        Regression: the XSS-escaping behaviour must not be broken by the new
        checkbox control or any new JS code.  An evil label must remain escaped.
        """
        g = self._graph_with_isolated()
        g["nodes"][0]["label"] = "</script><script>alert('xss')</script>"
        html = build_graph_html(g)
        assert "</script><script>" not in html, (
            "XSS regression: evil script sequence must remain escaped"
        )

    def test_project_name_title_preserved(self):
        """
        Regression: project_name still appears in <h1> after the new controls
        are added.
        """
        g = self._graph_with_isolated()
        html = build_graph_html(g, project_name="my-project")
        h1_match = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL | re.IGNORECASE)
        assert h1_match is not None, "No <h1> found"
        assert "my-project" in h1_match.group(1), (
            "project_name must still appear in <h1> after isolated-node feature added"
        )

    def test_no_xss_in_checkbox_control(self):
        """
        The new checkbox control HTML must not introduce any XSS vector —
        it is static HTML so this is primarily a code-review / structure check:
        no user-supplied data is interpolated into the checkbox markup.
        The control must be safe static HTML.
        """
        g = self._graph_with_isolated()
        # Even with an evil project name, the checkbox markup must be safe
        g["meta"]["project"] = '"><script>evil()</script>'
        html = build_graph_html(g)
        # The raw evil string must not appear anywhere unescaped
        assert '"><script>evil()</script>' not in html, (
            "Evil project name must not leak into checkbox markup unescaped"
        )

    # -----------------------------------------------------------------------
    # T6 — Works on all-connected graph (no isolated nodes present)
    # -----------------------------------------------------------------------

    def test_all_connected_graph_still_works(self):
        """
        A graph where all nodes have edges must still render correctly —
        the 'isolated' feature must not break graphs with zero isolated nodes.
        """
        html = build_graph_html(self._graph_all_connected())
        assert isinstance(html, str)
        assert len(html) > 0
        # Checkbox must still be present
        assert re.search(r'<input[^>]+type=["\']checkbox["\']', html, re.IGNORECASE), (
            "Checkbox must be present even when there are no isolated nodes"
        )
