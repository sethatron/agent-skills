#!/usr/bin/env python3
import sys
import os
import re
import json
import html
import argparse
import webbrowser
import http.server
import socketserver
from collections import Counter

try:
    import yaml
except ImportError:
    print("Error: pyyaml is required. Install with: pip install pyyaml")
    sys.exit(1)

STATUS_ORDER = ["mastered", "proficient", "applied", "conceptual", "exposed", "not_started"]
STATUS_COLORS = {
    "not_started": "#616161",
    "exposed": "#4fc3f7",
    "conceptual": "#2196f3",
    "applied": "#4caf50",
    "proficient": "#9c27b0",
    "mastered": "#ffd600",
}
PRIORITY_BORDERS = {
    "critical": {"width": 4, "color": "#f44336"},
    "high": {"width": 3, "color": "#ff9800"},
    "medium": {"width": 2, "color": "#78909c"},
    "low": {"width": 1, "color": "#546e7a"},
}
CATEGORY_COLORS = {}
CATEGORY_ORDER = []

PALETTE = [
    "#ef5350", "#ab47bc", "#5c6bc0", "#29b6f6", "#26a69a", "#66bb6a",
    "#d4e157", "#ffa726", "#8d6e63", "#78909c", "#ec407a", "#7e57c2",
]


def parse_kb(yaml_path):
    try:
        with open(yaml_path) as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        print(f"Error parsing YAML: {e}", file=sys.stderr)
        sys.exit(1)

    skip_keys = {"metadata"}
    topics = []
    categories = {}
    cat_idx = 0

    for cat_key, cat_val in data.items():
        if cat_key in skip_keys or not isinstance(cat_val, dict):
            continue
        cat_topics = []
        description = cat_val.get("description", "") if isinstance(cat_val.get("description"), str) else ""
        for sub_key, sub_val in cat_val.items():
            if not isinstance(sub_val, list):
                continue
            for topic in sub_val:
                if isinstance(topic, dict) and "name" in topic:
                    topic["_category"] = cat_key
                    topic["_subcategory"] = sub_key
                    cat_topics.append(topic)
        topics.extend(cat_topics)
        categories[cat_key] = {"description": description, "topics": cat_topics}
        CATEGORY_ORDER.append(cat_key)
        CATEGORY_COLORS[cat_key] = PALETTE[cat_idx % len(PALETTE)]
        cat_idx += 1

    return topics, categories


def build_name_resolver(topics):
    canonical = {}
    for t in topics:
        canonical[t["name"]] = t["name"]

    aliases = {}
    for name in canonical:
        m = re.match(r'^(.+?)\s*\((.+)\)$', name)
        if m:
            before, inside = m.group(1).strip(), m.group(2).strip()
            candidates = [before]
            if ',' not in inside:
                candidates.append(inside)
            for alias in candidates:
                if alias and alias not in canonical:
                    if alias in aliases and aliases[alias] != name:
                        print(f"Warning: alias '{alias}' maps to both '{aliases[alias]}' and '{name}'", file=sys.stderr)
                    else:
                        aliases[alias] = name

        if " / " in name:
            parts = name.split(" / ")
            for p in parts:
                p = p.strip()
                if p and p not in canonical:
                    if p in aliases and aliases[p] != name:
                        print(f"Warning: alias '{p}' maps to both '{aliases[p]}' and '{name}'", file=sys.stderr)
                    else:
                        aliases[p] = name

    all_names = list(canonical.keys())

    def resolve(ref):
        if ref in canonical:
            return ref
        if ref in aliases:
            return aliases[ref]
        ref_lower = ref.lower()
        pattern = re.compile(r'\b' + re.escape(ref_lower) + r'\b', re.IGNORECASE)
        for n in all_names:
            if pattern.search(n):
                print(f"Warning: substring fallback '{ref}' -> '{n}'", file=sys.stderr)
                return n
        return None

    return resolve


def build_graph_data(topics, resolve):
    name_to_id = {}
    nodes = []

    for i, t in enumerate(topics):
        nid = f"n{i}"
        name_to_id[t["name"]] = nid

    in_degree = Counter()
    out_degree = Counter()

    prereq_edges = []
    for t in topics:
        tid = name_to_id[t["name"]]
        for ref in (t.get("prerequisites") or []):
            resolved = resolve(ref)
            if resolved and resolved in name_to_id:
                src = name_to_id[resolved]
                if src != tid:
                    prereq_edges.append((src, tid, ref))
                    out_degree[src] += 1
                    in_degree[tid] += 1

    related_set = set()
    related_edges = []
    for t in topics:
        tid = name_to_id[t["name"]]
        for ref in (t.get("related") or []):
            resolved = resolve(ref)
            if resolved and resolved in name_to_id:
                rid = name_to_id[resolved]
                if rid != tid:
                    pair = tuple(sorted([tid, rid]))
                    if pair not in related_set:
                        related_set.add(pair)
                        related_edges.append((pair[0], pair[1]))

    for i, t in enumerate(topics):
        nid = f"n{i}"
        conns = in_degree.get(nid, 0) + out_degree.get(nid, 0)

        prereqs_resolved = []
        for ref in (t.get("prerequisites") or []):
            resolved = resolve(ref)
            if resolved and resolved in name_to_id:
                prereqs_resolved.append({"raw": ref, "name": resolved, "nodeId": name_to_id[resolved]})
            else:
                prereqs_resolved.append({"raw": ref, "name": None, "nodeId": None})

        related_resolved = []
        for ref in (t.get("related") or []):
            resolved = resolve(ref)
            if resolved and resolved in name_to_id:
                related_resolved.append({"raw": ref, "name": resolved, "nodeId": name_to_id[resolved]})
            else:
                related_resolved.append({"raw": ref, "name": None, "nodeId": None})

        nodes.append({"data": {
            "id": nid,
            "name": t["name"],
            "category": t["_category"],
            "subcategory": t["_subcategory"],
            "status": t.get("status", "not_started"),
            "priority": t.get("priority", "medium"),
            "difficulty": t.get("difficulty", 3),
            "description": t.get("description", ""),
            "tags": t.get("tags") or [],
            "source_context": t.get("source_context"),
            "prerequisites": prereqs_resolved,
            "related": related_resolved,
            "level_up_evidence": t.get("level_up_evidence") or [],
            "connections": conns,
            "size": min(30 + conns * 5, 80),
        }})

    edges = []
    seen_prereq = set()
    for src, tgt, _ in prereq_edges:
        key = (src, tgt)
        if key not in seen_prereq:
            seen_prereq.add(key)
            edges.append({"data": {"id": f"e_{src}_{tgt}", "source": src, "target": tgt, "type": "prerequisite"}})

    for a, b in related_edges:
        edges.append({"data": {"id": f"r_{a}_{b}", "source": a, "target": b, "type": "related"}})

    return nodes, edges


