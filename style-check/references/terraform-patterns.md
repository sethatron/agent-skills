# Terraform Component Patterns

Canonical patterns for Terraform-based Seiji deployable components, grounded in `ng-infrastructure`.

## Layer Organization

Terraform layers live under `terraform/layers/{domain}/{function}/deploy/`:

```
terraform/layers/
  base/init/
  network/platform/
  payment_integrity/provision/
  payment_integrity/deploy/
  onyx/provision/
  databricks/provision/
```

Each layer directory contains `.tf` files at the top level with a `deploy/` subdirectory holding `create.sh`, `destroy.sh`, `luna-config-spec.yaml`, `luna-dependencies.yaml`, and optionally a `migrations/` directory.

## deploy_functions.sh

Source: `scripts/terraform/deploy_functions.sh` (361 lines). Shared library sourced by every Terraform component's `create.sh` and `destroy.sh`.

### init_terraform()

The primary entry point. Installs Terraform via `tfenv`, configures backend, initializes providers, and generates tfvars from config spec.

```bash
function init_terraform() {
  if ! which tfenv > /dev/null; then
    echo '[ERROR] Please install `tfenv` to continue.'
    exit 1
  fi

  local aws_region=$(aws ec2 describe-availability-zones --output text --query 'AvailabilityZones[0].[RegionName]')
  local aws_account_id=$(aws sts get-caller-identity --output text --query Account)
  local airflow_deployment=${AIRFLOW_DEPLOYMENT:=0}

  if [[ ! $AIRFLOW_DEPLOYMENT == "1" ]]; then
    tfenv install
  fi

  export TF_PLUGIN_CACHE_DIR="$HOME/.terraform.d/plugin-cache"
  mkdir -p $TF_PLUGIN_CACHE_DIR

  generate_backend_tfvars $aws_account_id

  if should_init_databricks; then
    init_databricks
  fi

  init_snowflake

  if [[ ! ${AIRFLOW_DEPLOYMENT:-} == "1" ]]; then
    terraform init -upgrade -reconfigure -backend-config=backend.tfvars
  else
    terraform init -upgrade -reconfigure -backend-config=backend.tfvars -plugin-dir=$TF_PLUGIN_CACHE_DIR
  fi

  local workspace="${aws_account_id}::${LABEL}"
  terraform workspace new $workspace || terraform workspace select $workspace

  # OpsGenie API key retrieval (elided)

  seiji config generate tfvars --spec-path deploy/luna-config-spec.yaml
}
```

The critical final line `seiji config generate tfvars --spec-path deploy/luna-config-spec.yaml` reads the config spec, pulls values from SSM, and writes `.auto.tfvars` files that Terraform picks up automatically.

### generate_backend_tfvars()

Writes `backend.tfvars` with S3 state bucket and DynamoDB lock table:

```bash
function generate_backend_tfvars() {
  local aws_region=$(aws ec2 describe-availability-zones --output text --query 'AvailabilityZones[0].[RegionName]')

  if [ "$aws_region" == "us-east-1" ]; then
    bucket_name="abacus-tfstate-$1"
  else
    bucket_name="abacus-tfstate-$1-${aws_region}"
  fi

  cat <<EOF > backend.tfvars
bucket = "${bucket_name}"
dynamodb_table = "tfstate-lock-$1"
encrypt = true
region = "${aws_region}"
EOF
}
```

Backend config conventions:
- S3 bucket: `abacus-tfstate-{account_id}` (us-east-1) or `abacus-tfstate-{account_id}-{region}`
- DynamoDB lock table: `tfstate-lock-{account_id}`

### Workspace Format

```
${aws_account_id}::${LABEL}
```

Selected via `terraform workspace new $workspace || terraform workspace select $workspace`.

### init_databricks()

Conditionally initialized only when `.tf` files reference the Databricks provider (checked by `should_init_databricks()`). Creates a temporary `DATABRICKS_CONFIG_FILE` with account-level and per-workspace profiles. Supports both interactive (`databricks-cli`) and service principal (`oauth-m2m`) auth.

### init_snowflake()

Exports `SNOWFLAKE_ACCOUNT`, `SNOWFLAKE_USER`, `SNOWFLAKE_PASSWORD`, `SNOWFLAKE_ROLE` from Secrets Manager at `${LABEL}/snowflake/user/admin`. Falls back to a shared dev credential if the tenant-specific secret does not exist.

### Helper Functions

- `get_ssm_parameter_value(name)` - fetches a single SSM parameter
- `delete_key_from_ssm(name)` - deletes an SSM parameter if it exists
- `check_mac_version()` - verifies M1/M2 users have `m1-terraform-provider-helper`
- `check_sha256sum_available()` - ensures `sha256sum` is present (macOS needs `coreutils`)
- `detect_existing_metastore()` - checks for pre-existing Databricks metastore to avoid conflicts

## create.sh

Source: `scripts/terraform/create.sh` (39 lines). The canonical create hook for Terraform components.

```bash
#!/bin/bash
set -euE -o pipefail

source scripts/terraform/deploy_functions.sh

cd $(dirname $(dirname ${BASH_SOURCE[0]}))

check_mac_version
check_sha256sum_available

# Template rendering: expand .tmpl files per workspace
templates=$(find . -name '*.tmpl' | xargs -I {} basename {})
workspaces=$(aws ssm get-parameter --name /${LABEL}/config/_/workspaces/json \
  --output text --query Parameter.Value | jq -r '.[]')

for workspace in ${workspaces[@]}; do
  if [ -d "Configfile" ]; then
    cp -r Configfile Configfile_$workspace
  fi
  for template in ${templates[@]}; do
    dest_filename="$(echo "${template%.tmpl}")_$workspace.tf"
    sed "s/<WORKSPACE>/$workspace/g" $template > $dest_filename
  done
done

init_terraform

if echo $* | grep -e "--auto-approve"; then
  terraform apply --auto-approve
else
  terraform apply
fi
```

Key patterns:
1. Source `deploy_functions.sh` from the shared scripts path
2. `cd` to the layer root from its `deploy/` subdirectory
3. Template rendering loop: `.tmpl` files become `_${workspace}.tf` with `<WORKSPACE>` replaced
4. Call `init_terraform` (handles backend, providers, config spec)
5. `terraform apply` with optional `--auto-approve`

## destroy.sh Pattern

Mirrors `create.sh` but calls `terraform destroy` instead of `terraform apply`. Same template rendering and init sequence.

## Template Rendering

Files ending in `.tmpl` are per-workspace templates. The rendering loop:
1. Fetches workspace list from SSM: `/${LABEL}/config/_/workspaces/json`
2. For each workspace, copies `Configfile` directory if present
3. Substitutes `<WORKSPACE>` placeholder and writes `{name}_${workspace}.tf`

This allows a single layer to manage resources across multiple workspaces (e.g., one Databricks workspace config per tenant workspace).

## Migration Directory Convention

Migration scripts live in `deploy/migrations/` and follow the naming pattern:

```
\d{3}-description
```

For example: `001-rename-resource`, `002-import-state`. Seiji executes these in order during the `migrate` hook before `create`.
