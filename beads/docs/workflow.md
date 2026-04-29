# beads Workflow Integration


## Epic Structure

Five framework epics created during /beads init:

**Epic 1: [ENG] Workflow Engine** (P0) scope:dispatch
  dispatch_runner.py (P0, large), state_store.py (P1, medium),
  slack_notifier.py (P1, small), bottleneck_detector.py (P1, medium)

**Epic 2: [ENG] Ecosystem Management** (P1) scope:dispatch-manager
  skill_author.py (P2, large), optimus_manager.py (P2, medium),
  change_manager.py (P2, large), backup_manager.py (P2, small),
  changelog_writer.py (P2, small), ecosystem_map.py (P3, small),
  version_manager.py (P3, xs)

**Epic 3: [ENG] Knowledge Layer** (P1) scope:notebook
  update_runner.py (P2, medium), source_renderer.py (P2, small),
  source_manager.py (P2, small), query_runner.py (P2, small),
  briefing_loader.py (P2, xs)

**Epic 4: [ENG] Beads Integration** (P2) scope:beads
  label_enforcer.py (P3, xs), sync_runner.py (P3, xs)

**Epic 5: [ENG] Infrastructure** (P1) scope:ecosystem
  Cron approval and activation (P1, xs),
  NotebookLM auth automation (P2, small),
  Pre-bash hook refinements (P3, xs)
