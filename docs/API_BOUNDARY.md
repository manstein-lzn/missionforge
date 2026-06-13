# API Boundary

Last updated: 2026-06-12

Status: `reference`

## Goal

Keep the public MissionForge surface small enough that application teams extend
the system through contracts instead of patching runtime internals.

The package root is the stable programmer import surface. Module-level imports
may exist for implementation and focused tests, but product integrations should
depend on the root surface first unless this document explicitly marks a module
as adapter-specific.

## Primary Kernel Surface

New product integrations should start with the TaskContract/PiWorker kernel:

- Task authority:
  - `TaskContract`
  - `TaskContractRevision`
  - `ContractClause`
- Workspace and permission authority:
  - `WorkspacePolicy`
  - `PermissionManifest`
  - `NetworkPolicy`
  - `RunWorkspace`
- Projections:
  - `WorkerBrief`
  - `JudgeRubric`
  - `build_worker_brief`
  - `build_judge_rubric`
  - `project_worker_brief`
  - `project_judge_rubric`
- PiWorker call boundary:
  - `PiWorkerCall`
  - `PiWorkerCallAdapter`
  - `PiWorkerCallResult`
  - `PiWorkerCallRole`
  - `PiWorkerCallResultStatus`
- Execution and judgment packets:
  - `AgentExecutionPacket`
  - `AgentExecutionReport`
  - `AgentExecutionStatus`
  - `JudgePacket`
  - `JudgeReport`
  - `JudgeReportDecision`
  - `validate_execution_report_for_packet`
  - `validate_judge_packet_for_execution`
  - `validate_judge_report_for_packet`
- Default flow:
  - `AgenticFlowRunner`
  - `AgenticFlowResult`
  - `AgenticFlowStatus`
  - `AgenticFlowRefs`
  - `TaskContractFlowPreset`
  - `PiWorkerRuntimeFactory`
  - `create_default_task_contract_flow`
  - `create_default_piworker_adapter`
- Refs-first ledger and package:
  - `DecisionLedgerEventKind`
  - `TaskContractDecisionLedgerEntry`
  - `FinalPackage`
  - `RunReplayStatus`
  - `RunReplaySummary`
  - `replay_decision_ledger`
- Repair:
  - `RepairBrief`
  - `RepairTicket`
  - `RepairTicketStatus`
  - `RepairExecutionDirective`
  - `RepairExecutionDirectiveStatus`
  - `build_repair_ticket`
  - `build_repair_execution_directive`
  - `build_repair_rejudge_packet`
  - `run_repair_directive_with_default_piworker`
- Revision:
  - `TaskRevisionRequest`
  - `TaskRevisionDecision`
  - `TaskRevisionDecisionStatus`
  - `TaskRevisionAuthority`
  - `RevisionPendingRecord`
  - `RevisionPendingStatus`
  - `RevisionAppliedRecord`
  - `RevisionAppliedStatus`
  - `RevisionExecutionDirective`
  - `RevisionExecutionDirectiveStatus`
  - `build_revision_pending_record`
  - `load_revision_draft_contract`
  - `apply_task_contract_revision`
  - `build_revision_execution_directive`
  - `build_revision_rejudge_packet`
  - `build_revision_judge_result`
  - `run_revision_draft_with_default_piworker`
- Product integration contracts:
  - `ProductIntegration`
  - `TaskContractProductIntegration`
  - `ProductTaskContractCompileResult`
  - `ProductCompileResult`
  - `ProductCompileStatus`
  - `ProductArtifactRefs`
  - `ProductGateSpec`
  - `ProductGateResult`
  - `ProductGateStatus`

These are product-neutral primitives. They define authority, workspace shape,
tool access, artifact refs, semantic judgment packets, repair/revision records,
and replay. They do not contain product-specific meaning.

## FrontDesk Surface

FrontDesk is the high-intelligence requirements-discovery and intent-authoring
surface. It may discover needs and prepare intent bundles, but product-aware
output must pass through a product integration before becoming executable task
authority.

Stable root categories include:

- `FrontDesk` authoring facade
- `FrontDeskAuthoringSession`
- `FrontDeskIntentBundle`
- `ProductInquiryProfile`
- mission brief, semantic lock, solution plan, audit, approval, and freeze
  manifest records
- refs-only inspect and handoff records

FrontDesk output is not operational task truth by itself. The frozen
`TaskContract`, or an explicit revision of it, remains task authority.

## Compatibility Data Surface

