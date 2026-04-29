# dispatch Integration


## Slack Notifications

Channel: #dispatch (C0AQC48GL1G). Templates in `templates/slack/`.
Dedup: same content_hash not resent within 30 minutes.
Queue: if Slack MCP unavailable, queue in dispatch.db, flush on reconnect.


## Optimus Agent

Defined in `.claude/agents/optimus.md`. Runs as `claude -p` subprocess with
its own context window. Receives `optimus_brief.md` and produces `optimus_report.md`.

Triggers: auto after all daily tasks complete, queued for EOD otherwise, manual via `/dispatch optimus`.

Knowledge base at `~/.zsh/dispatch/optimus/`.

### Optional: NotebookLM Integration (requires /notebook skill)

If installed, Optimus can push findings to a NotebookLM notebook as a secondary
persistence layer. The local knowledge base is always maintained regardless.


## NotebookLM Integration Hooks

### Post-bottleneck_scan Hook (CRITICAL/HIGH only)

After bottleneck_scan completes, for each CRITICAL or HIGH severity
bottleneck, invoke `/dispatch-notebook query` with BC-01 and BC-02
queries, substituting the bottleneck type. Append inline:

    [BOTTLENECK] <description>
    [NOTEBOOK] Prior resolution: <BC-01 summary, 2-3 sentences>
    [NOTEBOOK] Prevention:       <BC-02 summary, 2-3 sentences>

On query failure: log error, display alert without notebook context.
Never block the bottleneck notification on a query failure.
MEDIUM severity bottlenecks do NOT trigger live queries.

### Task Start Notebook Query

On `/dispatch task start`, if the task has tags, invoke
`/dispatch-notebook query` with TC-01, substituting task.tags.
Timeout: 30 seconds. Display 2-3 sentence summary as [NOTEBOOK]
context block before task confirmation. Skip silently if no tags,
cache hit within 20 hours, or query failure.

### Post-/compact Briefing Re-injection

After any /compact event, re-inject the morning briefing summary
by reading `~/.zsh/dispatch/notebook/morning_briefing.md` and
compressing to max 5 bullets per section. This is a file read only —
no live NotebookLM query. The briefing is the persistent intelligence
anchor that survives context compaction.

### Briefing Staleness

If the morning briefing is older than 48 hours or missing:
inject warning "[NOTEBOOK] Briefing stale (>48h). Run /dispatch-notebook update."
Never block on a stale briefing.
