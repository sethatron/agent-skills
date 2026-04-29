# Slack Template Variable Reference

## Common Variables

All templates have access to:
- `date` — current date (YYYY-MM-DD)
- `timestamp` — current ISO 8601 timestamp
- `operator` — "@zettatron"

## Template-Specific Variables

### session_start.md.j2
| Variable | Type | Description |
|----------|------|-------------|
| step_count | int | Number of enabled workflow steps |
| carry_forward_count | int | Tasks carried from yesterday |
| step_names | list[str] | Ordered step names |

### step_complete.md.j2
| Variable | Type | Description |
|----------|------|-------------|
| step_name | str | Human-readable step name |
| duration | str | Step duration (e.g., "5m 32s") |
| summary | str | One-line outcome summary |

### blocker_detected.md.j2
| Variable | Type | Description |
|----------|------|-------------|
| severity | str | CRITICAL, HIGH, MEDIUM |
| description | str | What's blocked |
| resource_url | str | URL to blocked resource |

### bottleneck_detected.md.j2
| Variable | Type | Description |
|----------|------|-------------|
| blocked_resource | str | What you're blocking |
| reason | str | Why it's a bottleneck |
| pending_duration | str | How long blocked |
| action | str | Suggested resolution |

### task_started.md.j2
| Variable | Type | Description |
|----------|------|-------------|
| task_id | str | Jira issue key |
| title | str | Task title |
| priority | int | 1-4 |
| git_permission | bool | Git ops allowed |

### task_closed.md.j2
| Variable | Type | Description |
|----------|------|-------------|
| task_id | str | Jira issue key |
| title | str | Task title |
| duration_hours | float | Time from start to close |
| mr_count | int | Associated MRs |
| optimus_queued | bool | Optimus run queued |

### session_end.md.j2
| Variable | Type | Description |
|----------|------|-------------|
| closed | int | Tasks closed today |
| deferred | int | Tasks deferred |
| in_progress | int | Tasks still in progress |
| bottleneck_count | int | Bottlenecks detected |
| step_count | int | Steps executed |
| carry_forward_summary | str | Brief list of carry-over tasks |

### cron_suggestion.md.j2
| Variable | Type | Description |
|----------|------|-------------|
| cron_expression | str | Cron schedule |
| human_readable | str | "Weekdays at 8am" |
| command | str | Command to execute |
| rationale | str | Why this is suggested |
| cron_id | str | ID for approval command |