def compute_stats(topics, categories):
    total = len(topics)
    status_counts = Counter(t.get("status", "not_started") for t in topics)
    priority_counts = Counter(t.get("priority", "medium") for t in topics)
    engaged = total - status_counts.get("not_started", 0)

    by_status = {s: status_counts.get(s, 0) for s in STATUS_ORDER}
    by_priority = {p: priority_counts.get(p, 0) for p in ["critical", "high", "medium", "low"]}

    cat_stats = {}
    for ck, cv in categories.items():
        ct = cv["topics"]
        cat_stats[ck] = {
            "total": len(ct),
            "engaged": sum(1 for t in ct if t.get("status", "not_started") != "not_started"),
        }

    gaps = [
        {"name": t["name"], "priority": t.get("priority", "medium"), "status": t.get("status", "not_started")}
        for t in topics
        if t.get("priority") in ("critical", "high")
        and t.get("status", "not_started") in ("not_started", "exposed", "conceptual")
    ]
    gaps.sort(key=lambda g: (
        0 if g["priority"] == "critical" else 1,
        0 if g["status"] == "not_started" else 1 if g["status"] == "exposed" else 2,
    ))
    gaps = gaps[:20]

    evidence = []
    for t in topics:
        for e in (t.get("level_up_evidence") or []):
            if isinstance(e, dict) and e.get("timestamp"):
                evidence.append({
                    "topic": t["name"],
                    "from_level": e.get("from_level"),
                    "to_level": e.get("to_level"),
                    "timestamp": e.get("timestamp"),
                    "method": e.get("method"),
                    "summary": e.get("summary"),
                })
    evidence.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    evidence = evidence[:10]

    return {
        "total": total,
        "engaged": engaged,
        "by_status": by_status,
        "by_priority": by_priority,
        "categories": cat_stats,
        "priority_gaps": gaps,
        "recent_promotions": evidence,
    }


