# MissionForge

MissionForge is converging toward a simplified PiWorker-centered agent runtime:
PiWorker performs semantic work, while MissionForge core enforces contracts,
workspace boundaries, permissions, refs, ledgers, role separation, and explicit
revision.

It is intentionally not a SkillFoundry rewrite. SkillFoundry should become one
application on top of MissionForge. MissionForge owns the generic substrate:

```text
FrontDeskIntentBundle + ProductIntegration + TaskContract
  -> WorkerBrief + JudgeRubric + WorkspacePolicy + PermissionManifest
  -> PiWorker execution + independent PiWorker judgment
  -> FinalPackage + DecisionLedger + Artifacts + MetricLedger
```

## Design Stance

- Mission semantics live in Mission IR and profile data, not task-name branches.
- The runtime core does not depend on LangGraph. LangGraph is an optional host.
- The only first-class LLM worker target is PiWorker. Other LLM workers are not
  a planned extension point.
- The PiWorker design is inspired by the MIT-licensed PI GitHub project. The
  initial skeleton does not vendor PI code; any future copied or adapted PI
  code must retain required attribution.
- Context and evidence are first-class runtime objects, not chat memory.
- Executor self-report is never acceptance evidence.
- Semantic acceptance may be produced by an independent Judge PiWorker role
  using a frozen contract, judge rubric, artifact refs, and evidence refs.
- Repair must preserve the frozen contract. Contract changes require explicit
  revision.
- Steering proposals must be schema-validated, boundary-validated, and
  authority-validated before runtime commits state.
- Core code must not contain benchmark or product names such as Codexarium.
- Documentation starts and ends every module: each module has a module design
  document before implementation, and that document is updated when behavior
  changes.

## Design Program

MissionForge starts with formal architecture design, not code migration and not
a narrow MVP. The first repository state should clarify:

- the stable Mission IR contract
- the runtime state model
- the context/evidence ledger boundary
- the controlled steering proposal boundary
- the work-unit harness protocol
- the verifier and repair protocol
- the worker adapter boundary
- the optional host, observation, and control adapter boundary

Implementation starts only after these boundaries are explicit enough to keep
task-specific semantics out of runtime code.

## Development Plan

Implementation should be driven through the hardened development documents:

- [MissionForge Agentic Constitution](docs/MISSIONFORGE_AGENTIC_CONSTITUTION.md):
  simplified PiWorker-centered laws, preserved principles, and boundaries.
- [MissionForge Final System Shape](docs/MISSIONFORGE_FINAL_SYSTEM_SHAPE.md):
  target architecture with FrontDesk, Product Integration, TaskContract,
  WorkerBrief, JudgeRubric, PermissionManifest, Executor PiWorker, and Judge
  PiWorker.
- [Simplified Agent Runtime Implementation Plan](docs/MISSIONFORGE_SIMPLIFIED_AGENT_RUNTIME_IMPLEMENTATION_PLAN.md):
  staged development plan for converging from the current runtime to the
  simplified architecture.
- [Development Goal Protocol](docs/DEVELOPMENT_GOAL_PROTOCOL.md): `/goal`
  operating contract, verification discipline, safe-point control, and
  completion rules.
- [Component Development Plan](docs/COMPONENT_DEVELOPMENT_PLAN.md): six-phase
  component backlog from contract kernel through adapter preparation.
- [Component Acceptance Matrix](docs/COMPONENT_ACCEPTANCE_MATRIX.md): phase gate
  checklists and cross-cutting invariants.
- [Follow-On Goals](docs/FOLLOW_ON_GOALS.md): post-runtime-kernel goal
  contracts for adapter boundary preflight, faux PiWorker, product integration
  extraction, and optional host shells.
- [Product Integration Boundary](docs/PRODUCT_INTEGRATION_BOUNDARY.md):
  adapter cleanliness rule that keeps product-specific task semantics outside
  the `missionforge` Python package.
- [Phase 11 Operator Productization Plan](docs/PHASE11_OPERATOR_PRODUCTIZATION_PLAN.md):
  CLI, inspection, diagnosis, resume, review, and validation workflows on top
  of the Phase 10 durable runtime state.
- [Phase 11 Operator Productization Goals](docs/PHASE11_OPERATOR_PRODUCTIZATION_GOALS.md):
  `/goal`-ready implementation slices for the Phase 11 operator surface.
- [Phase 12-16 Decoupling Roadmap](docs/PHASE12_TO_16_DECOUPLING_ROADMAP.md):
  metric ledger, runtime decomposition, PiWorker boundary, mission
  revision, and store-interface phases.
- [Phase 15 Revision Runtime Repair Plan](docs/PHASE15_REVISION_RUNTIME_REPAIR_PLAN.md):
  follow-up plan for making recorded mission revisions become the active
  runtime contract state on resume and subsequent work.
- [Implementation Status And Next Phases](docs/IMPLEMENTATION_STATUS_AND_NEXT_PHASES.md):
  current implementation audit, remaining coupling risks, and recommended
  Phase 17-21 hardening path.

