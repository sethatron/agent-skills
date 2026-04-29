# Beads Label Taxonomy

Labels use namespaced convention: `<namespace>:<value>`. Every issue must have
at minimum one scope:, one kind:, and one source: label. Stub issues also
require layer: and phase: labels.

## scope -- which skill or component is affected

| Label | Target |
|-------|--------|
| scope:dispatch | /dispatch skill |
| scope:dispatch-manager | /dispatch-manager skill |
| scope:jira | /jira skill |
| scope:mr-review | /gitlab-mr-review skill |
| scope:notebook | /dispatch-notebook skill |
| scope:beads | /beads skill |
| scope:ecosystem | Cross-skill or infrastructure concern |
| scope:optimus | Optimus agent |
| scope:auditor | Beads Auditor agent |

## layer -- what kind of component is affected

| Label | Target |
|-------|--------|
| layer:script | Python script (scripts/*.py) |
| layer:skill-md | SKILL.md definition |
| layer:config | YAML config files |
| layer:contracts | Integration contracts (registry.yaml) |
| layer:agent | Claude Code agent definition |
| layer:workflow | workflow.yaml step definitions |
| layer:db | Database schema or migrations |
| layer:hook | Pre/PostToolUse hooks |

## source -- how the issue was identified

| Label | Origin |
|-------|--------|
| source:optimus | Identified by Optimus nightly analysis |
| source:audit | Identified by Beads Auditor agent |
| source:operator | Created directly by @zettatron |
| source:scaffold | Created during /beads init or skill registration |

## kind -- nature of the work

| Label | Description |
|-------|-------------|
| kind:stub | Needs implementation (was scaffolded as a stub) |
| kind:bug | Something is broken or behaves incorrectly |
| kind:improvement | Makes existing functionality better |
| kind:refactor | Structural change, same external behavior |
| kind:new-feature | Net-new capability |
| kind:debt | Technical debt (coupling, hardcoding, etc.) |
| kind:config | Configuration change only, no code change |
| kind:docs | Documentation or reference file only |

## phase -- implementation progress

| Label | Stage |
|-------|-------|
| phase:stub | Exists as stub, not yet started |
| phase:in-design | Being designed or specified |
| phase:in-progress | Actively being implemented |
| phase:review | Implemented, awaiting validation |
| phase:complete | Done and validated |

## effort -- rough size estimate

| Label | Duration |
|-------|----------|
| effort:xs | Under 1 hour |
| effort:small | 1-4 hours |
| effort:medium | 4-16 hours (one or two sessions) |
| effort:large | More than 16 hours / multi-session |

## Required Label Combinations

| Issue Type | Required Labels |
|-----------|-----------------|
| Any issue | scope:, kind:, source: |
| Stub issue | scope:, kind:stub, source:, layer:, phase:stub |
| Optimus finding | scope:, kind:improvement, source:optimus |
| Audit discovery | scope:, kind:, source:audit |
