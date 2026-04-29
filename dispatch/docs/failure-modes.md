# dispatch Failure Modes


## Failure Handling

- Step failure: log, Slack notify, mark FAILED, continue (unless blocking: true)
- Sub-skill failure: record, skip artifact collection, surface clear error
- Slack MCP down: queue messages, flush on reconnect, write fallback log
- DB corruption: integrity check → backup → re-init → recover from filesystem
- After 3 consecutive step failures: auto-disable step
