# jiratui Documentation Reference

This directory holds a local clone of the jiratui documentation for offline reference.

## First-Run Setup

On first `/jira` invocation, if this directory contains only this README, clone the docs:

```bash
git clone --depth 1 https://github.com/whyisdifficult/jiratui /tmp/jiratui-clone
cp -r /tmp/jiratui-clone/docs/* /Users/sethallen/agent-skills/jira/references/jiratui-docs/
cp /tmp/jiratui-clone/README.md /Users/sethallen/agent-skills/jira/references/jiratui-docs/upstream-README.md
rm -rf /tmp/jiratui-clone
```

To refresh: `python scripts/check_env.py --refresh-docs`

## jiratui CLI Quick Reference

```
jiratui issues search --project-key <KEY> [--jql <expr>] [--output json]
jiratui issues update <ISSUE-KEY> [--status <s>] [--assignee <u>] [--summary <t>] [--labels <l>]
jiratui comments list <ISSUE-KEY> [--output json]
jiratui comments add <ISSUE-KEY> --body <text>
jiratui users search <query> [--output json]
jiratui version
```

All commands that support `--output json` MUST use it. The skill parses JSON; it never scrapes TUI output.

## PROHIBITED Commands

- `jiratui issues delete` — irreversible, use Jira web UI instead
- `jiratui comments delete` — available but requires double operator confirmation
