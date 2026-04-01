---
name: aws-deploy-role
description: Bootstrap a self-service IAM deploy role for Terraform projects. Generates permission set policy, deploy role managed policies, trust policy, assume-role wrapper, and bootstrap script. Triggers on /aws-deploy-role, "bootstrap deploy role", "setup deploy role", "new aws project iam", "aws iam bootstrap", "deploy role setup", "create deploy role for terraform".
---

# AWS Deploy Role Bootstrap

Generate IAM policy files and an assume-role wrapper script for a new Terraform project using the self-service deploy role pattern: SSO permission set assumes a deploy role, the role's managed policies get expanded as needed during development, and eventually the role is deleted when permissions are promoted to the permission set.

## Parameters

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `project` | yes | — | Project name (kebab-case, used in role names and bucket names) |
| `account_id` | yes | — | AWS account ID |
| `region` | no | `us-east-1` | AWS region |
| `profile` | yes | — | AWS SSO profile name |
| `state_bucket` | no | `{project}-tfstate-{account_id}` | S3 bucket for Terraform state |

Prompt the user for required parameters before generating files.

## Generate Files

1. Read `assets/policies/permission-set.json.tpl` from this skill directory. Replace `{{PROJECT}}`, `{{ACCOUNT_ID}}`, `{{STATE_BUCKET}}` with parameter values. Write to `{project_root}/infra/policies/permission-set.json`.

2. Read `assets/policies/trust-policy.json.tpl` from this skill directory. Replace `{{PROJECT}}`, `{{ACCOUNT_ID}}` with parameter values. Write to `{project_root}/infra/policies/trust-policy.json`.

3. Read `assets/policies/deploy/platform.json.tpl` from this skill directory. Write to `{project_root}/infra/policies/deploy/platform.json` (no placeholders to replace).

4. Copy `scripts/assume-role.sh` from this skill directory to `{project_root}/assume-role.sh`. Ensure it is executable (`chmod +x`).

5. Copy `scripts/bootstrap.sh` from this skill directory to `{project_root}/scripts/bootstrap.sh`. Ensure it is executable (`chmod +x`).

## Bootstrap Sequence

> Step 1 is a one-time admin action. Steps 2–3 are developer self-service.

### Step 1: Apply permission set (requires Identity Center admin)

Copy `infra/policies/permission-set.json` into AWS IAM Identity Center as an
inline policy for the developer's permission set. This grants:
- S3 access for Terraform state
- `sts:AssumeRole` on the deploy role
- IAM management scoped to the deploy role and its managed policies

### Step 2: Create the deploy role (developer, self-service)

Run the bootstrap script:

```bash
./scripts/bootstrap.sh \
  --role-name {{PROJECT}}-deploy \
  --account-id {{ACCOUNT_ID}} \
  --trust-policy infra/policies/trust-policy.json \
  --policy-dir infra/policies/deploy \
  --profile {{PROFILE}}
```

### Step 3: Verify end-to-end

```bash
source ./assume-role.sh {{PROJECT}}-deploy
aws sts get-caller-identity
```

Present these commands to the user. Do NOT run them.

## backend.tf Integration

The provider assumes the deploy role. The S3 backend does NOT — it authenticates with the caller's SSO credentials directly.

```hcl
terraform {
  backend "s3" {
    region       = "{{REGION}}"
    bucket       = "{{STATE_BUCKET}}"
    key          = "{{PROJECT}}/terraform.tfstate"
    encrypt      = true
    use_lockfile = true
  }
}

provider "aws" {
  region = var.aws_region
  assume_role {
    role_arn    = "arn:aws:iam::{{ACCOUNT_ID}}:role/{{PROJECT}}-deploy"
    external_id = "{{PROJECT}}-deploy"
  }
  default_tags {
    tags = {
      App         = var.app
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}
```

## Permission Expansion Workflow

When `terraform plan` or `apply` returns `AccessDenied`:

1. Identify the denied action from the error message.
2. Add the action (and resource scope) to the appropriate file in `infra/policies/deploy/`. If the file would exceed 6,144 bytes URL-encoded, create a new file in the same directory.
3. Rerun the bootstrap script — it syncs all files in `--policy-dir` automatically.
4. Wait ~10 seconds for IAM propagation.
5. Retry the Terraform command.

## Gotchas

- **`local-exec` provisioners bypass `assume_role`**: They run as the SSO caller identity, not the assumed deploy role. Any `local-exec` provisioner that needs deploy role permissions must explicitly assume the role within its command block.
- **IAM policy propagation**: Takes 5-15 seconds after policy updates. Wait before retrying.
- **Cognito domain names**: Globally unique across all AWS accounts.
- **Some API actions require `Resource: "*"`**: Even when the resource is scoped (e.g., `cognito-idp:DescribeUserPoolDomain`, `cognito-idp:ListUserPools`).
- **Managed policy size limit**: Each policy file must be under 6,144 bytes URL-encoded. The bootstrap script validates this before making any AWS calls.
- **Managed policy count limit**: AWS default is 10 managed policies per role (requestable to 20). The bootstrap script warns if exceeded.

## Production Cutover

When the project is stable and permissions are finalized:

1. Merge the deploy role's managed policy actions into the SSO permission set.
2. Remove the `assume_role` block from the Terraform provider.
3. Detach and delete the managed policies, then delete the role:
   ```bash
   for POLICY_ARN in $(aws iam list-attached-role-policies \
     --role-name {{PROJECT}}-deploy \
     --query 'AttachedPolicies[].PolicyArn' --output text \
     --profile {{PROFILE}}); do
     aws iam detach-role-policy --role-name {{PROJECT}}-deploy --policy-arn "$POLICY_ARN" --profile {{PROFILE}}
     aws iam delete-policy --policy-arn "$POLICY_ARN" --profile {{PROFILE}}
   done
   aws iam delete-role --role-name {{PROJECT}}-deploy --profile {{PROFILE}}
   ```
