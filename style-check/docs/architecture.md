# Architecture

## Overview

style-check validates Abacus seiji components against established platform
patterns and generates scaffolds for new components. It operates purely on
local files with no API calls.

## Components

### Checkers (scripts/)
Eight independent checker modules, each returning a list of findings:
- `coordinate_checker` — validates coordinate format against registry
- `packaging_checker` — validates seiji-packaging.yaml schema
- `config_spec_checker` — validates luna-config-spec.yaml schema
- `dependency_checker` — validates luna-dependencies.yaml
- `deploy_hook_checker` — validates create.sh/destroy.sh patterns
- `terraform_checker` — enforces module usage, variable naming
- `helmsman_checker` — validates desired-state.yaml structure
- `manifest_checker` — checks manifest integration readiness

### Report Writer
Consumes findings from all checkers, computes an A-F compliance grade,
renders a markdown report via Jinja2.

### Scaffold Generator
Generates complete starter components from Jinja2 templates in
`templates/scaffolds/`. Supports terraform and helmsman types.

### References
Seven reference documents extracted from real Abacus repos providing
canonical patterns, schemas, and step-by-step guides.

## Data Flow

```
repo path -> checkers (parallel) -> findings list -> report_writer -> markdown report
user input -> scaffold_generator -> jinja2 templates -> output directory
```

## Configuration
All rules in `config/standards.yaml`. Known coordinates in
`references/coordinate-registry.md`.
