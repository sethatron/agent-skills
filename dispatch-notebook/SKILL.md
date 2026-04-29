---
name: dispatch-notebook
version: "1.0.0"
dsi_type: "A"
description: >-
  Use this skill when the user wants to interact with the Dispatch Framework
  Intelligence notebook in NotebookLM. Trigger on: "update the notebook",
  "push the Optimus report to NotebookLM", "what does the notebook say about
  [topic]", "refresh the dispatch knowledge base", "generate the morning
  briefing", "what patterns has NotebookLM identified", "ask NotebookLM about
  [topic]", "notebook is out of date", "sync the dispatch framework docs to
  NotebookLM", "dispatch intelligence briefing", "notebook status", "push this
  to the notebook", "what does NotebookLM think", "query the knowledge base",
  "refresh notebook sources", "prune old notebook sources", "initialize the
  notebook", "check notebook auth". Also trigger on /dispatch-notebook with
  any subcommand.
docs:
  architecture: docs/architecture.md
  integration: docs/integration.md
  failure_modes: docs/failure-modes.md
  quality: docs/quality.md
  workflow: docs/workflow.md
---

+------------------------------------------------------------------------+
| DISPATCH-NOTEBOOK GUARDRAILS                                           |
|                                                                        |
| CLI ONLY: All NotebookLM operations use the nlm CLI exclusively.      |
|   The notebooklm-mcp MCP server must NEVER be used by this skill.     |
|                                                                        |
| READ-ONLY INTELLIGENCE: NotebookLM is queried for synthesized insight |
|   only. It does not make decisions. Claude Code makes all decisions.   |
|                                                                        |
| NO LIVE STATE: Never upload files that change faster than daily.       |
|   (dispatch.db, in-progress task files, live MR diffs)                 |
|                                                                        |
| OPERATOR CONFIRMATION: init and reset require explicit confirmation.   |
|   Source updates are non-destructive (old source deleted only after    |
|   new one uploads successfully -- never the other way around).         |
|                                                                        |
| AUTH FAILURE: Never silently skip. Surface error with re-auth          |
|   instructions. Notify operator via Slack on failed update.            |
|                                                                        |
| SOURCE LIMIT: Never exceed 47 sources. Prune before upload if needed. |
|   Error and abort if still over 47 after prune attempt.                |
|                                                                        |
| GIT: git add / git commit / git push are PROHIBITED — no exceptions.  |
+------------------------------------------------------------------------+

## Environment Pre-Validation

Run `scripts/check_env.py` first on every invocation:

```bash
python scripts/check_env.py [--verbose] [--json] [--fix] [--skip-auth]
```

Validates: nlm on PATH, nlm authenticated, dispatch alias, notebook dir,
source inventory, Python packages, dispatch skill present, Slack MCP.

## Subcommands

### Read Operations (no confirmation required)

| Command | Description |
|---------|-------------|
| `/dispatch-notebook status` | Notebook health, source counts by tier, last update |
| `/dispatch-notebook query "<question>"` | One-shot query against the notebook |
| `/dispatch-notebook briefing` | Show latest morning intelligence briefing |
| `/dispatch-notebook sources` | List all sources with tier, title, upload date |
| `/dispatch-notebook auth` | Check nlm authentication status |

### Write Operations (operator confirmation required)

| Command | Description |
|---------|-------------|
| `/dispatch-notebook init` | Create notebook, set alias, push initial sources |
| `/dispatch-notebook update` | Run full 9-step update sequence |
| `/dispatch-notebook push tier1\|tier2\|tier3\|<path>` | Push specific tier or file |
| `/dispatch-notebook prune` | Remove expired sources |
| `/dispatch-notebook reset` | Delete and recreate the notebook |

## Scripts

| Script | Purpose | Implemented |
|--------|---------|-------------|
| `check_env.py` | Environment validation | Full |
| `nlm_runner.py` | NLM CLI subprocess gateway | Full |
| `update_runner.py` | 9-step update orchestration | Stub |
| `source_renderer.py` | Content rendering for upload | Stub |
| `source_manager.py` | Source lifecycle CRUD | Stub |
| `query_runner.py` | Query execution and caching | Stub |
| `briefing_loader.py` | Briefing generation and injection | Stub |

## References

- `references/nlm-ai-docs.md` — nlm CLI reference (ground truth)
- `references/step-snippet.yaml` — Workflow step definitions
- `references/artifact-schema.yaml` — Update log artifact schema
- `references/dispatch-changes.md` — Required /dispatch modifications
- `references/dispatch-manager-changes.md` — Required /dispatch-manager modifications
- `queries/*.yaml` — Query definitions with exact question text
- `templates/*.j2` — Jinja2 templates for content rendering

## Docs

See docs/ for detailed specifications:

- **Architecture and internals**: [docs/architecture.md](docs/architecture.md)
- **Integration contracts**: [docs/integration.md](docs/integration.md)
- **Failure modes and recovery**: [docs/failure-modes.md](docs/failure-modes.md)
- **Quality grades**: [docs/quality.md](docs/quality.md)
- **Workflow hooks**: [docs/workflow.md](docs/workflow.md)