def _build_css():
    return """
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    background: #1a1a2e;
    color: #e0e0e0;
    display: flex;
    height: 100vh;
    overflow: hidden;
}
#sidebar {
    width: 280px;
    flex-shrink: 0;
    background: #16213e;
    border-right: 1px solid #0f3460;
    overflow-y: auto;
    padding: 16px;
    transition: width 0.3s ease;
    position: relative;
}
#sidebar.collapsed { width: 0; padding: 0; overflow: hidden; }
#sidebar.collapsed #sidebar-content { display: none; }
#collapse-btn {
    position: absolute;
    right: -24px;
    top: 12px;
    width: 24px;
    height: 32px;
    background: #16213e;
    border: 1px solid #0f3460;
    border-left: none;
    color: #e0e0e0;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 12px;
    z-index: 200;
    border-radius: 0 4px 4px 0;
}
#cy-wrapper {
    flex: 1;
    min-width: 0;
    position: relative;
}
#cy { width: 100%; height: 100%; }
#empty-state {
    position: absolute;
    inset: 0;
    display: none;
    align-items: center;
    justify-content: center;
    color: #78909c;
    font-size: 18px;
    pointer-events: none;
}
#toolbar {
    position: absolute;
    bottom: 16px;
    right: 16px;
    display: flex;
    gap: 6px;
    z-index: 50;
}
#toolbar button {
    width: 36px;
    height: 36px;
    background: #16213e;
    border: 1px solid #0f3460;
    color: #e0e0e0;
    cursor: pointer;
    border-radius: 4px;
    font-size: 16px;
    display: flex;
    align-items: center;
    justify-content: center;
}
#toolbar button:hover { background: #1a1a4e; }
#detail-panel {
    position: fixed;
    right: 0;
    top: 0;
    width: 340px;
    height: 100vh;
    background: #16213e;
    border-left: 1px solid #0f3460;
    z-index: 100;
    transform: translateX(100%);
    transition: transform 0.3s ease;
    overflow-y: auto;
    padding: 16px;
}
#detail-panel.open { transform: translateX(0); }
#detail-close {
    position: absolute;
    top: 8px;
    right: 12px;
    background: none;
    border: none;
    color: #e0e0e0;
    font-size: 20px;
    cursor: pointer;
}
#tooltip {
    position: absolute;
    background: #0f3460;
    border: 1px solid #1a1a4e;
    padding: 8px 12px;
    border-radius: 6px;
    font-size: 12px;
    pointer-events: none;
    z-index: 300;
    display: none;
    max-width: 280px;
    line-height: 1.4;
}
h3 { font-size: 13px; color: #78909c; text-transform: uppercase; letter-spacing: 1px; margin: 16px 0 8px; }
h3:first-child { margin-top: 0; }
#search-box { position: relative; margin-bottom: 12px; }
#search-input {
    width: 100%;
    padding: 8px 28px 8px 10px;
    background: #1a1a2e;
    border: 1px solid #0f3460;
    color: #e0e0e0;
    border-radius: 4px;
    font-size: 13px;
    outline: none;
}
#search-input:focus { border-color: #29b6f6; }
#search-clear {
    position: absolute;
    right: 6px;
    top: 50%;
    transform: translateY(-50%);
    background: none;
    border: none;
    color: #78909c;
    cursor: pointer;
    font-size: 14px;
    display: none;
}
#search-count { font-size: 11px; color: #78909c; margin-top: 4px; display: block; min-height: 16px; }
.progress-bar {
    height: 6px;
    background: #1a1a2e;
    border-radius: 3px;
    margin: 6px 0 12px;
    overflow: hidden;
}
.progress-fill { height: 100%; background: #4caf50; border-radius: 3px; transition: width 0.3s; }
.cat-row {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 3px 0;
    font-size: 12px;
}
.cat-row input[type="checkbox"] {
    flex-shrink: 0;
    accent-color: #29b6f6;
    cursor: pointer;
}
.cat-dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    flex-shrink: 0;
}
.cat-label {
    flex: 1;
    cursor: pointer;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}
.cat-label:hover { text-decoration: underline; }
.filter-links { font-size: 11px; margin-bottom: 6px; }
.filter-links a { color: #29b6f6; cursor: pointer; text-decoration: none; margin-right: 8px; }
.filter-links a:hover { text-decoration: underline; }
.filter-group { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 8px; }
.filter-btn {
    padding: 4px 8px;
    font-size: 11px;
    border: 1px solid #0f3460;
    background: #1a1a2e;
    color: #78909c;
    border-radius: 3px;
    cursor: pointer;
    transition: all 0.15s;
}
.filter-btn.active { color: #e0e0e0; border-color: #29b6f6; background: #0f3460; }
.action-btn {
    display: block;
    width: 100%;
    padding: 6px;
    margin-bottom: 6px;
    font-size: 12px;
    background: #1a1a2e;
    border: 1px solid #0f3460;
    color: #e0e0e0;
    border-radius: 4px;
    cursor: pointer;
    text-align: center;
}
.action-btn:hover { background: #0f3460; }
.action-btn.active { border-color: #4caf50; color: #4caf50; }
.legend-row { display: flex; align-items: center; gap: 6px; font-size: 11px; padding: 2px 0; }
.legend-swatch {
    width: 14px;
    height: 14px;
    border-radius: 3px;
    flex-shrink: 0;
}
.legend-shape {
    width: 14px;
    height: 14px;
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 10px;
}
.detail-section { margin-bottom: 16px; }
.detail-section h4 { font-size: 12px; color: #78909c; margin-bottom: 4px; }
.detail-section p, .detail-section div { font-size: 13px; line-height: 1.5; }
.tag-pill {
    display: inline-block;
    padding: 2px 8px;
    background: #1a1a2e;
    border: 1px solid #0f3460;
    border-radius: 10px;
    font-size: 11px;
    margin: 2px;
}
.prereq-link {
    color: #29b6f6;
    cursor: pointer;
    text-decoration: none;
}
.prereq-link:hover { text-decoration: underline; }
.prereq-unresolved { opacity: 0.5; }
.filtered-msg {
    color: #f44336;
    font-size: 11px;
    margin-left: 4px;
    opacity: 0;
    transition: opacity 0.3s;
}
.filtered-msg.show { opacity: 1; }
#stats .stat-row {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    padding: 2px 0;
}
#stats .stat-label { flex: 1; }
#stats .stat-count { width: 30px; text-align: right; }
#stats .stat-bar {
    width: 60px;
    height: 4px;
    background: #1a1a2e;
    border-radius: 2px;
    overflow: hidden;
    flex-shrink: 0;
}
#stats .stat-bar-fill { height: 100%; border-radius: 2px; }
.gap-item {
    font-size: 12px;
    padding: 3px 0;
    cursor: pointer;
    color: #29b6f6;
}
.gap-item:hover { text-decoration: underline; }
.gap-priority { font-size: 10px; opacity: 0.7; margin-left: 4px; }
.evidence-item { font-size: 12px; padding: 4px 0; border-bottom: 1px solid #0f3460; }
.evidence-item:last-child { border-bottom: none; }
"""


