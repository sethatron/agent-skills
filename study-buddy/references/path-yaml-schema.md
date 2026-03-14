# Path YAML Schema Reference

A **path** is a saved learning plan stored as a YAML file. It captures a sequenced set of study sessions targeting a specific goal. Progress is **not** stored in the path — it is derived at runtime from the knowledge base.

## File Location

```
{data_root}/{slug}/paths/{goal-slug}.yaml
```

The filename (without extension) is the path slug. Example: `devops/paths/aws-networking-eks.yaml`.

## Schema

### Top-Level Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | string | yes | Human-readable path name |
| `goal` | string | yes | One-line description of the learning objective |
| `created` | string (YYYY-MM-DD) | yes | Date the path was generated |
| `status` | enum | yes | Current path state (see Status Enum) |

### `status` Enum

| Value | Meaning |
|---|---|
| `active` | Currently being worked through |
| `completed` | All sessions finished |
| `paused` | Temporarily suspended |
| `archived` | No longer relevant |

Only `status` is mutable after creation. All other fields are immutable.

### `summary` Block

| Field | Type | Description |
|---|---|---|
| `total_sessions` | int | Number of sessions in the path |
| `estimated_hours` | string | Time estimate range (e.g., "18-26") |
| `topics_covered` | int | Total topics across all sessions |
| `topics_deferred` | int | Topics excluded from this path |

### `external_prerequisites` List

Topics from outside this path's primary domain that must reach a sufficient level before certain sessions. Each entry:

| Field | Type | Description |
|---|---|---|
| `name` | string | Exact topic name as it appears in the KB |
| `category` | string | KB category the topic belongs to |
| `needed_before` | int | Session number that requires this topic |

### `deferred` List

Topic names (strings) that were considered but excluded from this path. Captured for future path expansion.

### `sessions` List

Ordered list of study sessions. Each session:

| Field | Type | Description |
|---|---|---|
| `number` | int | Session sequence number (1-indexed) |
| `theme` | string | Thematic label for the session |
| `topics` | list | Topics to cover in this session |

### Session `topics` Entry

Each topic has exactly 3 fields:

| Field | Type | Description |
|---|---|---|
| `name` | string | **Exact** match to the topic name in the knowledge base |
| `mode` | enum | Interaction mode for this topic |
| `target` | enum | Target mastery level after this session |

No other fields — descriptions, difficulty, priority, prerequisites all come from the KB.

### `mode` Enum

| Value | When Used |
|---|---|
| `LEARN` | Topic at `not_started` or `exposed` |
| `QUIZ` | Topic at `conceptual` |
| `SCENARIO` | Topic at `applied` |
| `MASTERY_CHALLENGE` | Topic at `proficient` |

### `target` Enum (Mastery Levels)

| Value | Order |
|---|---|
| `exposed` | 1 |
| `conceptual` | 2 |
| `applied` | 3 |
| `proficient` | 4 |
| `mastered` | 5 |

## Relationship to Knowledge Base

The path references topics by exact name. **All progress state is derived from the knowledge base at runtime**, not stored in the path. This eliminates dual-write consistency issues.

### Session Status Derivation Logic

When loading a path, compute each session's status by checking the KB:

| Derived Status | Condition |
|---|---|
| `completed` | Every topic in the session is at or above its `target` level in the KB |
| `in_progress` | At least one topic has been promoted beyond `not_started`, but not all are at target |
| `pending` | No topic in the session has been engaged (all at `not_started` or below their starting level) |

### Resume Logic

To find the next action when resuming a path:

1. Walk sessions in order
2. Find the first session that is not `completed`
3. Within that session, find the first topic whose KB status is below its `target`
4. Delegate to the study engine using that topic's `mode`

## Naming Convention

Path files use kebab-case slugs derived from the goal:

- "AWS Networking & EKS" → `aws-networking-eks.yaml`
- "CKA Certification Prep" → `cka-certification-prep.yaml`
- "Master K8s Auth" → `master-k8s-auth.yaml`

## Example

```yaml
name: "AWS Networking & EKS"
goal: "AWS networking and EKS operational expertise"
created: "2026-03-05"
status: active

summary:
  total_sessions: 12
  estimated_hours: "18-26"
  topics_covered: 47
  topics_deferred: 8

external_prerequisites:
  - name: "AWS IAM"
    category: identity
    needed_before: 11

deferred:
  - "IPv6 in VPC"
  - "Client VPN"

sessions:
  - number: 1
    theme: "Networking Foundations"
    topics:
      - name: "Network Address Translation (NAT)"
        mode: LEARN
        target: exposed
      - name: "IP Subnetting and CIDR Notation"
        mode: LEARN
        target: exposed
```
