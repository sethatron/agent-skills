# dispatch-notebook Failure Modes


## Failure Handling

| Failure | Behavior |
|---------|----------|
| Auth expired | Surface re-auth prompt, abort operation |
| Source limit (47) | Run prune, retry. Abort if still over. |
| nlm timeout | Log, surface to operator. Never silently skip. |
| Network error | Retry once after 10s, then raise. |
| Query failure | Log error, continue without notebook context |
| Briefing stale (>48h) | Inject warning, suggest update, continue |
| Notebook not initialized | Prompt `/dispatch-notebook init` |
| Source upload failure | Log, mark pending in inventory, retry on next update |
