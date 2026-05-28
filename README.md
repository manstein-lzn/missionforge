# MissionForge

MissionForge is a runtime for executing structured Mission IR with observable
LLM workers, controlled steering proposals, evidence gates, adaptive repair,
and verified closure.

It is intentionally not a SkillFoundry rewrite. SkillFoundry should become one
application on top of MissionForge. MissionForge owns the generic substrate:

```text
MissionIR + Workspace + WorkerProvider + ToolRegistry
  -> MissionResult + EvidenceLedger + Artifacts + Metrics
```

## Design Stance

- Mission semantics live in Mission IR and profile data, not task-name branches.
- The runtime core does not depend on LangGraph. LangGraph is an optional host.
- The only first-class worker target is PiWorker. Other workers are out of
  scope until the PiWorker path is complete.
- The PiWorker design is inspired by the MIT-licensed PI GitHub project. The
  initial skeleton does not vendor PI code; any future copied or adapted PI
  code must retain required attribution.
- Context and evidence are first-class runtime objects, not chat memory.
- Worker self-report is never acceptance evidence.
- LLM output is proposal, hypothesis, or review evidence; it is never
  acceptance by itself.
- Verifier failures must become structured repair inputs.
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

- [Development Goal Protocol](docs/DEVELOPMENT_GOAL_PROTOCOL.md): `/goal`
  operating contract, verification discipline, safe-point control, and
  completion rules.
- [Component Development Plan](docs/COMPONENT_DEVELOPMENT_PLAN.md): six-phase
  component backlog from contract kernel through adapter preparation.
- [Component Acceptance Matrix](docs/COMPONENT_ACCEPTANCE_MATRIX.md): phase gate
  checklists and cross-cutting invariants.
- [Follow-On Goals](docs/FOLLOW_ON_GOALS.md): post-runtime-kernel goal
  contracts for adapter boundary preflight, faux PiWorker, SkillFoundry
  compiler, and optional host shells.
- [Phase 11 Operator Productization Plan](docs/PHASE11_OPERATOR_PRODUCTIZATION_PLAN.md):
  CLI, inspection, diagnosis, resume, review, and validation workflows on top
  of the Phase 10 durable runtime state.
- [Phase 11 Operator Productization Goals](docs/PHASE11_OPERATOR_PRODUCTIZATION_GOALS.md):
  `/goal`-ready implementation slices for the Phase 11 operator surface.

## Package Layout

```text
src/missionforge/
  adapters/
    cli.py       Optional CLI/Python host shell around MissionRuntime
    contracts.py Adapter boundary, invocation, diagnostic, and result contracts
    observation.py Optional read-only run view and ControlRequest writer
    steering_llm.py Optional controlled steering LLM adapter
    piworker.py  Deterministic faux PiWorker adapter contracts and fixture run
    skillfoundry.py Deterministic FrontDesk refs to MissionIR compiler adapter
  contracts.py   Shared enums, errors, safe refs, hashing, validation helpers
  evidence.py    Evidence and artifact ref contracts
  freeze.py      Mission expansion and frozen contract hashing
  harness.py     Proposal validation and work-unit harness
  ir.py          Mission IR dataclasses and validation
  mission.py     Mission contract compatibility surface
  profiles.py    Capability and verification profile expansion
  runner.py      Public MissionRuntime/MissionResult boundary
  runtime.py     Deterministic runtime vertical slice
  steering.py    Controlled steering contract objects
  steering_store.py Run-local controlled steering artifact refs
  verifier.py    Verification routing
  verification.py Validator and verification result contracts
  work_unit.py   Work-unit and execution report contracts
  workers.py     Generic worker adapter protocol boundary
docs/
  ARCHITECTURE.md
  MISSION_IR.md
  DESIGN_PROGRAM.md
  DEVELOPMENT_PROTOCOL.md
  DEVELOPMENT_GOAL_PROTOCOL.md
  COMPONENT_DEVELOPMENT_PLAN.md
  COMPONENT_ACCEPTANCE_MATRIX.md
  FOLLOW_ON_GOALS.md
  PHASE11_OPERATOR_PRODUCTIZATION_PLAN.md
  PHASE11_OPERATOR_PRODUCTIZATION_GOALS.md
  modules/
    adapter_contracts.md
    controlled_steering.md
    skillfoundry_adapter.md
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
