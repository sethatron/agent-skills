# Personal MR Review — 2026-04-02

**Author:** zettatron
**Reviewed:** 2026-04-02T19:50Z
**Scope:** 5 non-draft MRs, 4 drafts noted

## Executive Summary

| Verdict | Count | MRs |
|---------|-------|-----|
| Needs changes | 3 | !92, !672, !1 (genesis) |
| Needs discussion | 2 | !575, !359 |

**No MRs are currently ready to merge.** All 5 have open items — unresolved reviewer threads, merge-order dependencies, or stale state.

### Priority Actions

1. **!92 + !575 (DSP-7955 cycle detection)** — Cross-repo pair. !92 must merge first. Both need approval. !92 has a high-priority item: cycle detection runs after `set_downstream` wiring.
2. **!672 (EKS 1.33 AMI)** — Blocked on Inderjit's unresolved question about `shared_ami_account`/`shared_kms_arn` in conntest1. Reply to unblock approval.
3. **!1 genesis** — Two unresolved threads from Inderjit (package manager hardening, Python variant). RC base image should be confirmed or bumped. 14 days stale.
4. **!359 (DEV_TENANTS)** — 5+ weeks stale with deliberately canceled auto-merge. Decide: merge or close.

---

## MR Details

### !92 — [DSP-7955 1/2] Implement cycle detection/resolution (airflow-helmsman)