These symbols remain available for older MissionIR data, migration tools, and
FrontDesk's current generic mapping path. They are not exported from the
`missionforge` package root and are not the runtime API for new product work:

- MissionIR and freeze path:
  - `missionforge.ir.MissionIR`
  - `missionforge.ir.MissionObjective`
  - `missionforge.ir.MissionConstraint`
  - `missionforge.ir.CapabilityProfileRef`
  - `missionforge.freeze.ExpandedMission`
  - `missionforge.freeze.FrozenMissionContract`
  - `missionforge.freeze.ContractManifest`
  - `missionforge.freeze.expand_mission`
  - `missionforge.freeze.freeze_mission`
- Older revision contracts:
  - `missionforge.revision.MissionRevision`
  - `missionforge.revision.MissionRevisionRequest`
  - `missionforge.revision.MissionRevisionDecision`
  - `missionforge.revision.MissionRevisionWorkflow`
  - `missionforge.revision_store.MissionRevisionStore`
  - `missionforge.revision_store.apply_mission_revision`
- Controlled steering and metric-dict surfaces.

Retired runtime/work-unit modules are not importable: `missionforge.runner`,
`missionforge.runtime`, `missionforge.work_unit`, `missionforge.harness`,
`missionforge.workers`, `missionforge.fake_worker`, and
`missionforge.adapters.piworker`. New code must use `TaskContract`,
`AgenticFlowRunner`, and `PiWorkerCall`.

## Evidence, Store, And Verifier Surface

These generic infrastructure contracts are stable because they are product
neutral and support both current and compatibility paths:

- evidence refs and stores:
  - `ArtifactRef`
  - `EvidenceRef`
  - `EvidenceLedger`
  - `EvidenceRecord`
  - `EvidenceSnapshot`
  - `FileEvidenceStore`
  - `InMemoryEvidenceStore`
- stores:
  - `RunStore`
  - `ArtifactStore`
  - `EventLogStore`
  - `JsonWorkspaceStore`
  - `JsonArtifactStore`
  - `JsonEventLogStore`
  - `JsonRunStore`
- verifier contracts:
  - `VerificationSpec`
  - `VerificationResult`
  - `ValidatorSpec`
  - `ValidatorResult`
  - `Verifier`
  - `verify_spec`
  - `run_validator`
- shared errors and helpers:
  - `ContractValidationError`
  - `MissionValidationError`
  - `MissionForgeError`
  - `VerificationStatus`
  - `ValidatorMode`
  - `ValidatorSeverity`
  - `EvidenceTrustLevel`
  - `stable_json_hash`
  - `validate_ref`
  - `assert_refs_only_payload`

## Adapter Boundary

Adapters may translate an external protocol into core contracts. They must not
carry product-specific MissionForge truth.

Allowed:

- CLI or host shell command envelopes
- refs-only operator results
- Pi Agent / PiWorker construction boundaries
- external integration code under `integrations/*`

PiWorker adapter paths expose the `PiWorkerCallAdapter.run_call(...)` boundary
and project `PiWorkerCall` into a minimal runtime input/sidecar contract. There
is no WorkUnitContract compatibility adapter in the active codebase.

Adapter-specific classes such as `PiAgentRuntimeConfig`,
`PiAgentExecutorNode`, and `PiAgentJudgeNode` live under
`missionforge.adapters.pi_agent_runtime`. They are intentionally not exported
from the package root.

## Internal Surface

These are implementation details and should not be re-exported from the package
root:

- `ActiveMissionContract`
- `RuntimeContractView`
- `PiAgentRuntimeAdapter`
- product integration compilers such as SkillFoundry
- adapter-private runtime modules
- product-specific package names or branch selectors

Internal modules may import these directly when needed. Applications should use
the primary kernel surface or explicit adapter modules.

## Product Integration Rule

Product integrations should depend on MissionForge in this order:

1. Gather product facts through FrontDesk, product UI, config, source refs, or
   external systems.
2. Compile product facts into `TaskContract`, `WorkspacePolicy`, and
   `PermissionManifest`.
3. Project `WorkerBrief` and `JudgeRubric`.
4. Run through `create_default_task_contract_flow(...)` or the same packet
   primitives.
5. Use product hard checks and product gates outside core.
6. Record refs-only ledgers, results, final packages, repair records, and
   revision records.
7. Keep MissionIR only for compatibility and migration.

If a product needs a branch in `src/missionforge`, the product boundary has
failed.
