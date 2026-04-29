# Team MR Review — 2026-04-02

**Reviewed:** 2026-04-02T19:41Z
**Team:** Rivlin.pereira, mahendra-gautam, alex_ai, srosenfeld, andrew.huddleston1, eric.shtivelberg, gordon.marx
**Scope:** 11 active MRs (updated within 3 days), 6 stale MRs skipped, 15 drafts noted

## Executive Summary

| Verdict | Count | MRs |
|---------|-------|-----|
| Ready to merge | 4 | !1553, !463, !414, !50 |
| Needs changes | 5 | !574, !1618, !38, !1 (coverself), !2 (otel) |
| Needs discussion | 2 | !1552, !1 (create-sso-app) |

**Critical/High findings requiring immediate attention:**
- **!1 coverself-helmsman** (gordon.marx) — CI pointing at non-existent `py3.14` variant and test branch; pipeline failing
- **!574 seiji-orchestrator** (eric.shtivelberg) — `except Exception` swallows real bugs; CI references feature branch dockerbase tag; Terraform versions removed from image
- **!2 otel-poc** (eric.shtivelberg) — `rg` usage in healthcheck breaks airgapped deploy; empty IAM role; broken `k8sattributes` pod association
- **!1618 ng-infrastructure** (eric.shtivelberg) — budget threshold variable has no input validation (0 or negative allowed)
- **!38 seiji-dockerbase** (eric.shtivelberg) — node16 variant build arg mismatch; Node 16 won't actually be installed
- **!414 onyx-helmsman** (gordon.marx) — deployment ordering dependency: must merge after !463

---

## Ready to Merge (4)

