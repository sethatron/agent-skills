# Required Changes in /dispatch for Notebook Integration

All changes below are applied by `/dispatch-notebook init` via
`/dispatch-manager edit config` and `/dispatch-manager add step`.
If automatic application fails, apply manually using these instructions.

NOTE: dispatch_runner.py is currently a stub. Sections marked [STUB TARGET]
describe design specifications for when the script is implemented.

## 1. workflow.yaml — Add Two Steps

### morning_briefing_load (position: FIRST in morning workflow)

Insert before all existing steps:

```yaml
  - id: morning_briefing_load
    name: "Morning Briefing Intelligence"
    skill: /dispatch-notebook
    args: "briefing"
    description: "Load NotebookLM intelligence briefing into session context"
    on_blocker: log_and_continue
    timeout_minutes: 2
    tags: [notebook, morning]
    enabled: true
```

### notebook_update (position: after optimus_nightly in EOD workflow)

Add to the `schedule` section or as a late-running step:

```yaml
  - id: notebook_update
    name: "Notebook Source Update"
    skill: /dispatch-notebook
    args: "update"
    description: "Refresh NotebookLM sources with latest framework state"
    on_blocker: notify_slack
    timeout_minutes: 15
    tags: [notebook, eod]
    enabled: true
```

## 2. dispatch SKILL.md — Add Hook Instructions

### Post-bottleneck_scan Hook (CRITICAL and HIGH only)

Add to the Bottleneck Detection section of dispatch SKILL.md:

> After bottleneck_scan completes, for each CRITICAL or HIGH severity
> bottleneck, invoke `/dispatch-notebook query` with BC-01 and BC-02
> queries, substituting the bottleneck type. Append inline:
>
>     [BOTTLENECK] <description>
>     [NOTEBOOK] Prior resolution: <BC-01 summary, 2-3 sentences>
>     [NOTEBOOK] Prevention:       <BC-02 summary, 2-3 sentences>
>
> On query failure: log error, display alert without notebook context.
> Never block the bottleneck notification on a query failure.
> MEDIUM severity bottlenecks do NOT trigger live queries.

### Task Start Notebook Query

Add to the Task State Machine section:

> On `/dispatch task start`, if the task has tags, invoke
> `/dispatch-notebook query` with TC-01, substituting task.tags.
> Timeout: 30 seconds. Display 2-3 sentence summary as [NOTEBOOK]
> context block before task confirmation. Skip silently if no tags,
> cache hit within 20 hours, or query failure.

### Post-/compact Briefing Re-injection

Add to the end of dispatch SKILL.md:

> After any /compact event, re-inject the morning briefing summary
> by reading the latest briefing file and calling
> briefing_loader.summarize_for_context(). This is a file read only —
> no live NotebookLM query. The briefing is the persistent intelligence
> anchor that survives context compaction.

## 3. dispatch_runner.py — Post-Step Hook [STUB TARGET]

When dispatch_runner.py is implemented, add a `post_step_hook` mechanism:

```python
def post_step_hook(step_id: str, step_result: dict, session: dict) -> None:
    """Called after each step completes. Dispatches to registered hooks."""
    hooks = {
        "bottleneck_scan": _notebook_bottleneck_hook,
        "weekly_review": _notebook_weekly_hook,
    }
    hook_fn = hooks.get(step_id)
    if hook_fn:
        try:
            hook_fn(step_result, session)
        except Exception:
            pass  # Never block workflow on hook failure
```

The bottleneck hook runs BC-01 and BC-02 queries for CRITICAL/HIGH bottlenecks.
The weekly review hook runs WS-01 and inserts the response as the opening
"NotebookLM Synthesis" section of weekly_report.md.

## 4. Briefing Staleness Handling

If the morning briefing is older than 48 hours or missing:
- Inject a warning: "[NOTEBOOK] Briefing stale (>48h). Run /dispatch-notebook update."
- Continue the session normally. Never block on a stale briefing.
