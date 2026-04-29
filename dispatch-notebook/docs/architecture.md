# dispatch-notebook Architecture


## Source Content Preparation

All sources rendered to annotated prose markdown before upload.
`scripts/source_renderer.py` handles rendering:

- SKILL.md files: verbatim with prepended header (version, path, type)
- YAML files: annotated markdown with field explanations
- Optimus reports: as-is with normalized header (period, counts)
- Session summaries: prose narrative from session.yaml fields

Content hash (SHA-256) computed before every upload, compared against
inventory. Hash match = skip upload.


## Architectural Split

**Claude Code handles:** executing nlm CLI commands, reading live
filesystem state, deciding what/when to push, transforming content,
routing query responses, source lifecycle, all scripting.

**NotebookLM handles:** synthesizing patterns across documents,
answering grounded questions with citations, generating summaries
that would overwhelm context windows, retaining 30+ Optimus reports,
cross-referencing architecture docs against operational data.

**Anti-patterns — never do these:**
- Ask NotebookLM to make decisions (routing, prioritization)
- Ask NotebookLM about live state (current session, today's tasks)
- Synthesize 30 Optimus reports in-context — push and query instead
- Upload files that change faster than daily
- Skip queries because Claude Code already knows — citations are the point

Every query: SPECIFIC, GROUNDED, ACTIONABLE.


## Idempotency

Read operations (status, query, briefing, sources, auth) are fully
idempotent. Update is idempotent within a day (hash-based dedup).
Source uploads are idempotent (content hash check).
