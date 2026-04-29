#!/usr/bin/env python3
"""docs/ split migration tool for dispatch-harness.

Reads a monolithic SKILL.md, classifies sections into docs/ categories,
writes split docs/ files, and rewrites SKILL.md in the target frontmatter format.

Usage:
    python migrate_skill.py <skill_dir> [--dry-run] [--json]
"""

import json as json_mod
import re
import sys
from pathlib import Path

import yaml

HARNESS_DIR = Path(__file__).resolve().parent.parent

DOC_CATEGORIES = ("architecture", "integration", "failure-modes", "quality", "workflow")

CATEGORY_TITLES = {
    "architecture": "Architecture",
    "integration": "Integration",
    "failure-modes": "Failure Modes",
    "quality": "Quality Grades",
    "workflow": "Workflow Integration",
}

SECTION_KEYWORDS = {
    "architecture": [
        "architecture", "component", "state store", "directory structure",
        "context window", "hooks", "data flow", "internal dep", "layer",
    ],
    "integration": [
        "integration", "slack", "notebook", "notebooklm", "sub-skill",
        "downstream", "registration", "ecosystem", "hook",
    ],
    "failure-modes": [
        "failure", "error handling", "recovery", "fallback", "corruption",
    ],
    "quality": [
        "quality", "grade", "test", "validation",
    ],
    "workflow": [
        "workflow", "engine", "step", "bottleneck", "priority", "triage",
        "cron", "schedule", "period review", "task state", "carry-forward",
        "carry forward", "git permission", "multi-day",
    ],
}

KEEP_PATTERNS = [
    "environment pre-validation",
    "subcommand",
    "script",
    "reference",
    "role",
]

KEEP_EXCLUSIONS = [
    "detail",
]

KEEP_ORDER = [
    "environment pre-validation",
    "role",
    "subcommand",
    "trigger",
    "script",
    "reference",
]


def classify_skill_md(skill_dir: Path) -> dict:
    """Classify each section of SKILL.md into target docs/ categories.

    Returns dict with keys: frontmatter, guardrails, keep, and one key per
    DOC_CATEGORIES entry. Each value (except frontmatter/guardrails) is a
    list of {heading, content} dicts.
    """
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        raise FileNotFoundError(f"No SKILL.md in {skill_dir}")

    text = skill_md.read_text()

    frontmatter = {}
    body = text
    fm_match = re.match(r"^---\n(.*?)\n---\n(.*)", text, re.DOTALL)
    if fm_match:
        frontmatter = yaml.safe_load(fm_match.group(1)) or {}
        body = fm_match.group(2)

    guardrails = ""
    guard_match = re.search(
        r"([┌+].*?[┐+]\n(?:.*\n)*?[└+].*?[┘+])", body
    )
    if guard_match:
        guardrails = guard_match.group(1).strip()
        body = body[: guard_match.start()] + body[guard_match.end() :]

    sections = _split_sections(body)

    classification = {
        "frontmatter": frontmatter,
        "guardrails": guardrails,
        "keep": [],
    }
    for cat in DOC_CATEGORIES:
        classification[cat] = []

    for section in sections:
        heading_lower = section["heading"].lower()

        is_keep = any(pat in heading_lower for pat in KEEP_PATTERNS)
        is_excluded = any(exc in heading_lower for exc in KEEP_EXCLUSIONS)
        if is_keep and not is_excluded:
            classification["keep"].append(section)
            continue

        best_cat = _score_section(section)
        classification[best_cat].append(section)

    return classification


def write_docs_files(
    skill_dir: Path, classification: dict, templates: dict | None = None
) -> list[Path]:
    """Write classified sections to docs/ files.

    If templates dict is provided (category -> jinja2.Template), uses them
    when structured data is available. Otherwise writes sections directly.
    Returns list of written file paths.
    """
    docs_dir = skill_dir / "docs"
    docs_dir.mkdir(exist_ok=True)

    skill_name = classification["frontmatter"].get("name", skill_dir.name)
    written = []

    for category in DOC_CATEGORIES:
        sections = classification.get(category, [])
        filename = f"{category}.md"
        title = CATEGORY_TITLES.get(category, category.title())

        if not sections:
            content = f"# {skill_name} {title}\n\nTo be populated.\n"
        else:
            parts = [f"# {skill_name} {title}\n"]
            for section in sections:
                parts.append(f"\n## {section['heading']}\n\n{section['content']}\n")
            content = "\n".join(parts)

        path = docs_dir / filename
        path.write_text(content)
        written.append(path)

    return written


