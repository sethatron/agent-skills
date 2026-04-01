---
name: Bacon Release Agent
description: Release Agent for NextGen platform deployments. This skill should be used when the user says '/bacon', 'bring home the bacon', 'run bacon', 'release', 'start release', or pastes a QA Slack message containing release branch information (project names with 'Branch: release-x.x.x' patterns). Automates Jira CMD ticket creation, GitLab merge request creation, deployment manifest updates, config variance detection, and Slack notification generation for AIR, ONYX, and Platform releases.
version: 1.0.0
---

# Bacon Release Agent

Automates the NextGen platform release process end-to-end. Replaces the legacy `relman` bash script.

## Scripts

All scripts live at `~/.claude/skills/bacon/scripts/`. The main CLI is `bacon.py` which imports from `gitlab_client.py`, `jira_client.py`, `git_ops.py`, and `merge_conflict_check.py`.

**IMPORTANT**: Shell state does not persist between Bash tool calls. Always use the full path directly — never rely on a `$BACON` variable set in a prior command.

```bash
# Every command must use the full path inline:
python3 ~/.claude/skills/bacon/scripts/bacon.py <subcommand>

# Source creds in the same command when needed:
source ~/.jira_creds.env && python3 ~/.claude/skills/bacon/scripts/bacon.py <subcommand>
```

## Reference Files

- `references/release-types.md` — Release type classification and flow definitions
- `references/output-templates.md` — CMD body (ADF), MR descriptions, Slack notification templates
- `references/manifest-mapping.md` — Project-to-manifest-anchor mapping, version validation
- `references/api-reference.md` — Jira Service Desk + GitLab API specs with curl examples

## Workflow Overview

```
INPUT → CLASSIFY → FETCH_REPOS → EXTRACT_TICKETS → MERGE_CONFLICT_CHECK
  → VALIDATE_VERSIONS → CREATE_CMD → CREATE_PROJECT_MRS → UPDATE_MANIFEST
  → DETECT_CONFIG_VARIANCE → CREATE_CONFIG_MR → GENERATE_SLACK → SAVE_ARTIFACTS
```

For compound releases (AIR/ONYX + Platform), the flow has 3 phases with 2 human gates. See "Compound Release Flow" below.

## Dry-Run Mode

Triggered when the parsed output includes `"dry_run_level"`. Two levels:

### Trigger Detection

The `parse` command detects "dry-run" or "dry-run (N)" in the input text and includes `"dry_run_level": N` in the output JSON. Default level is 0 if no number is specified.

### Level 0: Preview Only

Call the `preview` subcommand once with the parsed JSON. No multi-stage flow needed.

```bash
echo '$PARSED_JSON' | python3 ~/.claude/skills/bacon/scripts/bacon.py --dry-run-level 0 preview
```

This runs all stages read-only and outputs a single structured JSON document showing what every stage would produce. Present the output to the operator and stop — no further commands needed.

### Level 1: Sandboxed Execution

Follow the normal multi-stage flow with these modifications:

1. **After `fetch-repos`**, call `setup-dryrun-branches` to create isolated `-dryrun` branches:
```bash
echo '$PARSED_JSON' | python3 ~/.claude/skills/bacon/scripts/bacon.py --dry-run-level 1 setup-dryrun-branches
```

2. **Pass `--dry-run-level 1` on every subsequent command** — this is a global flag before the subcommand name:
```bash
python3 ~/.claude/skills/bacon/scripts/bacon.py --dry-run-level 1 create-cmd < input.json
python3 ~/.claude/skills/bacon/scripts/bacon.py --dry-run-level 1 create-mr < input.json
```

3. **Use dryrun branch names** in all payloads — the `setup-dryrun-branches` output maps project → dryrun branch name. Use those names as `source_branch` values.

4. **CMD ticket**: Returns `CMD-0000` (no Jira API call). Use `CMD-0000` in all MR titles and manifest commits.