**MR:** [airflow-helmsman!92](https://gitlab.com/abacusinsights/abacus-v2/next-gen-platform/airflow-helmsman/-/merge_requests/92)
**Branch:** DSP-7955 -> master | **Pipeline:** passed | **Approval:** not approved (1 required)

**Summary:** Adds DFS-based cycle detection and edge-breaking to the Airflow deploy trigger and DAG template. New `DAG_CYCLE` status in DynamoDB, Slack notifications with cycle details, import error retrieval from Airflow API. This is the server-side half of DSP-7955.

**Findings:** 0 critical, 1 high, 2 medium, 3 low

- **HIGH** — `detect_dependency_cycles` runs *after* `set_downstream` wiring. If a cycle exists, Airflow's internal graph already has it before the exception is raised. Safer to check against `planned_edges` *before* wiring (like `break_edge_cycles` does).
- **MEDIUM** — Pre-flight cycle check scans output for bare substring `'cycle'` — false positive risk from lifecycle log messages. Tighten to look for the specific exception format.
- **MEDIUM** — `break_edge_cycles` removes whichever back-edge DFS finds first, which is traversal-order-dependent. Acceptable for escape-hatch use, but should be documented as non-deterministic.
- **LOW** — Slack notification formatting duplicated between pre-flight and retry-failure blocks. Extract helper.

**Verdict:** Needs changes — confirm post-wiring detection is safe or move it earlier.

---

### !575 — [DSP-7955 1/2] DAG cycle detection/resolution additions (seiji-orchestrator)

**MR:** [seiji-orchestrator!575](https://gitlab.com/abacusinsights/seiji/seiji-orchestrator/-/merge_requests/575)
**Branch:** DSP-7955 -> master | **Pipeline:** passed (59% coverage) | **Approval:** not approved

**Summary:** CLI/orchestrator companion to !92. Threads `--fix-dag-cycle` flag from Typer CLI to ADT SQS message, handles `DAG_CYCLE`/`FAILED`/`TIMEOUT` statuses in monitoring loop. Also fixes a pre-existing bug where timeouts silently reported success.

**Findings:** 0 critical, 0 high, 2 medium, 2 low

- **MEDIUM** — `deployment_status` initialized in monitoring method but accessed with `getattr` defensively. Initialize in `__init__` for consistency.
- **MEDIUM** — Unclear if `apply()` forwards `fix_dag_cycle` to `deployer_execute()`. The `run` path clearly threads it; the `apply` path's body is not in the diff. Verify.

**Cross-repo dependency:** !92 must merge first (or simultaneously). If !575 lands first, CLI sends `fix_dag_cycle` and expects `DAG_CYCLE` status, but old ADT ignores both. Degraded to timeout — not catastrophic but not intended behavior.

**Verdict:** Needs discussion — verify `apply()` threading and confirm merge order with !92.

---

### !672 — [DSP-7003] Update dev,qa,client eks_source_ami for EKS 1.33

**MR:** [luna-config-files!672](https://gitlab.com/abacusinsights/lunatic-dove/luna-config-files/-/merge_requests/672)
**Branch:** DSP-7003 -> master | **Pipeline:** passed | **Approval:** not approved (1 required)

**Summary:** Updates EKS source AMI from 1.32 to 1.33 across dev, QA, and client baselines. Also adds `shared_ami_account` and `shared_kms_arn` to conntest1 dev config and updates seijidev KMS to a multi-region key.

**Findings:** 0 critical, 1 high, 1 medium, 1 low

- **HIGH** — Inderjit's **unresolved thread** asks "Where are these being used?" about `shared_ami_account`/`shared_kms_arn` additions in conntest1. These are unrelated to the EKS AMI bump and need explanation. Reply to unblock.
- **MEDIUM** — KMS key change from standard to multi-region (`mrk-` prefix) is operationally significant. Confirm old key is being retired and new key is replicated to target regions.

**Verdict:** Needs changes — reply to Inderjit's thread, get approval.

---

### !1 — [DSP-7413] Bump genesis version

**MR:** [genesis!1](https://gitlab.com/abacusinsights/abacus-v2/next-gen-platform/genesis/genesis/-/merge_requests/1)
**Branch:** DSP-7413 -> master | **Pipeline:** passed | **Approval:** not approved (1 required) | **Age:** 14 days

**Summary:** Initial MR for genesis container image. Dockerfile wraps upstream `genesis:v1.12.0-rc.1` with security hardening (setuid stripping, non-root user, package manager removal). CI uses kitchen-souschef templates.

**Findings:** 0 critical, 1 high, 1 medium, 2 low

- **HIGH** — Base image is a release candidate (`v1.12.0-rc.1`). Confirm RC is intentional or bump to stable if available.
- **MEDIUM** — Souschef version pinned to `master` (moving target).

**Unresolved threads (2):**
1. Inderjit asks about removing additional package managers (`wget`, `yum`, `gem`).
2. Inderjit asks about using a newer Python variant. Eric confirmed py3.14 exists.

**Verdict:** Needs changes — reply to both threads, confirm or update RC base image.

---

### !359 — [DSP-7085] Re-enable DEV_TENANTS deployments for Onyx

**MR:** [onyx-helmsman!359](https://gitlab.com/abacusinsights/abacus-v2/next-gen-platform/onyx-helmsman/-/merge_requests/359)
**Branch:** DSP-7085 -> qa | **Pipeline:** passed | **Approved by:** Luisa Nevers | **Age:** 5+ weeks

**Summary:** Uncomments `airflow-deploy.yml` include and `generate-deploy-pipeline` job to re-enable DEV_TENANTS deployments. Single-file change.

**Findings:** 0 critical, 1 high, 1 medium, 2 low

- **HIGH** — Auto-merge was deliberately canceled on 2026-02-23 with no recorded explanation. After 5+ weeks stale, need to determine if the original blocker is resolved.
- **MEDIUM** — `DEPLOY_CONFIG_REFERENCE_BRANCH: "qa"` is hardcoded; confirm promotion model handles this.

**Verdict:** Needs discussion — determine why auto-merge was canceled, decide merge or close, rebase if merging.

---

## Draft MRs (4)

| MR | Project | Title | Last Updated |
|----|---------|-------|--------------|
| !1631 | ng-infrastructure | Draft: GAIPI-45 Review: Example changes | 2026-03-24 |
| !2 | abacus-dispatch-cursor | Draft: Create eks-upgrade skill | 2026-03-24 |
| !1 | seiji-encore | Draft: [DSP-7726] Support explicit destroys | 2026-02-20 |
| !386 | kitchen-souschef | Draft: [refimpl] BuildKit | 2025-08-06 |

---

## Action Items

| Priority | MR | Action |
|----------|-----|--------|
| **1** | !672 | Reply to Inderjit's thread about shared_ami_account/shared_kms_arn |
| **2** | !1 (genesis) | Reply to both Inderjit threads; bump RC to stable if available |
| **3** | !92 | Confirm post-wiring cycle detection is safe; seek approval |
| **4** | !575 | Verify apply() threads fix_dag_cycle; merge after !92 |
| **5** | !359 | Decide: merge (rebase first) or close |

---
*Review generated by gitlab-mr-review skill v2.0.0*
