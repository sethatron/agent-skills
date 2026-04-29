# Contract Registry Guide

## Location

`/Users/sethallen/agent-skills/dispatch-manager/contracts/registry.yaml`

## Structure

```yaml
version: "1.0"
last_updated: "YYYY-MM-DD"
updated_by: "<subcommand>"

contracts:
  <contract_id>:
    description: "..."
    ...contract-specific fields...
    consumers: [<skills>]
    producers: [<skills>]
```

## Mutation Rules

### Immutable Fields
Fields listed in a contract's `immutable_fields` can NEVER be:
- Renamed
- Retyped (changed from string to int, etc.)
- Removed

This is enforced BEFORE confirmation, BEFORE backup, BEFORE execution.
No exception path exists.

### Permitted Operations
- **Append** new fields to an `extensible: true` contract
- **Add** a new contract for a new TYPE A/C skill
- **Add** a new caller to `jira_caller.known_callers`

### Blocked Operations
- **Rename** any field in any existing contract
- **Retype** any field in any existing contract
- **Remove** any field from any existing contract
- **Remove** a contract while its producer skill is still registered

## Adding a New Skill Contract

When a TYPE A or C skill is registered, dispatch-manager appends a new
contract entry under the `contracts:` key:

```yaml
  <slug>_artifact:
    description: "Artifact frontmatter for <slug>"
    schema_version: "1.0"
    required_fields: [skill_name, skill_version, produced_at, artifact_path, status]
    custom_fields: [<fields from interview>]
    immutable_fields: [skill_name, skill_version, produced_at, artifact_path, status, <custom>]
    extensible: true
    producer: <slug>
    consumers: [dispatch]
```

## New Caller Registration

When a skill that invokes /jira is registered, append to `jira_caller.known_callers`:

```yaml
- { value: <slug>, skill: <slug> }
```

## Reading the Registry Programmatically

```python
import yaml
from pathlib import Path

registry = yaml.safe_load(Path("contracts/registry.yaml").read_text())
for contract_id, contract in registry["contracts"].items():
    print(f"{contract_id}: {contract['description']}")
```

## Validating Contracts

```bash
python scripts/contract_validator.py --verbose
```

This reads registry.yaml and checks each contract against live files.
Exit 0 = all valid. Non-zero = drift detected.
