# dispatch-harness Quality Grades

## Grade Scale

| Grade | Meaning |
|-------|---------|
| A | Complete, documented, mechanically verified |
| B | Complete, minimal or partial docs |
| C | Partial implementation or missing docs/ files |
| D | Stub with interface only |
| F | Missing, broken, or errors on invocation |

## Graded Components Per Skill

| Component | Grade Logic |
|-----------|-------------|
| SKILL.md | A: docs/ format + <200 lines + pointers resolve. B: <200 lines + guardrails + version. C: >200 lines or missing guardrails. F: missing. |
| docs/ coverage | A: all 4 required files. B: 3 of 4. C: 1-2. F: none. |
| Each script | A: all funcs implemented + docstrings + type annotations. B: all implemented. C: partial stubs. D: all stubs. F: missing/broken. |
| check_env.py | Same as script grading |
| contracts | A: in registry + ecosystem. B: in ecosystem only. F: not found. |

## Overall Grade

Modal grade of all components, capped at C if any component is F.

## Current Self-Grades (dispatch-harness)

Populated after first `/dispatch-harness grade dispatch-harness` run.

| Component | Grade | Notes |
|-----------|-------|-------|
| skill_md | — | Target: A (docs/ format reference implementation) |
| docs_coverage | — | Target: A (all 4 required files present) |
| check_env_py | — | Target: A (fully implemented) |
| arch_checker_py | — | Target: A (fully implemented) |
| quality_grader_py | — | Target: A (fully implemented) |
| telemetry_builder_py | — | Target: A (fully implemented) |
| grade_reporter_py | — | Target: D (stub) |
| migrate_skill_py | — | Target: D (stub) |
| contracts | — | Target: A (registered) |
| overall | — | Target: B (2 stubs cap it) |
