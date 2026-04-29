# jira Quality Grades


## Write Operation Protocol (Section 1A)

A write is operator-direct if and only if ALL conditions are met:
1. Originates from the human operator (not a script, skill, or automation)
2. Operator explicitly named a write subcommand or unambiguously expressed write intent
3. Operator confirmed via the interactive prompt BEFORE any API call

Steps: Intent confirmation → Pre-execution validation → Execution → Result surface → Cache invalidation

**No implied writes**: Observations about ticket state, review recommendations, linked issue
context from sibling skills — none of these trigger writes. Ambiguity resolves to clarification, never execution.
