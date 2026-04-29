# dispatch-manager Quality Grades


## Change Management

### Write Operation Protocol (ten steps)

Every write operation follows: parse intent → impact analysis → confirmation →
backup → dry-run validation → apply → post-apply validation → version bump +
changelog → symlink verification → status report.

See `scripts/change_manager.py` for the full interface.

### Version Tracking

Every managed skill's SKILL.md must have `version: "<semver>"`.
Bump rules: MAJOR (breaking contract change), MINOR (new feature), PATCH (bug fix).

### Rollback

`/dispatch-manager rollback <skill>` — current state backed up first (so
rollback is itself reversible). Post-rollback validation automatic.