def rewrite_skill_md(skill_dir: Path, classification: dict) -> str:
    """Rewrite SKILL.md in target format with docs/ pointers.

    Returns the new content (also written to disk).
    """
    fm = classification["frontmatter"].copy()

    if "dsi_type" not in fm:
        fm["dsi_type"] = "A"

    has_workflow = fm.get("dsi_type") in ("A", "C")

    fm["docs"] = {
        "architecture": "docs/architecture.md",
        "integration": "docs/integration.md",
        "failure_modes": "docs/failure-modes.md",
        "quality": "docs/quality.md",
    }
    if has_workflow:
        fm["docs"]["workflow"] = "docs/workflow.md"

    parts = []

    parts.append("---")
    parts.append(_build_frontmatter(fm))
    parts.append("---\n")

    if classification["guardrails"]:
        parts.append(classification["guardrails"])
        parts.append("")

    kept = _order_kept_sections(classification["keep"])
    for section in kept:
        parts.append(f"## {section['heading']}\n")
        parts.append(section["content"])
        parts.append("")

    parts.append("## Docs\n")
    parts.append("See docs/ for detailed specifications:\n")
    parts.append(
        "- **Architecture and internals**: [docs/architecture.md](docs/architecture.md)"
    )
    parts.append(
        "- **Integration contracts**: [docs/integration.md](docs/integration.md)"
    )
    parts.append(
        "- **Failure modes and recovery**: [docs/failure-modes.md](docs/failure-modes.md)"
    )
    parts.append("- **Quality grades**: [docs/quality.md](docs/quality.md)")
    if has_workflow:
        parts.append(
            "- **Workflow hooks**: [docs/workflow.md](docs/workflow.md)"
        )
    parts.append("")

    content = "\n".join(parts)

    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(content)

    return content


def _build_frontmatter(fm: dict) -> str:
    lines = []

    if "name" in fm:
        lines.append(f"name: {fm['name']}")
    if "version" in fm:
        lines.append(f'version: "{fm["version"]}"')
    if "dsi_type" in fm:
        lines.append(f'dsi_type: "{fm["dsi_type"]}"')
    if "description" in fm:
        desc = fm["description"].strip()
        lines.append("description: >-")
        words = desc.split()
        current = " "
        for word in words:
            if len(current) + len(word) + 1 > 78:
                lines.append(current)
                current = "  " + word
            else:
                current = current + " " + word
        if current.strip():
            lines.append(current)
    if "docs" in fm:
        lines.append("docs:")
        for key, val in fm["docs"].items():
            lines.append(f"  {key}: {val}")

    return "\n".join(lines)


def _split_sections(body: str) -> list[dict]:
    sections = []
    current_heading = None
    current_lines: list[str] = []

    for line in body.split("\n"):
        if line.startswith("## ") and not line.startswith("### "):
            if current_heading is not None:
                sections.append(
                    {
                        "heading": current_heading,
                        "content": "\n".join(current_lines).strip(),
                    }
                )
            current_heading = line[3:].strip()
            current_lines = []
        else:
            current_lines.append(line)

    if current_heading is not None:
        sections.append(
            {
                "heading": current_heading,
                "content": "\n".join(current_lines).strip(),
            }
        )

    return sections


def _score_section(section: dict) -> str:
    heading_lower = section["heading"].lower()
    preview = section["content"][:500].lower()

    best_cat = "architecture"
    best_score = 0

    for category, keywords in SECTION_KEYWORDS.items():
        score = 0
        for kw in keywords:
            if kw in heading_lower:
                score += 3
            elif kw in preview:
                score += 1
        if score > best_score:
            best_score = score
            best_cat = category

    return best_cat


def _order_kept_sections(sections: list[dict]) -> list[dict]:
    def sort_key(section: dict) -> int:
        heading_lower = section["heading"].lower()
        for i, pat in enumerate(KEEP_ORDER):
            if pat in heading_lower:
                return i
        return len(KEEP_ORDER)

    return sorted(sections, key=sort_key)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Migrate SKILL.md to docs/ format")
    parser.add_argument("skill_dir", type=Path, help="Path to skill directory")
    parser.add_argument(
        "--dry-run", action="store_true", help="Print classification without writing"
    )
    parser.add_argument(
        "--json", action="store_true", help="Output classification as JSON"
    )
    args = parser.parse_args()

    skill_dir = args.skill_dir.resolve()
    classification = classify_skill_md(skill_dir)

    if args.json:
        out = {}
        for key in ("keep",) + DOC_CATEGORIES:
            out[key] = [
                {"heading": s["heading"], "lines": s["content"].count("\n") + 1}
                for s in classification.get(key, [])
            ]
        out["guardrails_present"] = bool(classification["guardrails"])
        out["frontmatter_keys"] = list(classification["frontmatter"].keys())
        json_mod.dump(out, sys.stdout, indent=2)
        print()
        sys.exit(0)

    print(f"Skill: {classification['frontmatter'].get('name', skill_dir.name)}")
    print(f"Frontmatter keys: {list(classification['frontmatter'].keys())}")
    print(f"Guardrails: {'yes' if classification['guardrails'] else 'no'}")
    print()

    for key in ("keep",) + DOC_CATEGORIES:
        sections = classification.get(key, [])
        label = key if key != "keep" else "keep (stays in SKILL.md)"
        if sections:
            print(f"  {label}:")
            for s in sections:
                lines = s["content"].count("\n") + 1
                print(f"    - {s['heading']} ({lines} lines)")
        else:
            print(f"  {label}: (empty)")
    print()

    if args.dry_run:
        print("Dry run — no files written.")
        sys.exit(0)

    written = write_docs_files(skill_dir, classification)
    print(f"Wrote {len(written)} docs/ files:")
    for p in written:
        print(f"  {p.relative_to(skill_dir)}")

    rewrite_skill_md(skill_dir, classification)
    new_lines = (skill_dir / "SKILL.md").read_text().count("\n") + 1
    print(f"Rewrote SKILL.md ({new_lines} lines)")


if __name__ == "__main__":
    main()
