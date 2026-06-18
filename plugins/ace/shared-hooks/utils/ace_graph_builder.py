#!/usr/bin/env python3
"""
ACE Graph Builder - Render the local ACE knowledge-graph as an interactive HTML report.

NO side effects on import.

Public API:
    resolve_graph_db(settings_path, cache_dir) -> str or None
    load_graph(db_path, min_weight=2, max_edges=1500) -> dict
    build_graph_html(graph_dict) -> str
"""

import html as _html
import json
import os
import shutil
import sqlite3
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# DB resolution
# ---------------------------------------------------------------------------

def _read_settings_env(settings_path):
    """Return (org_id, project_id) from settings.json or (None, None)."""
    if settings_path is None:
        return None, None
    p = Path(settings_path)
    if not p.exists():
        return None, None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, None
    env = data.get("env", {})
    org = env.get("ACE_ORG_ID") or None
    proj = env.get("ACE_PROJECT_ID") or None
    return org, proj


def _db_has_patterns(db_path):
    """Return True if the DB file exists and has at least one row in patterns."""
    try:
        uri = "file:{}?mode=ro&immutable=1".format(Path(db_path).resolve().as_posix())
        con = sqlite3.connect(uri, uri=True)
        cur = con.cursor()
        cur.execute("SELECT COUNT(*) FROM patterns")
        count = cur.fetchone()[0]
        con.close()
        return count > 0
    except Exception:
        return False


