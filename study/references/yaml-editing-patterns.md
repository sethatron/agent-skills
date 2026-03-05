# YAML Editing Patterns

Knowledge base path: `/Users/sethallen/agent-skills/study/knowledge-base.yaml` (symlink to the canonical location).

Indentation structure: 0 (category) -> 2 (subcategory) -> 4 (array `- name:`) -> 6 (topic fields).

All edits use the Edit tool with targeted string replacement. Every pattern below shows the exact `old_string` and `new_string` values.

---

## Pattern 1: Update a Topic's Status

The Edit tool requires `old_string` to be unique in the file. Since many topics share the same status value, you MUST include the unique `name` and enough surrounding context to guarantee uniqueness.

### Example: Topic with string source_context

```
old_string:
    - name: "veth pair"
      description: "Virtual Ethernet device pair — two linked virtual NICs where traffic into one exits the other; used to connect Linux network namespaces"
      difficulty: 3
      priority: high
      prerequisites: ["Network Namespace", "Linux Namespaces"]
      related: ["Container Network Interface (CNI)", "overlay network"]
      tags: [linux, containers, networking]
      status: not_started
      source_context: "kubernetes-internals-guide, Part III Chapter 3"

new_string:
    - name: "veth pair"
      description: "Virtual Ethernet device pair — two linked virtual NICs where traffic into one exits the other; used to connect Linux network namespaces"
      difficulty: 3
      priority: high
      prerequisites: ["Network Namespace", "Linux Namespaces"]
      related: ["Container Network Interface (CNI)", "overlay network"]
      tags: [linux, containers, networking]
      status: exposed
      source_context: "kubernetes-internals-guide, Part III Chapter 3"
```

### Example: Topic with null source_context

```
old_string:
    - name: "Network Address Translation (NAT)"
      description: "Rewriting source or destination IP/port in packet headers as they traverse a router or firewall"
      difficulty: 2
      priority: critical
      prerequisites: []
      related: ["DNAT", "iptables", "kube-proxy"]
      tags: [networking, fundamentals]
      status: not_started
      source_context: null

new_string:
    - name: "Network Address Translation (NAT)"
      description: "Rewriting source or destination IP/port in packet headers as they traverse a router or firewall"
      difficulty: 2
      priority: critical
      prerequisites: []
      related: ["DNAT", "iptables", "kube-proxy"]
      tags: [networking, fundamentals]
      status: exposed
      source_context: null
```

---

## Pattern 2: Add level_up_evidence (First Promotion)

When a topic has no existing `level_up_evidence`, append it after the `source_context` line. Include the `name` line in the `old_string` for uniqueness if the `status` + `source_context` combination isn't unique (multiple topics can share both `status: not_started` and `source_context: null`).

```
old_string:
    - name: "veth pair"
      description: "Virtual Ethernet device pair — two linked virtual NICs where traffic into one exits the other; used to connect Linux network namespaces"
      difficulty: 3
      priority: high
      prerequisites: ["Network Namespace", "Linux Namespaces"]
      related: ["Container Network Interface (CNI)", "overlay network"]
      tags: [linux, containers, networking]
      status: not_started
      source_context: "kubernetes-internals-guide, Part III Chapter 3"

new_string:
    - name: "veth pair"
      description: "Virtual Ethernet device pair — two linked virtual NICs where traffic into one exits the other; used to connect Linux network namespaces"
      difficulty: 3
      priority: high
      prerequisites: ["Network Namespace", "Linux Namespaces"]
      related: ["Container Network Interface (CNI)", "overlay network"]
      tags: [linux, containers, networking]
      status: exposed
      source_context: "kubernetes-internals-guide, Part III Chapter 3"
      level_up_evidence:
        - from_level: not_started
          to_level: exposed
          timestamp: "2026-03-04T14:30:00Z"
          method: learn
          summary: "Completed LEARN session; engaged with explanation"
```

---

## Pattern 3: Append to Existing level_up_evidence

Find the last evidence entry's `summary` line and append after it. If the summary text isn't unique across all evidence entries in the file, include more preceding context (the `from_level`, `to_level`, `timestamp` lines) to ensure uniqueness.

```
old_string:
          summary: "Completed LEARN session; engaged with explanation"

new_string:
          summary: "Completed LEARN session; engaged with explanation"
        - from_level: exposed
          to_level: conceptual
          timestamp: "2026-03-05T10:00:00Z"
          method: quiz
          summary: "Correctly explained why veth pairs exist and how they connect network namespaces"
```

---

## Pattern 4: Add a New Topic to an Existing Subcategory

Find the last topic in the target subcategory (its `source_context` line) and append. Include the next section header in both old and new strings to anchor the edit precisely.

```
old_string:
      source_context: "last-topic-source-context"

next_category_or_subcategory_header:

new_string:
      source_context: "last-topic-source-context"

    - name: "New Topic Name"
      description: "One-line description"
      difficulty: 3
      priority: medium
      prerequisites: []
      related: []
      tags: []
      status: not_started
      source_context: null

next_category_or_subcategory_header:
```

---

## Safety Rules

1. **ALWAYS** read the topic's current state before editing. Grep for its name, then Read the surrounding lines to get the full block.
2. **NEVER** use bare `status: not_started` as `old_string` — it matches many lines and the Edit will fail or hit the wrong target.
3. **ALWAYS** include the topic's unique `name` line in the Edit context to guarantee uniqueness.
4. **After editing**, Read the modified lines back to verify YAML validity (correct indentation, no broken structure).
5. When a topic has `source_context: null`, match the literal string `null`, not an empty string or quotes.
6. Get the timestamp via `date -u +"%Y-%m-%dT%H:%M:%SZ"` before writing any evidence entry. Never fabricate or hardcode timestamps.
7. Preserve exact indentation: 4 spaces for `- name:`, 6 spaces for fields, 6 spaces for `level_up_evidence:`, 8 spaces for `- from_level:`, 10 spaces for evidence fields.
