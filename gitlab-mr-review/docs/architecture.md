# gitlab-mr-review Architecture


## Invocation Modes

### /mr-review team

Fetch open MRs from team roster (config/team.yaml). Operator (@zettatron) excluded.
Generates review.md for each MR. Draft MRs included but listed separately under
"Draft / In Progress" heading. Use `--exclude-drafts` to suppress.

### /mr-review personal

Fetch open MRs authored by operator (@zettatron) only.

### /mr-review personal investigate

Investigation mode for resolving comments on operator's own MRs. Presents:
- [1] Use existing local project directory
- [2] Fresh investigation environment (clone)

Retrieves all open comment threads, assesses each as VALID/INVALID/SUBOPTIMAL.
Only VALID issues drive code changes. Changes validated iteratively. Generates
investigation review.md with Investigation Log and Resolution Status sections.

Critical evaluation: never apply changes solely because a comment requests it.
Evaluate on merit: correctness, security, performance, pattern consistency.

### /mr-review <gitlab-mr-url> [<url> ...]

Direct Mode — bypasses roster lookup. Reviews only specified MRs.
Multiple URLs accepted (space- or newline-separated). Each MR validated before review.
If a URL is inaccessible, error for that MR; continue processing remaining URLs.

`/mr-review <url> investigate` — investigation mode for any MR (not just operator's).

### /mr-review <mode> directory: <path>

Custom output directory. Date hierarchy always appended.


## Team Configuration

Defined in `config/team.yaml`:
- Operator: @zettatron
- Team: @Rivlin.pereira, @mahendra-gautam, @alex_ai, @srosenfeld,
  @andrew.huddleston1, @eric.shtivelberg, @gordon.marx
- Excluded file patterns (lock files, generated, vendored, binary)
- Draft policy and cache settings


## Caching

Location: `<skill_dir>/cache/mrs/` (team/personal) and `cache/direct/` (per-MR).

- Cache file naming: `mrs_YYYYMMDD_HHMMSS_<scope>.json`
- Stale threshold: 6 hours (configurable) — prompts operator before using stale cache
- `--force-refresh`: Always fetch fresh, no prompt
- `--use-cache`: Always use existing, error if none exists
- Flags are mutually exclusive
- Previous cache files retained for audit (pruned after 30 days)
- Direct Mode does not use team/personal cache


## Review Output

### Default location
```
~/.zsh/review/<YYYY>/<MM>/<DD>/<branch-name>/review.md
```

### Custom location
```
<custom_path>/<YYYY>/<MM>/<DD>/<branch-name>/review.md
```

Branch name: MR source branch, sanitized (/ → -, strip special chars).

### review.md Frontmatter (Stable API Contract)

The frontmatter schema is a versioned API with the dispatch skill.
Do not rename, retype, or remove any field. New fields append only.

```yaml
---
mr_id: <integer>
mr_iid: <integer>
mr_url: <string>
project: <string>
title: <string>
author: <string>
source_branch: <string>
target_branch: <string>
state: open | draft | merged | closed
pipeline_status: passed | failed | running | pending | canceled | none
pipeline_url: <string | null>
has_conflicts: <bool>
approvals_required: <integer>
approvals_given: <integer>
approved_by: [<username>, ...]
verdict_critical: <integer>
verdict_major: <integer>
verdict_minor: <integer>
verdict_suggestion: <integer>
linked_issues: [<issue-iid>, ...]
review_timestamp: <ISO 8601 UTC>
review_path: <absolute path>
previous_review_path: <path | null>
skill_version: <string>
---
```

### review.md Body Sections

1. **MR Summary** — metadata table, description, excluded files note
2. **Pipeline Status Block** — always present; failure/no-pipeline warnings
3. **Merge Conflict Block** — always present; blocking flag if conflicts
4. **Approval Status Block** — required/given/pending
5. **Linked Issues Block** — from closing keywords
6. **Diff Analysis** — file-by-file breakdown with findings
7. **Existing Review Comments** — API comments with VALID/INVALID/SUBOPTIMAL/ADDRESSED
8. **Cross-Project Context** — if MR touches shared interfaces
9. **Summary of Recommended Changes** — CRITICAL/MAJOR/MINOR/SUGGESTION
10. **External References** — authoritative links for non-obvious recommendations
11. **Resolution Paths** — for CRITICAL and MAJOR items
12. **Review Metadata** — timestamp, cache info, skill version
13. **Review Delta** — if previous review exists for this branch


## File Exclusion Policy

Before diff analysis, filter excluded patterns from `config/team.yaml`:
- Lock files: noted but not analyzed
- Generated files: excluded unless generator config changed
- Vendored: excluded entirely
- Binary/media: excluded entirely

Override: `--include-generated`, `--include-vendor`

If only lock files changed: "This MR contains only lock file changes. No code analysis performed."


## Jira Linked Issue Context

When closing keywords (Closes #N, Fixes #N) reference Jira issue keys in MR
description or title, invoke the jira skill with `JIRA_CALLER=gitlab-mr-review`
to fetch context. This is always read-only — the jira skill enters FORCED
READ-ONLY MODE and rejects any write attempt.


## Review Methodology

Load `references/review-criteria.md` for the full methodology. Key principles:
depth over surface, security review, infrastructure-specific criteria.
All findings grounded in observed data. Unverified speculation labeled
`[UNVERIFIED INFERENCE]`.


## Git Operations

Permitted: clone, checkout, fetch, diff, log (all read-only).
Clones target the review output directory, never inside existing repos.
Review branch: `<source-branch>-review` (never pushed).


## Idempotency

Re-running on the same MR produces a new review.md with a new timestamp.
Previous reviews are preserved. Review Delta section computes the diff.
