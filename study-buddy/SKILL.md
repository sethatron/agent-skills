---
name: study-buddy
description: >-
  Multi-topic study orchestrator. Manages multiple knowledge bases (DevOps,
  project codebases, certifications) each with independent progress tracking.
  Use when the user says "/study-buddy", "study-buddy", "study buddy",
  "switch topic", "generate kb", "generate knowledge base", "enrich",
  "enrich kb", "enrich knowledge base", "add coverage for", "fill gaps",
  "find missing topics", "resume path", "show path", "path status",
  "list paths", "my paths", "generate guides", "expand guide",
  "deeper guide", "guide for", "sandbox", "sandbox challenge",
  or references a specific study topic by name.
  Delegates to the study engine skill for actual learning interactions.
---

# Study Buddy — Multi-Topic Orchestrator

Manages multiple study topics, each with its own knowledge base and progress. Delegates to the study engine skill (`/study`) for actual learning interactions (LEARN, QUIZ, SCENARIO, PROJECT, MASTERY CHALLENGE, STATUS, PATH).

## Data Root

```
/Users/sethallen/DSP/SEIJIV2/_meta/study-buddy/
```

Global config: `{data_root}/config.yaml`

## Topic Discovery

A **topic** is any subdirectory of the data root that contains a `study.yaml` file. No registry to maintain — adding a topic is creating a directory with `study.yaml` and `knowledge-base.yaml`.

To discover topics:
1. List subdirectories of the data root (exclude `.git`, `node_modules`, hidden dirs)
2. For each subdirectory, check if `study.yaml` exists
3. Each match is a topic; the directory name is the **slug** (e.g., `devops`, `archon`)

## Commands

### `/study-buddy` (no arguments) — List Topics

1. Discover all topics
2. For each topic, read `study.yaml` to get `name` and `description`
3. Run the stats script against each topic's KB for a one-line summary
4. Display a table:

```
Available Topics:

  devops    DevOps & Platform Engineering    42/209 engaged
  archon    Archon Framework                 0/87 engaged

Use /study-buddy [topic] to start studying.
```

### `/study-buddy [topic]` — Activate Topic

1. Discover topics and match the argument to a slug (case-insensitive, partial match OK if unambiguous)
2. If no match, list available topics
3. Load the topic's `study.yaml`
4. Resolve paths (see Path Resolution below)
5. Read the study engine's SKILL.md from `{skill_source}/SKILL.md`
6. Run: `python3 {skill_source}/scripts/kb-stats.py {kb_path}`
7. Enter study mode following the study engine's behavioral spec

**Path Override — CRITICAL:** When executing the study engine's behavior for the active topic, replace ALL hardcoded paths from the study engine's SKILL.md with the resolved paths below. The study engine's SKILL.md references its own default KB; you MUST use the topic's KB instead.

### `/study-buddy generate [source]` — Generate New Topic

See the Generation section below.

### `/study-buddy enrich [topic]` — Enrich Existing KB

See the Enrichment section below.

## Path Resolution

Given a topic at `{data_root}/{slug}/`:

| Resource | Path |
|---|---|
| Knowledge base | `{data_root}/{slug}/knowledge-base.yaml` |
| study.yaml | `{data_root}/{slug}/study.yaml` |
| Skill source | `study.yaml` → `skill.source`, falling back to `config.yaml` → `defaults.skill_source` |
| Stats script | `python3 {skill_source}/scripts/kb-stats.py {kb_path}` |
| DAG script | `python3 {skill_source}/scripts/kb-dag.py --kb {kb_path}` |
| Skill SKILL.md | `{skill_source}/SKILL.md` |
| Skill references | `{skill_source}/references/` |
| Saved paths | `{data_root}/{slug}/paths/*.yaml` |
| Topic guides | `{data_root}/{slug}/docs/` |
| Sandbox challenges | `{data_root}/{slug}/sandbox/` |

### Path Override Instructions

When operating in study mode for an active topic, use these paths **instead of** any hardcoded paths in the study engine's SKILL.md:

