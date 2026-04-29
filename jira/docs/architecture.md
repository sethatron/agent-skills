# jira Architecture


## Cross-Skill Invocation Mode (JIRA_CALLER)

Check the `JIRA_CALLER` environment variable at startup:
- **Unset or `operator`**: standard mode (reads + confirmed writes permitted)
- **Any other value** (e.g. `gitlab-mr-review`, `dispatch`): **FORCED READ-ONLY MODE**

In FORCED READ-ONLY MODE, ALL write subcommands are rejected immediately:
```json
{
  "error": "WRITE_BLOCKED_CROSS_SKILL",
  "subcommand": "<attempted subcommand>",
  "caller": "<JIRA_CALLER value>",
  "message": "Write operations require direct operator invocation."
}
```
No confirmation prompt is presented. The calling skill surfaces the error as-is.

Unset JIRA_CALLER emits a deprecation warning in verbose mode.


## Natural Language Handling

Map natural language to the closest subcommand. Always surface the resolved command:
- READ: `Interpreted as: /jira search [jql: ...] — proceed? [Y/n]`
- WRITE: Route through full Section 1A protocol. Both interpretation AND operation require confirmation.

Ambiguous queries → ask for clarification. Ambiguous write-intent → default to clarification, never execution.


## Caching

Location: `<skill_dir>/cache/jira/`
- Issue detail TTL: 30 min (configurable)
- Search results TTL: 30 min
- Sprint TTL: 60 min
- Bypass: `--no-cache` on any subcommand
- Force refresh: `--refresh` on any subcommand
- Write ops invalidate affected cache entries immediately


## Output Format

- Issue keys hyperlinked: `[PROJ-123](https://<base_url>/browse/PROJ-123)`
- Statuses as consistent text labels
- Tables for list views; definition-list Markdown for detail views
- Descriptions truncated at 500 chars with `[truncated — use /jira issue <key> for full detail]`
- JSON output: 2-space indent. CSV: header row included.


## Skill Configuration

`config/jira.yaml` — operator-scoped defaults. All optional overrides.
See file for all fields with types, defaults, and documentation.
