# Failure Modes

## Missing seiji-packaging.yaml
**Impact:** Grade F, all packaging/hook/coordinate checks skipped.
**Recovery:** Create the file using `style-check guide new-component`.

## Malformed YAML
**Impact:** Checker crashes on that file; other dimensions still run.
**Recovery:** Fix YAML syntax errors.

## Unknown Coordinate Product
**Impact:** MAJOR finding. Component may work but doesn't follow convention.
**Recovery:** Use a known product prefix (nextgen, secops, luna, kitchen).

## Raw Terraform Resources
**Impact:** CRITICAL findings. Violates module-first architecture.
**Recovery:** Wrap resources in internal modules sourced from GitLab.

## Missing Config Spec
**Impact:** CRITICAL finding. Component won't receive SSM config.
**Recovery:** Create luna-config-spec.yaml with variable definitions.

## Scaffold Template Missing
**Impact:** scaffold_generator fails with FileNotFoundError.
**Recovery:** Ensure templates/scaffolds/ directory is intact.
