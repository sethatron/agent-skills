# Release Type Decision Tree

## Classification Rules

Based on which projects appear in the Slack message:

```
Input Projects
  │
  ├─ Only ng-abacus-insights-runtime ──────────────→ AIR_ONLY
  │
  ├─ Only ng-onyx-runtime ─────────────────────────→ ONYX_ONLY
  │
  ├─ Both ng-abacus-insights-runtime AND
  │  ng-onyx-runtime (no others) ──────────────────→ AIR_ONYX
  │
  ├─ Neither AIR nor ONYX present ─────────────────→ PLATFORM
  │
  └─ AIR and/or ONYX WITH other projects ──────────→ COMPOUND
```

## Runtime Project Set

- `ng-abacus-insights-runtime` (AIR)
- `ng-onyx-runtime` (ONYX)

All other projects are "platform" projects.

## Flow Definitions

### AIR_ONLY / ONYX_ONLY / AIR_ONYX (Single-Phase)
1. FETCH_REPOS
2. EXTRACT_TICKETS
3. MERGE_CONFLICT_CHECK
4. VALIDATE_VERSIONS
5. CREATE_CMD (naming: "AIR x.x.x Release" / "ONYX x.x.x Release" / "AIR x.x.x / ONYX x.x.x Release")
6. CREATE_PROJECT_MRS (release branch → master)
7. GENERATE_SLACK_OUTPUT
8. SAVE_RELEASE_ARTIFACTS

No manifest update needed. No config variance detection needed.

### PLATFORM (Single-Phase)
1. FETCH_REPOS
2. EXTRACT_TICKETS
3. MERGE_CONFLICT_CHECK
4. VALIDATE_VERSIONS
5. CREATE_CMD (naming: "NextGen xx.x.x Release")
6. CREATE_PROJECT_MRS (release branch → master)
7. UPDATE_MANIFEST
8. DETECT_CONFIG_VARIANCE
9. CREATE_CONFIG_MR
10. GENERATE_SLACK_OUTPUT
11. SAVE_RELEASE_ARTIFACTS

### COMPOUND (Three-Phase with 2 Human Gates)

**Phase 1/3: AIR/ONYX Release**
1. Extract tickets for AIR/ONYX projects ONLY
2. MERGE_CONFLICT_CHECK (AIR/ONYX projects only)
3. CREATE_CMD for AIR/ONYX
4. CREATE_PROJECT_MRS for AIR/ONYX (release branch → master)
5. Generate AIR/ONYX Slack notification
6. **PAUSE_1** — wait for operator to confirm MR merged

**Phase 2/3: Pre-Release to QA**
7. VALIDATE_AIR_ONYX_MERGED
8. CREATE_PRERELEASE_BRANCHES (CMD-{num} from qa)
9. UPDATE_GLOBALS_TF
10. CREATE_PRERELEASE_MRS (CMD-{num} → qa, merge on approval)
11. Generate pre-release Slack notification
12. **PAUSE_2** — wait for operator to confirm pre-release MRs merged
13. CHERRYPICK_INTO_RELEASE

**Phase 3/3: Platform Release**
14. Extract tickets for platform projects
15. MERGE_CONFLICT_CHECK (platform projects)
16. VALIDATE_VERSIONS
17. Create NEW CMD for platform
18. CREATE_PROJECT_MRS (release branch → master)
19. UPDATE_MANIFEST
20. DETECT_CONFIG_VARIANCE
21. CREATE_CONFIG_MR
22. VERIFY_ECR_IMAGE — confirm AIR/ONYX image in ECR
23. Generate platform Slack notification
24. SAVE_RELEASE_ARTIFACTS

## CMD Naming Conventions

| Release Type | CMD Summary Format |
|---|---|
| AIR_ONLY | `AIR {air_version} Release` |
| ONYX_ONLY | `ONYX {onyx_version} Release` |
| AIR_ONYX | `AIR {air_version} / ONYX {onyx_version} Release` |
| PLATFORM | `NextGen {version} Release` |
| COMPOUND Phase 1 | Same as AIR/ONYX naming above |
| COMPOUND Phase 3 | `NextGen {version} Release` |

## MR Title Format

All MR titles follow: `[CMD-{num}] {CMD summary}`

Example: `[CMD-2201] NextGen 26.2.29 Release`
