---
name: gitlab-mr-review
version: "1.0.0"
dsi_type: "A"
description: >-
  Use this skill whenever the user mentions MR review, merge requests, GitLab
  review, team review, /mr-review, pastes a GitLab MR URL, or asks about open
  PRs or code review. Trigger on: "review my team's MRs", "check open merge
  requests", "investigate MR", "pull my open MRs", "review this MR: <url>",
  "what needs reviewing", "review these MRs", "look at this merge request",
  "check the queue", "team review", "personal review". Also trigger when a
  GitLab URL pattern (gitlab.com/.../-/merge_requests/...) appears in the
  user's message — confirm whether they want a review initiated.
docs:
  architecture: docs/architecture.md
  integration: docs/integration.md
  failure_modes: docs/failure-modes.md
  quality: docs/quality.md
  workflow: docs/workflow.md
---

┌─────────────────────────── OPERATIONAL GUARDRAILS ───────────────────────────┐
│  PROHIBITED — NO EXCEPTIONS                                                  │
│    - git add / git commit / git push (any variant)                           │
│    - Any write operation to GitLab (comments, approvals, edits, merges)      │
│    - Posting under any identity (user, bot, anonymous, etc.)                 │
│                                                                              │
│  OPERATOR-ONLY ACTIONS                                                       │
│    - Committing and pushing changes                                          │
│    - Responding to or resolving MR comments                                  │
│    - Approving, merging, or closing MRs                                      │
└──────────────────────────────────────────────────────────────────────────────┘

## Environment Pre-Validation

Run `scripts/check_env.py` first on every invocation:
1. Python >= 3.10
2. Packages: requests, jinja2, gitpython
3. git binary on PATH
4. GITLAB_TOKEN set (sourced from `~/.config/git/token.env` if not in environment)
5. GITLAB_URL reachable (default: https://gitlab.com)
6. Token scopes: read_api, read_repository
7. Cache directory writable
8. Review output directory creatable

```bash
python scripts/check_env.py [--verbose] [--json]
```

## Scripts

- `scripts/check_env.py` — environment validation
- `scripts/gitlab_client.py` — paginated GitLab API client
- `scripts/cache_manager.py` — cache lifecycle
- `scripts/review_writer.py` — review.md generation with Jinja2
- `scripts/git_utils.py` — read-only git operations

## References

- `references/review-criteria.md` — extended review methodology
- `references/gitlab-api-notes.md` — pagination, rate limits, token scopes
- `templates/review.md.j2` — Jinja2 template for review.md

## Deep Review Findings (Claude-in-the-loop)

After `mr_review_runner.py` generates review.md files with diffs, perform a
deep code review of each **non-draft** MR. For each MR, write a
`findings.json` file alongside `review.md` in the MR directory:

```bash
~/.zsh/review/YYYY/MM/DD/{scope}/mr_{iid}/findings.json
```

### findings.json schema

```json
{
  "mr_iid": 468,
  "findings": [
    {
      "severity": "critical|major|minor|suggestion",
      "file": "path/to/file.tf",
      "line": "45",
      "description": "Brief description of the issue",
      "suggestion": "- old line\n+ new line"
    }
  ],
  "verdict": "APPROVE|REQUEST_CHANGES|COMMENT",
  "verdict_summary": "One-sentence summary of the review verdict."
}
```

- `severity`: CRITICAL (security, data loss), MAJOR (logic errors, breaking
  changes, missing validation), MINOR (style, naming, minor risk), SUGGESTION
  (improvements, not blocking)
- `file`: path relative to the repo root (from the diff `new_path`)
- `line`: line number or range (e.g. "45" or "45-50"), empty string if N/A
- `suggestion`: diff-formatted suggested change, or empty string if N/A
- `verdict`: overall recommendation for the MR
- `verdict_summary`: one sentence explaining the verdict

### Review checklist

For each non-draft MR, analyze the diff for:
1. Security issues (hardcoded secrets, injection, auth bypass)
2. Logic errors and edge cases
3. Breaking changes and backwards incompatibility
4. Missing error handling at system boundaries
5. Infrastructure: resource naming, tagging, variable usage, state drift
6. Version consistency across coordinated MRs
7. Missing tests for critical paths
8. Stale MRs (age > 90 days) and failed pipelines

### After writing all findings.json files

Rebuild the README.md to include findings:

```bash
python scripts/mr_review_runner.py rebuild-index ~/.zsh/review/YYYY/MM/DD/{scope}
```

This regenerates README.md with the Findings column in the summary table and
per-MR findings sections with suggested changes.

## Cross-Skill Integration

When this skill fetches Jira issue context for linked issues (Closes/Fixes/Resolves #N),
it sets `JIRA_CALLER=gitlab-mr-review` to invoke the jira skill in FORCED READ-ONLY MODE.
This ensures no Jira write operations occur from MR review context.

## Docs

See docs/ for detailed specifications:

- **Architecture and internals**: [docs/architecture.md](docs/architecture.md)
- **Integration contracts**: [docs/integration.md](docs/integration.md)
- **Failure modes and recovery**: [docs/failure-modes.md](docs/failure-modes.md)
- **Quality grades**: [docs/quality.md](docs/quality.md)
- **Workflow hooks**: [docs/workflow.md](docs/workflow.md)
