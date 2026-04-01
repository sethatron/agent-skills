# Manifest Mapping

## Project-to-Anchor Mapping

The `default-manifest.yaml` in `ng-deployment-config-files` uses YAML anchors at the top of the file. Each project maps to a specific anchor name.

Format: `{anchor}: &{anchor} "{version}"`

| Project | Manifest Anchor |
|---|---|
| ng-infrastructure | ng-infrastructure-version |
| ng-air-continuous-deployment | ng-air-continuous-deployment-version |
| ng-governance-infrastructure | ng-governance-infrastructure-version |
| onyx-infrastructure | onyx-infrastructure-version |
| onyx-helmsman | onyx-helmsman-version |
| mdp-gateway | mdp-gateway-version |
| ng-abacus-inbound-infra | ng-abacus-inbound-infra-version |
| ng-orchestration-service | ng-orchestration-service-version |
| ng-monitoring-utils | ng-monitoring-utils-version |
| ng-airbyte-services | ng-airbyte-services-version |
| ng-data-copier | ng-data-copier-version |
| ng-landing-decrypt | ng-landing-decrypt-version |
| ng-landing-decrypt-service | ng-landing-decrypt-service-version |
| ng-databricks-outbound-infra | ng-databricks-outbound-infra-version |
| ng-manifest-file-processor | ng-manifest-file-processor-version |
| ng-nasco-event-api | ng-nasco-event-api-version |
| ng-point-click-api | ng-point-click-api-version |
| ng-prime-api | ng-prime-api-version |
| asg-updater | asg-updater-version |
| ng-data-ingestion-api | ng-data-ingestion-api-version |
| auth0-idm | auth0-idm-version |
| auth0-infrastructure | auth0-infrastructure-version |

## Projects NOT in Manifest

These projects do NOT have manifest anchors (they are runtime/image projects):
- `ng-abacus-insights-runtime` (AIR)
- `ng-onyx-runtime` (ONYX)

## Manifest Update Process

1. Checkout master of `ng-deployment-config-files`
2. Create branch `release-{version}`
3. For each released project with a manifest anchor, update the version:
   - Find line: `{anchor}: &{anchor} "{old_version}"`
   - Replace with: `{anchor}: &{anchor} "{new_version}"`
4. Commit and push

## Version Validation

For each project being updated, verify:
1. The current master tag (`git describe --tags master`)
2. The calculated `next_tag()` value
3. The version from the Slack message (branch name `release-X.X.X` → X.X.X)

**Warning conditions:**
- Version skips more than 1 patch increment (e.g., 26.2.3 → 26.2.5)
- Major/minor doesn't match expected (month boundary edge case)
- Calculated version differs from Slack message version (use Slack version — it's authoritative)

## Excluded Tenants (Config Variance)

These tenant config files are excluded from config variance detection:
- `abacus-config.yaml` (internal)
- `abacusqa-config.yaml` (QA)
- `qawest-config.yaml` (QA)
- `alexwest-config.yaml` (future use)
