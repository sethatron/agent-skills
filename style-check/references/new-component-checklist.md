# New Component Checklist

Step-by-step guide for creating a new seiji component from scratch.

## 1. Choose Coordinate and Type

Pick a coordinate following the `{product}.{subsystem}.{operation}` pattern:
- **Terraform** -- infrastructure provisioning, configurations, permissions, networking. Operations: `provision`, `init`, `configurations`, `tokens`, `permissions`, etc.
- **Helmsman** -- Kubernetes service deployments via Helm. Operation: `deploy`.

Example: `nextgen.myservice.provision` (Terraform) or `nextgen.myservice.deploy` (Helmsman).

## 2. Create Directory Structure

### Terraform
```bash
mkdir -p terraform/layers/myservice/provision/deploy
mkdir -p terraform/layers/myservice/provision/deploy/migrations
```

### Helmsman
```bash
mkdir -p deploy deploy/migrations local-charts values
```

## 3. Write seiji-packaging.yaml

### Terraform Example
```yaml
shared-executor-config: &shared-executor-config
  executor:
    image: "473376902650.dkr.ecr.us-east-1.amazonaws.com/seiji-orchestrator"
    tag: "latest-terraform1.1.7-py3.10"

deployable_packages:
  nextgen.myservice.provision:
    <<: *shared-executor-config
    descriptors:
      config: "terraform/layers/myservice/provision/deploy/luna-config-spec.yaml"
      dependencies: "terraform/layers/myservice/provision/deploy/luna-dependencies.yaml"
    hooks:
      create: "terraform/layers/myservice/provision/deploy/create.sh"
      destroy: "terraform/layers/myservice/provision/deploy/destroy.sh"
      migrate: "terraform/layers/myservice/provision/deploy/migrations"
    files:
      include:
        - "terraform/layers/myservice/provision/*.tf"
        - "terraform/layers/myservice/provision/deploy/*.sh"
        - "terraform/layers/myservice/provision/deploy/*.yaml"
        - "scripts/terraform/*"
        - ".terraform-version"
```

### Helmsman Example
```yaml
deployable_packages:
  nextgen.myservice.deploy:
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
        - "local-charts"
        - "deploy/deploy_functions.sh"
```

## 4. Write luna-config-spec.yaml

Config variables live under two scopes:
- `config._` -- globals shared across all components (e.g., `workspaces`, `admin_cidrs`)
- `config.{coordinate}` -- component-specific variables

Each variable has: `default`, `description`, `type` (`str`, `bool`, `list`, `map`, `int`), `required`, `tfvar` (Terraform only).

```yaml
config:
  _:
    workspaces:
      default: []
      description: "List of active workspaces in this environment."
      type: list
      required: true
      tfvar: true
  nextgen.myservice.provision:
    instance_type:
      default: "m5.large"
      description: "EC2 instance type for the service."
      type: str
      required: false
      tfvar: true
    replica_count:
      default: 2
      description: "Number of replicas to deploy."
      type: int
      required: false
      tfvar: true
    feature_enabled:
      default: false
      description: "Enable the experimental feature."
      type: bool
      required: false
      tfvar: true
```

## 5. Write luna-dependencies.yaml

Declare which components must be deployed before this one, with semver constraints:

```yaml
dependencies:
  nextgen.base.init: ">=22.12.0"
  nextgen.eks.provision: ">=24.1.0"
  nextgen.network.platform: ">=23.6.0"
```

## 6. Write create.sh

### Terraform Pattern (canonical)

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

For workspace-scoped Terraform layers (need per-workspace template expansion), add before `init_terraform`:

```bash
templates=$(find . -name '*.tmpl' | xargs -I {} basename {})
workspaces=$(aws ssm get-parameter --name /${LABEL}/config/_/workspaces/json --output text --query Parameter.Value | jq -r '.[]')

for workspace in ${workspaces[@]}; do
  for template in ${templates[@]}; do
    dest_filename="$(echo "${template%.tmpl}")_$workspace.tf"
    sed "s/<WORKSPACE>/$workspace/g" $template > $dest_filename
  done
done
```

