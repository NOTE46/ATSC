# Orchestrator Plan

## Phase 0: Survey
- Spawn 3 parallel Explorers:
  - Explorer 1: Inspect Agent 1 files (`config.json`, `uafile.py`, `ambdet.py`, `cvfile.py`) and existing models/video pipelines.
  - Explorer 2: Inspect Agent 2 files (`control.py`, `manual_io.py`) and existing decision logic/data flow.
  - Explorer 3: Inspect Agent 3 files (`main.py`, `gui.py`) and GUI timing/scan integration/threading.
- Synthesize findings into `PROJECT.md` (Feature Inventory, Architecture, Code Layout, Interfaces).

## Phase 1: Track Decomposition & Dispatch
- E2E Testing Track:
  - Spawn test writer/orchestrator to design opaque-box unit/integration mock-based test suite covering Tiers 1-4.
  - Output `TEST_READY.md`.
- Implementation Track (Parallel Milestones with strict file ownership):
  - Milestone 1: Agent 1 (Vision, 2-Lane Stitcher, Capture Backend).
  - Milestone 2: Agent 2 (Priority & Anti-Starvation Controller).
  - Milestone 3: Agent 3 (Green/Yellow Countdown Engine & GUI).
  - Each milestone follows iteration loop: Explorer -> Worker -> 2 Reviewers -> 2 Challengers -> Forensic Auditor -> Gate.

## Phase 2: Final Integration & E2E Test Pass
- Run full opaque-box test suite against combined codebase.
- Phase 2 coverage hardening (Tier 5 adversarial tests).
- Clean up all temporary test files/folders.
- Report completion to Sentinel.