def resolve_graph_db(settings_path, cache_dir):
    """
    Locate the best ACE cache DB to use.

    1. If settings_path exists and contains ACE_ORG_ID + ACE_PROJECT_ID,
       look for '<org>__<project>.db' in cache_dir.
    2. Fallback: pick the most-recently-modified *.db in cache_dir that has
       a non-empty patterns table.
    3. Return None if nothing usable is found.

    Args:
        settings_path: path to .claude/settings.json (str or None)
        cache_dir: path to ~/.ace-cache or equivalent (str)

    Returns:
        str path to the chosen DB, or None.
    """
    cache = Path(cache_dir) if cache_dir else None

    # --- env-first ---
    org_id, project_id = _read_settings_env(settings_path)
    if org_id and project_id and cache and cache.is_dir():
        candidate = cache / "{}__{}.db".format(org_id, project_id)
        if candidate.exists() and _db_has_patterns(str(candidate)):
            return str(candidate)

    # --- fallback: most-recently-modified non-empty DB ---
    if cache is None or not cache.is_dir():
        return None

    dbs = sorted(
        cache.glob("*.db"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for db in dbs:
        if _db_has_patterns(str(db)):
            return str(db)

    return None


# ---------------------------------------------------------------------------
# Graph loading
# ---------------------------------------------------------------------------

def _copy_db_to_tempdir(db_path):
    """
    Copy the DB (+ WAL/SHM shards) to a temp directory to avoid WAL lock.
    Returns the path of the copy.
    """
    src = Path(db_path)
    tmpdir = tempfile.mkdtemp(prefix="ace_graph_")
    dst = Path(tmpdir) / src.name
    shutil.copy2(str(src), str(dst))
    for ext in ("-wal", "-shm"):
        sidecar = src.parent / (src.name + ext)
        if sidecar.exists():
            shutil.copy2(str(sidecar), str(dst.parent / (dst.name + ext)))
    return str(dst), tmpdir


def _parse_payload(pattern_id, payload_json):
    """
    Parse payload_json defensively.
    Returns a dict with the needed fields, or None if unparseable.
    """
    try:
        data = json.loads(payload_json)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def load_graph(db_path, min_weight=2, max_edges=1500):
    """
    Load the ACE knowledge graph from a local SQLite DB.

    Reads via a copy of the DB to avoid WAL lock conflicts.

    Args:
        db_path:    Path (str) to the *.db file.
        min_weight: Minimum co-application weight for an edge to be included.
        max_edges:  Maximum number of edges to render (top-N by weight).

    Returns:
        dict with keys:
            nodes: list of {id, domain, section, label, reward, degree}
            edges: list of {src, dst, weight}
            meta:  {total_patterns, total_edges, rendered_edges, truncated, project, org}
    """
    if not Path(db_path).exists():
        raise FileNotFoundError(f"DB not found: {db_path}")

    db_copy, tmpdir = _copy_db_to_tempdir(db_path)
    try:
        # Plain open is safe here: db_copy is our private copy, not the live file.
        con = sqlite3.connect(str(db_copy))
        con.row_factory = sqlite3.Row

        # --- load patterns ---
        cur = con.cursor()
        cur.execute("SELECT pattern_id, payload_json FROM patterns")
        raw_patterns = cur.fetchall()

        # --- load edges (graceful fallback when edges table is absent) ---
        try:
            cur.execute("SELECT src, dst, weight FROM edges WHERE weight >= ?", (min_weight,))
            raw_edges = cur.fetchall()
        except sqlite3.OperationalError:
            raw_edges = []

        # --- total counts for meta ---
        cur.execute("SELECT COUNT(*) FROM patterns")
        total_patterns = cur.fetchone()[0]
        try:
            cur.execute("SELECT COUNT(*) FROM edges")
            total_edges = cur.fetchone()[0]
        except sqlite3.OperationalError:
            total_edges = 0

        con.close()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    # --- parse nodes ---
    nodes_by_id = {}  # type: Dict[str, dict]
    for row in raw_patterns:
        pid = row["pattern_id"]
        parsed = _parse_payload(pid, row["payload_json"])
        if parsed is None:
            continue  # skip malformed rows
        content = str(parsed.get("content") or "")
        # Truncate label to 120 chars
        label = content[:120] + ("..." if len(content) > 120 else "")
        reward_val = parsed.get("cumulative_v15_reward")
        try:
            reward = float(reward_val) if reward_val is not None else 0.0
        except (TypeError, ValueError):
            reward = 0.0
        nodes_by_id[pid] = {
            "id": pid,
            "domain": str(parsed.get("domain") or "unknown"),
            "section": str(parsed.get("section") or "unknown"),
            "label": label,
            "reward": reward,
            "degree": 0,  # populated below
        }

    valid_ids = set(nodes_by_id.keys())

    # --- filter edges: both endpoints must exist ---
    valid_edges = [
        {"src": r["src"], "dst": r["dst"], "weight": r["weight"]}
        for r in raw_edges
        if r["src"] in valid_ids and r["dst"] in valid_ids
    ]

    # --- sort by weight descending, then truncate ---
    valid_edges.sort(key=lambda e: e["weight"], reverse=True)
    truncated = len(valid_edges) > max_edges
    kept_edges = valid_edges[:max_edges]

    # --- compute degree from kept edges only ---
    for edge in kept_edges:
        nodes_by_id[edge["src"]]["degree"] += 1
        nodes_by_id[edge["dst"]]["degree"] += 1

    # Extract org/project from DB filename heuristically
    db_stem = Path(db_path).stem
    parts = db_stem.split("__")
    org_hint = parts[0] if len(parts) >= 2 else ""
    proj_hint = parts[1] if len(parts) >= 2 else db_stem

    return {
        "nodes": list(nodes_by_id.values()),
        "edges": kept_edges,
        "meta": {
            "total_patterns": total_patterns,
            "total_edges": total_edges,
            "rendered_edges": len(kept_edges),
            "truncated": truncated,
            "project": proj_hint,
            "org": org_hint,
        },
    }


# ---------------------------------------------------------------------------
# HTML generation
# ---------------------------------------------------------------------------

# Cytoscape.js is the chosen CDN library:
# - Widely used, permissive MIT license
# - Excellent force-directed layout (cose/cola)
# - Easy node/edge styling API
# - ~300KB minified (acceptable for a local dev tool)
# - The JSON blob is fully inline; the CDN is only needed for the JS renderer

_CDN_SCRIPT = "https://unpkg.com/cytoscape@3.29.2/dist/cytoscape.min.js"


def build_graph_html(graph_dict, project_name=None):
    """
    Build a self-contained interactive HTML report for the ACE knowledge graph.

    Security: all pattern-derived data is embedded ONLY via _safe_json() into a
    JS variable.  _safe_json() encodes '<', '>', '&' as JSON unicode escapes
    (\\u003c, \\u003e, \\u0026) so pattern content cannot break out of the
    <script> block or inject arbitrary HTML.  The tooltip uses JS-level
    string replacement to escape before innerHTML assignment.

    Args:
        graph_dict:   dict as returned by load_graph()
        project_name: human-readable project name (str or None).  When truthy,
                      used in the <h1> title instead of the raw project ID.
                      HTML-escaped via html.escape().  Falls back to
                      graph_dict['meta']['project'] when None/falsy.

    Returns:
        str: a self-contained HTML document.
    """
    nodes = graph_dict.get("nodes", [])
    edges = graph_dict.get("edges", [])
    meta = graph_dict.get("meta", {})

    truncated = meta.get("truncated", False)
    total_edges = meta.get("total_edges", 0)
    rendered_edges = meta.get("rendered_edges", len(edges))
    total_patterns = meta.get("total_patterns", len(nodes))
    project = meta.get("project", "")
    org = meta.get("org", "")

    # --- build Cytoscape elements ---
    cy_elements = []
    for node in nodes:
        cy_elements.append({
            "data": {
                "id": node["id"],
                "domain": node["domain"],
                "section": node["section"],
                "label": node["label"],
                "reward": node["reward"],
                "degree": node["degree"],
            }
        })
    for edge in edges:
        cy_elements.append({
            "data": {
                "source": edge["src"],
                "target": edge["dst"],
                "weight": edge["weight"],
            }
        })

    # --- collect unique domains for filter UI ---
    domains = sorted({n["domain"] for n in nodes})

    # Embed all data as a single JSON blob.
    # Security: escape HTML-dangerous characters as unicode escapes so that
    # pattern content cannot break out of the <script> block or inject HTML.
    # json.dumps does NOT escape < > & by default in Python's stdlib.
    # We post-process: replace < -> <, > -> >, & -> &
    # These are valid JSON unicode escapes; JS decodes them transparently.
    graph_data = {
        "nodes": nodes,
        "edges": edges,
        "meta": meta,
    }

    def _safe_json(obj):
        """json.dumps with HTML-dangerous chars escaped as unicode escapes."""
        raw = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
        # Replace HTML-dangerous chars with JSON unicode escapes
        raw = raw.replace("&", "\\u0026")
        raw = raw.replace("<", "\\u003c")
        raw = raw.replace(">", "\\u003e")
        return raw

    graph_json = _safe_json(graph_data)
    cy_json = _safe_json(cy_elements)
    domains_json = _safe_json(domains)

    truncated_note = ""
    if truncated:
        truncated_note = (
            "Showing top <strong>{}</strong> of <strong>{}</strong> edges "
            "(filtered by weight).".format(rendered_edges, total_edges)
        )

    # Prefer human project_name; fall back to raw project ID from meta.
    display_project = _html.escape(str(project_name)) if project_name else (
        _html.escape(str(project)) if project else ""
    )
    title = "ACE Knowledge Graph"
    if display_project:
        title += " &mdash; {}".format(display_project)

    html = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ACE Knowledge Graph</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
          background: #0f1117; color: #e2e8f0; height: 100vh; display: flex;
          flex-direction: column; }}
  #header {{ padding: 12px 20px; background: #1a1d27; border-bottom: 1px solid #2d3147;
             display: flex; align-items: center; gap: 16px; flex-wrap: wrap; }}
  #header h1 {{ font-size: 16px; font-weight: 600; color: #7c93f5; white-space: nowrap; }}
  #meta-bar {{ font-size: 12px; color: #8892b0; }}
  #controls {{ display: flex; gap: 12px; align-items: center; flex-wrap: wrap; margin-left: auto; }}
  .ctrl-group {{ display: flex; align-items: center; gap: 6px; font-size: 12px; }}
  label {{ color: #8892b0; }}
  input[type=range] {{ width: 100px; accent-color: #7c93f5; }}
  select {{ background: #252836; color: #e2e8f0; border: 1px solid #3d4266;
            border-radius: 4px; padding: 3px 6px; font-size: 12px; }}
  #truncated-note {{ font-size: 11px; color: #e2a458; padding: 2px 8px;
                     background: #2a1f00; border-radius: 3px; }}
  #cy {{ flex: 1; background: #0f1117; }}
  #tooltip {{ position: absolute; pointer-events: none; display: none;
              background: #1e2235; border: 1px solid #3d4266; border-radius: 6px;
              padding: 10px 14px; max-width: 320px; font-size: 12px;
              line-height: 1.5; z-index: 100; box-shadow: 0 4px 16px rgba(0,0,0,0.6); }}
  #tooltip .tt-id   {{ color: #7c93f5; font-family: monospace; font-size: 10px; }}
  #tooltip .tt-dom  {{ color: #5bb5a6; font-weight: 600; margin-top: 2px; }}
  #tooltip .tt-sec  {{ color: #8892b0; font-size: 11px; }}
  #tooltip .tt-content {{ color: #d0daf5; margin-top: 6px; }}
  #tooltip .tt-reward  {{ color: #f5c842; margin-top: 4px; font-size: 11px; }}
  #legend {{ position: absolute; bottom: 12px; left: 16px; background: #1a1d27cc;
             border: 1px solid #2d3147; border-radius: 6px; padding: 8px 12px;
             font-size: 11px; z-index: 50; max-width: 200px; }}
  #legend h4 {{ font-size: 11px; color: #7c93f5; margin-bottom: 6px; }}
  .legend-item {{ display: flex; align-items: center; gap: 6px; margin: 3px 0; }}
  .legend-dot {{ width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }}
