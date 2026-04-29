# dispatch-manager Failure Modes


## Self-Modification

When modifying dispatch-manager itself:
- Operator must type `self-modify` as explicit confirmation
- Full directory backup created regardless of change scope
- Never combined with contract changes in same operation
- See `references/recovery.md` for manual recovery when self-modification fails


## Failure Handling

| Failure | Behavior |
|---------|----------|
| Managed skill missing | Report in status, skip in validation |
| Broken symlink | Report with fix command |
| Registry parse error | Surface error, suggest recovery |
| DSI validation FAIL | Block registration, surface report |
| Contract drift | Report drift details, suggest resolution |
| Backup dir unwritable | Block all write operations |
| Self-modification error | Rollback from pre-modification backup |