def _build_sidebar_html(stats, categories, config):
    h = html.escape
    parts = []
    parts.append('<div id="sidebar-content">')

    parts.append('<h3>Search</h3>')
    parts.append('<div id="search-box"><input id="search-input" type="text" placeholder="Search topics...">')
    parts.append('<button id="search-clear">&times;</button></div>')
    parts.append('<span id="search-count"></span>')

    pct = round(stats["engaged"] / stats["total"] * 100) if stats["total"] else 0
    parts.append('<h3>Progress</h3>')
    parts.append(f'<div style="font-size:13px">{stats["engaged"]}/{stats["total"]} engaged ({pct}%)</div>')
    parts.append(f'<div class="progress-bar"><div class="progress-fill" style="width:{pct}%"></div></div>')

    parts.append('<div id="stats"></div>')

    parts.append('<h3>Categories</h3>')
    parts.append('<div class="filter-links"><a id="cat-all">All</a><a id="cat-none">None</a></div>')
    for ck in config["categoryOrder"]:
        color = config["categoryColors"].get(ck, "#78909c")
        cs = stats["categories"].get(ck, {"total": 0, "engaged": 0})
        parts.append(f'<div class="cat-row">')
        parts.append(f'<input type="checkbox" class="cat-check" value="{h(ck)}" checked>')
        parts.append(f'<span class="cat-dot" style="background:{color}"></span>')
        parts.append(f'<span class="cat-label" data-cat="{h(ck)}">{h(ck)} <span style="opacity:0.5">({cs["engaged"]}/{cs["total"]})</span></span>')
        parts.append('</div>')

    parts.append('<h3>Status</h3>')
    parts.append('<div class="filter-group" id="status-filters">')
    for s in config["statusOrder"]:
        cnt = stats["by_status"].get(s, 0)
        parts.append(f'<button class="filter-btn active" data-status="{h(s)}">{h(s)} ({cnt})</button>')
    parts.append('</div>')

    parts.append('<h3>Priority</h3>')
    parts.append('<div class="filter-group" id="priority-filters">')
    for p in ["critical", "high", "medium", "low"]:
        cnt = stats["by_priority"].get(p, 0)
        parts.append(f'<button class="filter-btn active" data-priority="{h(p)}">{h(p)} ({cnt})</button>')
    parts.append('</div>')

    parts.append('<h3>Actions</h3>')
    parts.append('<button class="action-btn" id="btn-fit">Fit All</button>')
    parts.append('<button class="action-btn" id="btn-suggested">Show Suggested</button>')
    parts.append('<button class="action-btn" id="btn-related">Toggle Related Edges</button>')
    parts.append('<button class="action-btn" id="btn-export">Export PNG</button>')

    parts.append('<h3>Legend</h3>')
    for s in config["statusOrder"]:
        c = config["statusColors"].get(s, "#616161")
        parts.append(f'<div class="legend-row"><span class="legend-swatch" style="background:{c}"></span>{h(s)}</div>')
    parts.append('<div style="margin-top:6px">')
    for p, info in config["priorityBorders"].items():
        parts.append(f'<div class="legend-row"><span class="legend-swatch" style="border:{info["width"]}px solid {info["color"]};background:transparent"></span>{h(p)}</div>')
    parts.append('</div>')
    parts.append('<div style="margin-top:6px">')
    shapes = [("1-2", "ellipse"), ("3", "roundrect"), ("4", "diamond"), ("5", "star")]
    icons = {"ellipse": "&#9679;", "roundrect": "&#9632;", "diamond": "&#9670;", "star": "&#9733;"}
    for label, shape in shapes:
        parts.append(f'<div class="legend-row"><span class="legend-shape">{icons[shape]}</span>difficulty {label}</div>')
    parts.append('</div>')
    parts.append('</div>')

    return "\n".join(parts)


def _build_detail_panel_html():
    return """<div id="detail-panel">
<button id="detail-close">&times;</button>
<div id="detail-content"></div>
</div>"""