</style>
</head>
<body>
<div id="header">
  <h1>{title}</h1>
  <div id="meta-bar">
    {n_nodes} patterns &nbsp;&bull;&nbsp; {n_edges} edges rendered
    {truncated_html}
  </div>
  <div id="controls">
    <div class="ctrl-group">
      <label for="wt-slider">Min weight</label>
      <input type="range" id="wt-slider" min="1" max="50" value="1">
      <span id="wt-val">1</span>
    </div>
    <div class="ctrl-group">
      <label for="dom-filter">Domain</label>
      <select id="dom-filter">
        <option value="">All</option>
      </select>
    </div>
  </div>
</div>
<div id="cy"></div>
<div id="tooltip"></div>
<div id="legend"><h4>Legend</h4><div id="legend-items"></div></div>

<script src="{cdn}"></script>
<script>
// ── inline data (safely JSON-encoded) ──────────────────────────────────────
var graphData = {graph_json};
var cyElements = {cy_json};
var allDomains = {domains_json};

// ── domain colour palette ──────────────────────────────────────────────────
var PALETTE = [
  "#7c93f5","#5bb5a6","#e2a458","#c47ef5","#f5c842",
  "#e25882","#58d4f5","#a5d65e","#f58a42","#42b9f5",
  "#d65ea5","#5ef5c4","#f5e042","#e06060","#60c2e0"
];
var domColour = {{}};
allDomains.forEach(function(d, i) {{
  domColour[d] = PALETTE[i % PALETTE.length];
}});

