# Coordinate Registry

All 96 seiji coordinates from `ng-deployment-config-files/manifests/default-manifest.yaml`.

Type inference: `.deploy` = Helmsman; `.mock` = Helmsman; all others = Terraform.

| Coordinate | Version Anchor | Type |
|-----------|---------------|------|
| nextgen.airbyte.config_poller | ng-infrastructure-version | Terraform |
| nextgen.airbyte.deploy | ng-infrastructure-version | Helmsman |
| nextgen.airbyte.provision | ng-infrastructure-version | Terraform |
| nextgen.airbyte.proxy | ng-infrastructure-version | Terraform |
| nextgen.airbyte_cron_monitor.deploy | ng-airbyte-services-version | Helmsman |
| nextgen.airbyte_notification_setup.deploy | ng-airbyte-services-version | Helmsman |
| nextgen.airflow.irsa | airflow-infrastructure-version | Terraform |
| nextgen.airflow.provision | airflow-infrastructure-version | Terraform |
| nextgen.airflow_cd.deploy | airflow-helmsman-version | Helmsman |
| nextgen.asg_updater.deploy | asg-updater-version | Helmsman |
| nextgen.asg_updater.provision | asg-updater-version | Terraform |
| nextgen.base.init | ng-infrastructure-version | Terraform |
| nextgen.data_copier_api.deploy | data-copier-api-version | Helmsman |
| nextgen.data_ingestion_api.deploy | ng-data-ingestion-api-version | Helmsman |
| nextgen.data_ingestion_api.provision | ng-data-ingestion-api-version | Terraform |
| nextgen.databricks.configurations | ng-infrastructure-version | Terraform |
| nextgen.databricks.connector_deployer | ng-infrastructure-version | Terraform |
| nextgen.databricks.manifest_file_processor | ng-manifest-file-processor-version | Terraform |
| nextgen.databricks.mdm | ng-infrastructure-version | Terraform |
| nextgen.databricks.onyx | onyx-infrastructure-version | Terraform |
| nextgen.databricks.permissions | ng-infrastructure-version | Terraform |
| nextgen.databricks.provision | ng-infrastructure-version | Terraform |
| nextgen.databricks.tokens | ng-infrastructure-version | Terraform |
| nextgen.databricks_continuous_deployment.provision | ng-air-continuous-deployment-version | Terraform |
| nextgen.datacopier.provision | ng-infrastructure-version | Terraform |
| nextgen.eks.deploy | ng-infrastructure-version | Helmsman |
| nextgen.eks.provision | ng-infrastructure-version | Terraform |
| nextgen.file_receipt_notification.deploy | ng-monitoring-utils-version | Helmsman |
| nextgen.genesis.deploy | genesis-helmsman-version | Helmsman |
| nextgen.genesis.provision | genesis-infrastructure-version | Terraform |
| nextgen.gitlab.provision | ng-infrastructure-version | Terraform |
| nextgen.governance.common | ng-governance-infrastructure-version | Terraform |
| nextgen.governance.data_profiling | ng-governance-infrastructure-version | Terraform |
| nextgen.governance.data_spike | ng-governance-infrastructure-version | Terraform |
| nextgen.governance.enterprise_dq_rule_index | ng-governance-infrastructure-version | Terraform |
| nextgen.governance.lineage | ng-governance-infrastructure-version | Terraform |
| nextgen.governance.provision | ng-governance-infrastructure-version | Terraform |
| nextgen.governance.reconciliation | ng-governance-infrastructure-version | Terraform |
| nextgen.governance.referential_integrity | ng-governance-infrastructure-version | Terraform |
| nextgen.irdm_consumer.provision | irdm-infrastructure-version | Terraform |
| nextgen.irdm_producer.provision | irdm-infrastructure-version | Terraform |
| nextgen.kafka.bridge | ng-infrastructure-version | Terraform |
| nextgen.kafka.provision | ng-infrastructure-version | Terraform |
| nextgen.kafka.proxy | ng-infrastructure-version | Terraform |
| nextgen.landing_decrypt_service.deploy | ng-landing-decrypt-service-version | Helmsman |
| nextgen.mdp_gateway.deploy | mdp-gateway-version | Helmsman |
| nextgen.mdp_gateway.provision | mdp-gateway-version | Terraform |
| nextgen.nasco_api.deploy | ng-nasco-event-api-version | Helmsman |
| nextgen.nasco_api.mock | ng-nasco-event-api-version | Helmsman |
| nextgen.nasco_api.provision | ng-nasco-event-api-version | Terraform |
| nextgen.network.platform | ng-infrastructure-version | Terraform |
| nextgen.ng_landing_decrypt.deploy | ng-landing-decrypt-version | Helmsman |
| nextgen.onyx.cdn | onyx-infrastructure-version | Terraform |
| nextgen.onyx.databricks_secrets | onyx-infrastructure-version | Terraform |
| nextgen.onyx.deploy | onyx-helmsman-version | Helmsman |
| nextgen.onyx.epa | onyx-infrastructure-version | Terraform |
| nextgen.onyx.fite | onyx-infrastructure-version | Terraform |
| nextgen.onyx.healthlake | onyx-infrastructure-version | Terraform |
| nextgen.onyx.insights | onyx-infrastructure-version | Terraform |
| nextgen.onyx.mdp | onyx-infrastructure-version | Terraform |
| nextgen.onyx.monitor | onyx-infrastructure-version | Terraform |
| nextgen.onyx.network | onyx-infrastructure-version | Terraform |
| nextgen.onyx.payer | onyx-infrastructure-version | Terraform |
| nextgen.onyx.policies | onyx-infrastructure-version | Terraform |
| nextgen.onyx.provision | onyx-infrastructure-version | Terraform |
| nextgen.onyx.sla_dashboard | onyx-infrastructure-version | Terraform |
| nextgen.onyx.slap | onyx-infrastructure-version | Terraform |
| nextgen.onyx.storage | onyx-infrastructure-version | Terraform |
| nextgen.orchestration_service.db_migrate | ng-orchestration-service-version | Terraform |
| nextgen.orchestration_service.deploy | ng-orchestration-service-version | Helmsman |
| nextgen.orchestration_service.provision | ng-orchestration-service-version | Terraform |
| nextgen.point_click_care.deploy | ng-point-click-api-version | Helmsman |
| nextgen.point_click_care.provision | ng-point-click-api-version | Terraform |
| nextgen.prime_api.deploy | ng-prime-api-version | Helmsman |
| nextgen.prime_api.provision | ng-prime-api-version | Terraform |
| nextgen.prime_api_mock.deploy | ng-prime-api-version | Helmsman |
| nextgen.reltio.bridge | ng-infrastructure-version | Terraform |
| nextgen.reltio.outbound | ng-infrastructure-version | Terraform |
| nextgen.reltio.proxy | ng-infrastructure-version | Terraform |
| nextgen.salesforce.bridge | ng-infrastructure-version | Terraform |
| nextgen.salesforce.proxy | ng-infrastructure-version | Terraform |
| nextgen.security.policies | ng-infrastructure-version | Terraform |
| nextgen.security.roles | ng-infrastructure-version | Terraform |
| nextgen.sendgrid.provision | ng-monitoring-utils-version | Terraform |
| nextgen.sftp.provision | ng-infrastructure-version | Terraform |
| nextgen.sftp_service.deploy | ng-abacus-inbound-infra-version | Helmsman |
| nextgen.sftp_service.test_server | ng-abacus-inbound-infra-version | Terraform |
| nextgen.snowflake.configurations | ng-infrastructure-version | Terraform |
| nextgen.snowflake.provision | ng-infrastructure-version | Terraform |
| nextgen.ssh_service.bridge | ng-databricks-outbound-infra-version | Terraform |
| nextgen.ssh_service.tunnel_manager | ng-databricks-outbound-infra-version | Terraform |
| nextgen.storage.common | ng-infrastructure-version | Terraform |
| nextgen.storage.job_metadata_db | ng-infrastructure-version | Terraform |
| nextgen.test_jump_server.bastionhost | ng-databricks-outbound-infra-version | Terraform |
| secops.auth0.idm | auth0-idm-version | Terraform |
| secops.auth0.provision | auth0-infrastructure-version | Terraform |

