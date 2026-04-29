# Manual Recovery Procedures

## Restore Any Skill from Backup

```bash
# List available backups
ls /Users/sethallen/agent-skills/<skill>/backups/

# Copy backup over current files (preserves backup)
cp -r /Users/sethallen/agent-skills/<skill>/backups/<ver>_<timestamp>/* \
      /Users/sethallen/agent-skills/<skill>/
```

## Rebuild Symlinks

```bash
# Verify current state
ls -la ~/.claude/skills/

# Recreate a broken symlink
ln -sf /Users/sethallen/agent-skills/<skill>/ ~/.claude/skills/<skill>

# Core skill symlinks:
ln -sf /Users/sethallen/agent-skills/jira/ ~/.claude/skills/jira
ln -sf /Users/sethallen/agent-skills/gitlab-mr-review/ ~/.claude/skills/gitlab-mr-review
ln -sf /Users/sethallen/agent-skills/gitlab-mr-review/ ~/.claude/skills/mr-review
ln -sf /Users/sethallen/agent-skills/dispatch/ ~/.claude/skills/dispatch
ln -sf /Users/sethallen/agent-skills/dispatch-manager/ ~/.claude/skills/dispatch-manager
```

## Reset registry.yaml

If `contracts/registry.yaml` is corrupted:

1. The canonical copy is version-controlled in the git repo:
   ```bash
   cd /Users/sethallen/agent-skills
   git checkout -- dispatch-manager/contracts/registry.yaml
   ```

2. If git state is also broken, re-discover contracts manually:
   - Read jira SKILL.md → find JIRA_CALLER section
   - Read gitlab-mr-review review_writer.py → extract FRONTMATTER_FIELDS
   - Check directory existence for artifact paths
   - Write a fresh registry.yaml following the schema in `references/contract-guide.md`

## Re-run DSI Validation

```bash
cd /Users/sethallen/agent-skills/dispatch-manager

# Validate a specific skill
python scripts/dsi_validator.py /Users/sethallen/agent-skills/<skill> --type B --verbose

# Validate all managed skills
for skill in jira gitlab-mr-review dispatch dispatch-manager; do
    echo "=== $skill ==="
    python scripts/dsi_validator.py /Users/sethallen/agent-skills/$skill --verbose
done
```

## Re-run Contract Validation

```bash
python scripts/contract_validator.py --verbose
```

## When dispatch-manager Itself Is Broken

If dispatch-manager is non-functional:

1. **Check the symlink first**:
   ```bash
   ls -la ~/.claude/skills/dispatch-manager
   ```

2. **Restore from backup**:
   ```bash
   ls /Users/sethallen/agent-skills/dispatch-manager/backups/
   cp -r /Users/sethallen/agent-skills/dispatch-manager/backups/<latest>/* \
         /Users/sethallen/agent-skills/dispatch-manager/
   ```

3. **Restore from git**:
   ```bash
   cd /Users/sethallen/agent-skills
   git checkout -- dispatch-manager/
   ```

4. **Nuclear option — re-scaffold**:
   Delete and re-create:
   ```bash
   rm -rf /Users/sethallen/agent-skills/dispatch-manager
   rm ~/.claude/skills/dispatch-manager
   ```
   Then re-run the skill creation process.

5. **Other skills still work**: dispatch-manager being broken does NOT affect
   /jira, /mr-review, or /dispatch. They operate independently. Only ecosystem
   management features (validation, contract checking, skill creation) are
   affected.

## Verify Recovery

After any recovery action:

```bash
python scripts/check_env.py --verbose
python scripts/dsi_validator.py /Users/sethallen/agent-skills/dispatch-manager --type B --verbose
python scripts/contract_validator.py --verbose
```

All three must pass before considering recovery complete.