// ── populate domain filter ─────────────────────────────────────────────────
var sel = document.getElementById("dom-filter");
allDomains.forEach(function(d) {{
  var opt = document.createElement("option");
  opt.value = d;
  opt.textContent = d;
  sel.appendChild(opt);
}});

// ── build legend ───────────────────────────────────────────────────────────
var legendEl = document.getElementById("legend-items");
allDomains.slice(0, 10).forEach(function(d) {{
  var item = document.createElement("div");
  item.className = "legend-item";
  var dot = document.createElement("div");
  dot.className = "legend-dot";
  dot.style.background = domColour[d] || "#888";
  var lbl = document.createElement("span");
  lbl.textContent = d.length > 22 ? d.slice(0, 20) + "…" : d;
  item.appendChild(dot);
  item.appendChild(lbl);
  legendEl.appendChild(item);
}});

// ── Cytoscape init ─────────────────────────────────────────────────────────
var cy = cytoscape({{
  container: document.getElementById("cy"),
  elements: cyElements,
  style: [
    {{
      selector: "node",
      style: {{
        "background-color": function(ele) {{
          return domColour[ele.data("domain")] || "#888";
        }},
        "width": function(ele) {{
          var r = ele.data("reward") || 0;
          return Math.max(12, Math.min(48, 12 + r * 2));
        }},
        "height": function(ele) {{
          var r = ele.data("reward") || 0;
          return Math.max(12, Math.min(48, 12 + r * 2));
        }},
        "label": "",
        "border-width": 1.5,
        "border-color": "#ffffff",
        "border-opacity": 0.13,
        "opacity": 0.9,
      }}
    }},
    {{
      selector: "node.highlighted",
      style: {{
        "border-width": 3,
        "border-color": "#ffffff",
        "opacity": 1,
        "z-index": 10,
      }}
    }},
    {{
      selector: "node.faded",
      style: {{ "opacity": 0.15 }}
    }},
    {{
      selector: "edge",
      style: {{
        "line-color": "#3d4266",
        "width": function(ele) {{
          var w = ele.data("weight") || 1;
          return Math.max(0.5, Math.min(4, w / 10));
        }},
        "opacity": 0.5,
        "curve-style": "bezier",
      }}
    }},
    {{
      selector: "edge.highlighted",
      style: {{
        "line-color": "#7c93f5",
        "opacity": 1,
        "z-index": 5,
      }}
    }},
    {{
      selector: "edge.faded",
      style: {{ "opacity": 0.05 }}
    }},
  ],
  layout: {{
    name: "cose",
    animate: false,
    randomize: true,
    nodeRepulsion: 4096,
    idealEdgeLength: 80,
    edgeElasticity: 100,
    gravity: 0.25,
    numIter: 1000,
  }},
  minZoom: 0.05,
  maxZoom: 4,
}});

