# Seiji Component Anatomy

## What is a seiji component?

A deployable unit in the Abacus NextGen platform, identified by a coordinate (e.g., `nextgen.onyx.deploy`), packaged via `seiji-packaging.yaml`, configured via `luna-config-spec.yaml`, with dependencies declared in `luna-dependencies.yaml`, and deployed via hook scripts (`create.sh`, `destroy.sh`).

## Two Component Types

### Terraform Components

Coordinates typically end in `.provision`, `.init`, `.configurations`, `.tokens`, `.permissions`, `.platform`, `.irsa`, `.common`, `.bridge`, `.proxy`, `.outbound`, `.policies`, `.roles`, or other non-`.deploy` suffixes.

#### Directory Layout

```
repo/
├── terraform/
│   ├── layers/{domain}/{function}/
│   │   ├── *.tf
│   │   └── deploy/
│   │       ├── create.sh                 # Usually symlink to scripts/terraform/create.sh
│   │       ├── destroy.sh
│   │       ├── luna-config-spec.yaml
│   │       ├── luna-dependencies.yaml
│   │       └── migrations/               # Optional numbered migration scripts
│   └── modules/                          # Reusable TF modules
├── scripts/
│   └── terraform/
│       ├── create.sh                     # Canonical entry point
│       └── deploy_functions.sh           # Core: init_terraform(), generate_backend_tfvars()
├── seiji-packaging.yaml
└── .terraform-version
```

#### Key Patterns

`create.sh` sources `deploy_functions.sh`, calls `init_terraform`, then runs `terraform apply`:

```bash
#!/bin/bash
set -euE -o pipefail

source scripts/terraform/deploy_functions.sh
cd $(dirname $(dirname ${BASH_SOURCE[0]}))

check_mac_version
check_sha256sum_available

init_terraform

if echo $* | grep -e "--auto-approve"; then
  terraform apply --auto-approve
else
  terraform apply
fi
```

`init_terraform()` performs:
1. Installs terraform via `tfenv install`
2. Sets up plugin cache at `$HOME/.terraform.d/plugin-cache`
3. Calls `generate_backend_tfvars` to create `backend.tfvars` with S3 state bucket (`abacus-tfstate-{account_id}`) and DynamoDB lock table
4. Initializes providers (Databricks, Snowflake) as needed
5. Runs `terraform init -upgrade -reconfigure -backend-config=backend.tfvars`
6. Selects workspace `${aws_account_id}::${LABEL}`
7. Calls `seiji config generate tfvars --spec-path deploy/luna-config-spec.yaml`

`destroy.sh` follows the same pattern but calls `terraform destroy` instead of `terraform apply`.

Executor image: `473376902650.dkr.ecr.us-east-1.amazonaws.com/seiji-orchestrator:latest-terraform1.1.7-py3.10`

#### Real Example: ng-infrastructure `nextgen.base.init`

From `seiji-packaging.yaml`:
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

From `luna-config-spec.yaml` (globals under `config._`):
```yaml
config:
  _:
    admin_cidrs:
      default:
        - "20.185.17.149/32"
        - "40.87.14.255/32"
      description: "Known-trusted CIDRs which will be able to access the k8s control plane, S3 buckets, and other resources."
      required: false
      tfvar: true
      type: list
    admin_unfiltered_cidrs:
      default: []
      description: "Known-trusted CIDRs which will not be subject to WAF rules."
      required: false
      tfvar: true
      type: list
```

From `luna-dependencies.yaml` (e.g., `nextgen.network.platform`):
```yaml
dependencies:
  nextgen.base.init: ">=22.12.0"
```

---

### Helmsman Components

Coordinates end in `.deploy`.

#### Directory Layout

```
repo/
├── deploy/
│   ├── create.sh                         # Sources deploy_functions.sh, runs helmsman
│   ├── destroy.sh
│   ├── deploy_functions.sh               # update_kubeconfig(), run_helmsman_isolated()
│   ├── luna-config-spec.yaml
│   ├── luna-dependencies.yaml
│   └── migrations/
├── local-charts/                         # Custom Helm charts
│   └── {chart-name}/
├── values/                               # Helm values files
│   └── {chart-name}-values.yaml
├── desired-state.yaml                    # Helmsman state file
├── desired-state-workspace.yaml          # Workspace-scoped variant
├── seiji-packaging.yaml
└── dsf_helm_cache.py                     # Optional: helm cache for Airflow deployments
```

#### Key Patterns

`deploy_functions.sh` provides two core functions:

