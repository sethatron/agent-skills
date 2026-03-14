# Knowledge Base Generation Guide

How to analyze a source project and generate a structured knowledge base for the study engine.

## Knowledge Base YAML Schema

Every generated KB must follow this exact structure, matching the schema used by the study engine:

```yaml
metadata:
  version: "1.0.0"
  created: "{today's date}"
  owner: "seffie"
  description: >
    {One-paragraph description of what this KB covers}
  difficulty_scale:
    1: "Foundational — core concept everyone should know"
    2: "Beginner — requires basic context"
    3: "Intermediate — working professional knowledge"
    4: "Advanced — deep internals and edge cases"
    5: "Expert — protocol specs, wire formats, source-level understanding"
  status_values:
    not_started: "No engagement with this topic yet"
    exposed: "Has encountered the concept but cannot explain independently"
    conceptual: "Can explain the concept; understands the what and why"
    applied: "Can use in guided practice; understands the how"
    proficient: "Can apply independently, troubleshoot, explain tradeoffs"
    mastered: "Can teach it, debug edge cases, and connect across domains"
  level_up_evidence_schema:
    from_level: "Level before promotion"
    to_level: "Level after promotion"
    timestamp: "ISO 8601 datetime"
    method: "learn | quiz | scenario | project | mastery_challenge"
    summary: "1-2 sentence description of demonstrated competence"

category_name:
  description: "What this category covers"

  subcategory_name:
    - name: "Topic Name"
      description: "One-line description of what the topic IS"
      difficulty: 3
      priority: high
      prerequisites: ["Other Topic Name"]
      related: ["Related Topic Name"]
      tags: [tag1, tag2]
      status: not_started
      source_context: "path/to/relevant/file.go"
```

### Per-Topic Fields

| Field | Type | Required | Notes |
|---|---|---|---|
| name | string | yes | Display name, unique within the KB |
| description | string | yes | What the topic IS, not how to use it |
| difficulty | int 1-5 | yes | See calibration below |
| priority | enum | yes | critical, high, medium, low |
| prerequisites | list[string] | yes | Names of topics that should be understood first (can be empty) |
| related | list[string] | yes | Sibling/cross-cutting topics (can be empty) |
| tags | list[string] | yes | Freeform tags for filtering |
| status | enum | yes | Always `not_started` for generated KBs |
| source_context | string/null | yes | File path or doc reference that best explains this topic |

## Source Analysis by Language

### Go Projects

1. **Entry points:** Read `go.mod` for module name and dependencies. Scan `cmd/` for main packages — each is an entry point.
2. **Domain packages:** Scan `internal/` (or `pkg/`) — each subdirectory is typically a bounded context. Read the package-level doc comments and exported types.
3. **API surface:** Look for `.proto` files (gRPC), OpenAPI specs, or HTTP handler registrations (`http.HandleFunc`, `mux.Router`, `gin.Engine`).
4. **Key interfaces:** Grep for `type.*interface` — interfaces define contracts and extension points.
5. **Configuration:** Check for config structs, environment variable reads, flag definitions.
6. **Testing patterns:** Scan `*_test.go` files for test helpers, fixtures, integration test setup.

### Python Projects

1. **Entry points:** Read `pyproject.toml` or `setup.py` for package metadata. Check for `__main__.py`, CLI entry points, or FastAPI/Flask app creation.
2. **Dependencies:** Parse `pyproject.toml` `[project.dependencies]`, `requirements.txt`, or `Pipfile`.
3. **Package structure:** Scan the main package directory. Each subpackage with `__init__.py` is a module boundary.
4. **API surface:** Look for FastAPI routers (`@app.get`, `@router.post`), Flask blueprints, or Django URL patterns.
5. **Data models:** Grep for Pydantic models (`BaseModel`), SQLAlchemy models (`Base`), dataclasses.
6. **Configuration:** Check for settings modules, `.env` loading, config classes.

### TypeScript/JavaScript Projects

1. **Entry points:** Read `package.json` for `main`, `scripts`, dependencies. Check `tsconfig.json` for project structure.
2. **Package structure:** Scan `src/` — look for barrel exports (`index.ts`), module boundaries.
3. **API surface:** Look for route definitions (Express, Next.js pages/app router, tRPC routers).
4. **Type definitions:** Scan for `interface` and `type` declarations — these define the domain model.
5. **State management:** Check for Redux stores, Context providers, Zustand stores.
6. **Build/bundler config:** Check webpack, vite, esbuild configurations for build pipeline understanding.

