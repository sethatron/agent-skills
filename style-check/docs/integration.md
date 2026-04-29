# Integration

## Cross-Skill

### gitlab-mr-review
style-check can be invoked from MR review context using `--diff <branch>`
mode to scan only changed files. Set `STYLE_CHECK_CALLER=gitlab-mr-review`
for JSON-only output.

### dispatch-harness
Quality grades from style-check reports can feed into the dispatch-harness
grading system.

## Artifacts

### Input
- `seiji-packaging.yaml` — component manifest
- `luna-config-spec.yaml` — config specification
- `luna-dependencies.yaml` — dependency declaration
- `deploy/create.sh`, `deploy/destroy.sh` — hook scripts
- `desired-state.yaml` — helmsman state (helmsman components only)
- `.tf` files — Terraform configurations

### Output
- `style-report.md` — YAML frontmatter + findings report
- Generated scaffold files (when using `guide new-component`)

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `STYLE_CHECK_CALLER` | Set by cross-skill callers; forces JSON output |
