# Patterns

## Slack notifications are mandatory
ALWAYS send Slack notifications at session milestones — especially `[COMPLETE]` at task end and `[BLOCKER]` when stuck. Never skip or defer them.

## kitchendev deployment
- Coordinate: `kitchen.eks.deploy`
- Repository path: Points to the helmsman project directory directly (e.g., `/path/to/kitchen-eks-helmsman`), NOT the parent directory
- Env vars: `KUBECONFIG=~/.kubeconfig/kubeconfig_kitchendev AWS_PROFILE=abacus-kitchen-dev AWS_DEFAULT_REGION=us-east-1 LABEL=kitchendev`
- ECR registry: Account 473376902650, accessed via `AWS_PROFILE=abacus-kitchen`

## ECR image forking workflow
1. Create repo in 473376902650 if needed (AWS_PROFILE=abacus-kitchen)
2. Set org-wide pull policy (org: o-b529w2g9h7)
3. Pull with `--platform linux/amd64`
4. Login to private ECR
5. Tag and push
6. Verify from target account

## Fluent Bit on EKS with Container Insights
- Use aws-for-fluent-bit stable branch (2.34.x = Fluent Bit v1.9.10)
- Config structure: @INCLUDE pattern with application-log.conf, dataplane-log.conf, host-log.conf
- IMDSv2 support: use `aws` filter with `imds_version v2`
- Log level: `error` to reduce noise
- Storage: filesystem-backed with `storage.backlog.mem_limit 5M`
