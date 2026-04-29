# dispatch-manager Integration


## Ecosystem Map

Managed skills defined in `config/ecosystem.yaml`:

| Skill | Type | Dependencies | Produces |
|-------|------|-------------|----------|
| jira | B | — | jira_export |
| gitlab-mr-review | A | jira | review_md |
| dispatch | A | jira, mr-review | session_yaml, optimus_report |
| dispatch-manager | B | all three | changelog, contract_updates |

Extended skills registered via `/dispatch-manager skill register` are
appended under `extended_skills` in ecosystem.yaml.

Processing order: leaf-first (jira → gitlab-mr-review → dispatch → dispatch-manager).
See `references/ecosystem-map.md` for the full dependency graph.


## New Skill Creation

`/dispatch-manager new skill` runs a six-phase guided interview:

1. **Identity** — slug, name, purpose, description
2. **Integration Type** — A / B / C selection
3. **Dependencies** — caller identification, git permission needs
4. **Artifact Contract** [A/C] — output schema definition
5. **Guardrails** — prohibited/confirmed operations
6. **Trigger Patterns** — command syntax, natural language phrases

After confirmation: generates via /skill-creator, runs DSI validation,
registers in ecosystem.yaml, creates symlink, offers workflow.yaml integration.

See `scripts/skill_author.py` for the full interface.
