#!/usr/bin/env python3
import sys
import os
from collections import Counter
from datetime import datetime

try:
    import yaml
except ImportError:
    print("Error: pyyaml is required. Install with: pip install pyyaml")
    sys.exit(1)

def main():
    kb_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "knowledge-base.yaml")
    kb_path = os.path.realpath(kb_path)

    with open(kb_path) as f:
        data = yaml.safe_load(f)

    SKIP_KEYS = {"metadata"}
    LEVELS = ["mastered", "proficient", "applied", "conceptual", "exposed", "not_started"]

    topics = []
    category_stats = {}

    for cat_key, cat_val in data.items():
        if cat_key in SKIP_KEYS or not isinstance(cat_val, dict):
            continue
        cat_topics = []
        for sub_key, sub_val in cat_val.items():
            if not isinstance(sub_val, list):
                continue
            for topic in sub_val:
                if isinstance(topic, dict) and "name" in topic:
                    cat_topics.append(topic)
        topics.extend(cat_topics)
        category_stats[cat_key] = cat_topics

    total = len(topics)
    level_counts = Counter(t.get("status", "not_started") for t in topics)
    priority_counts = Counter(t.get("priority", "medium") for t in topics)
    engaged = total - level_counts.get("not_started", 0)

    print(f"Knowledge Base: {engaged}/{total} topics engaged\n")

    print("By Level:")
    max_count = max(level_counts.values()) if level_counts else 1
    for level in LEVELS:
        count = level_counts.get(level, 0)
        bar_len = int((count / max_count) * 30) if max_count > 0 else 0
        bar = "\u2588" * bar_len
        print(f"  {level:<14} {count:>3}  {bar}")

    print(f"\nBy Priority:")
    for p in ["critical", "high", "medium", "low"]:
        print(f"  {p:<10} {priority_counts.get(p, 0):>3}")

    print(f"\nBy Category:")
    for cat_key, cat_topics in category_stats.items():
        cat_engaged = sum(1 for t in cat_topics if t.get("status", "not_started") != "not_started")
        print(f"  {cat_key:<30} {cat_engaged:>2}/{len(cat_topics):<2} engaged")

    critical_gaps = [
        t for t in topics
        if t.get("priority") in ("critical", "high")
        and t.get("status", "not_started") in ("not_started", "exposed", "conceptual")
    ]
    critical_gaps.sort(key=lambda t: (
        0 if t.get("priority") == "critical" else 1,
        LEVELS.index(t.get("status", "not_started")) if t.get("status", "not_started") in LEVELS else 99
    ))

    if critical_gaps:
        print(f"\nPriority Gaps (critical/high topics below proficient):")
        for i, t in enumerate(critical_gaps[:10], 1):
            print(f"  {i}. {t['name']} ({t.get('priority')}, {t.get('status', 'not_started')})")

    evidence_entries = []
    for t in topics:
        for e in t.get("level_up_evidence", []) or []:
            if isinstance(e, dict) and e.get("timestamp"):
                try:
                    ts = datetime.fromisoformat(e["timestamp"].replace("Z", "+00:00"))
                    evidence_entries.append((ts, t["name"], e.get("from_level"), e.get("to_level")))
                except (ValueError, TypeError):
                    pass

    if evidence_entries:
        evidence_entries.sort(key=lambda x: x[0], reverse=True)
        print(f"\nRecent Promotions ({len(evidence_entries)} total):")
        for ts, name, from_l, to_l in evidence_entries[:5]:
            print(f"  {ts.strftime('%Y-%m-%d %H:%M')} | {name}: {from_l} -> {to_l}")

if __name__ == "__main__":
    main()