### !1553 — DSP-7927: Add new preprd workspace's Gitlab branch to PHP
**MR:** [ng-deployment-config-files!1553](https://gitlab.com/abacusinsights/abacus-v2/next-gen-platform/ng-deployment-config-files/-/merge_requests/1553)
**Author:** srosenfeld | **Pipeline:** passed | **Findings:** 0 critical, 0 high, 0 medium, 1 low
Clean single-file config addition mapping 4 workspaces to GitLab branches for PHP tenant.

### !463 — DSP-7993: make new config variables per-workspace (onyx-infrastructure)
**MR:** [onyx-infrastructure!463](https://gitlab.com/abacusinsights/abacus-v2/next-gen-platform/onyx-infrastructure/-/merge_requests/463)
**Author:** gordon.marx | **Pipeline:** passed | **Approved by:** eric.shtivelberg | **Findings:** 0 critical, 0 high, 1 medium, 2 low
Converts `SLAP_ACTIVE_MEMBER_SEARCH` and `SLAP_REQUIRES_CONSENT_ERROR_PAGE` to per-workspace SSM parameters. **Caveat:** Ensure config-files repo populates per-workspace values before applying Terraform, otherwise workspaces will silently default to `"False"`.

### !414 — DSP-7993: make new config variables per-workspace (onyx-helmsman)
**MR:** [onyx-helmsman!414](https://gitlab.com/abacusinsights/abacus-v2/next-gen-platform/onyx-helmsman/-/merge_requests/414)
**Author:** gordon.marx | **Pipeline:** passed | **Approved by:** inderjit.bassi | **Findings:** 1 critical (ordering), 0 high, 0 medium, 1 low
Consumer half of the two-MR change. **Must merge after !463** — the SSM parameters must exist before this helmsman reads them. Existing error handling provides graceful fallback, but SLAP would run with wrong defaults.

### !50 — [DSP-7912] Update gitlab runners
**MR:** [gitlabrunner-helmsman!50](https://gitlab.com/abacusinsights/kitchen/gitlabrunner-helmsman/-/merge_requests/50)
**Author:** mahendra-gautam | **Pipeline:** passed | **Approved by:** eric.shtivelberg | **Findings:** 0 critical, 0 high, 0 medium, 1 low
Single-line Helm chart version bump 0.86.0 -> 0.87.0. Clean.

---

## Needs Changes (5)

### !574 — [DSP-7893] Finalize seiji-orchestrator Python 3.11 + uv/ruff
**MR:** [seiji-orchestrator!574](https://gitlab.com/abacusinsights/seiji/seiji-orchestrator/-/merge_requests/574)
**Author:** eric.shtivelberg | **55 files** | **Pipeline:** passed | **Findings:** 0 critical, 2 high, 3 medium, 4 low

**Before merge:**
1. **HIGH** — `except Exception` in `__init__.py` swallows all import errors, not just the optional CRT dep. Narrow to `ImportError`.
2. **HIGH** — Terraform 0.13.7 and 1.10.1 removed from Dockerfile with `TFENV_AUTO_INSTALL=false`. Confirm no deployed components reference those versions.
3. **MEDIUM** — `.gitlab-ci.yml` references `SEIJI_DOCKERBASE_VERSION=py311_upgrade_DSP-7893` (feature branch). Must be updated to stable release tag before merge.
4. **MEDIUM** — Airflow base image jump 2.6.1 -> 2.10.5 — verify DAG and provider compatibility.
5. **MEDIUM** — `botocore[crt]` listed as hard dependency but code treats it as optional.

### !1618 — DSP-7709: add account-level Databricks budgets and budget policies
**MR:** [ng-infrastructure!1618](https://gitlab.com/abacusinsights/abacus-v2/next-gen-platform/ng-infrastructure/-/merge_requests/1618)
**Author:** eric.shtivelberg | **35 files** | **Pipeline:** passed | **Findings:** 0 critical, 1 high, 3 medium, 4 low

**Before merge:**
1. **HIGH** — `budget_monthly_threshold_usd` has no validation — 0 or negative values create non-functional budgets. Add `condition = var.budget_monthly_threshold_usd > 0`.
2. **MEDIUM** — Single 100% alert threshold. Add 50%/80% tiers for early warning.
3. **MEDIUM** — No workspace exclusion mechanism — budget is all-or-nothing per the `workspaces` variable.
4. **MEDIUM** — `tostring()` on the threshold is fragile if provider schema changes.

### !38 — [DSP-7893] Modernize seiji-dockerbase for py3.11 + uv
**MR:** [seiji-dockerbase!38](https://gitlab.com/abacusinsights/seiji/seiji-dockerbase/-/merge_requests/38)
**Author:** eric.shtivelberg | **3 files** | **Pipeline:** passed | **Findings:** 0 critical, 1 high, 2 medium, 2 low

**Before merge:**
1. **HIGH** — `build:kaniko_node16_py311` CI job passes `--build-arg node_version_15=16.17.1` but the Dockerfile no longer has that ARG. The node16 variant image will only have Node 20, not Node 16. Fix or remove the node16 variant.
2. **MEDIUM** — Default Python version mismatch: Dockerfile says 3.11.15, CI passes 3.11.11.
3. **MEDIUM** — `curl | sh` for uv install is unpinned. Pin version for reproducible builds.

### !1 — add pre-commit to coverself-helmsman
**MR:** [coverself-helmsman!1](https://gitlab.com/abacusinsights/abacus-v2/next-gen-platform/coverself/coverself-helmsman/-/merge_requests/1)
**Author:** gordon.marx | **19 files** | **Pipeline:** failing | **Findings:** 1 critical, 1 high, 1 medium, 2 low

**Before merge:**
1. **CRITICAL** — `.gitlab-ci.yml` uses `SOUSCHEF_VERSION=gmarx-check-service-account` (test branch) and `SOUSCHEF_VARIANT=terraform1.1.7-py3.14` (Python 3.14 doesn't exist). Pipeline is failing. Revert to valid values.
2. **HIGH** — Unquoted `{{ssm:` values in `envoy-values.yaml` — bare `{{` can break strict YAML parsers. Should be single-quoted like the rest.
3. **MEDIUM** — SSM path quoting style is inconsistent between lines.

### !2 — DSP-7878: Streamline OTel -> Prometheus OTLP metrics path
**MR:** [abacus-otel-poc!2](https://gitlab.com/abacusinsights/abacus-v2/next-gen-platform/abacus-otel-poc/-/merge_requests/2)
**Author:** eric.shtivelberg | **51 files** | **Pipeline:** passed | **Approved by:** gordon.marx | **Findings:** 1 critical, 2 high, 3 medium, 4 low

**Before merge:**
1. **CRITICAL** — `verify_minimal_otel_pipeline.sh` uses `rg` (ripgrep) while rest of MR specifically replaces `rg` with portable `grep -E` for airgapped compat. Replace with `grep -Eq`.
2. **HIGH** — `otel_collector` IAM role has no policies attached after cleanup. Role is empty skeleton.
3. **HIGH** — `k8sattributes` lost its `pod_association` block. OTLP-forwarded traffic won't be correctly associated with source pods.
4. **MEDIUM** — DaemonSet lost `k8s.node.name` injection — restore from existing `K8S_NODE_NAME` env var.
5. **MEDIUM** — `set -x` in `make-gitlab-tag` will echo the GITLAB_TOKEN during SSM retrieval.
6. **MEDIUM** — Namespace finalizer force-removal is aggressive; could orphan resources.

---

## Needs Discussion (2)

### !1552 — DSP-8006: Add 0057 IGs to Nevada Dev/Stg
**MR:** [ng-deployment-config-files!1552](https://gitlab.com/abacusinsights/abacus-v2/next-gen-platform/ng-deployment-config-files/-/merge_requests/1552)
**Author:** srosenfeld | **Pipeline:** passed | **Findings:** 0 critical, 0 high, 1 medium, 1 low

**Open thread:** inderjit.bassi and srosenfeld disagree on YAML anchor naming convention. Inderjit prefers state-specific names (`nevada_onyx_igs`, `wisconsin_onyx_igs`) for consistency with other gw configs. Steve prefers composition-based names (`onyx_igs_with_0057`) since the lists are identical across states. Needs resolution.

### !1 — DSP-7992: Initial commit, create-sso-app
**MR:** [create-sso-app!1](https://gitlab.com/abacusinsights/randos/create-sso-app/-/merge_requests/1)
**Author:** srosenfeld | **Pipeline:** passed (warnings) | **Findings:** 0 visible critical, 1 high (cannot review)

**Blocker:** The `create_sso_app.py` diff is collapsed/truncated in API response. The primary script cannot be reviewed without expanding on GitLab. Given the author's own description ("working but kind of unwieldy") and a commit titled "Fix hallucinations", a human must review the full script for secrets, error handling, and SSO security before approval.

---

## Stale MRs (not reviewed — last activity >7 days)

| MR | Author | Last Updated | Title |
|----|--------|--------------|-------|
| !1 | andrew.huddleston1 | 2026-03-19 | [DSP-0000] more seiji context |
| !80 | andrew.huddleston1 | 2026-03-18 | [DSP-7866] Test DEV_TENANTS |
| !3 | srosenfeld | 2024-11-21 | Enable PITR for Dynamo tables |
| !16 | srosenfeld | 2024-11-21 | Add SOUSCHEF_VARIANT to gitlab-ci.yml |
| !37 | alex_ai | 2023-01-25 | DSP-3667 - Migrate abacus forks |
| !4 | srosenfeld | 2022-08-08 | Enable PITR for Dynamo tables |

---

## Draft MRs (15)

Notable drafts:
- **alex_ai** — Two `NextGen 26.3.45 Release` MRs (!415, !464) updated 2026-03-31
- **gordon.marx** — `{DSP-0000} temp` (!455) updated 2026-04-01
- **andrew.huddleston1** — `[DSP-7582] Enabled slapv3_idp_configuration` (!1371) updated 2026-01-30
- 3 drafts with merge conflicts: !438 (gordon.marx), !117 (mahendra-gautam), !74 (srosenfeld)

---

## Team Activity Summary

| Author | Ready | Draft | Total | Needs Attention |
|--------|-------|-------|-------|-----------------|
| eric.shtivelberg | 4 | 0 | 4 | 4 MRs need changes |
| srosenfeld | 4 (+2 stale) | 4 | 10 | 1 needs discussion, 1 needs human review |
| gordon.marx | 3 | 2 | 5 | 1 pipeline failing, 1 deployment ordering |
| mahendra-gautam | 1 | 5 | 6 | Ready to merge |
| andrew.huddleston1 | 2 (stale) | 1 | 3 | Stale |
| alex_ai | 1 (stale) | 2 | 3 | Stale |
| Rivlin.pereira | 0 | 1 | 1 | Draft with conflicts |

---
*Review generated by gitlab-mr-review skill v2.0.0*