### Rust Projects

1. **Entry points:** Read `Cargo.toml` for package metadata, dependencies, workspace members.
2. **Module structure:** Scan `src/` for `mod.rs` files and `lib.rs` public API.
3. **Traits:** Grep for `trait` definitions — these are the key abstractions.
4. **Error handling:** Look for custom error types, `thiserror`/`anyhow` usage patterns.
5. **Unsafe code:** Grep for `unsafe` blocks to identify low-level concerns.

### Documentation-Only Sources

1. Read all `.md` files, focusing on architecture docs, ADRs, API references.
2. Look for `docs/`, `.scribe/`, `architecture/`, `design/` directories.
3. Extract concepts, terminology, and relationships from the documentation structure.

## Category Design Heuristics

Map the project's architecture to KB categories:

| Source Structure | Category Strategy |
|---|---|
| `internal/{pkg}/` or `src/{module}/` | One category per major package/module |
| Layered architecture (API, service, data) | Categories by architectural layer |
| Microservices | One category per service + shared categories for common patterns |
| Monolith with clear domains | Categories by domain boundary |

### Guidelines

- **3-8 topics per subcategory.** Fewer means the subcategory is too granular; more means it should be split.
- **3-6 subcategories per category.** Keep categories focused.
- **Name categories after what they represent**, not the directory name. `agent_orchestration` over `internal_agents`.
- **Create cross-cutting categories** for: configuration, testing patterns, deployment, shared utilities — if they have enough topics (3+).

## Difficulty Calibration

| Level | Criteria | Examples |
|---|---|---|
| 1 | Foundational concepts anyone working with the codebase should know | "What is this project?", "High-level architecture", "Key terminology" |
| 2 | Basic components and their purpose | Individual modules, config options, basic API endpoints |
| 3 | Standard patterns and working knowledge | How components interact, data flow, common operations |
| 4 | Deep internals and edge cases | Error handling strategies, performance characteristics, concurrency patterns |
| 5 | Expert-level, novel, or subtle | Design tradeoffs, extension mechanisms, failure modes under load |

## Priority Assignment

| Priority | Criteria |
|---|---|
| critical | Core architecture that everything else depends on. Must understand to contribute. |
| high | Important subsystems, key integrations, frequently-touched code paths. |
| medium | Useful knowledge for working with the codebase. Enhances understanding. |
| low | Nice-to-know. Edge features, historical decisions, rarely-touched code. |

## DAG Construction

Prerequisites define the learning order. They flow from foundational → advanced.

### Rules

1. **Prerequisites must reference existing topic names exactly.** Validate all references resolve.
2. **No circular dependencies.** If A requires B and B requires A, one link must be removed.
3. **Every topic should be reachable from a root.** Root topics have empty prerequisites.
4. **Keep prerequisite chains shallow.** A chain of 5+ prerequisites suggests missing intermediate topics or over-specification.
5. **Use prerequisites for "must understand first" relationships.** Use `related` for "helpful to also know" connections.

### Validation

After generating the KB, mentally (or programmatically) verify:
- No topic lists a prerequisite that doesn't exist in the KB
- No cycles exist in the prerequisite graph
- At least some topics have empty prerequisites (roots)
- No topic has more than 4-5 direct prerequisites (suggests the topic is too broad or prerequisites are too granular)

## Source Context

Point to the specific file, function, or doc section that best explains each topic.

| Topic Type | source_context Format |
|---|---|
| Code module | `internal/controller/controller.go` |
| API endpoint | `api/routes/users.py:create_user` |
| Config pattern | `config/settings.go` |
| Architecture concept | `docs/architecture.md` or `README.md#architecture` |
| No clear single source | `null` |

## Common Pitfalls

**Too granular:** Don't create topics for individual functions or methods. A topic should represent a concept, pattern, or component that takes real effort to understand.

**Too broad:** Don't create topics that cover entire packages. "The auth module" is too broad; "JWT validation pipeline", "Session management", "OAuth2 token exchange" are appropriately scoped.

**Missing the forest:** Don't only create topics for code artifacts. Include: architectural decisions, design patterns used, deployment model, key abstractions, error handling philosophy.

**Ignoring dependencies:** A topic about "the reconciliation loop" should list the data structures and interfaces it uses as prerequisites.

**Flat hierarchy:** Avoid dumping all topics into one category. Even small projects have natural groupings.

**Disconnected topics:** Every topic should have at least one prerequisite OR be a root topic with at least one topic depending on it. Isolated topics suggest missing connections.
