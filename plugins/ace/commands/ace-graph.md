---
disable-model-invocation: true
description: Render the local ACE knowledge-graph as a self-contained interactive HTML report
argument-hint: "[--min-weight N] [--max-edges N]"
allowed-tools: Bash(${CLAUDE_PLUGIN_ROOT}/scripts/ace-cli:*), Bash(python3:*), Read
---

# ACE Graph

Visualise the ACE knowledge-graph stored in the local cache DB as an interactive force-directed HTML report. Nodes = patterns, edges = co-application pairs. Node colour = domain, node size = reward score, edge width = co-application weight.

**Requirement:** the local graph cache is filled by the CLI (the graph cache needs ace-cli >= 4.2.1 and its sqlite binary; the plugin-pinned CLI has both). If the report says no cache DB was found, run a search first, or `/ace:ace-doctor`.

## Instructions for Claude

When the user runs `/ace:ace-graph`, execute the following Python script in a single Bash call.

```bash
python3 -c "
import json, os, sys, platform, subprocess
from pathlib import Path

# -- parse args ---------------------------------------------------------------
args = sys.argv[1:]
min_weight = 2
max_edges  = 1500
i = 0
while i < len(args):
    if args[i] in ('--min-weight', '--min_weight') and i + 1 < len(args):
        try:
            min_weight = int(args[i + 1])
        except ValueError:
            pass
        i += 2
    elif args[i] in ('--max-edges', '--max_edges') and i + 1 < len(args):
        try:
            max_edges = int(args[i + 1])
        except ValueError:
            pass
        i += 2
    else:
        i += 1

# -- resolve ace_graph_builder -----------------------------------------------
import glob

def _resolve_builder():
    root = os.environ.get('CLAUDE_PLUGIN_ROOT', '')
    if root:
        cand = Path(root) / 'shared-hooks' / 'utils' / 'ace_graph_builder.py'
        if cand.exists():
            return cand
    home = Path.home()
    patterns = [
        str(home / '.claude/plugins/cache/*/ace/*/shared-hooks/utils/ace_graph_builder.py'),
        str(home / '.claude/plugins/cache/*/*/ace/*/shared-hooks/utils/ace_graph_builder.py'),
    ]
    matches = []
    for pat in patterns:
        matches.extend(glob.glob(pat))
    if not matches:
        return None
    matches.sort(key=lambda m: os.path.getmtime(m), reverse=True)
    return Path(matches[0])

builder_path = _resolve_builder()
if builder_path is None:
    print('ace_graph_builder not found. Re-install the ACE plugin.')
    sys.exit(1)

sys.path.insert(0, str(builder_path.parent))
from ace_graph_builder import resolve_graph_db, load_graph, build_graph_html

# -- resolve DB (8.1.0: the ids come from the one core; never another project's newest DB) -----------------
import subprocess as _sp
_ctx = _sp.run([os.path.join('${CLAUDE_PLUGIN_ROOT}', 'scripts', 'ace-context'), '--json'], capture_output=True, text=True)
try:
    ctx = json.loads(_ctx.stdout or '{}')
except ValueError:
    ctx = {}
if not ctx.get('bound'):
    print(_ctx.stderr.strip() or 'ACE is not bound here. Run /ace:ace-configure.')
    sys.exit(0)
cache_dir = Path.home() / '.ace-cache'
db_path = resolve_graph_db(ctx['orgId'], ctx['projectId'], str(cache_dir), os.environ.get('ACE_SERVER_URL'))
if db_path is None:
    print('No ACE cache DB for this project yet.')
    print('')
    print('The local cache is populated after patterns are searched. Run a few')
    print('tasks with ACE enabled, then try again.')
    sys.exit(0)

# -- load graph ---------------------------------------------------------------
print('Loading graph from:', db_path)
g = load_graph(db_path, min_weight=min_weight, max_edges=max_edges)

meta = g['meta']
nodes = g['nodes']
edges = g['edges']
truncated = meta.get('truncated', False)
project_id = meta.get('project', '')

# -- resolve human project name via ace-cli -----------------------------------
project_name = None
try:
    result = subprocess.run(
        [os.path.join('${CLAUDE_PLUGIN_ROOT}', 'scripts', 'ace-cli'), 'projects', '--json', '--org', ctx['orgId']],
        capture_output=True, text=True, timeout=8,
    )
    if result.returncode == 0 and result.stdout.strip():
        projects_data = json.loads(result.stdout)
        # ace-cli 4.x records use project_id/project_name; accept id/name as fallback
        project_list = projects_data if isinstance(projects_data, list) else projects_data.get('projects', [])
        for p in project_list:
            if isinstance(p, dict) and (p.get('project_id') or p.get('id')) == project_id:
                project_name = p.get('project_name') or p.get('name') or None
                break
except Exception:
    project_name = None

# -- compute hubs (top 5 by degree) ------------------------------------------
hubs = sorted(nodes, key=lambda n: n['degree'], reverse=True)[:5]

# -- build HTML ---------------------------------------------------------------
html = build_graph_html(g, project_name=project_name)

# -- write report -------------------------------------------------------------
report_dir = Path.home() / '.claude' / 'usage-data'
report_dir.mkdir(parents=True, exist_ok=True)
report_file = report_dir / 'ace-graph.html'
report_file.write_text(html, encoding='utf-8')

# -- print summary ------------------------------------------------------------
print('')
print('ACE Knowledge Graph')
if project_name:
    print('  Project  : {} ({})'.format(project_name, project_id))
else:
    print('  Project  : {}'.format(project_id))
print('  Patterns : {}'.format(meta.get('total_patterns', len(nodes))))
print('  Edges    : {} rendered (min_weight={})'.format(
    meta.get('rendered_edges', len(edges)), min_weight))
if truncated:
    print('  (truncated from {} total to top {} by weight)'.format(
        meta.get('total_edges', '?'), max_edges))
print('')
if hubs:
    print('Top hubs by co-application degree:')
    for h in hubs:
        print('  [{:3d}] {} | {} | {}'.format(
            h['degree'],
            h['id'],
            h['domain'],
            h['label'][:60],
        ))
print('')
print('Report: {}'.format(report_file))
print('  file://{}'.format(report_file))

if platform.system() == 'Darwin':
    subprocess.run(['open', str(report_file)], check=False)
" "$@"
```

