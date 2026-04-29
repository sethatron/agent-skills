# dispatch-notebook Workflow Integration


## Daily Update Workflow

### Trigger Points

Two workflow.yaml steps added during init (see `references/step-snippet.yaml`):

1. **morning_briefing_load** — first in morning workflow. Reads briefing,
   compresses to bullets, injects into session context. Never blocks.
2. **notebook_update** — EOD after optimus_nightly. Triggers full update.

### Update Sequence (scripts/update_runner.py)

1. Auth check (`nlm login --check`). Abort on failure.
2. Inventory reconciliation vs live source list.
3. TIER 2 update: render, hash, replace changed Optimus sources.
4. TIER 3 update: same for last 7 days of session files.
5. TIER 1 update: hash each framework doc, replace if changed.
6. Prune expired sources (expires_at < now).
7. Generate morning briefing (all MB queries).
8. Slack notification.
9. Write entry to update_log.yaml.

Running update twice in the same day is safe. Hash detection prevents
duplicate uploads. Second run adds a new log entry only.