### Helmsman Pattern

```bash
#!/bin/bash
set -euE -o pipefail

export AWS_RETRY_MODE=adaptive
export AWS_MAX_ATTEMPTS=10

source "$(dirname "${BASH_SOURCE[0]}")/deploy_functions.sh"

update_kubeconfig

export KUBECONFIG=/tmp/${LABEL}.kubeconfig
export ACCOUNT_ID=$(aws sts get-caller-identity --query "Account" --output text)

run_helmsman_isolated "myservice" "_" \
  --apply \
  --subst-env-values \
  --subst-ssm-values \
  --always-upgrade \
  --migrate-context \
  -f desired-state.yaml \
  -group myservice
```

## 7. Write deploy_functions.sh (Helmsman only)

For Terraform components, the shared `scripts/terraform/deploy_functions.sh` already exists in ng-infrastructure.

For Helmsman, create `deploy/deploy_functions.sh` with at minimum:

```bash
#!/bin/bash
set -euo pipefail

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

  shopt -s dotglob nullglob
  for entry in "$(pwd)"/*; do
    local base="$(basename "${entry}")"
    [[ "${base}" == ".helmsman-tmp" ]] && continue
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

  [[ "${SEIJI_KEEP_TMP:-0}" != "1" ]] && rm -rf "${worker_root}"
}
```

## 8. Write destroy.sh

### Terraform
```bash
#!/bin/bash
set -euE -o pipefail

source scripts/terraform/deploy_functions.sh
cd $(dirname $(dirname ${BASH_SOURCE[0]}))

init_terraform

if echo $* | grep -e "--auto-approve"; then
  terraform destroy --auto-approve
else
  terraform destroy
fi
```

### Helmsman
Mirrors `create.sh` but passes `--destroy` to helmsman instead of `--apply`. May also need cleanup scripts for CRDs or persistent resources.

## 9. Write desired-state.yaml (Helmsman only)

```yaml
metadata:
  description: My Service Helm Deployment

context: myservice

helmRepos:
  abacus: s3://abacus-artifacts-kitchen/helm
  bitnami: https://charts.bitnami.com/bitnami

namespaces:
  myservice:

apps:
  myservice-app:
    name: myservice-app
    group: myservice
    description: "Main application deployment"
    chart: abacus/myservice
    version: "${HELM_SEMVER}"
    namespace: myservice
    enabled: true
    wait: true
    timeout: 600
    valuesFiles:
      - values/myservice-values.yaml
    set:
      image.tag: "${SEIJI_COMPONENT_VERSION}"
```

For workspace-scoped deployments, create `desired-state-workspace.yaml` and invoke helmsman per workspace with `-group myservice-${WORKSPACE}`.

## 10. Add to ng-deployment-config-files

### Version Anchor

Add at the top of `manifests/default-manifest.yaml`:

```yaml
myservice-version: &myservice-version "1.0.0"
```

### Deployable Entry

Add under `deployables:`:

```yaml
  nextgen.myservice.provision:
    <<: *shared-vars
    version: *myservice-version

  nextgen.myservice.deploy:
    <<: *shared-vars
    version: *myservice-version
```

### Tenant Overrides

If specific tenants need different versions or `exists: false`, add entries in the tenant-specific manifest overlays (e.g., `manifests/tenants/{tenant}.yaml`).

## 11. Validate

Run the manifest verifier:

```bash
bin/verify_manifest
```

This checks that all coordinates referenced in the manifest have corresponding `seiji-packaging.yaml` entries and that version anchors resolve.

## 12. Test Locally

```bash
seiji deployer run --target nextgen.myservice.provision --executor native
```

This runs the component's `create.sh` hook locally using your current AWS credentials and environment variables. Set `LABEL` to your target environment label first:

```bash
export LABEL=myenv
seiji deployer run --target nextgen.myservice.provision --executor native
```
