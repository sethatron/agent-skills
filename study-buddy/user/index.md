# Study Buddy — User Guide

A multi-topic study system. Each topic gets its own knowledge base, its own progress tracking, and its own mastery journey — so you can study DevOps networking, a project codebase, and a new framework without any of them stepping on each other.

## Getting Started

| Command | What It Does |
|---|---|
| `/study-buddy` | List all topics with engagement stats |
| `/study-buddy [topic]` | Activate a topic and enter study mode |
| `/study-buddy generate [path-or-url]` | Generate a new topic from a codebase |
| `/study-buddy enrich [topic]` | Analyze and enrich an existing KB's relationships and coverage |
| `/study-buddy enrich [topic] with [source]` | Enrich a KB using an external source (cert exam, docs, repo) |

When you activate a topic, you get a stats summary (level distribution, priority gaps, recent activity) and then drop straight into study mode. From there, interact naturally — "teach me about X", "quiz me", "give me a scenario", "study status".

Switch topics at any time with `/study-buddy [other-topic]`.

**`/study-buddy` vs `/study`:** `/study-buddy` is the primary interface — it handles topic selection, path resolution, and delegates to the study engine. `/study` is a direct shortcut to the engine using its default KB. Use it when you want a quick session without topic switching overhead.

## Study Modes

Once a topic is active, all 7 modes work identically regardless of which topic you're in.

| Mode | Trigger Phrases | What It Does |
|------|----------------|--------------|
| LEARN | "teach me", "explain", "what is", "learn about" | Teach a topic from first principles, calibrated to current level |
| QUIZ | "quiz me", "test me", "check my knowledge" | Test knowledge with targeted questions |
| SCENARIO | "give me a scenario", "practice scenario", "troubleshoot" | Multi-topic real-world exercise |
| PROJECT | "assign me a project", "give me a project", "hands-on" | Hands-on buildable artifact |
| MASTERY CHALLENGE | "mastery challenge", "I'm ready to level up", "challenge me" | Formal 5-component assessment for proficient/mastered |
| STATUS | "study status", "progress", "how am I doing" | Progress dashboard with recommendations |
| PATH | "learning path", "study path", "study plan", "prep for" | Sequenced learning plan for a goal |

You don't always need an explicit trigger. If you ask a question that maps to a KB topic, the system recognizes it and can teach it in context, then offer to formalize the learning.

For detailed behavioral specs, prerequisites, and status update criteria for each mode, see the study engine's `interaction-modes.md` (located at `agent-skills/study/references/interaction-modes.md`).

## Mastery Levels

Every topic in every knowledge base progresses through 6 levels independently:

| Level | Name | What It Feels Like |
|-------|------|--------------------|
| 0 | not_started | You haven't encountered this yet. |
| 1 | exposed | You've heard about it and could recognize it in context, but couldn't explain it cold. |
| 2 | conceptual | You could whiteboard the concept and explain why it exists to a colleague. |
| 3 | applied | You've used it in a realistic scenario and understand the operational mechanics. |
| 4 | proficient | You can troubleshoot problems involving this, explain tradeoffs, and make design decisions. |
| 5 | mastered | You could teach a workshop on it, handle edge-case questions, and apply it creatively in unfamiliar contexts. |

**Key rules:**

- Levels must be reached in order (exception: LEARN can jump 2 levels max)
- `proficient` and `mastered` require a formal MASTERY CHALLENGE — they can't be reached through LEARN, QUIZ, or SCENARIO alone
- Every promotion records evidence with a timestamp and summary of what was demonstrated
- Topics are never demoted

Real-world experience counts. If you share work you've done — a script you wrote, an incident you debugged, infrastructure you built — and it demonstrates understanding of KB topics, the study buddy can record it as level-up evidence.

**Progress is per-topic.** Reaching `proficient` on a networking concept in your DevOps topic doesn't affect your status on that same concept in another topic's KB. Each topic is a completely independent mastery journey. When you generate a new topic, everything starts at `not_started`.

For complete promotion criteria, pass thresholds, anti-gaming rules, and the evidence schema, see the study engine's `level-system.md` (located at `agent-skills/study/references/level-system.md`).

## Recommended Workflows

### Daily Sprint (30-45 min)

**Best for:** Steady, sustainable progress on a single topic.

1. `/study-buddy [topic]` — review your stats summary
2. Follow STATUS recommendations for what to study next
3. Alternate between LEARN and QUIZ on 2-3 related topics
4. End with a SCENARIO if time allows

Rotate which topic you study between sessions, not within them. Deep engagement with one topic per session builds stronger connections than skimming across several.

### Deep Dive (2-3 hours)