5. **MRs**: Created as Draft with `[DRY-RUN]` prefix in the title and a warning banner in description.

6. **Manifest update**: Uses `dryrun-{version}` branch automatically.

7. **At PAUSE points**: Operator says "continue" to proceed. Skip merge verification — `verify-mr-merged` returns simulated success at level 1.

8. **Cherry-pick**: Skip entirely at level 1. Output what would happen instead (the draft MR won't be merged, so there's no merge commit to cherry-pick).

9. **Artifacts**: Saved to `~/.release/{version}-dryrun/`.

10. **After testing**, clean up all dryrun artifacts:
```bash
python3 ~/.claude/skills/bacon/scripts/bacon.py cleanup-dryrun --version {version}
# Or with artifact deletion:
python3 ~/.claude/skills/bacon/scripts/bacon.py cleanup-dryrun --version {version} --delete-artifacts
```

`cleanup-dryrun` deletes remote/local dryrun branches, closes Draft MRs with `[DRY-RUN]` in the title, and optionally removes the dryrun artifact directory.

### Level 1 Compound Flow

- **Phase 1**: Full execution — draft MR for AIR/ONYX runtime on dryrun branches
- **Phase 2**: Branch creation + globals update on dryrun branches. Pre-release MRs created as Draft. Cherry-pick skipped — output what would happen
- **Phase 3**: Full execution — draft MRs for platform projects, dryrun manifest

## Stage Execution

### Stage 1: Parse Input

```bash
echo '<slack_message>' | python3 ~/.claude/skills/bacon/scripts/bacon.py parse
```

Returns JSON with: `projects` (name, branch, tag, branch_version), `version`, `ngqa_ticket`, `adhoc_tickets`, `globals_files`, `build_directives`, `onyx_from_to`, `release_type`.

The operator MUST provide the release version (e.g., "Version: 26.2.29"). If missing, ask for it.

### Stage 2: Classify

The `parse` command includes `release_type` in its output. Classification rules:
- Only `ng-abacus-insights-runtime` → AIR_ONLY
- Only `ng-onyx-runtime` → ONYX_ONLY
- Both AIR and ONYX (no others) → AIR_ONYX
- Neither AIR nor ONYX → PLATFORM
- AIR/ONYX with other projects → COMPOUND

### Stage 3: Fetch Repos

```bash
echo '$PARSED_JSON' | python3 ~/.claude/skills/bacon/scripts/bacon.py fetch-repos
```

Clones (or fetches) all project repos to `~/.release/git/`. Also fetches `ng-deployment-config-files`. Returns status per project — stop if any fail.

### Stage 4: Extract Tickets

For each project:
```bash
python3 ~/.claude/skills/bacon/scripts/bacon.py extract-tickets --project {name} --branch {branch}
```

Returns ticket IDs found in the git log between master and the release branch (excluding tickets already in master).

Then enrich each project's tickets with summaries and breaking status:
```bash
echo '{"tickets": ["DSP-7707", "XFORM-1817"], "project": "ng-infrastructure"}' | python3 ~/.claude/skills/bacon/scripts/bacon.py enrich-tickets
```

Also include any adhoc tickets from the parsed input (set project="included").

### Stage 4b: Merge Conflict Check

For ALL release types (not just compound):
```bash
echo '$PARSED_JSON' | python3 ~/.claude/skills/bacon/scripts/bacon.py check-conflicts
```

Returns per-project conflict status. For each project:
- **Clean** — no action needed
- **Simple conflict** — present to operator with auto-resolution option
- **Complex conflict** — PAUSE, present details, ask operator for guidance

If complex conflicts exist, stop and ask the operator before proceeding to CREATE_CMD. See `references/output-templates.md` for conflict report format.

For complex conflicts, create a temporary visualization branch and Draft MR via:
```bash
echo '{"project": "...", "source_branch": "conflict-{version}", "target_branch": "master", "title": "DRAFT: ...", "description": "...", "draft": true}' | python3 ~/.claude/skills/bacon/scripts/bacon.py create-mr
```