## Package Layout

```text
src/missionforge/
  adapters/
    cli.py       Optional CLI/Python host shell around MissionRuntime
    contracts.py Adapter boundary, invocation, diagnostic, and result contracts
    observation.py Optional read-only run view and ControlRequest writer
    steering_llm.py Optional controlled steering LLM adapter
    piworker.py  Deterministic faux PiWorker adapter contracts and fixture run
  contracts.py   Shared enums, errors, safe refs, hashing, validation helpers
  evidence.py    Evidence and artifact ref contracts
  freeze.py      Mission expansion and frozen contract hashing
  harness.py     Proposal validation and work-unit harness
  ir.py          Mission IR dataclasses and validation
  json_store.py  Default workspace-relative JSON/JSONL store backend
  metric_store.py Run-local metric event/projection storage
  metrics.py     MetricEvent and MetricProjection contracts
  mission.py     Mission contract compatibility surface
  piworker_runtime.py Narrow PiWorker/PI Agent runtime construction boundary
  profiles.py    Capability and verification profile expansion
  revision.py    Mission revision contracts and conservative workflow
  revision_store.py Run-local mission revision artifact storage
  runner.py      Public MissionRuntime/MissionResult boundary
  runtime.py     Deterministic runtime vertical slice
  runtime_attempts.py RuntimeAttempt assembly helper
  runtime_state_writer.py Durable runtime state writer
  steering.py    Controlled steering contract objects
  steering_store.py Run-local controlled steering artifact refs
  stores.py      RunStore/ArtifactStore/EventLogStore protocols
  verifier.py    Verification routing
  verification.py Validator and verification result contracts
  work_unit.py   Work-unit and execution report contracts
  workers.py     Worker protocol boundary used by PiWorker-compatible adapters
docs/
  ARCHITECTURE.md
  MISSION_IR.md
  DESIGN_PROGRAM.md
  DEVELOPMENT_PROTOCOL.md
  DEVELOPMENT_GOAL_PROTOCOL.md
  PRODUCT_INTEGRATION_BOUNDARY.md
  COMPONENT_DEVELOPMENT_PLAN.md
  COMPONENT_ACCEPTANCE_MATRIX.md
  FOLLOW_ON_GOALS.md
  PHASE11_OPERATOR_PRODUCTIZATION_PLAN.md
  PHASE11_OPERATOR_PRODUCTIZATION_GOALS.md
  PHASE12_TO_16_DECOUPLING_ROADMAP.md
  modules/
    adapter_contracts.md
    controlled_steering.md
    metrics.md
    store.md
integrations/
  skillfoundry/
    External product integration that compiles SkillFoundry/FrontDesk refs
    into MissionIR without being part of the missionforge Python package.
```

## Development

Use the Node version declared in `.nvmrc` for `workers/pi-agent-runtime`.

```bash
./scripts/validate.sh
```

For a faster local rerun after `workers/pi-agent-runtime/node_modules` is
already installed:

```bash
MISSIONFORGE_SKIP_NPM_CI=1 ./scripts/validate.sh
```

## Operator Commands

Phase 11 exposes deterministic refs-only operator commands through the optional
CLI adapter:

```bash
python -m missionforge.adapters.cli run --workspace . --mission-ref missions/input.mission.json
python -m missionforge.adapters.cli inspect --workspace . --run run-sample-mission
python -m missionforge.adapters.cli diagnose --workspace . --run run-sample-mission
python -m missionforge.adapters.cli resume --workspace . --run run-sample-mission --mission-ref missions/input.mission.json
python -m missionforge.adapters.cli control halt --workspace . --run run-sample-mission --reason "Pause before the next attempt."
python -m missionforge.adapters.cli review record --workspace . --run run-sample-mission --decision approved --review-ref reviews/reviewer-decision.json
python -m missionforge.adapters.cli validate
```

Each command emits a `missionforge.command_result.v1` envelope. Command output
must cite refs instead of embedding raw transcripts, provider payloads, prompts,
stdout/stderr bodies, artifact bodies, or secrets.

## Controlled Steering

Controlled steering is implemented as an opt-in protocol over the deterministic
runtime. Core contracts live in `missionforge.steering`, run-local steering
artifacts live under `runs/{mission_run_id}/steering/`, and optional live LLM
integration is adapter-only. Runtime completion still comes from verifier
status, not proposal confidence, worker self-report, reviewer prose, CLI, RPC,
or dashboard output.

The default runtime path remains deterministic and offline. Proposal mode is
enabled only by injecting providers into `RuntimeEngine` or `MissionRuntime`.

## Product Integrations

MissionForge core adapters are protocol, process, host, worker, or provider
boundaries. They must not contain product-specific task semantics.

Product integrations live outside the `missionforge` Python package. The
SkillFoundry migration bridge is now under `integrations/skillfoundry/` and
depends on MissionForge rather than being imported by it.

```bash
./scripts/validate_integrations.sh skillfoundry
```
