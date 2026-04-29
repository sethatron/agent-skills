# Quality

## Compliance Grades

| Grade | Criteria |
|-------|----------|
| A | 0 critical, 0 major findings |
| B | 0 critical, 1-2 major findings |
| C | 0 critical, 3+ major findings |
| D | 1+ critical findings |
| F | 5+ critical findings or missing seiji-packaging.yaml |

## Check Dimensions

| Dimension | Scripts | Weight |
|-----------|---------|--------|
| Coordinate | coordinate_checker.py | Core |
| Packaging | packaging_checker.py | Core |
| Config Spec | config_spec_checker.py | Core |
| Dependencies | dependency_checker.py | Core |
| Deploy Hooks | deploy_hook_checker.py | Core |
| Terraform | terraform_checker.py | Type-specific |
| Helmsman | helmsman_checker.py | Type-specific |
| Manifest | manifest_checker.py | Advisory |

## Severity Levels

- **CRITICAL** — must fix before deployment (missing required files, raw resources)
- **MAJOR** — should fix (wrong patterns, missing descriptions)
- **MINOR** — nice to have (tfvar alignment, cosmetic)
- **SUGGESTION** — informational (manifest integration tips)
