# jira Integration


## Tool Integration

**Primary**: jiratui CLI via `scripts/jiratui_runner.py` — always `--output json`.
**Fallback**: Jira REST API v3 via `scripts/jira_client.py` — for features jiratui lacks.
Credentials sourced from jiratui config (parsed at runtime, never cached).


## Integration with Sibling Skills

- **gitlab-mr-review**: Sets `JIRA_CALLER=gitlab-mr-review` to fetch linked issue context. Always read-only.
- **dispatch**: Sets `JIRA_CALLER=dispatch` for jira_mentions step. Always read-only.
- Both share the same check_env.py pattern but maintain separate scripts. No shared library dependency.
- Credentials never interchanged (GitLab uses GITLAB_TOKEN; Jira uses jiratui config).