## Summary by Version Anchor

| Version Anchor | Count | Current Version |
|---------------|-------|-----------------|
| ng-infrastructure-version | 34 | 26.4.0rc3 |
| onyx-infrastructure-version | 16 | 26.3.20rc1 |
| ng-governance-infrastructure-version | 8 | 26.4.0rc1 |
| ng-orchestration-service-version | 3 | 26.3.3rc6 |
| ng-nasco-event-api-version | 3 | 26.1.0 |
| ng-prime-api-version | 3 | 25.7.0 |
| ng-databricks-outbound-infra-version | 3 | 25.9.0 |
| mdp-gateway-version | 2 | 26.3.0rc1 |
| ng-data-ingestion-api-version | 2 | 26.3.0rc3 |
| ng-point-click-api-version | 2 | 25.7.0 |
| ng-airbyte-services-version | 2 | 26.3.1rc1 |
| asg-updater-version | 2 | 25.12.2 |
| ng-abacus-inbound-infra-version | 2 | 26.3.0rc2 |
| ng-monitoring-utils-version | 2 | 26.2.0 |
| irdm-infrastructure-version | 2 | 26.2.0rc3 |
| airflow-infrastructure-version | 2 | 26.1.0 |
| auth0-infrastructure-version | 1 | 26.4.0rc1 |
| auth0-idm-version | 1 | 26.3.0rc4 |
| onyx-helmsman-version | 1 | 26.4.4rc2 |
| airflow-helmsman-version | 1 | 26.2.0 |
| data-copier-api-version | 1 | 26.2.0rc1 |
| genesis-helmsman-version | 1 | 26.3.1rc2 |
| genesis-infrastructure-version | 1 | 26.3.1rc4 |
| genai-infrastructure-version | 0 | 25.8.0 |
| ng-air-continuous-deployment-version | 1 | 26.3.4rc2 |
| ng-landing-decrypt-version | 1 | 26.3.0rc3 |
| ng-landing-decrypt-service-version | 1 | 26.3.2 |
| ng-manifest-file-processor-version | 1 | 25.11.1 |

## Summary by Type

- **Terraform:** 72 coordinates
- **Helmsman:** 24 coordinates
