---
name: style-check
version: "1.0.0"
dsi_type: "A"
description: >-
  Seiji component standards validator and new-component scaffold generator.
  Use when user says "/style-check", "validate component", "check component standards",
  "new seiji component", "create a new component", "check packaging", "validate seiji",
  "does this follow the pattern", "component compliance", "scaffold a component",
  "style check", "standards check". Also trigger on: "does this match existing patterns",
  "check the coordinate", "validate the config spec", "check terraform compliance",
  "is this packaged correctly".
docs:
  architecture: docs/architecture.md
  integration: docs/integration.md
  failure_modes: docs/failure-modes.md
  quality: docs/quality.md
---

# Seiji Component Standards

Validates Abacus seiji components against established platform patterns and
generates scaffolds for new components.

## Guardrails

- Analysis is read-only: no modifications to existing files
- Scaffold generation writes to a user-specified output directory only
- No git operations
- No API calls — purely local file analysis
- When `STYLE_CHECK_CALLER` != operator, JSON output only
- Does NOT enforce code style (black, linting) — that's separate tooling

## Environment Pre-Validation

```bash
python scripts/check_env.py [--verbose]
```

Validates: Python 3.10+, pyyaml, jinja2, git binary.

## Subcommands

| Command | Description |
|---------|-------------|
| `/style-check` | Full scan of current repo against all dimensions |
| `/style-check --path <dir>` | Scan specific directory |
| `/style-check --diff <branch>` | Scan only changed files (MR mode) |
| `/style-check guide new-component` | Interactive: scaffold a new seiji component |
| `/style-check guide terraform` | Terraform layer creation guide with scaffold |
| `/style-check guide helmsman` | Helmsman deployment guide with scaffold |

## Check Dimensions

1. **Coordinate** — format, known products/operations, registry lookup
2. **Packaging** — seiji-packaging.yaml schema, hooks, descriptors, executor
3. **Config Spec** — luna-config-spec.yaml schema, variable types, tfvar alignment
4. **Dependencies** — luna-dependencies.yaml schema, coordinate cross-references
5. **Deploy Hooks** — create.sh/destroy.sh existence, deploy_functions.sh sourcing
6. **Terraform** — no raw `resource "aws_*"`, module enforcement, output descriptions
7. **Helmsman** — desired-state.yaml structure, app fields, chart sources
8. **Manifest** — version anchor naming, integration readiness

## Scaffold Generation

When invoked with `guide new-component`, prompts for:
- Coordinate (e.g., `nextgen.newsystem.provision`)
- Type: Terraform or Helmsman
- Dependencies (existing coordinates)
- Config variables

Then generates a complete starter component with all required files
pre-filled from canonical templates.

## References

- `references/seiji-component-anatomy.md` — what makes a valid component
- `references/coordinate-registry.md` — all 96 known coordinates
- `references/terraform-patterns.md` — deploy_functions.sh, create.sh
- `references/helmsman-patterns.md` — desired-state.yaml, run_helmsman_isolated
- `references/config-spec-reference.md` — luna-config-spec.yaml schema
- `references/packaging-reference.md` — seiji-packaging.yaml schema
- `references/new-component-checklist.md` — step-by-step creation guide
