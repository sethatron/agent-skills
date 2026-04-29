# gitlab-mr-review Integration


## GitLab API Integration

Via `scripts/gitlab_client.py`:
- Paginated (per_page=100, follows X-Next-Page)
- Token from GITLAB_TOKEN env var
- Token scope validation at startup (cached in-memory for invocation)
- `--dry-run` flag for testing without API calls

Per-MR data fetched:
- MR metadata (title, description, state, draft, branches, author, labels, etc.)
- Diffs (paginated)
- Discussions/comments (paginated)
- Pipeline status (from head_pipeline field; null = "No pipeline")
- Approval status (required, given, approved_by, rules_left)
- Merge conflicts (has_conflicts field)
- Closing issues (parsed from description: Closes/Fixes/Resolves #N)
