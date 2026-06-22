# Migration Guide

MissionForge has been slimmed to a PiWorker-centered kernel.

## Removed Active Surfaces

- `missionforge.agent_packets`
- `missionforge.agentic_flow`
- `missionforge.agentic_repair`
- `missionforge.agentic_repair_controller`
- `missionforge.agentic_revision_controller`
- `missionforge.adapters.task_contract_runtime`
- `create_default_task_contract_flow`
- `TaskContractFlowPreset`

These were replaced by the smaller `PiWorkerCall` boundary and product-level
flows built outside core.

## Replacement Pattern

Old code that asked MissionForge core to run an executor/judge flow should now:

1. Compile product meaning into a frozen `TaskContract`.
2. Build role-specific `PiWorkerCall` objects.
3. Run them with `run_piworker_call(...)`.
4. Let an independent product judge artifact decide semantic acceptance.
5. Record refs-only packages and usage metrics in the product integration.

For new products, prefer the compact `missionforge.kernel` API or an external
integration such as DeepResearch v2.
