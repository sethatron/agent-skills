# dispatch-manager Workflow Integration


## Dispatch Skill Interface (DSI)

The DSI is the formal specification that any skill must satisfy to be
dispatch-framework compatible. See `references/dsi-guide.md` for the
complete guide with examples.

### DSI Skill Types

- **TYPE A** — Workflow Step Skill: dispatch calls it automatically.
  Requires artifact contract and step snippet.
- **TYPE B** — On-Demand Managed Skill: operator calls directly.
  No artifact contract required.
- **TYPE C** — Hybrid: both TYPE A and TYPE B requirements.

### DSI Requirements (DSI-01 through DSI-10)

Defined in `dsi/checklist.yaml`. Evaluated by `scripts/dsi_validator.py`:

```bash
python scripts/dsi_validator.py <skill-path> [--type A|B|C] [--verbose] [--json]
```

Exit codes: 0 = all PASS, 1 = any WARN, 2 = any FAIL.


## Optimus Finding Workflow

Finding lifecycle: PENDING → REVIEWING → ACCEPTED → IN_PROGRESS → IMPLEMENTED
(or DECLINED / DEFERRED at any point).

Tracked in `optimus/findings.yaml`. See `scripts/optimus_manager.py`.

`/dispatch-manager implement optimus <finding-id>`:
1. Load and display finding
2. Build implementation plan by category (workflow_gap, tooling, process,
   automation, mcp_integration, new_skill)
3. Execute via write protocol