// ── tooltip ────────────────────────────────────────────────────────────────
var tooltip = document.getElementById("tooltip");

cy.on("mouseover", "node", function(evt) {{
  var d = evt.target.data();
  // All strings come from the JSON blob — already safe, no innerHTML injection
  var safeId = d.id.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
  var safeDom = d.domain.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
  var safeSec = d.section.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
  var safeLbl = d.label.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
  tooltip.innerHTML = (
    "<div class=\\"tt-id\\">" + safeId + "</div>" +
    "<div class=\\"tt-dom\\">" + safeDom + "</div>" +
    "<div class=\\"tt-sec\\">" + safeSec + "</div>" +
    "<div class=\\"tt-content\\">" + safeLbl + "</div>" +
    "<div class=\\"tt-reward\\">reward: " + (d.reward || 0).toFixed(2) +
    " &nbsp; degree: " + (d.degree || 0) + "</div>"
  );
  tooltip.style.display = "block";
}});

cy.on("mouseout", "node", function() {{
  tooltip.style.display = "none";
}});

cy.on("mousemove", function(evt) {{
  if (tooltip.style.display !== "none") {{
    tooltip.style.left = (evt.originalEvent.clientX + 14) + "px";
    tooltip.style.top  = (evt.originalEvent.clientY - 10) + "px";
  }}
}});

// ── click: highlight 1-hop neighbours ─────────────────────────────────────
cy.on("tap", "node", function(evt) {{
  cy.elements().removeClass("highlighted faded");
  var node = evt.target;
  var hood = node.closedNeighborhood();
  cy.elements().not(hood).addClass("faded");
  hood.addClass("highlighted");
}});

cy.on("tap", function(evt) {{
  if (evt.target === cy) {{
    cy.elements().removeClass("highlighted faded");
  }}
}});

// ── min-weight slider ──────────────────────────────────────────────────────
var wtSlider = document.getElementById("wt-slider");
var wtVal    = document.getElementById("wt-val");
wtSlider.addEventListener("input", function() {{
  var minW = parseInt(this.value, 10);
  wtVal.textContent = minW;
  cy.edges().forEach(function(e) {{
    if ((e.data("weight") || 0) < minW) {{
      e.style("display", "none");
    }} else {{
      e.style("display", "element");
    }}
  }});
}});

// ── domain filter ──────────────────────────────────────────────────────────
sel.addEventListener("change", function() {{
  var chosen = this.value;
  if (!chosen) {{
    cy.nodes().style("display", "element");
    cy.edges().style("display", "element");
    return;
  }}
  cy.nodes().forEach(function(n) {{
    if (n.data("domain") === chosen) {{
      n.style("display", "element");
    }} else {{
      n.style("display", "none");
    }}
  }});
  cy.edges().forEach(function(e) {{
    var src = cy.getElementById(e.data("source"));
    var tgt = cy.getElementById(e.data("target"));
    if (src.style("display") === "element" && tgt.style("display") === "element") {{
      e.style("display", "element");
    }} else {{
      e.style("display", "none");
    }}
  }});
}});
</script>
</body>
</html>""".format(
        title=title,
        n_nodes=total_patterns,
        n_edges=rendered_edges,
        truncated_html=(
            ' &nbsp;&bull;&nbsp; <span id="truncated-note">' + truncated_note + "</span>"
            if truncated_note else ""
        ),
        cdn=_CDN_SCRIPT,
        graph_json=graph_json,
        cy_json=cy_json,
        domains_json=domains_json,
    )

    return html
