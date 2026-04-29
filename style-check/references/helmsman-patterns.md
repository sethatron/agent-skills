# Helmsman Component Patterns

Canonical patterns for Helmsman-based Seiji deployable components, grounded in `onyx-helmsman`.

## desired-state.yaml

The Helmsman desired state file defines which Helm charts to deploy. Structure:

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
  onyx-mongodb-snapshots:
    name: onyx-mongodb-snapshots
    group: onyx
    description: "Temporary monitoring for all mongodb clusters"
    chart: local-charts/mongodb-snapshots
    version: "0.0.1"
    namespace: onyx-mongodb
    enabled: true
    wait: true
    timeout: 600
    valuesFiles:
      - values/mongodb-snapshots-values.yaml

  onyx-mongodb-monitoring:
    name: onyx-mongodb-monitoring
    group: onyx
    chart: local-charts/mongodb-monitoring
    version: "0.0.1"
    namespace: onyx-mongodb
    enabled: true
    wait: true
    timeout: 600
    priority: -60
    valuesFiles:
      - values/mongodb-monitoring-values.yaml
```

### App Definition Fields

| Field | Description |
|---|---|
| `name` | Release name in the cluster |
| `group` | Logical grouping for selective deployment via `-group` flag |
| `chart` | Chart source: `local-charts/...`, `abacus/...`, `bitnami/...`, or `dapr/...` |
| `version` | Chart version |
| `namespace` | Target Kubernetes namespace |
| `enabled` | Whether to deploy this app |
| `wait` | Wait for pods to be ready |
| `timeout` | Timeout in seconds |
| `valuesFiles` | List of values files to merge |
| `priority` | Deployment order (lower = earlier, negative values deploy first) |

### Chart Sources

- `abacus` - S3-backed Helm repo at `s3://abacus-artifacts-kitchen/helm`
- `bitnami` - Public Bitnami charts
- `dapr` - Dapr runtime charts
- `local-charts/` - Charts vendored in the repository

## deploy_functions.sh

Source: `deploy/deploy_functions.sh` (64 lines). Two functions.

### update_kubeconfig()

```bash
function update_kubeconfig {
  local kubeconfig_path=${1:-/tmp/${LABEL}.kubeconfig}
  aws eks update-kubeconfig --name "${LABEL}" --kubeconfig "${kubeconfig_path}"
  chmod go-r "${kubeconfig_path}"
}
```

### run_helmsman_isolated()

Creates a fully isolated temp workspace per helmsman invocation to prevent collisions during parallel runs:

```bash
function run_helmsman_isolated {
  local component=$1
  local workspace_scope=$2
  shift 2

  local seiji_tmp_root=${SEIJI_TMP_ROOT:-/tmp/seiji-tmp}
  local run_id=${SEIJI_RUN_ID:-$(date +%s)}
  local worker_root="${seiji_tmp_root}/${LABEL}/${component}/${workspace_scope}/${run_id}-$$"
  local current_workdir
  current_workdir="$(pwd)"
  local worker_workdir="${worker_root}/workdir"

  mkdir -p "${worker_root}/tmp" \
           "${worker_root}/helm-cache" \
           "${worker_root}/helm-config" \
           "${worker_workdir}" \
           "${worker_root}/logs"

  local entry
  shopt -s dotglob nullglob
  for entry in "${current_workdir}"/*; do
    local base
    base="$(basename "${entry}")"
    if [[ "${base}" == ".helmsman-tmp" ]]; then
      continue
    fi
    ln -s "${entry}" "${worker_workdir}/${base}"
  done
  shopt -u dotglob nullglob

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

  if [[ "${SEIJI_KEEP_TMP:-0}" != "1" ]]; then
    rm -rf "${worker_root}"
  fi
}
```

Isolation strategy:
- Separate `KUBECONFIG` per run
- Separate `HELM_CACHE_HOME` and `HELM_CONFIG_HOME`
- Separate `TMPDIR` (helmsman writes `.helmsman-tmp` here)
- Symlinks source files from the real workdir, skipping `.helmsman-tmp`
- Cleanup after run unless `SEIJI_KEEP_TMP=1`

## create.sh Pattern

Source: `deploy/create.sh`. Structure:

```bash
#!/bin/bash
set -euE -o pipefail

export AWS_RETRY_MODE=adaptive
export AWS_MAX_ATTEMPTS=10

source "$(dirname "${BASH_SOURCE[0]}")/deploy_functions.sh"

update_kubeconfig
export KUBECONFIG=/tmp/${LABEL}.kubeconfig
export ACCOUNT_ID=$(aws sts get-caller-identity --query "Account" --output text)

# Export SSM parameters needed by Helm values
export ADMIN_CIDRS=$(aws ssm get-parameter ... --name /${LABEL}/config/_/admin_cidrs/json | jq -r 'join(",")')
```

Then the core deployment flow:

1. **Airflow helm caching** (when `AIRFLOW_DEPLOYMENT=1`):
   ```bash
   helm repo update abacus
   python deploy/dsf_helm_cache.py "$desired_state_file_name" "$helm_version"
   ```
   Rewrites chart references in `desired-state.yaml` to use cached paths, avoiding registry lookups during Airflow runs.

2. **Global (non-workspace) helmsman run**:
   ```bash
   run_helmsman_isolated "onyx" "_" \
       -apply                        \
       -f desired-state.yaml         \
       -group onyx                   \
       --always-upgrade              \
       --subst-env-values            \
       --subst-ssm-values            \
       --verbose                     \
       --p 5                         \
       --migrate-context             \
       ${no_update:-}
   ```

3. **Per-workspace parallel loop**:
   ```bash
   for workspace in ${onyx_enabled_workspaces[@]:-}; do
   (
     export WORKSPACE=$workspace
     # fetch workspace-specific SSM params, secrets, passwords
     # ...
     run_helmsman_isolated "onyx" "${workspace}" \
         -apply \
         -f desired-state-workspace.yaml \
         -group "onyx-workspace-${workspace}" \
         --always-upgrade --subst-env-values --subst-ssm-values \
         --verbose --p 5 --migrate-context ${no_update:-}
   ) &
   workspace_batch_pids+=($!)
   ```
   Parallelism is bounded by `MAX_WORKSPACE_PARALLEL` (default 3 locally, full fan-out in Airflow).

### Helmsman Flags

| Flag | Purpose |
|---|---|
| `-apply` | Apply the desired state |
| `-destroy` | Destroy releases in the group |
| `-f desired-state.yaml` | Desired state file |
| `-group {component}-${WORKSPACE}` | Scope to a logical group |
| `--always-upgrade` | Upgrade even if version unchanged |
| `--subst-env-values` | Substitute `$ENV_VAR` in values files |
| `--subst-ssm-values` | Substitute `{{ssm /path}}` in values files |
| `--migrate-context` | Handle kubeconfig context renames |
| `--p 5` | Parallelism: deploy up to 5 charts concurrently |
| `-no-update` | Skip `helm repo update` (used in Airflow after explicit cache) |
| `--verbose` | Extended logging |

## Workspace Isolation

Each workspace gets its own helmsman invocation scoped by `-group`. The `run_helmsman_isolated` function ensures no filesystem or kubeconfig collisions between parallel workspace deployments. Workspace-specific desired state uses `desired-state-workspace.yaml`.

## seiji-packaging.yaml

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
      - "deploy/dsf_helm_cache.py"
      - "deploy/deploy_functions.sh"
```

Helmsman components include chart directories (`local-charts`), values files (`values`), desired state files, and deploy scripts in their packaging.