def _build_js():
    return """
var DATA = __KB_DAG_DATA__;

cytoscape.use(cytoscapeDagre);

var selectedNodeId = null;
var showRelated = false;

var styleArr = [
    {selector: 'node', style: {
        'label': 'data(name)', 'text-max-width': 120, 'text-wrap': 'ellipsis',
        'text-valign': 'bottom', 'text-margin-y': 5, 'font-size': 10,
        'color': '#e0e0e0', 'width': 'data(size)', 'height': 'data(size)',
        'background-color': '#616161', 'border-width': 2, 'border-color': '#78909c',
        'text-outline-color': '#1a1a2e', 'text-outline-width': 1
    }},
    {selector: 'node[status="not_started"]', style: {'background-color': '#616161'}},
    {selector: 'node[status="exposed"]', style: {'background-color': '#4fc3f7'}},
    {selector: 'node[status="conceptual"]', style: {'background-color': '#2196f3'}},
    {selector: 'node[status="applied"]', style: {'background-color': '#4caf50'}},
    {selector: 'node[status="proficient"]', style: {'background-color': '#9c27b0'}},
    {selector: 'node[status="mastered"]', style: {'background-color': '#ffd600'}},
    {selector: 'node[priority="critical"]', style: {'border-width': 4, 'border-color': '#f44336'}},
    {selector: 'node[priority="high"]', style: {'border-width': 3, 'border-color': '#ff9800'}},
    {selector: 'node[priority="medium"]', style: {'border-width': 2, 'border-color': '#78909c'}},
    {selector: 'node[priority="low"]', style: {'border-width': 1, 'border-color': '#546e7a'}},
    {selector: 'node[difficulty <= 2]', style: {'shape': 'ellipse'}},
    {selector: 'node[difficulty = 3]', style: {'shape': 'roundrectangle'}},
    {selector: 'node[difficulty = 4]', style: {'shape': 'diamond'}},
    {selector: 'node[difficulty >= 5]', style: {'shape': 'star'}},
    {selector: 'edge[type="prerequisite"]', style: {
        'line-color': '#455a64', 'target-arrow-color': '#455a64',
        'target-arrow-shape': 'triangle', 'curve-style': 'bezier',
        'opacity': 0.6, 'width': 1.5
    }},
    {selector: 'edge[type="related"]', style: {
        'line-color': '#37474f', 'line-style': 'dashed',
        'curve-style': 'bezier', 'opacity': 0.3, 'width': 1,
        'display': 'none'
    }},
    {selector: '.highlighted', style: {
        'text-outline-color': '#ffffff', 'text-outline-width': 2,
        'border-color': '#ffffff', 'border-width': 3,
        'z-index': 20
    }},
    {selector: '.ancestor', style: {
        'border-color': '#ffd600', 'border-width': 3,
        'text-outline-color': '#ffd600', 'text-outline-width': 1,
        'z-index': 15
    }},
    {selector: '.ancestor-needed', style: {
        'border-color': '#f44336', 'border-width': 3,
        'text-outline-color': '#f44336', 'text-outline-width': 1,
        'z-index': 15
    }},
    {selector: '.descendant', style: {
        'border-color': '#29b6f6', 'border-width': 3,
        'text-outline-color': '#29b6f6', 'text-outline-width': 1,
        'z-index': 15
    }},
    {selector: '.dimmed', style: {'opacity': 0.15}},
    {selector: '.suggested', style: {
        'border-color': '#4caf50', 'border-width': 4,
        'border-style': 'double',
        'z-index': 20
    }},
    {selector: 'edge.path-edge', style: {
        'line-color': '#ffd600', 'target-arrow-color': '#ffd600',
        'width': 2.5, 'opacity': 1, 'z-index': 15
    }}
];

var cy = cytoscape({
    container: document.getElementById('cy'),
    elements: { nodes: DATA.nodes, edges: DATA.edges },
    style: styleArr,
    layout: {
        name: 'dagre',
        rankDir: 'TB',
        nodeSep: 50,
        rankSep: 80,
        fit: true,
        padding: 40
    },
    minZoom: 0.1,
    maxZoom: 4,
    wheelSensitivity: 0.3
});

function esc(s) {
    if (s == null) return '';
    var d = document.createElement('div');
    d.textContent = String(s);
    return d.innerHTML;
}

var nameToId = {};
DATA.nodes.forEach(function(n) { nameToId[n.data.name] = n.data.id; });

var tooltip = document.getElementById('tooltip');
cy.on('mouseover', 'node', function(evt) {
    var d = evt.target.data();
    var stars = '';
    for (var i = 0; i < 5; i++) stars += i < d.difficulty ? '\\u2605' : '\\u2606';
    tooltip.innerHTML = '<div style="font-weight:600;margin-bottom:4px">' + esc(d.name) + '</div>' +
        '<div>' + esc(d.status) + ' \\u00b7 ' + esc(d.priority) + ' \\u00b7 ' + stars + '</div>';
    tooltip.style.display = 'block';
    var e = evt.originalEvent;
    var tw = tooltip.offsetWidth, th = tooltip.offsetHeight;
    var x = e.pageX + 12, y = e.pageY + 12;
    if (x + tw > window.innerWidth) x = e.pageX - tw - 12;
    if (y + th > window.innerHeight) y = e.pageY - th - 12;
    tooltip.style.left = x + 'px';
    tooltip.style.top = y + 'px';
});
cy.on('mouseout', 'node', function() { tooltip.style.display = 'none'; });

function clearSelection() {
    cy.elements().removeClass('highlighted ancestor ancestor-needed descendant dimmed path-edge suggested');
    selectedNodeId = null;
    hideDetailPanel();
}

function hideDetailPanel() {
    document.getElementById('detail-panel').classList.remove('open');
}

function showDetailPanel(d) {
    document.getElementById('detail-panel').classList.add('open');
    var c = document.getElementById('detail-content');
    var h = '<h2 style="font-size:16px;margin-bottom:12px;margin-top:24px">' + esc(d.name) + '</h2>';

    h += '<div class="detail-section"><h4>Description</h4><p>' + esc(d.description) + '</p></div>';
    h += '<div class="detail-section"><h4>Status</h4><p>' + esc(d.status) + '</p></div>';
    h += '<div class="detail-section"><h4>Priority</h4><p>' + esc(d.priority) + '</p></div>';

    var stars = '';
    for (var i = 0; i < 5; i++) stars += i < d.difficulty ? '\\u2605' : '\\u2606';
    h += '<div class="detail-section"><h4>Difficulty</h4><p>' + stars + ' (' + d.difficulty + '/5)</p></div>';
    h += '<div class="detail-section"><h4>Category</h4><p>' + esc(d.category) + ' / ' + esc(d.subcategory) + '</p></div>';

    h += '<div class="detail-section"><h4>Prerequisites</h4><div>';
    if (d.prerequisites.length === 0) {
        h += '<span style="opacity:0.5">None</span>';
    } else {
        d.prerequisites.forEach(function(p) {
            if (p.nodeId) {
                h += '<span class="prereq-link" data-node="' + esc(p.nodeId) + '">' + esc(p.name) + '</span><span class="filtered-msg" data-for="' + esc(p.nodeId) + '">Filtered out</span><br>';
            } else {
                h += '<span class="prereq-unresolved">' + esc(p.raw) + '</span><br>';
            }
        });
    }
    h += '</div></div>';

    h += '<div class="detail-section"><h4>Related</h4><div>';
    if (d.related.length === 0) {
        h += '<span style="opacity:0.5">None</span>';
    } else {
        d.related.forEach(function(r) {
            if (r.nodeId) {
                h += '<span class="prereq-link" data-node="' + esc(r.nodeId) + '">' + esc(r.name) + '</span><span class="filtered-msg" data-for="' + esc(r.nodeId) + '">Filtered out</span><br>';
            } else {
                h += '<span class="prereq-unresolved">' + esc(r.raw) + '</span><br>';
            }
        });
    }
    h += '</div></div>';

    if (d.tags && d.tags.length) {
        h += '<div class="detail-section"><h4>Tags</h4><div>';
        d.tags.forEach(function(t) { h += '<span class="tag-pill">' + esc(t) + '</span>'; });
        h += '</div></div>';
    }

    h += '<div class="detail-section"><h4>Source</h4><p>' + (d.source_context ? esc(d.source_context) : 'None') + '</p></div>';

    h += '<div class="detail-section"><h4>Evidence</h4>';
    if (!d.level_up_evidence || d.level_up_evidence.length === 0) {
        h += '<p style="opacity:0.5">No evidence recorded</p>';
    } else {
        d.level_up_evidence.forEach(function(e) {
            h += '<div class="evidence-item">' + esc(e.from_level) + ' &rarr; ' + esc(e.to_level) +
                '<br><span style="opacity:0.6;font-size:11px">' + esc(e.timestamp) + ' &middot; ' + esc(e.method) + '</span>' +
                (e.summary ? '<br><span style="font-size:11px">' + esc(e.summary) + '</span>' : '') + '</div>';
        });
    }
    h += '</div>';

    h += '<div class="detail-section"><h4>Connectivity</h4><p>' + d.connections + ' connections</p></div>';

    c.innerHTML = h;

    c.querySelectorAll('.prereq-link').forEach(function(el) {
        el.addEventListener('click', function() {
            var nid = el.getAttribute('data-node');
            var node = cy.getElementById(nid);
            if (node.style('display') === 'none') {
                var msg = el.parentNode.querySelector('.filtered-msg[data-for="' + nid + '"]');
                if (msg) {
                    msg.classList.add('show');
                    setTimeout(function() { msg.classList.remove('show'); }, 1500);
                }
                return;
            }
            node.emit('tap');
            cy.animate({ center: { eles: node }, duration: 300 });
        });
    });
}

cy.on('tap', 'node', function(evt) {
    var node = evt.target;
    clearSelection();
    selectedNodeId = node.id();
    node.addClass('highlighted');

    var ancestors = node.predecessors('node');
    var descendants = node.successors('node');
    var pathEdges = node.predecessors('edge').union(node.successors('edge'));

    var metStatuses = {'conceptual':1,'applied':1,'proficient':1,'mastered':1};
    ancestors.forEach(function(a) {
        if (metStatuses[a.data('status')]) a.addClass('ancestor');
        else a.addClass('ancestor-needed');
    });
    descendants.addClass('descendant');
    pathEdges.addClass('path-edge');

    var involved = node.union(ancestors).union(descendants).union(pathEdges);
    cy.elements().difference(involved).addClass('dimmed');

    showDetailPanel(node.data());
});

cy.on('tap', function(evt) {
    if (evt.target === cy) clearSelection();
});

document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') clearSelection();
});

document.getElementById('detail-close').addEventListener('click', function() {
    clearSelection();
});

var searchInput = document.getElementById('search-input');
var searchClear = document.getElementById('search-clear');
var searchCount = document.getElementById('search-count');
var searchTimer;

function runSearch() {
    var query = searchInput.value.trim().toLowerCase();
    searchClear.style.display = query ? 'block' : 'none';
    if (!query) {
        searchCount.textContent = '';
        return;
    }
    if (selectedNodeId) {
        var visNodes = cy.nodes().filter(function(n) { return n.style('display') !== 'none'; });
        var matches = visNodes.filter(function(n) {
            var d = n.data();
            return d.name.toLowerCase().indexOf(query) >= 0 ||
                (d.tags || []).some(function(t) { return t.toLowerCase().indexOf(query) >= 0; }) ||
                d.description.toLowerCase().indexOf(query) >= 0;
        });
        searchCount.textContent = matches.length + ' matches';
        return;
    }
    cy.elements().removeClass('highlighted dimmed');
    var visNodes = cy.nodes().filter(function(n) { return n.style('display') !== 'none'; });
    var matches = visNodes.filter(function(n) {
        var d = n.data();
        return d.name.toLowerCase().indexOf(query) >= 0 ||
            (d.tags || []).some(function(t) { return t.toLowerCase().indexOf(query) >= 0; }) ||
            d.description.toLowerCase().indexOf(query) >= 0;
    });
    matches.removeClass('dimmed').addClass('highlighted');
    visNodes.not(matches).addClass('dimmed');
    searchCount.textContent = matches.length + ' matches';
    if (matches.length > 0) cy.animate({ fit: { eles: matches, padding: 80 }, duration: 400 });
}

searchInput.addEventListener('input', function() {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(function() {
        clearSelection();
        runSearch();
    }, 200);
});

searchClear.addEventListener('click', function() {
    searchInput.value = '';
    searchClear.style.display = 'none';
    searchCount.textContent = '';
    clearSelection();
});

var catChecks = document.querySelectorAll('.cat-check');
var statusBtns = document.querySelectorAll('#status-filters .filter-btn');
var prioBtns = document.querySelectorAll('#priority-filters .filter-btn');

function applyFilters() {
    var activeCats = new Set();
    catChecks.forEach(function(c) { if (c.checked) activeCats.add(c.value); });
    var activeStatuses = new Set();
    statusBtns.forEach(function(b) { if (b.classList.contains('active')) activeStatuses.add(b.dataset.status); });
    var activePrios = new Set();
    prioBtns.forEach(function(b) { if (b.classList.contains('active')) activePrios.add(b.dataset.priority); });

    cy.batch(function() {
        cy.nodes().forEach(function(node) {
            var d = node.data();
            var vis = activeCats.has(d.category) && activeStatuses.has(d.status) && activePrios.has(d.priority);
            node.style('display', vis ? 'element' : 'none');
        });
        cy.edges().forEach(function(edge) {
            var srcVis = edge.source().style('display') !== 'none';
            var tgtVis = edge.target().style('display') !== 'none';
            if (edge.data('type') === 'related') {
                edge.style('display', (srcVis && tgtVis && showRelated) ? 'element' : 'none');
            } else {
                edge.style('display', (srcVis && tgtVis) ? 'element' : 'none');
            }
        });
    });

    if (selectedNodeId) {
        var sel = cy.getElementById(selectedNodeId);
        if (sel.style('display') === 'none') clearSelection();
    }

    var visCount = cy.nodes().filter(function(n) { return n.style('display') !== 'none'; }).length;
    document.getElementById('empty-state').style.display = visCount === 0 ? 'flex' : 'none';

    if (searchInput && searchInput.value.trim()) runSearch();
}

catChecks.forEach(function(c) { c.addEventListener('change', applyFilters); });
statusBtns.forEach(function(b) {
    b.addEventListener('click', function() { b.classList.toggle('active'); applyFilters(); });
});
prioBtns.forEach(function(b) {
    b.addEventListener('click', function() { b.classList.toggle('active'); applyFilters(); });
});

document.getElementById('cat-all').addEventListener('click', function() {
    catChecks.forEach(function(c) { c.checked = true; });
    applyFilters();
});
document.getElementById('cat-none').addEventListener('click', function() {
    catChecks.forEach(function(c) { c.checked = false; });
    applyFilters();
});

document.querySelectorAll('.cat-label').forEach(function(lbl) {
    lbl.addEventListener('click', function() {
        var cat = lbl.getAttribute('data-cat');
        var nodes = cy.nodes().filter(function(n) {
            return n.data('category') === cat && n.style('display') !== 'none';
        });
        if (nodes.length > 0) cy.animate({ fit: { eles: nodes, padding: 80 }, duration: 400 });
    });
});

document.getElementById('btn-fit').addEventListener('click', function() {
    cy.animate({ fit: { padding: 40 }, duration: 400 });
});

document.getElementById('btn-suggested').addEventListener('click', function() {
    clearSelection();
    var visible = cy.nodes().filter(function(n) { return n.style('display') !== 'none'; });
    var suggested = visible.filter(function(node) {
        var d = node.data();
        if (['not_started','exposed'].indexOf(d.status) < 0) return false;
        if (['critical','high'].indexOf(d.priority) < 0) return false;
        var directPrereqs = node.incomers('node');
        if (directPrereqs.length === 0) return true;
        return directPrereqs.every(function(p) {
            return ['conceptual','applied','proficient','mastered'].indexOf(p.data('status')) >= 0;
        });
    });
    suggested.addClass('suggested');
    visible.not(suggested).addClass('dimmed');
    if (suggested.length > 0) cy.animate({ fit: { eles: suggested, padding: 80 }, duration: 400 });
});

document.getElementById('btn-related').addEventListener('click', function() {
    showRelated = !showRelated;
    this.classList.toggle('active', showRelated);
    applyFilters();
});

document.getElementById('btn-export').addEventListener('click', function() {
    var png = cy.png({ full: true, scale: 2, bg: '#1a1a2e' });
    var a = document.createElement('a');
    a.href = png; a.download = 'kb-dag.png'; a.click();
});

document.getElementById('toolbar').querySelector('[data-action="zoomin"]').addEventListener('click', function() {
    cy.zoom({ level: cy.zoom() * 1.3, renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } });
});
document.getElementById('toolbar').querySelector('[data-action="zoomout"]').addEventListener('click', function() {
    cy.zoom({ level: cy.zoom() / 1.3, renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } });
});
document.getElementById('toolbar').querySelector('[data-action="fit"]').addEventListener('click', function() {
    cy.animate({ fit: { padding: 40 }, duration: 400 });
});

var collapseBtn = document.getElementById('collapse-btn');
var sidebar = document.getElementById('sidebar');
collapseBtn.addEventListener('click', function() {
    sidebar.classList.toggle('collapsed');
    collapseBtn.textContent = sidebar.classList.contains('collapsed') ? '\\u203a' : '\\u2039';
});
sidebar.addEventListener('transitionend', function() { cy.resize(); });

var resizeTimer;
window.addEventListener('resize', function() {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function() { cy.resize(); }, 200);
});

function renderStats() {
    var s = DATA.stats;
    var el = document.getElementById('stats');
    var h = '';

    h += '<h3>Status Breakdown</h3>';
    var maxS = 0;
    DATA.config.statusOrder.forEach(function(st) { if (s.by_status[st] > maxS) maxS = s.by_status[st]; });
    DATA.config.statusOrder.forEach(function(st) {
        var cnt = s.by_status[st] || 0;
        var pct = maxS > 0 ? (cnt / maxS * 100) : 0;
        var color = DATA.config.statusColors[st] || '#616161';
        h += '<div class="stat-row"><span class="stat-label" style="color:' + color + '">' + st + '</span>';
        h += '<span class="stat-count">' + cnt + '</span>';
        h += '<div class="stat-bar"><div class="stat-bar-fill" style="width:' + pct + '%;background:' + color + '"></div></div></div>';
    });

    h += '<h3>Categories</h3>';
    DATA.config.categoryOrder.forEach(function(ck) {
        var cs = s.categories[ck] || {total:0,engaged:0};
        var color = DATA.config.categoryColors[ck] || '#78909c';
        var pct = cs.total > 0 ? (cs.engaged / cs.total * 100) : 0;
        h += '<div class="stat-row"><span class="cat-dot" style="background:' + color + ';display:inline-block;margin-right:4px"></span>';
        h += '<span class="stat-label">' + ck + '</span>';
        h += '<span class="stat-count">' + cs.engaged + '/' + cs.total + '</span>';
        h += '<div class="stat-bar"><div class="stat-bar-fill" style="width:' + pct + '%;background:' + color + '"></div></div></div>';
    });

    if (s.priority_gaps.length > 0) {
        h += '<h3>Priority Gaps</h3>';
        s.priority_gaps.slice(0, 8).forEach(function(g) {
            var nid = nameToId[g.name];
            h += '<div class="gap-item" data-node="' + (nid || '') + '">' + esc(g.name) +
                '<span class="gap-priority">' + g.priority + ' / ' + g.status + '</span></div>';
        });
    }

    if (s.recent_promotions.length > 0) {
        h += '<h3>Recent Promotions</h3>';
        s.recent_promotions.slice(0, 5).forEach(function(p) {
            h += '<div class="evidence-item">' + esc(p.topic) + '<br>' +
                '<span style="opacity:0.6;font-size:11px">' + esc(p.from_level) + ' &rarr; ' + esc(p.to_level) +
                ' &middot; ' + esc(p.timestamp) + '</span></div>';
        });
    }

    el.innerHTML = h;

    el.querySelectorAll('.gap-item').forEach(function(item) {
        item.addEventListener('click', function() {
            var nid = item.getAttribute('data-node');
            if (nid) {
                var node = cy.getElementById(nid);
                if (node.style('display') !== 'none') {
                    node.emit('tap');
                    cy.animate({ center: { eles: node }, duration: 300 });
                }
            }
        });
    });
}

renderStats();
"""


