# Framework Epic Structure

Five epics created during `/beads init`. Each maps to a major area of the
dispatch framework. All epics use `source:scaffold` label.

## Epic 1: [ENG] Workflow Engine (P0)

Scope: dispatch | The core execution layer.

| Script | Priority | Effort | Status |
|--------|----------|--------|--------|
| dispatch_runner.py | P0 | large | stub |
| state_store.py | P1 | medium | stub |
| slack_notifier.py | P1 | small | stub |
| bottleneck_detector.py | P1 | medium | stub |

Additional labels: `layer:script, kind:stub, phase:stub`

## Epic 2: [ENG] Ecosystem Management (P1)

Scope: dispatch-manager | The skill management and write-protocol layer.

| Script | Priority | Effort | Status |
|--------|----------|--------|--------|
| skill_author.py | P2 | large | stub |
| optimus_manager.py | P2 | medium | stub |
| change_manager.py | P2 | large | stub |
| backup_manager.py | P2 | small | stub |
| changelog_writer.py | P2 | small | stub |
| ecosystem_map.py | P3 | small | stub |
| version_manager.py | P3 | xs | stub |

Additional labels: `layer:script, kind:stub, phase:stub`

## Epic 3: [ENG] Knowledge Layer (P1)

Scope: notebook | The NotebookLM integration scripts.

| Script | Priority | Effort | Status |
|--------|----------|--------|--------|
| update_runner.py | P2 | medium | stub |
| source_renderer.py | P2 | small | implemented |
| source_manager.py | P2 | small | implemented |
| query_runner.py | P2 | small | stub |
| briefing_loader.py | P2 | xs | stub |

Additional labels: `layer:script, kind:stub, phase:stub`

Note: source_renderer.py and source_manager.py were implemented during
dispatch-notebook init. The auditor should detect these and close their
issues if they exist.

## Epic 4: [ENG] Beads Integration (P2)

Scope: beads | The beads skill's own implementation.

| Script | Priority | Effort | Status |
|--------|----------|--------|--------|
| label_enforcer.py | P3 | xs | stub |
| sync_runner.py | P3 | xs | stub |

Additional labels: `layer:script, kind:stub, phase:stub`

## Epic 5: [ENG] Infrastructure (P1)

Scope: ecosystem | Cross-skill infrastructure work.

| Issue | Priority | Effort | Labels |
|-------|----------|--------|--------|
| Cron approval and activation | P1 | xs | scope:dispatch, kind:improvement |
| NotebookLM auth automation | P2 | small | scope:notebook, kind:improvement |
| Pre-bash hook refinements | P3 | xs | scope:dispatch, layer:hook, kind:improvement |

Additional labels: `source:scaffold`