## Arguments

- `--min-weight N` (default: 2) — minimum co-application count for an edge to appear
- `--max-edges N` (default: 1500) — cap on rendered edges (top-N by weight); a note is shown when truncated

## What You'll See

**Terminal output:**
- Pattern count, rendered edge count, min-weight filter
- Top 5 hub patterns (highest co-application degree)
- Path to the saved HTML file

**Interactive HTML report** (saved to `~/.claude/usage-data/ace-graph.html`):
- Force-directed graph (Cytoscape.js, cose layout)
- Node colour = domain, node size = cumulative reward score
- Edge width = co-application weight
- Hover a node to see its content snippet and reward
- Click a node to highlight its 1-hop neighbourhood
- Min-weight slider to thin the graph live
- Domain filter dropdown to isolate a single domain
- Legend with domain colours

## Usage

```
# Default (min_weight=2, max_edges=1500)
/ace:ace-graph

# Show only strong co-applications
/ace:ace-graph --min-weight 5

# Limit to 500 edges for a cleaner view
/ace:ace-graph --max-edges 500

# Combine
/ace:ace-graph --min-weight 3 --max-edges 800
```

## See Also

- `/ace:ace-patterns` - View full pattern list
- `/ace:ace-top`      - Highest-reward patterns
- `/ace:ace-insights` - Per-task helpfulness report
- `/ace:ace-status`   - Playbook statistics