def generate_html(nodes, edges, stats, categories, config):
    css = _build_css()
    sidebar_html = _build_sidebar_html(stats, categories, config)
    detail_html = _build_detail_panel_html()
    js = _build_js()

    payload = {
        "nodes": nodes,
        "edges": edges,
        "stats": stats,
        "config": config,
    }
    json_str = json.dumps(payload).replace('</', '<\\/')
    js = js.replace('__KB_DAG_DATA__', json_str, 1)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Knowledge Base DAG</title>
<style>{css}</style>
</head>
<body>
<div id="sidebar">
<button id="collapse-btn">&lsaquo;</button>
{sidebar_html}
</div>
<div id="cy-wrapper">
<div id="cy"></div>
<div id="empty-state">No topics match current filters</div>
<div id="toolbar">
<button data-action="zoomin" title="Zoom in">+</button>
<button data-action="zoomout" title="Zoom out">&minus;</button>
<button data-action="fit" title="Fit all">&#8644;</button>
</div>
</div>
{detail_html}
<div id="tooltip"></div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/cytoscape/3.30.4/cytoscape.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/dagre@0.8.5/dist/dagre.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/cytoscape-dagre@2.5.0/cytoscape-dagre.js"></script>
<script>{js}</script>
</body>
</html>"""


def serve(html_path, port):
    directory = os.path.dirname(os.path.abspath(html_path))

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=directory, **kwargs)
        def log_message(self, fmt, *args):
            pass

    try:
        with socketserver.TCPServer(("", port), Handler) as httpd:
            httpd.allow_reuse_address = True
            print(f"Serving at http://localhost:{port}/")
            print("Press Ctrl+C to stop")
            httpd.serve_forever()
    except OSError as e:
        print(f"Error: port {port} in use. Try --port {port + 1}", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Knowledge Base DAG Visualizer")
    parser.add_argument("--kb", help="Path to knowledge-base.yaml")
    parser.add_argument("--port", type=int, default=8808)
    parser.add_argument("--no-serve", action="store_true")
    parser.add_argument("--output", default="/tmp/kb-dag/index.html")
    parser.add_argument("--no-open", action="store_true")
    args = parser.parse_args()

    kb_path = args.kb or os.path.realpath(os.path.join(os.path.dirname(__file__), '..', 'knowledge-base.yaml'))

    if not os.path.exists(kb_path):
        print(f"Error: KB file not found: {kb_path}", file=sys.stderr)
        sys.exit(1)

    topics, categories = parse_kb(kb_path)
    resolve = build_name_resolver(topics)
    nodes, edges = build_graph_data(topics, resolve)
    stats = compute_stats(topics, categories)

    config = {
        "statusColors": STATUS_COLORS,
        "statusOrder": STATUS_ORDER,
        "priorityBorders": PRIORITY_BORDERS,
        "categoryColors": CATEGORY_COLORS,
        "categoryOrder": CATEGORY_ORDER,
    }

    html_out = generate_html(nodes, edges, stats, categories, config)

    out_dir = os.path.dirname(args.output)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(args.output, 'w') as f:
        f.write(html_out)
    print(f"Written to {args.output}")

    if not args.no_serve:
        if not args.no_open:
            webbrowser.open(f"http://localhost:{args.port}/")
        serve(args.output, args.port)


if __name__ == "__main__":
    main()
