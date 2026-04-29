# Hook Changes for dispatch-harness

These changes extend `~/.claude/skills/dispatch/.claude/hooks/pre_bash_guard.py`.

## Current Hook Structure

The hook currently:
1. Reads JSON on stdin (tool_input with command field)
2. Checks if command matches GIT_WRITE_PATTERNS
3. If git write: checks dispatch.db for active task git_permission
4. Logs all commands to bash_log
5. Returns JSON with decision (allow/block)

## New Function: check_architecture_constraint

Add AFTER the `is_git_write_command` function and BEFORE `main()`:

```python
ARCH_PATH = Path(os.path.expanduser("~/.zsh/dispatch/contracts/architecture.yaml"))
ARCH_VIOLATIONS_LOG = Path(os.path.expanduser("~/.zsh/dispatch/harness/arch-violations.log"))

SKILL_INVOKE_PATTERNS = [
    r"/(\w[\w-]+)",           # /<slug> invocation
    r"claude\s+-p\s+\S*?/agent-skills/(\w[\w-]+)",  # claude -p with skill path
]

def check_architecture_constraint(command: str) -> str | None:
    """
    Parse skill slug from command, check against architecture.yaml.
    Returns warning message if violation detected, None otherwise.
    Never blocks -- violations are warnings only.
    """
    if not ARCH_PATH.exists():
        return None

    try:
        import yaml
        arch = yaml.safe_load(ARCH_PATH.read_text())
    except Exception:
        return None

    dep_order = arch.get("dependency_order", [])
    known_slugs = {entry["slug"] for entry in dep_order}
    calls_map = {entry["slug"]: set(entry.get("calls", [])) for entry in dep_order}

    # Detect which skill is being invoked
    called_slug = None
    for pattern in SKILL_INVOKE_PATTERNS:
        match = re.search(pattern, command)
        if match:
            candidate = match.group(1)
            if candidate in known_slugs:
                called_slug = candidate
                break

    if not called_slug:
        return None

    # Determine calling context (best effort from cwd or env)
    # This is approximate -- the hook doesn't always know the calling skill
    calling_slug = os.environ.get("DISPATCH_SKILL_CONTEXT", "unknown")

    if calling_slug == "unknown" or calling_slug == called_slug:
        return None

    declared_calls = calls_map.get(calling_slug, set())
    if called_slug not in declared_calls:
        warning = (
            f"ARCH WARN: {calling_slug} -> {called_slug} "
            f"not declared in architecture.yaml"
        )
        _log_arch_violation(calling_slug, called_slug, command[:80])
        return warning

    return None


def _log_arch_violation(calling: str, called: str, command_snippet: str) -> None:
    """Append violation to arch-violations.log."""
    try:
        ARCH_VIOLATIONS_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(ARCH_VIOLATIONS_LOG, "a") as f:
            f.write(
                f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} "
                f"{calling} -> {called} "
                f"cmd: {command_snippet}\n"
            )
    except Exception:
        pass
```

## Integration into main()

In `main()`, add the architecture check AFTER the git check and BEFORE the
final allow. The architecture check WARNS but does NOT block:

```python
def main():
    # ... (existing stdin parsing) ...

    # ... (existing git write check -- may exit 2 to block) ...

    # Architecture constraint check (warn only, never block)
    arch_warning = check_architecture_constraint(command)
    if arch_warning:
        # Log but do not block
        log_command(conn, command, blocked=False, block_reason=arch_warning)

    # ... (existing final log and allow) ...
```

## session.yaml Extension

When a violation is detected, also record it in the session if accessible:

```python
# Optional: append to session.yaml arch_violations[] if session path known
# This is a nice-to-have, not required for the hook to function
```

## Important Notes

- The architecture check NEVER blocks (exit 0 always for arch violations)
- The architecture check NEVER replaces the git write check
- If architecture.yaml is missing, skip silently
- If YAML parsing fails, skip silently
- The log file is append-only, never truncated by the hook
- The `DISPATCH_SKILL_CONTEXT` env var is set by dispatch_runner.py when invoking sub-skills (future -- currently a stub)
