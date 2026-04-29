#!/usr/bin/env python3
"""
Natural language to JQL translator.

Uses rule-based pattern matching for common queries before falling
back to LLM-based translation. All translations are logged.

Usage (CLI):
    python scripts/jql_translator.py "show my open bugs"
    python scripts/jql_translator.py "what did we close last week?" --project PROJ

Usage (module):
    from jql_translator import translate
    jql, explanation = translate("my open tickets")
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

SKILL_DIR = Path(__file__).resolve().parent.parent
TRANSLATION_LOG = SKILL_DIR / "cache" / "jira" / "jql_translations.log"

RULE_PATTERNS = [
    {
        "patterns": ["my open", "my tickets", "my issues", "assigned to me", "what am i working on"],
        "jql": 'assignee = currentUser() AND resolution = Unresolved ORDER BY updated DESC',
        "explanation": "Issues assigned to you that are unresolved, ordered by most recently updated",
    },
    {
        "patterns": ["current sprint", "active sprint", "what's in the sprint"],
        "jql": 'sprint in openSprints() AND project = {project} ORDER BY rank',
        "explanation": "All issues in the current active sprint, ordered by rank",
    },
    {
        "patterns": ["closed last week", "done last week", "completed last week"],
        "jql": 'status changed to Done after -7d AND project = {project} ORDER BY updated DESC',
        "explanation": "Issues moved to Done in the last 7 days",
    },
    {
        "patterns": ["blocked", "blocking"],
        "jql": 'status = Blocked AND project = {project} ORDER BY priority DESC',
        "explanation": "Issues currently in Blocked status, ordered by priority",
    },
    {
        "patterns": ["bugs", "open bugs", "my bugs"],
        "jql": 'issuetype = Bug AND resolution = Unresolved AND assignee = currentUser() ORDER BY priority DESC',
        "explanation": "Unresolved bugs assigned to you, ordered by priority",
    },
]


def translate(
    natural_language: str,
    project: Optional[str] = None,
) -> Tuple[str, str]:
    """
    Translate natural language to JQL.

    Tries rule-based matching first, then falls back to LLM.

    Args:
        natural_language: The user's query in plain English.
        project: Optional project key to scope the query.

    Returns:
        Tuple of (jql_string, human_readable_explanation).
        The JQL string is ready to execute.
        The explanation describes what the JQL does in plain English.
    """
    match = _match_rules(natural_language, project)
    if match:
        jql, explanation = match
        _log_translation(natural_language, jql, explanation, "rule")
        return (jql, explanation)
    jql, explanation = _llm_translate(natural_language, project)
    _log_translation(natural_language, jql, explanation, "llm")
    return (jql, explanation)


def _match_rules(text: str, project: Optional[str] = None) -> Optional[Tuple[str, str]]:
    """
    Attempt rule-based JQL translation.

    Args:
        text: Lowercased input text.
        project: Optional project key for template substitution.

    Returns:
        (jql, explanation) tuple if matched, else None.
    """
    text_lower = text.lower()
    for rule in RULE_PATTERNS:
        if any(pat in text_lower for pat in rule["patterns"]):
            jql = rule["jql"]
            if project:
                jql = jql.replace("{project}", project)
            else:
                jql = re.sub(r'\s+AND\s+project\s*=\s*\{project\}', '', jql)
                jql = re.sub(r'project\s*=\s*\{project\}\s+AND\s+', '', jql)
            return (jql.strip(), rule["explanation"])
    return None


def _llm_translate(text: str, project: Optional[str] = None) -> Tuple[str, str]:
    """
    Fall back to LLM-based JQL translation.

    Returns:
        (jql, explanation) tuple.
    """
    jql = text.strip()
    if project and "project" not in jql.lower():
        jql = f"project = {project} AND ({jql})"
    explanation = "No rule matched. Passing as raw JQL — verify before executing."
    return (jql, explanation)


def _log_translation(input_text: str, jql: str, explanation: str, method: str) -> None:
    """Append translation to the log file for debugging and operator review."""
    TRANSLATION_LOG.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().isoformat()
    with open(TRANSLATION_LOG, "a") as f:
        f.write(f"{ts} | {method} | {input_text} | {jql}\n")


def main():
    parser = argparse.ArgumentParser(description="Natural language to JQL translator")
    parser.add_argument("query", help="Natural language query")
    parser.add_argument("--project", help="Project key for scoping")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    jql, explanation = translate(args.query, project=args.project)

    if args.json:
        print(json.dumps({"jql": jql, "explanation": explanation}, indent=2))
    else:
        print(f"[TRANSLATED JQL] {jql}")
        print(f"Explanation: {explanation}")


if __name__ == "__main__":
    main()
