# beads Architecture


## br Constraints

br NEVER runs git commands. Always run `br sync --flush-only` before any
git commit in ~/.zsh/dispatch/. All br commands in scripts must use:
`subprocess.run(['br', ...], cwd=DISPATCH_DIR)`


## Database and Project Setup

Project directory: ~/.zsh/dispatch/
Database: ~/.zsh/dispatch/.beads/beads.db (gitignored)
JSONL export: ~/.zsh/dispatch/.beads/issues.jsonl (version controlled)
Config: ~/.zsh/dispatch/.beads/config.yaml

The skill ensures ~/.zsh/dispatch/.gitignore contains:
```
.beads/*.db
.beads/*.db-shm
.beads/*.db-wal
!.beads/issues.jsonl
!.beads/config.yaml
!.beads/metadata.json
```


## Idempotency

/beads init is idempotent: checks existing issues by title match before
creating. Running init twice creates no duplicates.

All read operations are idempotent. Write operations (create, close, defer)
are single-shot and not repeated on re-invocation.
