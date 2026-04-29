# beads Failure Modes


## Failure Handling

| Failure | Behavior |
|---------|----------|
| br not found | Error with install instructions |
| .beads/ not initialized | Prompt /beads init |
| br command fails | Log error, surface to operator |
| Board sync fails | Log, Slack notify, do not block session |
| Auditor exceeds 50 commands | Abort audit, report partial results |
| Duplicate issue detected | Skip creation, log |
