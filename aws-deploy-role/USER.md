# AWS Deploy Role — User Guide

Self-service IAM deploy role pattern for Terraform projects. The SSO permission set grants narrow permissions (state bucket + assume role + role/policy management), while the deploy role's managed policies grow as you develop.

## Quick Start

```
/aws-deploy-role
```

Claude will prompt for project name, account ID, region, and SSO profile, then generate files:

| Generated file | Purpose |
|---|---|
| `infra/policies/permission-set.json` | Inline policy for your SSO permission set |
| `infra/policies/trust-policy.json` | Trust policy allowing account root to assume the role |
| `infra/policies/deploy/platform.json` | Starter managed policy (STS only) |
| `assume-role.sh` | Shell wrapper to assume the deploy role |
| `scripts/bootstrap.sh` | Idempotent create-or-update script for the role |

## Bootstrap Sequence

### Step 1 — Apply permission set (one-time, requires Identity Center admin)

Copy the contents of `infra/policies/permission-set.json` into AWS IAM Identity Center as an inline policy on the developer's permission set.

### Step 2 — Create the deploy role (self-service)

```bash
./scripts/bootstrap.sh \
  --role-name <project>-deploy \
  --account-id <account-id> \
  --trust-policy infra/policies/trust-policy.json \
  --policy-dir infra/policies/deploy \
  --profile <sso-profile>
```

The script is idempotent — re-run it anytime to sync managed policies with the files in `--policy-dir`.

### Step 3 — Verify

```bash
source ./assume-role.sh <project>-deploy
aws sts get-caller-identity
```

You should see the assumed role ARN in the output.

## Day-to-Day Usage

### Assuming the role

```bash
source ./assume-role.sh <role-name>
```

This exports `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and `AWS_SESSION_TOKEN` into your shell. Credentials expire after 1 hour (STS default).

### Expanding permissions

When `terraform plan` or `apply` returns `AccessDenied`:

1. Note the denied action and resource from the error.
2. Add them to the appropriate file in `infra/policies/deploy/`. If a file would exceed 6,144 bytes URL-encoded, create a new `.json` file in the same directory — it will be auto-discovered.
3. Rerun the bootstrap script:
   ```bash
   ./scripts/bootstrap.sh \
     --role-name <project>-deploy \
     --account-id <account-id> \
     --trust-policy infra/policies/trust-policy.json \
     --policy-dir infra/policies/deploy \
     --profile <sso-profile>
   ```
4. Wait ~10 seconds for IAM propagation, then retry.

### Production cutover

When permissions are finalized:

1. Merge the deploy role's managed policy actions into the SSO permission set.
2. Remove the `assume_role` block from your Terraform provider.
3. Delete the managed policies and role:
   ```bash
   for POLICY_ARN in $(aws iam list-attached-role-policies \
     --role-name <project>-deploy \
     --query 'AttachedPolicies[].PolicyArn' --output text \
     --profile <sso-profile>); do
     aws iam detach-role-policy --role-name <project>-deploy --policy-arn "$POLICY_ARN" --profile <sso-profile>
     aws iam delete-policy --policy-arn "$POLICY_ARN" --profile <sso-profile>
   done
   aws iam delete-role --role-name <project>-deploy --profile <sso-profile>
   ```

## Gotchas

- **`local-exec` provisioners** run as the SSO caller, not the assumed role. They must assume the role explicitly in their command block.
- **IAM propagation** takes 5–15 seconds after policy updates.
- **Some actions require `Resource: "*"`** even when logically scoped (e.g. `cognito-idp:DescribeUserPoolDomain`).
- **Permission set deny statements** override scoped allows. If you add IAM actions to the deploy role's policies, make sure they aren't blanket-denied in the permission set.
- **Managed policy size limit**: each file must be under 6,144 bytes URL-encoded. The bootstrap script validates this before making any AWS calls.
