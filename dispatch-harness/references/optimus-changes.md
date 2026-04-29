# Optimus Changes for dispatch-harness

These changes apply to `~/.claude/agents/optimus.md`.

## Telemetry Digest Context Injection

Add the following block immediately AFTER the `## Your Role` heading and BEFORE
the existing role description text:

```markdown
## Telemetry Context

Before beginning analysis, check for a telemetry digest:

```bash
ls -t ~/.zsh/dispatch/harness/telemetry/*-digest.md 2>/dev/null | head -1
```

If a digest exists, read the most recent one first. Ground your findings in this
operational data — it contains step performance stats, fragility rankings, drift
events, and context window metrics from the past 7 sessions.

If no digest exists, note "No telemetry digest available" and continue with your
standard analysis. Do not treat the absence as an error.
```

## Exact Insertion Point

File: `~/.claude/agents/optimus.md`

Insert AFTER line 17 (`## Your Role`) and BEFORE line 19 (`Perform a critical...`).

The resulting structure should be:

```
## Your Role
## Telemetry Context
<new block>
Perform a critical, data-driven analysis of:
```