```bash
function update_kubeconfig {
  local kubeconfig_path=${1:-/tmp/${LABEL}.kubeconfig}
  aws eks update-kubeconfig --name "${LABEL}" --kubeconfig "${kubeconfig_path}"
  chmod go-r "${kubeconfig_path}"
}

function run_helmsman_isolated {
  local component=$1
  local workspace_scope=$2
  shift 2

  local seiji_tmp_root=${SEIJI_TMP_ROOT:-/tmp/seiji-tmp}
  local run_id=${SEIJI_RUN_ID:-$(date +%s)}
  local worker_root="${seiji_tmp_root}/${LABEL}/${component}/${workspace_scope}/${run_id}-$$"
  local worker_workdir="${worker_root}/workdir"

  mkdir -p "${worker_root}/tmp" \
           "${worker_root}/helm-cache" \
           "${worker_root}/helm-config" \
           "${worker_workdir}" \
           "${worker_root}/logs"

  # Symlink everything except .helmsman-tmp for isolation
  for entry in "$(pwd)"/*; do
    local base="$(basename "${entry}")"
    [[ "${base}" == ".helmsman-tmp" ]] && continue
    ln -s "${entry}" "${worker_workdir}/${base}"
  done

  local kubeconfig_path="${worker_root}/kubeconfig"
  update_kubeconfig "${kubeconfig_path}"

  (
    export KUBECONFIG="${kubeconfig_path}"
    export TMPDIR="${worker_root}/tmp"
    export HELM_CACHE_HOME="${worker_root}/helm-cache"
    export HELM_CONFIG_HOME="${worker_root}/helm-config"
    cd "${worker_workdir}"
    helmsman "$@"
  )

  [[ "${SEIJI_KEEP_TMP:-0}" != "1" ]] && rm -rf "${worker_root}"
}
```

`create.sh` calls `run_helmsman_isolated` with flags like `--subst-env-values`, `--subst-ssm-values`, `--always-upgrade`, `--migrate-context`.

Workspace-scoped deployments invoke helmsman once per workspace with `-group {component}-${WORKSPACE}`.

Charts sourced from:
- `abacus` S3 repo: `s3://abacus-artifacts-kitchen/helm`
- `bitnami`: `https://charts.bitnami.com/bitnami`
- `local-charts/` directory

#### Real Example: onyx-helmsman `nextgen.onyx.deploy`

From `seiji-packaging.yaml`:
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

From `luna-config-spec.yaml`:
```yaml
config:
  _:
    epa_enabled_workspaces:
      default: []
      description: "Workspaces to enable epa (electronic prior authorization)"
      type: list
      required: true
      tfvar: false
  nextgen.onyx.deploy:
    access_logs_enabled:
      default: true
      description: "Enables access logging for the external FITE and SLAP load balancers."
      type: bool
      required: false
      tfvar: true
```

From `luna-dependencies.yaml`:
```yaml
dependencies:
  nextgen.onyx.provision: ">=23.11.1"
  nextgen.onyx.slap: ">=23.11.3"
  nextgen.onyx.fite: ">=23.11.3"
  nextgen.onyx.storage: ">=23.11.3"
  nextgen.onyx.cdn: ">=23.11.3"
  nextgen.onyx.databricks_secrets: ">=23.11.3"
  nextgen.onyx.insights: ">=23.11.3"
  nextgen.onyx.healthlake: ">=23.11.3"
  nextgen.onyx.epa: ">=26.1.5"
  nextgen.onyx.payer: ">=23.11.1"
```

From `desired-state.yaml`:
```yaml
metadata:
  description: Onyx Helm Chart

context: onyx

helmRepos:
  bitnami: https://charts.bitnami.com/bitnami
  abacus: s3://abacus-artifacts-kitchen/helm
  dapr: https://dapr.github.io/helm-charts

namespaces:
  onyx-mongodb:
  dapr-system:

apps:
  onyx-mongodb:
    name: onyx-mongodb
    group: onyx
    description: "Bitnami Mongodb chart"
    chart: bitnami/mongodb
    version: "13.6.4"
    namespace: onyx-mongodb
    enabled: true
    wait: true
    timeout: 600
    valuesFiles:
      - values/mongodb-values.yaml
```

---

## Required Files for ALL Components

| File | Purpose |
|------|---------|
| `seiji-packaging.yaml` | Declares coordinate, executor, hooks, descriptors, files to include |
| `luna-config-spec.yaml` | Defines config variables with types, defaults, descriptions |
| `luna-dependencies.yaml` | Declares dependency coordinates with version constraints |
| `create.sh` | Deployment hook (entry point for `seiji deployer run`) |
| `destroy.sh` | Teardown hook |

## Coordinate Naming

Format: `{product}.{subsystem}.{operation}` -- dot-separated, lowercase, underscores allowed in subsystem names.

Products: `nextgen`, `secops`, `luna`, `kitchen`.

## SSM Parameter Paths

- Config: `/${LABEL}/config/{component}/{variable}`
- Secrets: `/${LABEL}/secrets/{component}/{variable}`
- Global config (shared across components): `/${LABEL}/config/_/{variable}`

## Manifest Integration

Each component gets a version anchor in `ng-deployment-config-files/manifests/default-manifest.yaml`:

```yaml
onyx-helmsman-version: &onyx-helmsman-version "26.4.4rc2"

deployables:
  nextgen.onyx.deploy:
    <<: *shared-vars
    version: *onyx-helmsman-version
```

The `shared-vars` anchor provides the common `package.protocol: spack` and `exists: true` fields.
