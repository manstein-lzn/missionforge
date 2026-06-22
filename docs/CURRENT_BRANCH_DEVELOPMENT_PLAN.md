# Current Branch Development Plan

Status: active slimming and DeepResearch v2 hardening.

## Current Direction

- Keep MissionForge core product-neutral.
- Keep PiWorker as the only first-class intelligent worker.
- Keep `PiWorkerCall` and `missionforge.kernel` as the active runtime surface.
- Keep FrontDesk as a high-intelligence requirements-discovery surface.
- Keep DeepResearch v2 as a product integration, not a core branch.

## Completed Slimming

- Removed the old skill-building integration.
- Removed legacy TaskContract flow, packet, repair, and revision controllers.
- Removed the retired auxiliary worker entrypoint.
- Kept refs-first ledger/package primitives only where they remain
  product-neutral.

## Next Work

- Continue reducing product semantics from core.
- Keep DeepResearch v2 thin: product manuals, rubrics, source tools, and
  report contracts should carry research semantics.
- Improve user-facing progress, resume, final paths, and usage summaries.
- Prefer PiWorker-authored review/judge artifacts over Python semantic gates.
