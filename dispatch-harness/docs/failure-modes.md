# dispatch-harness Failure Modes

## Script Failures

| Failure | Detection | Recovery |
|---------|-----------|----------|
| architecture.yaml missing | arch_checker.py exits with error | Run `/dispatch-harness init` to create |
| architecture.yaml parse error | yaml.safe_load raises | Regenerate from ecosystem.yaml |
| Cycle detected in dependency graph | arch_checker.py check_cycles() | Fix architecture.yaml calls[] entries |
| dispatch.db unavailable | telemetry_builder falls back to YAML | Session data from filesystem |
| dispatch.db has no sessions | telemetry_builder returns empty digest | Expected on fresh install |
| quality_grader can't parse script | ast.parse raises SyntaxError | Script graded F |
| Script file missing | os.path.exists check | Script graded F |
| ecosystem.yaml missing | check_env fails | Reinstall dispatch-manager |
| registry.yaml missing | check_env fails | Reinstall dispatch-manager |
| Beads not initialized | br commands fail | Run `/beads init` first |
| br binary not found | check_env fails | Install beads_rust |

## Entropy Agent Failures

| Failure | Detection | Recovery |
|---------|-----------|----------|
| br not available | shutil.which check at start | Abort with install instructions |
| architecture.yaml missing | File read fails | Skip E-04 and E-07, note in report |
| quality-grades.yaml missing | File read fails | Skip E-08, note in report |
| grade-history.yaml missing | File read fails | Skip E-08, note in report |
| Issue creation fails | br create returns non-zero | Log error, continue to next finding |
| 20-issue limit reached | Counter tracking | Stop creating, note remaining in report |
| Phase 2 abort | Unrecoverable error | Report partial results, still sync |

## Grade Change Events

| Event | Severity | Action |
|-------|----------|--------|
| Grade regression (any component) | P0 if overall drops, P1 if component | Create beads bug issue |
| Grade improvement | Informational | Close corresponding beads issue if exists |
| No grade history exists | Expected at init | First run establishes baseline |
| Grade file write fails | Error | Log error, do not update history |

## Init Failures

| Failure | Detection | Recovery |
|---------|-----------|----------|
| check_env fails | Exit code 1 | Fix prerequisite before retrying |
| Cycle in architecture.yaml | check_cycles returns non-empty | Fix calls[] before proceeding |
| Symlink creation fails | ln -s returns non-zero | Check permissions, create manually |
| ecosystem.yaml write fails | YAML write error | Surface for manual edit |
| Registry write fails | YAML write error | Surface for manual edit |

## Pre-Bash Hook Failures

| Failure | Detection | Recovery |
|---------|-----------|----------|
| architecture.yaml missing | File not found | Skip arch check, allow command |
| architecture.yaml parse error | yaml.safe_load raises | Skip arch check, allow command |
| Violation detected | calls[] mismatch | Log warning, allow command (never block) |
| Log file write fails | IOError | Silently continue (never block user) |
