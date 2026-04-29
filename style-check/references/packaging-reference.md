# Packaging Reference (seiji-packaging.yaml)

Defines how a repository's deployable components are packaged, deployed, and contacted. Every infrastructure repo has a `seiji-packaging.yaml` at its root.

## Top-Level Schema

From `SeijiPackaging` in `seiji_pkg/models.py`:

```yaml
deployable_packages:
  {artifact.coordinate.name}:
    descriptors: ...
    hooks: ...
    plugins: ...
    files: ...
    contact: ...
    executor: ...
```

`deployable_packages` is a `Dict[str, DeployablePackage]` where keys are dotted artifact coordinates (e.g., `nextgen.base.init`, `nextgen.onyx.deploy`).

## DeployablePackage Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `descriptors` | object | no | Paths to config spec and dependencies files |
| `hooks` | object | no | Paths to lifecycle scripts (defaults provided) |
| `plugins` | object | no | Plugin flags for lightswitch, AMI refresh, etc. |
| `files` | object | yes | Include/exclude patterns for packaging |
| `contact` | object | no | Team contact information |
| `executor` | object | no | Custom Docker execution environment |

## Descriptors

```yaml
descriptors:
  config: "deploy/luna-config-spec.yaml"        # optional
  dependencies: "deploy/luna-dependencies.yaml"  # optional
```

## Hooks

```yaml
hooks:
  create: "deploy/create.sh"        # required (default: deploy/create.sh)
  destroy: "deploy/destroy.sh"      # required (default: deploy/destroy.sh)
  migrate: "deploy/migrations"      # optional
  verify: "deploy/verify.sh"        # optional
```

The `migrate` hook points to a directory containing numbered migration scripts (`001-description`, `002-description`). Seiji runs these in order before `create`.

## Plugins

```yaml
plugins:
  lightswitch_component: ["component-name"]  # list of lightswitch component names
  lightswitch_refresh: true                  # refresh with lightswitch-refresh command
  ami_refresh: true                          # refresh with refresh-amis command
  always_refresh: true                       # always refresh even if tag unchanged
```

All plugin fields are optional.

## Files

```yaml
files:
  include:
    - "terraform/layers/base/init/*.tf"
    - "scripts/terraform/*"
    - ".terraform-version"
  exclude: []   # optional, defaults to []
```

`include` defaults to `["**/*"]` if not specified. Globs are relative to the repo root.

## Contact

```yaml
contact:
  alias: "Team Name"
  email: "team@example.com"
  jira: "DSP"                          # project key or full URL
  slack: "#team-channel"
  git: "https://gitlab.com/org/repo"
```

All contact fields are required when the `contact` block is present. `jira` accepts either a project key (`[A-Z]+`) or a full URL. `slack` must start with `#`.

## Executor

```yaml
executor:
  image: "473376902650.dkr.ecr.us-east-1.amazonaws.com/seiji-orchestrator"
  tag: "latest-terraform1.1.7-py3.10"
  command: "custom-entrypoint.sh"  # optional
```

`image` is required; `tag` and `command` are optional.

## YAML Anchor Pattern

Use a shared anchor to DRY executor config across multiple packages:

```yaml
shared-executor-config: &shared-executor-config
  executor:
    image: "473376902650.dkr.ecr.us-east-1.amazonaws.com/seiji-orchestrator"
    tag: "latest-terraform1.1.7-py3.10"

deployable_packages:
  nextgen.base.init:
    <<: *shared-executor-config
    # ...
  nextgen.network.platform:
    <<: *shared-executor-config
    # ...
```

## Terraform Component Example

From `ng-infrastructure` (`nextgen.base.init`):

```yaml
shared-executor-config: &shared-executor-config
  executor:
    image: "473376902650.dkr.ecr.us-east-1.amazonaws.com/seiji-orchestrator"
    tag: "latest-terraform1.1.7-py3.10"

deployable_packages:
  nextgen.base.init:
    <<: *shared-executor-config
    descriptors:
      config: "terraform/layers/base/init/deploy/luna-config-spec.yaml"
    hooks:
      create: "terraform/layers/base/init/deploy/create.sh"
      destroy: "terraform/layers/base/init/deploy/destroy.sh"
      migrate: "terraform/layers/base/init/deploy/migrations"
    files:
      include:
        - "terraform/layers/base/init/*.tf"
        - "scripts/terraform/*"
        - ".terraform-version"
```

Terraform packages typically include the layer's `.tf` files, the shared `scripts/terraform/*`, and `.terraform-version`.

## Helmsman Component Example

From `onyx-helmsman` (`nextgen.onyx.deploy`):

```yaml
deployable_packages:
  nextgen.onyx.deploy:
    descriptors:
      config: "deploy/luna-config-spec.yaml"
      dependencies: "deploy/luna-dependencies.yaml"
    hooks:
      create: "deploy/create.sh"
      destroy: "deploy/destroy.sh"
      migrate: "deploy/migrations"
    files:
      include:
      - "values"
      - "*.yaml"
      - "*.sh"
      - "desired-state.yaml"
      - "desired-state-workspace.yaml"
      - "deploy/deploy-utils.sh"
      - "local-charts"
      - "deploy/destroy-requirements.txt"
      - "deploy/destroy-fite-slap-credentials.py"
      - "deploy/dsf_helm_cache.py"
      - "deploy/deploy_functions.sh"
```

Helmsman packages include chart directories, values files, desired state files, and helper scripts. No executor block means it uses the orchestrator default.