**Best for:** Mastering a topic cluster, certification prep, or pushing toward a MASTERY CHALLENGE.

1. `/study-buddy [topic]`
2. Use PATH to generate a structured plan for your goal
3. Work through the path: LEARN foundational topics, QUIZ to verify, SCENARIO to apply
4. When you feel ready for a cluster, request a MASTERY CHALLENGE

### Project Onboarding

**Best for:** Ramping up on a codebase you're about to work on.

1. `/study-buddy generate /path/to/project` — generate a KB from the codebase
2. Review the generated categories and topics — check that difficulty and priority assignments make sense
3. `/study-buddy [new-topic]` then ask for STATUS to see the landscape
4. Start with LEARN on critical-priority topics — these are the concepts you'll hit first in the code
5. As you work in the codebase, come back and QUIZ yourself on what you've encountered

Generated KBs are a strong starting point but not perfect. You can add topics organically during study sessions — mention something not in the KB and the system will offer to add it.

### Opportunistic Learner

**Best for:** Context-driven learning when you encounter something at work.

1. Hit something you don't fully understand while working
2. `/study-buddy [relevant-topic]`
3. "Teach me about [the thing you encountered]"
4. Learn it in context, then switch back to your work

The multi-topic system makes this cheap — you're not disrupting a single linear study plan, just activating the relevant topic and learning what you need.

## Generating Knowledge Bases

```
/study-buddy generate /path/to/project
/study-buddy generate https://github.com/user/repo
```

The generator analyzes a codebase — structure, dependencies, source code — and produces a categorized knowledge base with difficulty ratings, prerequisites, and cross-references.

**What makes a good source:** Projects with clear module boundaries, reasonable size, and some documentation. Well-structured codebases with distinct components produce better KBs than monolithic files.

**What to expect:** The output is a categorized KB where each topic has a name, description, difficulty (1-5), priority (critical/high/medium/low), prerequisites, and related topics. The generator makes reasonable guesses about difficulty and priority based on code complexity and dependency depth, but you should review them.

**After generation:**

1. Review the generated `study.yaml` and `knowledge-base.yaml` in the new topic directory
2. Run STATUS to see the full landscape — total topics, category breakdown, priority distribution
3. Start studying — critical-priority topics are usually the best entry point
4. Add new topics during study sessions as you discover gaps

**Adding topics manually:** Create a directory under `_meta/study-buddy/` with a `study.yaml` (name, description, type, created) and `knowledge-base.yaml` following the standard schema. The topic is auto-discovered on next use.

## Enriching Knowledge Bases

```
/study-buddy enrich [topic]
/study-buddy enrich [topic] with "ANS-C01 exam"
/study-buddy enrich [topic] with /path/to/docs
/study-buddy enrich [topic] with https://github.com/user/repo
```

Two modes of enrichment:

**Graph enrichment** (no source) audits the KB's internal structure — fixes missing bidirectional relationships, connects isolated topics, fills empty `related` arrays, expands terse descriptions, and identifies genuine gaps where a bridging topic would connect existing clusters.

**Source-enriched** (with a source) uses external material to identify coverage gaps. Point it at a certification exam name, a documentation directory, or a GitHub repo. The system compiles the source's topic landscape, diffs it against the KB, and proposes additions for anything missing or underrepresented.

Both modes present a structured plan before making any changes. You approve all proposed changes, select specific ones, or request modifications. Existing progress (statuses, evidence, source context) is never touched — enrichment is strictly additive.

## Tools

### Stats Dashboard

```bash
python3 /Users/sethallen/agent-skills/study/scripts/kb-stats.py /path/to/knowledge-base.yaml
```

Outputs level distribution, priority breakdown, per-category engagement, and recent promotions. The study buddy runs this on session start, but you can run it directly against any topic's KB.

### DAG Visualizer

```bash
python3 /Users/sethallen/agent-skills/study/scripts/kb-dag.py /path/to/knowledge-base.yaml
```

Launches an interactive graph visualization in your browser. The prerequisite DAG is rendered with topics colored by status, priority, or category. Use `--no-serve` to generate the HTML file without launching a local server.

Both scripts accept the path to any topic's `knowledge-base.yaml` as an argument. Both require `pyyaml` (`pip install pyyaml`).

## Learning Philosophy

- **Understand, don't memorize.** The goal is whiteboard-depth understanding — if you can't explain *why*, you don't understand it yet.
- **Build a web, not a list.** Topics connect through prerequisites and relationships. Connected knowledge decays slower than isolated facts.
- **Apply immediately.** Scenarios and projects create durable memory that reading alone can't match.
- **Spaced practice beats cramming.** Short daily sessions outperform marathon study blocks. The system is designed for steady progress.
