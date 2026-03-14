# Knowledge Base Enrichment Guide

How to analyze an existing knowledge base and enrich its relationships, coverage, and descriptions.

## Core Principle: Preserve What Exists

Enrichment is additive. Never delete or overwrite existing work.

- Never delete topics, statuses, or level_up_evidence
- Only add to `related` and `prerequisites` arrays, never remove entries
- Expand descriptions by appending detail, not rewriting from scratch
- Never change `status` or `source_context` during enrichment

## Mode 1: Graph Enrichment

Audit the KB's internal structure. Run these 6 checks in order:

### Check 1: Missing Bidirectional Relationships

If topic A lists B in its `related` array, B should list A. Scan all topics, collect every `related` pair, flag one-directional links.

### Check 2: Empty `related` Arrays

Every topic should have at least 1 related topic. Topics with `related: []` are disconnected from the knowledge graph. Find the most natural sibling or cross-cutting connection.

### Check 3: Missing Prerequisite Links

Look for:
- Advanced topics (difficulty 4-5) with empty prerequisites
- Topics that reference concepts in their description that exist as other topics but aren't listed as prerequisites
- Implicit dependency chains — if A requires B and B requires C, A may also need C listed if the chain isn't obvious

### Check 4: Terse Descriptions

Descriptions under ~10 words or that only say what something does without saying what it IS. A good description defines the concept, not just its function. Expand to 15-30 words covering what it is, why it matters, or how it relates to the domain.

### Check 5: Disconnected Clusters

Groups of topics connected to each other but linked to the rest of the graph by 0-1 edges. These clusters are isolated knowledge islands. Add `related` links between the cluster and the main graph where genuine conceptual connections exist.

### Check 6: Missing Bridging Topics

After checks 1-5, identify genuine gaps — concepts that connect existing clusters but don't have their own topic. Only add bridging topics if:
- The concept is real and would take effort to learn
- It naturally connects 2+ existing topics
- It isn't already covered by an existing topic under a different name

New bridging topics use: `status: not_started`, `source_context: null`.

## Mode 2: Source-Enriched

Use an external source to identify coverage gaps.

### Source Type: Web Research

Syntax: `enrich [topic] with "search query"` (e.g., `enrich devops with "ANS-C01 exam"`)

1. WebSearch the source query to compile the topic landscape (exam domains, documentation outline, technology coverage areas)
2. Extract a flat list of concepts/topics the source covers
3. Diff against the KB (see Diffing Methodology below)
4. Propose additions based on gaps

### Source Type: Local Documentation

Syntax: `enrich [topic] with /path/to/docs`

1. Glob for readable files (`.md`, `.txt`, `.rst`, `.yaml`, etc.)
2. Read key files — focus on architecture docs, API references, concept guides
3. Extract concepts, terminology, and relationships
4. Diff against the KB

### Source Type: GitHub Repository

Syntax: `enrich [topic] with https://github.com/user/repo`

1. Clone shallow: `git clone --depth 1` to a temp directory
2. Analyze like a local project — README, structure, key source files
3. Extract concepts and patterns
4. Diff against the KB

## Diffing Methodology

After compiling topics from the external source, categorize each against the KB:

| Category | Meaning | Action |
|---|---|---|
| Missing entirely | Source covers it, KB doesn't have it | Propose as new topic |
| Partial coverage | KB has a related topic but doesn't cover this angle | Propose description expansion or new topic |
| Adequate | KB covers it sufficiently | No action |
| Deeper than KB | Source goes deeper than KB's current description | Propose description expansion |

For certification exams specifically:
- Map exam domains/objectives to KB categories
- Calculate approximate coverage % per domain
- Flag domains below ~60% coverage as priority gaps

## Plan Format

Present a structured plan before making any edits. The plan must include:

### Summary
- Total proposed changes (new topics, relationship additions, description expansions, prerequisite additions)
- Before/after projections (topic count, avg relationships per topic)

### New Topics Table

| Topic | Category > Subcategory | Difficulty | Priority | Prerequisites | Related |
|---|---|---|---|---|---|

### Relationship Additions Table

| Topic | Adding to `related` | Reason |
|---|---|---|

### Description Expansions Table

| Topic | Current Description | Proposed Description |
|---|---|---|

### Prerequisite Additions Table

| Topic | Adding to `prerequisites` | Reason |
|---|---|---|

The user approves all, selectively approves, or requests modifications before any edits are made.

## YAML Editing Patterns for Enrichment

All edits use the Edit tool. See `yaml-editing-patterns.md` for the full pattern library.

### Modifying a `related` Array

Include the full topic block from `- name:` through `source_context:` (or through the end of `level_up_evidence` if present) in the `old_string` to guarantee uniqueness. Change only the `related` line.

```
old_string:
    - name: "Topic A"
      description: "Description of topic A"
      difficulty: 3
      priority: high
      prerequisites: ["Topic B"]
      related: ["Topic C"]
      tags: [networking]
      status: exposed
      source_context: null

new_string:
    - name: "Topic A"
      description: "Description of topic A"
      difficulty: 3
      priority: high
      prerequisites: ["Topic B"]
      related: ["Topic C", "Topic D", "Topic E"]
      tags: [networking]
      status: exposed
      source_context: null
```

### Adding New Topics

Use Pattern 4 from `yaml-editing-patterns.md` — find the last topic in the target subcategory and append before the next section header. All new enrichment topics use:

```yaml
      status: not_started
      source_context: null
```

### Expanding Descriptions

Same approach as modifying `related` — include the full topic block, change only the `description` field.

### Modifying `prerequisites`

Same approach — include the full topic block, change only the `prerequisites` line.

## Validation Checklist

Run after all enrichment edits are complete:

1. **DAG validation:** `python3 {skill_source}/scripts/kb-dag.py --kb {kb_path} --validate`
   - No broken references (every name in `prerequisites` and `related` exists as a topic)
   - No cycles in prerequisites
2. **Stats comparison:** `python3 {skill_source}/scripts/kb-stats.py {kb_path}`
   - Topic count matches expected (baseline + new topics added)
   - No status changes from baseline (enrichment doesn't modify status)
3. **Spot-check:** Read 2-3 modified topics back from the file to verify YAML validity and correct indentation
