# jira Failure Modes


## Failure Handling

| Failure | Behavior |
|---------|----------|
| jiratui non-zero exit | Surface full stderr, suggest `--verbose` rerun |
| API 401/403 | Surface token expiry guidance with regeneration URL |
| API 429 | Back off with exponential delay, retry |
| Network timeout | Surface error, suggest `--no-cache` retry |
| JQL parse error | Surface Jira's error message, suggest correction |