### Stage 5: Validate Versions

For each project:
```bash
python3 ~/.claude/skills/bacon/scripts/bacon.py next-tag --project {name}
```

Compare calculated version vs. Slack branch version. If they diverge, warn the operator but use the Slack version (it's authoritative).

### Stage 6: Create CMD Ticket

Prepare the CMD payload and create via API:
```bash
echo '{
  "projects": [...],
  "tickets": [...],
  "version": "26.2.29",
  "release_type": "PLATFORM",
  "ngqa_ticket": "NGQA-3900"
}' | python3 ~/.claude/skills/bacon/scripts/bacon.py create-cmd
```

Returns `key`, `browse_url`, `portal_url`, `summary`. The description is ADF format (see `references/output-templates.md`).

CMD naming conventions — see `references/release-types.md`.

### Stage 7: Create Project MRs

For each project:
```bash
echo '{
  "project": "ng-infrastructure",
  "source_branch": "release-26.2.6",
  "target_branch": "master",
  "title": "[CMD-2201] NextGen 26.2.29 Release",
  "description": "..."
}' | python3 ~/.claude/skills/bacon/scripts/bacon.py create-mr
```

Returns `iid`, `web_url`, `state`. If an MR already exists for the source branch, it will be updated.

Per-project MR description contains ONLY that project's tickets (see `references/output-templates.md`).

### Stage 8: Update Manifest

For PLATFORM and COMPOUND Phase 3 releases only:
```bash
echo '{
  "version": "26.2.29",
  "cmd_key": "CMD-2201",
  "updates": {
    "ng-infrastructure": "26.2.6",
    "mdp-gateway": "26.2.1"
  }
}' | python3 ~/.claude/skills/bacon/scripts/bacon.py update-manifest
```

Updates version anchors in `ng-deployment-config-files/manifests/default-manifest.yaml`. See `references/manifest-mapping.md` for the complete project-to-anchor mapping.

### Stage 9: Detect Config Variance

```bash
python3 ~/.claude/skills/bacon/scripts/bacon.py detect-variance
```

Compares master vs qa in `ng-deployment-config-files/tenant-specific-overrides/`. Excludes: abacus-config.yaml, abacusqa-config.yaml, qawest-config.yaml, alexwest-config.yaml.

### Stage 10: Create Config MR

Create the ng-deployment-config-files MR using the same `create-mr` command with the aggregated ticket table as description.

### Stage 10b: Verify ECR Image (Compound Only)

For compound releases, before generating the final platform Slack notification, ask:
```
Before I generate the final platform release Slack notification, please confirm:
Has the AIR/ONYX image been pushed to ECR and is available for deployment?
```

Only proceed after operator confirms.

### Stage 11: Generate Slack Notification

Compose the Slack notification using the templates in `references/output-templates.md`. Every hyperlink MUST be fully populated — no empty parentheses. Use the CMD URL from Stage 6 and MR URLs from Stage 7.

Present the Slack notification to the operator in a code block for easy copying.

### Stage 12: Save Artifacts

```bash
echo '{
  "version": "26.2.29",
  "files": {
    "state.json": {"type": "PLATFORM", "version": "26.2.29", "cmd": "CMD-2201"},
    "slack_notification.md": "...",
    "merge_conflict_report.md": "...",
    "mr_links.json": {"ng-infrastructure": "https://..."}
  }
}' | python3 ~/.claude/skills/bacon/scripts/bacon.py save-artifacts
```

Saves to `~/.release/{version}/`.

## Compound Release Flow (AIR/ONYX + Platform)

When `release_type == "COMPOUND"`, execute three phases within a single conversation:

### Phase 1/3: AIR/ONYX Release

1. Extract tickets for AIR/ONYX projects ONLY
2. Merge conflict check for AIR/ONYX projects
3. Create CMD for AIR/ONYX (naming: "AIR x.x.x Release" etc.)
4. Create MR(s) for AIR/ONYX (release branch → master)
5. Output AIR/ONYX Slack notification
6. **PAUSE_1** — Display phase complete message (see `references/output-templates.md`), wait for operator to confirm MR merged

### Phase 2/3: Pre-Release to QA

After operator confirms MR merged:

7. Verify MR actually merged:
```bash
python3 ~/.claude/skills/bacon/scripts/bacon.py verify-mr-merged --project ng-abacus-insights-runtime --iid {iid}
```

8. Create pre-release branches and update globals.tf:
```bash
echo '{
  "project": "ng-governance-infrastructure",
  "branch": "CMD-2201",
  "files": ["terraform/layers/databricks/governance/reconciliation/globals.tf"],
  "air_version": "2.0.18",
  "from_to": []
}' | python3 ~/.claude/skills/bacon/scripts/bacon.py update-globals
```

The `create_branch_from` + `update_globals` sequence: checkout qa → create CMD-{num} branch → update globals.tf → commit → push.

9. Create pre-release MRs (CMD-{num} → qa) with `merge_when_pipeline_succeeds: true`:
```bash
echo '{
  "project": "ng-governance-infrastructure",
  "source_branch": "CMD-2201",
  "target_branch": "qa",
  "title": "[CMD-2201] AIR 2.0.18 Pre-Release",
  "description": "...",
  "merge_when_pipeline_succeeds": true
}' | python3 ~/.claude/skills/bacon/scripts/bacon.py create-mr
```

10. Output pre-release Slack notification
11. **PAUSE_2** — Wait for operator to confirm pre-release MRs merged

### Phase 2/3 continued: Cherry-Pick

12. For each project with a pre-release MR, get the merge commit SHA and cherry-pick into release branch:
```bash
echo '{"project": "ng-governance-infrastructure", "branch": "release-26.2.0", "merge_commit_sha": "abc123"}' | python3 ~/.claude/skills/bacon/scripts/bacon.py cherry-pick
```

### Phase 3/3: Platform Release

13. Continue with standard PLATFORM flow for remaining projects (Stages 4-12)
14. Create a NEW CMD for the platform release
15. Before final Slack notification, run VERIFY_ECR_IMAGE gate

## Error Handling

STOP and ask the operator when:
- Git fetch/clone fails
- Jira API returns 401/403
- GitLab API returns 401/403
- Version validation finds > 1 patch increment skip
- Project from Slack message has no git repo
- Release branch doesn't exist
- Existing MR has conflicting title
- Any unexpected error

Handle gracefully:
- 429 rate limiting (scripts retry automatically)
- 5xx server errors (scripts retry once)
- Missing Jira summaries (use ticket ID as placeholder)
- Projects with no tags (date-based versioning)

## Important Constraints

1. Create per-release directory at `~/.release/{version}/`
2. Use `~/.release/git/` for persistent git repos
3. Construct valid ADF JSON for Jira descriptions (not plain text)
4. Create CMD tickets and MRs via API (not browser)
5. Every hyperlink in Slack output MUST be fully populated
6. Stop and ask when inconsistencies detected
7. All MR/CMD titles: `[CMD-{num}] {release_type} {version} Release`

## Quick Reference

| Data | Location |
|---|---|
| Git repos | `~/.release/git/{project}/` |
| Release artifacts | `~/.release/{version}/` |
| Credentials | `~/.jira_creds.env` |
| Manifest | `~/.release/git/ng-deployment-config-files/manifests/default-manifest.yaml` |
| Scripts | `~/.claude/skills/bacon/scripts/` |
| Templates | `~/.claude/skills/bacon/references/output-templates.md` |
| API specs | `~/.claude/skills/bacon/references/api-reference.md` |
| Anchor map | `~/.claude/skills/bacon/references/manifest-mapping.md` |
| Release types | `~/.claude/skills/bacon/references/release-types.md` |