- **Knowledge base:** `{data_root}/{slug}/knowledge-base.yaml` (replaces the study engine's default KB path)
- **Stats command:** `python3 {skill_source}/scripts/kb-stats.py {data_root}/{slug}/knowledge-base.yaml`
- **DAG command:** `python3 {skill_source}/scripts/kb-dag.py --kb {data_root}/{slug}/knowledge-base.yaml`
- **Reference docs:** read from `{skill_source}/references/` (unchanged — these are engine docs, not topic-specific)
- **KB edits:** all Edit tool operations target `{data_root}/{slug}/knowledge-base.yaml`
- **YAML editing patterns:** the patterns in `{skill_source}/references/yaml-editing-patterns.md` apply, but the file path is the topic's KB
- **Topic guides:** when `source_context` is a relative path ending in `.md`, resolve to `{data_root}/{slug}/{source_context}`. The study engine should Read this resolved path to ground its teaching.
- **Sandbox directory:** `{data_root}/{slug}/sandbox/`. The study engine generates sandbox files here, using the topic slug as the subdirectory name. The slug rule is the same as for guide filenames (defined in `references/guide-generation.md`).

## Study Mode Behavior

Once a topic is activated, all study interactions follow the study engine's SKILL.md exactly, with the path overrides above. The user interacts normally — "teach me X", "quiz me on Y", "study status" — and the orchestrator transparently routes to the correct KB.

**Exception — ad-hoc prerequisites:** When an active path exists and LEARN mode flags a prerequisite gap that the user chooses to address, the orchestrator performs additional steps (guide generation, path update) before delegating to the study engine. See "Ad-Hoc Prerequisite Handling During Path Execution" below.

The user can switch topics at any time with `/study-buddy [other-topic]`.

## Ad-Hoc Prerequisite Handling During Path Execution

**Trigger:** During LEARN mode with an active path, the study engine flags a prerequisite gap (interaction-modes.md step 3) and the user chooses to learn the prerequisite first.

**Flow:**

1. **Check for active path.** If no path is active, skip — delegate to study engine normally (no guide generation, no path update).
2. **Check if already in current or earlier session.** If the prerequisite topic already appears in the current session or a completed earlier session, skip steps 3-4 — it's already tracked. Proceed directly to step 5.
3. **Add to current session in path YAML.** Prepend the topic to the current session's `topics` list so it comes before the topic that needs it. Use `mode: LEARN` and `target: exposed` (minimum useful prerequisite level). Update `summary.topics_covered` count (+1). Use the Edit tool with the session header + first existing topic as the `old_string` anchor.
4. **Handle duplicates in later sessions.** If the topic appears in a later session, leave it — the derivation logic will auto-complete that entry once the KB status reaches the target. No modification needed.
5. **Generate guide if missing.** Compute the expected guide filename using the slug rule from `references/guide-generation.md`. Check if `{data_root}/{slug}/docs/{topic-slug}.md` exists.
   - If missing: generate following `references/guide-generation.md` instructions (web research, full template, all sections substantive). If the topic's current `source_context` is a non-path string, capture it in the guide's Further Reading section.
   - After writing: update `source_context` in the KB to point to the guide (e.g., `"docs/x-509-certificate.md"`). Use the full topic block as `old_string` per yaml-editing-patterns.md Pattern 1 / Safety Rule 3.
   - If guide already exists: report "Guide for {topic} already exists."
6. **Depth prompt.** Same as `resume path` step 7 — ask if the user wants the guide expanded with a more comprehensive deep-dive before proceeding. This applies to all guides, including freshly generated ones.
7. **Delegate to study engine.** The topic now has a guide (`source_context` points to `.md` file). Proceed with LEARN mode step 4 using the guide-first flow (present path → summary → verification questions).

**Recursive prerequisites:** If the pulled-forward prerequisite itself has prerequisites at `not_started`, the LEARN flow for that topic will flag them (step 3), and this entire ad-hoc handling flow triggers again. Each level is handled one topic at a time.

**Path YAML edit pattern:** To prepend a topic to a session, use the Edit tool:

```
old_string:
  - number: N
    theme: "Session Theme"
    topics:
      - name: "First Existing Topic"
        mode: LEARN
        target: exposed

new_string:
  - number: N
    theme: "Session Theme"
    topics:
      - name: "New Prerequisite Topic"
        mode: LEARN
        target: exposed
      - name: "First Existing Topic"
        mode: LEARN
        target: exposed
```

Include enough of the first existing topic entry (all 3 fields) to guarantee uniqueness.

## Paths — Saved Learning Plans

A **path** is a YAML file in `{topic_dir}/paths/` that captures a sequenced learning plan.

### Path Discovery

Any `.yaml` file in `{data_root}/{slug}/paths/` is a path. The filename (without extension) is the path slug.

### Commands

#### `show paths` / `list paths` — List Available Paths
1. Glob `{data_root}/{active_topic}/paths/*.yaml`
2. For each path, read `name`, `status`, and `summary`
3. Compute progress: for each session, check if all topics have reached target in KB
4. Display table with name, status, sessions completed/total

#### `resume path [name]` — Resume a Path
1. Match path slug (partial, case-insensitive)
2. Load the path YAML
3. Compute session progress from KB (see derivation logic in `references/path-yaml-schema.md`)
4. Find the first incomplete session
5. **Generate guides for the session** (see Guide Generation below):
   - For each topic in the session, compute the expected guide filename using the slug rule
   - Check if `{data_root}/{slug}/docs/{topic-slug}.md` exists
   - If any are missing, generate them (read `references/guide-generation.md` for instructions)
   - Update `source_context` in the KB for each newly generated guide
   - If all exist, report: "All guides for Session N are up to date."
6. Within the session, find the first topic below its target
7. **Per-topic depth prompt** (before delegating each topic to the study engine):
   - Ask: "Before we dive into {topic}, would you like me to expand the existing guide with a more comprehensive deep-dive?"
   - If yes: follow the enrichment instructions in `references/guide-generation.md`, then proceed
   - If no: proceed directly
8. Display path progress summary, then delegate to study engine for that topic using the specified mode

#### `path status` — Detailed Path Progress
1. Load the active path (or ask which one if multiple are active)
2. For each session, compute completion from KB
3. Display session-by-session breakdown with per-topic status vs. target

## Guide Generation — Per-Session Topic Guides

Comprehensive guide documents are generated per-session during path resume.
The orchestrator handles all guide generation (web research, file writes, KB
updates) — the study engine only reads finished guides.

### Guide Discovery

Guides live in `{data_root}/{slug}/docs/`. The filename is derived from the
topic name using the slug conversion rule in `references/guide-generation.md`.
A guide exists if the computed file path resolves to an actual file.

### Generation Triggers

1. **Automatic on `resume path`**: missing guides for the current session's
   topics are generated before teaching begins (step 5 of resume path)
2. **User-requested enrichment**: user says "expand guide" or "deeper guide"
   for a specific topic — follow enrichment instructions in the reference doc
3. **Explicit**: user says "generate guides for session N" — generate all
   missing guides for that session
4. **Ad-hoc prerequisite pull-forward**: when a prerequisite topic is pulled
   forward during path execution (see Ad-Hoc Prerequisite Handling), a guide
   is generated before teaching begins — same generation flow as `resume path`
   step 5, including web research and KB `source_context` update

### KB Integration

After writing a guide file, update the topic's `source_context` in the KB
to point to the guide. Use Pattern 1 from `{skill_source}/references/yaml-editing-patterns.md`:
include the full topic block from `- name:` through `source_context:` (and
`resources:` if present) as the `old_string`, changing only the `source_context` value.

For topics where `source_context` is `null`, match the literal string `null`
(Safety Rule 5 from yaml-editing-patterns.md).

For topics where `source_context` has an existing non-path value (e.g.,
"kubernetes-internals-guide, Part III Chapter 3"), the old value is captured
in the guide's Further Reading section before being replaced.

## Generation — `/study-buddy generate [source]`

Creates a new topic from a project codebase, documentation, or URL.

### Supported Sources

| Source | Syntax | Handling |
|---|---|---|
| Local project | `/study-buddy generate /path/to/project` | Read files directly via Glob/Grep/Read |
| GitHub repo | `/study-buddy generate https://github.com/user/repo` | Clone via `git clone --depth 1` to temp dir, then analyze as local |
| Documentation | `/study-buddy generate /path/to/docs --type docs` | Documentation-only analysis (no source code) |

### Generation Flow

Read `references/kb-generation-guide.md` for the detailed methodology, then execute:

**Step 1: Accept input and determine topic slug**
- Parse the source argument (path or URL)
- Infer a slug from the source (e.g., "archon" from `/path/to/archon`, "repo-name" from GitHub URL)
- Ask the user to confirm or change the slug
- Verify `{data_root}/{slug}/` doesn't already exist

**Step 2: Analyze the source**
- Read `references/kb-generation-guide.md` for language-specific analysis instructions
- For local projects: README, dependency manifests, directory structure, key source files, existing docs
- For GitHub: clone shallow, then analyze as local
- Identify: tech stack, architecture, modules/packages, key interfaces, integration points, patterns

**Step 3: Generate the knowledge base**
- Design categories matching the project's architecture
- Extract topics (20-100+ depending on complexity)
- Set all required fields per topic: name, description, difficulty, priority, prerequisites, related, tags, status (all `not_started`), source_context, resources (optional — omit if no resources exist yet)
- Validate the DAG (no cycles, no unresolved prerequisites)
- Follow the exact YAML schema from the existing DevOps KB

**Step 4: Generate study.yaml**
```yaml
name: "{project name}"
description: "{one-line description}"
type: project
created: "{today's date}"

skill:
  source: {resolved default_skill_source from config.yaml}

source:
  path: {original source path}
  type: {detected language/type}

goals:
  - "{generated based on project analysis}"

tags: [{generated from tech stack}]
```

**Step 5: Write files and confirm**
- Create `{data_root}/{slug}/`
- Write `knowledge-base.yaml` and `study.yaml`
- Run stats: `python3 {skill_source}/scripts/kb-stats.py {data_root}/{slug}/knowledge-base.yaml`
- Report: "Topic '{name}' created with N topics across M categories. Use `/study-buddy {slug}` to start studying."

## Enrichment — `/study-buddy enrich [topic]`

Analyzes and enriches an existing KB's relationships, coverage, and descriptions.

### Syntax

| Syntax | Mode |
|---|---|
| `/study-buddy enrich [topic]` | Graph enrichment — audit internal structure |
| `/study-buddy enrich [topic] with [source]` | Source-enriched — diff against external material |

### Source Types (Mode 2)

| Source | Syntax Example |
|---|---|
| Web research | `enrich devops with "ANS-C01 exam"` |
| Local docs | `enrich devops with /path/to/docs` |
| GitHub repo | `enrich devops with https://github.com/user/repo` |

### Enrichment Flow

Read `references/kb-enrichment-guide.md` for the detailed methodology, then execute:

**Step 1: Load and snapshot**
- Resolve the topic slug to its KB path (same as topic activation)
- Read the full `knowledge-base.yaml`
- Run stats: `python3 {skill_source}/scripts/kb-stats.py {kb_path}`
- Record the baseline: topic count, relationship counts, category breakdown

**Step 2: Analyze** (mode-dependent)
- **Graph enrichment (no source):** Audit the DAG using the 6 checks from the enrichment guide — bidirectional links, empty related arrays, missing prerequisites, terse descriptions, disconnected clusters, missing bridging topics
- **Source-enriched (with source):** Analyze the external source (web search, read local docs, or clone repo), compile a topic landscape, diff against the KB using the methodology in the enrichment guide

**Step 3: Present plan for approval**
- Show a structured plan with tables: new topics, relationship additions, description expansions, prerequisite additions
- Include before/after projections (topic count, avg relationships per topic)
- Wait for user approval — all, selective, or modified

**Step 4: Execute approved changes**
- Add new topics with `status: not_started`, `source_context: null` (no `resources` block — added later when resources are generated)
- Enrich `related` arrays bidirectionally (if adding A→B, also add B→A)
- Expand descriptions by replacing the full topic block, changing only the description
- Add prerequisites where identified
- Preserve all existing statuses, evidence, source_context, and resources values

**Step 5: Validate and report**
- Run DAG validation: `python3 {skill_source}/scripts/kb-dag.py --kb {kb_path} --validate`
- Run stats: `python3 {skill_source}/scripts/kb-stats.py {kb_path}`
- Report before/after comparison: topics added, relationships added, descriptions expanded
