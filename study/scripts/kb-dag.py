#!/usr/bin/env python3
import sys
import os
import re
import json
import shutil
import argparse
import webbrowser
import http.server
import socketserver
import signal
import time
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

WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'kb-dag-web')
PID_FILE = "/tmp/kb-dag/server.pid"


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
            "resources": t.get("resources") or {},
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


def _read_asset(filename):
    path = os.path.join(WEB_DIR, filename)
    if not os.path.exists(path):
        print(f"Error: missing asset {path}", file=sys.stderr)
        sys.exit(1)
    with open(path) as f:
        return f.read()


def generate_html(standalone, data_payload):
    template = _read_asset('template.html')
    css = _read_asset('style.css')
    js = _read_asset('app.js')

    if standalone:
        style_block = f'<style>{css}</style>'
        data_block = f'<script>var DATA = {data_payload};</script>'
        script_block = f'<script>{js}</script>'
    else:
        style_block = '<link rel="stylesheet" href="style.css">'
        data_block = '<script src="data.js"></script>'
        script_block = '<script src="app.js"></script>'

    html_out = template
    html_out = html_out.replace('<!-- STYLE_BLOCK -->', style_block)
    html_out = html_out.replace('<!-- DATA_BLOCK -->', data_block)
    html_out = html_out.replace('<!-- SCRIPT_BLOCK -->', script_block)
    return html_out


def serve(html_path, port):
    directory = os.path.dirname(os.path.abspath(html_path))

    class ReusableTCPServer(socketserver.TCPServer):
        allow_reuse_address = True

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=directory, **kwargs)
        def end_headers(self):
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            super().end_headers()
        def log_message(self, fmt, *args):
            pass

    try:
        with ReusableTCPServer(("", port), Handler) as httpd:
            print(f"Serving at http://localhost:{port}/")
            print("Press Ctrl+C to stop")
            httpd.serve_forever()
    except OSError as e:
        print(f"Error: port {port} in use. Try --port {port + 1}", file=sys.stderr)
        sys.exit(1)


def read_pid():
    try:
        with open(PID_FILE) as f:
            return int(f.read().strip())
    except (FileNotFoundError, ValueError):
        return None


def is_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def kill_existing():
    pid = read_pid()
    if pid is None:
        return None
    if not is_alive(pid):
        os.remove(PID_FILE)
        return None
    try:
        os.kill(pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        os.remove(PID_FILE)
        return None
    for _ in range(20):
        time.sleep(0.1)
        if not is_alive(pid):
            break
    else:
        try:
            os.kill(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    try:
        os.remove(PID_FILE)
    except FileNotFoundError:
        pass
    return pid


def stop_server():
    killed = kill_existing()
    if killed is None:
        print("No server running")
    else:
        print(f"Stopped server (PID {killed})")
    sys.exit(0)


def daemonize(port, html_path, open_browser):
    kill_existing()
    os.makedirs(os.path.dirname(PID_FILE), exist_ok=True)
    child_pid = os.fork()
    if child_pid > 0:
        with open(PID_FILE, 'w') as f:
            f.write(str(child_pid))
        if open_browser:
            webbrowser.open(f"http://localhost:{port}/")
        print(f"Background server started (PID {child_pid}) at http://localhost:{port}/")
        return
    os.setsid()
    os.close(0)
    devnull = os.open(os.devnull, os.O_RDWR)
    os.dup2(devnull, 1)
    os.dup2(devnull, 2)
    serve(html_path, port)


def main():
    parser = argparse.ArgumentParser(description="Knowledge Base DAG Visualizer")
    parser.add_argument("--kb", help="Path to knowledge-base.yaml")
    parser.add_argument("--port", type=int, default=8808)
    parser.add_argument("--no-serve", action="store_true")
    parser.add_argument("--output", default="/tmp/kb-dag/index.html")
    parser.add_argument("--no-open", action="store_true")
    parser.add_argument("--background", action="store_true")
    parser.add_argument("--stop", action="store_true")
    args = parser.parse_args()

    if args.stop:
        stop_server()

    if args.background and args.no_serve:
        parser.error("--background and --no-serve are mutually exclusive")

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

    payload = {"nodes": nodes, "edges": edges, "stats": stats, "config": config}
    json_str = json.dumps(payload).replace('</', '<\\/')

    out_dir = os.path.dirname(args.output)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    html_out = generate_html(standalone=args.no_serve, data_payload=json_str)
    with open(args.output, 'w') as f:
        f.write(html_out)
    print(f"Written to {args.output}")

    if not args.no_serve:
        shutil.copy2(os.path.join(WEB_DIR, 'style.css'), os.path.join(out_dir, 'style.css'))
        shutil.copy2(os.path.join(WEB_DIR, 'app.js'), os.path.join(out_dir, 'app.js'))
        with open(os.path.join(out_dir, 'data.js'), 'w') as f:
            f.write(f'var DATA = {json_str};')
        if args.background:
            daemonize(args.port, args.output, not args.no_open)
        else:
            if not args.no_open:
                webbrowser.open(f"http://localhost:{args.port}/")
            serve(args.output, args.port)


if __name__ == "__main__":
    main()
