# Guide Generation Reference

Per-session topic guide generation for study paths. Guides are comprehensive,
web-sourced documents that serve as the single source of truth for teaching.

## Slug Generation Rule

Lowercase topic name → replace `(`, `)`, `/`, `&` with empty → replace spaces
and remaining special chars with hyphens → collapse consecutive hyphens →
strip leading/trailing hyphens → append `.md`

| Topic Name | Filename |
|---|---|
| Network Address Translation (NAT) | `network-address-translation-nat.md` |
| VPC Endpoints (Interface and Gateway) | `vpc-endpoints-interface-and-gateway.md` |
| IRSA (IAM Roles for Service Accounts) | `irsa-iam-roles-for-service-accounts.md` |
| aws-iam-authenticator | `aws-iam-authenticator.md` |
| Network ACLs (NACLs) | `network-acls-nacls.md` |

## Guide Template

Every guide follows this structure:

```markdown
# {Topic Name}

> {One-line description from KB}

## Why This Exists
Problem statement and motivation. What was the world like before this
existed? What pain point or architectural need drove its creation?
Ground the reader in the motivation before any mechanics.

## Core Concepts
The foundational mental model. Define all key terms. Explain the "what"
at a level sufficient for the `conceptual` mastery level. Use analogies
where they genuinely clarify. No hand-waving.

## How It Works
Deep dive into mechanics and internals. This section takes a reader from
"I get the concept" to "I understand the implementation." Cover:
- Architecture / internal components
- Data flow / request lifecycle
- Protocol details where relevant
- Configuration and key parameters

## Deep Dive
Internals, implementation specifics, protocol-level details, advanced
configuration. The nitty-gritty that separates surface understanding from
true expertise. Supports `proficient`+ understanding.

## Practical Application
Real-world usage patterns. How to actually use this, with concrete
examples. CLI commands, configuration snippets, deployment patterns.
Calibrated for the `applied` mastery level.

## Failure Modes and Pitfalls
What goes wrong. Common misconfigurations, debugging approaches,
security considerations, performance gotchas. This section supports
QUIZ and SCENARIO mode question generation.

## Relationship to Other Topics

### Prerequisites
{For each prerequisite from KB — read the prerequisite's KB entry to
understand the connection}: Why this dependency exists, what concepts
from the prerequisite carry forward into this topic.

### Related Topics
{For each related topic from KB — read the related topic's KB entry}:
How they interact, compare, or complement each other. Cross-cutting
concerns and integration points.

## Key Takeaways
3-5 bullet points capturing the essential understanding. A reader who
internalizes these can pass a conceptual-level quiz.

## Further Reading
- [Official documentation]({url})
- [RFC/specification]({url}) (where applicable)
- [Recommended deep-dive article or video]({url})
- {Preserved original source_context reference, if any}

---
*Last updated: {YYYY-MM-DD}*
```

## Guide Generation Instructions

For each topic:

1. Read the topic's full KB entry (name, description, difficulty, prerequisites,
   related, tags, source_context)
2. Read KB entries for all prerequisite and related topics (to write the
   Relationship section accurately)
3. Capture the existing `source_context` value — if non-null and non-path,
   preserve it for the Further Reading section
4. Perform web research using WebSearch:
   - Official documentation (AWS docs, K8s docs, IETF RFCs, Linux man pages)
   - Current best practices and recent changes (2025-2026)
   - Architectural explanations from authoritative sources
   - Known issues, deprecations, or migration paths
5. Write the guide following the template — all sections must have substantive
   content
6. Verify external links are real URLs (not fabricated)

## Guide Enrichment Instructions

When the user requests deeper coverage for an existing guide:

1. Read the existing guide
2. Perform additional web research focusing on areas the existing guide covers
   thinly
3. Expand all sections — particularly "Deep Dive", "How It Works", and
   "Failure Modes"
4. Add new external resource links
5. Overwrite the guide file with the expanded version
6. `source_context` does not change (already points to this file)

## Quality Criteria

- Every section in the template must have substantive content (not stubs or
  one-liners)
- At least 3 external resource links with real, working URLs
- All prerequisite and related topic connections explained with specifics
- No hand-waving on technical details — the guide replaces general knowledge
- The guide must be self-contained: a reader should be able to understand the
  topic from this document alone
