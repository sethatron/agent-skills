## [1.0.1] — 2026-04-03
### Fixed
- Jira search endpoint migrated from deprecated POST /rest/api/3/search to GET /rest/api/3/search/jql (jira skill: jira_client.py, jiratui_runner.py)
- MR review pipeline_status always "none" — added single-MR detail fetch in enrich_mr (mr-review skill: mr_review_runner.py)
- dispatch-manager check_env.py now auto-initializes dispatch.db when missing

### Added
- state_store.py task CLI subcommands: list, create, show, start, close, defer, block, unblock, submit, git-allow, abandon (dispatch skill)
- Auto-init dispatch.db schema in check_env.py (dispatch + dispatch-manager skills)
- Stale MR data fallback with [STALE] warning in collect_artifact (dispatch skill: dispatch_runner.py)
- Default search fields in jira_client.py search_jql() for new Jira API endpoint

## [1.0.0] — 2026-04-01
### Added
- Initial dispatch-manager skill scaffolding
- Ecosystem map with four core skills (jira, gitlab-mr-review, dispatch, dispatch-manager)
- Contract registry with three discovered contracts (jira_caller, review_md_frontmatter, artifact_paths)
- DSI compliance checklist (DSI-01 through DSI-10)
- Environment pre-validation (check_env.py)
- DSI compliance validator (dsi_validator.py)
- Contract assertion validator (contract_validator.py)
- Jinja2 templates for new skill generation (check_env, guardrails, step-snippet, artifact-schema)
- Reference documentation (recovery, DSI guide, ecosystem map, contract guide)
- DSI result: COMPLIANT
