# Mastery Level System

## The Six Levels

| Level | Name | Meaning | Evidence Required to Reach |
|-------|------|---------|---------------------------|
| 0 | not_started | No engagement with this topic | Default state |
| 1 | exposed | Has encountered the concept but cannot explain independently | Completed a LEARN session; engaged with the explanation |
| 2 | conceptual | Can explain the what and why | Correctly answered 2+ open-ended comprehension questions in LEARN or QUIZ; answers demonstrate understanding beyond restating definitions |
| 3 | applied | Can use in guided practice | Completed a SCENARIO involving the topic with correct diagnosis/approach, OR completed a PROJECT involving the topic |
| 4 | proficient | Can apply independently, troubleshoot, explain tradeoffs | Passed a MASTERY CHALLENGE at the proficient tier (3 hard questions + 1 scenario + 1 teach-back, pass 4/5) |
| 5 | mastered | Can teach, debug edge cases, connect across domains | Passed a MASTERY CHALLENGE at the mastered tier (same format but expert-level difficulty, pass 4/5) |

## Promotion Rules

- Levels must be reached in order. No skipping (e.g., not_started directly to applied is not allowed).
- **Exception:** if a user demonstrates deep understanding during LEARN, they can advance up to 2 levels in one session (not_started to conceptual).
- Promotions to `proficient` and `mastered` REQUIRE a formal MASTERY CHALLENGE. These levels cannot be reached through organic interaction in LEARN, QUIZ, or SCENARIO modes.
- A single QUIZ session can promote at most 1 level.
- After any promotion, record a `level_up_evidence` entry (see schema below).

## What Constitutes a Pass (Per Transition)

| Transition | What Constitutes a Pass | What Does NOT Count |
|-----------|------------------------|---------------------|
| not_started -> exposed | User received the explanation and engaged with it (asked questions, responded to prompts, demonstrated they were processing the material) | Simply being told about the topic without interaction |
| exposed -> conceptual | User correctly answered WHY the concept exists and HOW it relates to prerequisites | Restating the definition; yes/no answers; naming the concept without explaining it |
| conceptual -> applied | User correctly walked through a scenario or completed a hands-on exercise, demonstrating operational understanding | Describing what they would do without actually reasoning through specifics |
| applied -> proficient | Passed mastery challenge: answered edge-case questions, explained tradeoffs, taught the concept clearly | Getting conceptual questions right but missing edge cases or tradeoffs |
| proficient -> mastered | Passed mastery challenge at expert tier: connected across domains, handled novel applications, demonstrated teaching ability at depth | Being proficient at the standard cases but unable to generalize |

## Anti-Gaming Rules

- QUIZ questions must vary between sessions. Never ask the same question twice in a conversation.
- MASTERY CHALLENGE cannot be retried in the same conversation. If the user asks to retry, explain they should study the identified gaps first and try in a new session.
- Teach-back must demonstrate genuine understanding. If the user recites a memorized definition, probe deeper with follow-up questions targeting the mechanics and edge cases.
- If a user asks to be manually promoted ("just mark me as mastered"), explain the evidence requirement and offer the appropriate mode to earn the promotion.

## level_up_evidence Schema

Each promotion appends an entry to the topic's `level_up_evidence` array in the knowledge base YAML:

```yaml
      level_up_evidence:
        - from_level: not_started
          to_level: exposed
          timestamp: "2026-03-04T14:30:00Z"
          method: learn
          summary: "Completed LEARN session on veth pairs; engaged with explanation"
        - from_level: exposed
          to_level: conceptual
          timestamp: "2026-03-04T15:00:00Z"
          method: quiz
          summary: "Correctly explained why veth pairs exist and how they connect network namespaces"
```

### Field Specifications

- **Indentation:** `level_up_evidence` at 6 spaces (same level as `status`, `source_context`). Array entries at 8 spaces (`- from_level:`), fields at 10 spaces.
- **timestamp:** Run `date -u +"%Y-%m-%dT%H:%M:%SZ"` via Bash to get current UTC time before writing. Never fabricate timestamps.
- **method:** One of: `learn`, `quiz`, `scenario`, `project`, `mastery_challenge`
- **from_level / to_level:** Must be adjacent levels (or at most 2 apart for the LEARN exception).
- **summary:** 1-2 sentences describing what the user demonstrated. Be specific — "answered correctly" is insufficient; describe WHAT they answered correctly about.

## Demotion Policy

- Topics are never demoted.
- If a user struggles with a previously-promoted topic, note it in conversation and suggest a review QUIZ, but do not lower the level.
- The `level_up_evidence` history preserves the full record of how each level was reached.
