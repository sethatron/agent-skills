# study.yaml Schema Reference

Each topic directory contains a `study.yaml` that configures the topic.

## Required Fields

```yaml
name: "Human-readable topic name"
description: "One-line description of what the topic covers"
type: domain | project | certification
created: "YYYY-MM-DD"
```

### type

| Value | Use Case |
|---|---|
| `domain` | General knowledge area (DevOps, networking, etc.) |
| `project` | Generated from a specific codebase |
| `certification` | Targeted at a specific cert (CKA, AWS SAA, etc.) |

## Optional Fields

### skill

Specifies which study engine to use. Falls back to `config.yaml` → `defaults.skill_source` if omitted.

```yaml
skill:
  source: /absolute/path/to/study-skill
```

### source

For project-type topics, links back to the original codebase.

```yaml
source:
  path: /absolute/path/to/project
  type: go | python | typescript | rust | java | docs
```

### goals

Learning objectives for the topic.

```yaml
goals:
  - "Understand the reconciliation loop architecture"
  - "Be able to extend the plugin system"
```

### resources

External references the user can consult.

```yaml
resources:
  - name: "Resource Name"
    path: /absolute/path/to/resource
```

### tags

Freeform tags for filtering and discovery.

```yaml
tags: [go, kubernetes, controllers, grpc]
```

## Conventions (not configured)

These paths are derived by convention, not declared in study.yaml:

| Resource | Convention |
|---|---|
| Knowledge base | `knowledge-base.yaml` in the same directory as `study.yaml` |
| Stats script | `{skill.source}/scripts/kb-stats.py` |
| DAG script | `{skill.source}/scripts/kb-dag.py` |
| Skill references | `{skill.source}/references/` |

## Future Fields (not yet implemented)

### milestones

Measurable checkpoints with target levels and topic filters.

```yaml
milestones:
  - name: "Core Architecture"
    description: "Understand all foundational components"
    target_level: conceptual
    target_topics_filter:
      tags: [core, architecture]
```

### cross_references

Connections to other study-buddy topics with shared concepts.

```yaml
cross_references:
  - topic: devops
    shared_concepts: ["Kubernetes RBAC", "Service mesh"]
```

## Full Example

```yaml
name: "Archon Framework"
description: "AI agent orchestration framework built with Python, FastAPI, and Pydantic AI"
type: project
created: "2026-03-05"

skill:
  source: /Users/sethallen/agent-skills/study

source:
  path: /Users/sethallen/DSP/SEIJIV2/Archon/archon
  type: python

goals:
  - "Understand the agent orchestration architecture"
  - "Be able to extend Archon with new agent types"
  - "Deep knowledge of the MCP tool integration layer"

resources:
  - name: "Archon README"
    path: /Users/sethallen/DSP/SEIJIV2/Archon/archon/README.md

tags: [python, fastapi, ai-agents, pydantic, mcp]
```
