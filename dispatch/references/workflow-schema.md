# Workflow YAML Schema Reference

## Top-Level Fields

```yaml
version: "1.0"                    # Schema version (required)

operator:
  gitlab_username: "@username"    # GitLab username for MR filtering
  jira_username: "email@co.com"   # Jira username/email
  slack_channel: "#channel"       # Display name
  slack_channel_id: "C0..."       # Slack API channel ID
  timezone: "America/Phoenix"     # IANA timezone

defaults:
  git_permission: false           # Default git permission for new tasks
  require_human_gate: true        # Pause at human gates
  slack_notify_on: [...]          # Event types that trigger notifications
```

## Step Schema

```yaml
steps:
  - id: unique_step_id            # String, unique within workflow
    name: "Human-Readable Name"   # Display name
    skill: /skill-name            # Sub-skill to invoke (mutually exclusive with runner)
    runner: scripts/script.py     # Python script to run (mutually exclusive with skill)
    args: "arguments"             # Arguments for skill or script
    description: "What this does" # Human description
    on_blocker: notify_slack      # Event handler
    timeout_minutes: 30           # Max duration before timeout
    tags: [tag1, tag2]            # For filtering and grouping
    enabled: true                 # Toggle without removing
    blocking: false               # If true, workflow stops on failure
```

## Human Gates

```yaml
human_gates:
  - after: step_id                # Step that must complete first
    message: "Prompt text"        # Message shown to operator
```

## Schedule

```yaml
schedule:
  job_name:
    cron: "0 8 * * 1-5"          # Standard cron expression
    command: "script.py --args"   # Command to execute
    approval_required: true       # Requires /dispatch cron approve
    approved: false               # Set true after approval
```

## Extensibility

- Adding a step: add an entry to `steps:`. No SKILL.md changes needed.
- Adding a notification template: add a `.j2` file to `templates/slack/`.
- Adding a bottleneck condition: add to `scripts/bottleneck_detector.py`.
