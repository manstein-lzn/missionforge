# MissionForge Pi-Based Minimal Kernel Development Plan

Last updated: 2026-06-03

Status: consolidation plan for converging MissionForge into a Pi-based,
orthogonal, minimal, complete intelligent delegation kernel.

## One-Sentence Target

MissionForge is a deterministic delegation kernel around Pi: Pi runs the
agent loop, while MissionForge freezes contracts, bounds tools, records
evidence, validates outputs, routes independent judgment, and controls repair
or revision.

The core formula is:

```text
MissionForge = Pi Agent loop + hard MissionForge boundary + deterministic validation
```

## Current State

MissionForge is already moving in the right direction, but it is not yet in its
final shape.

What is already aligned:

- `TaskContract`, `WorkerBrief`, `JudgeRubric`, `WorkspacePolicy`, and
  `PermissionManifest` exist as the contract shell.
- `AgentExecutionPacket`, `JudgePacket`, `AgentExecutionReport`, and
  `JudgeReport` separate executor and judge roles.
- `PiWorkerCall` and `PiWorkerCallResult` now define the beginning of a shared
  "unreliable intelligent RPC" boundary.
- `PiAgentExecutorNode`, `PiAgentJudgeNode`, and FrontDesk Pi nodes already
  project work into Pi-backed runtime calls.
- `RunWorkspace` and `PermissionEnforcer` enforce refs, writable roots, denied
  refs, command declarations, and unsupported hard policies.
- Runtime results and operator surfaces are increasingly refs-first and
  ledger-oriented.
- Benchmark/value-benchmark code has been removed from the active product
  lane, reducing core noise.
- `create_default_task_contract_flow()` can assemble a TaskContract-native
  runner with Pi-backed executor and judge nodes.
- `workers/pi-agent-runtime` already contains a Pi Agent loop sidecar with
  guarded file tools, exact bash allowlist behavior, env allowlist handling,
  faux-provider tests, and secret redaction.
- SkillFoundry now lives as an external integration and can compile
  FrontDesk/product intent into TaskContract-shaped outputs.

What is still not final:

- MissionForge is in convergence/cutover, not early design. The missing work is
  default-path closure and cleanup, not inventing more abstractions.
- Repair and revision records exist, but repair/revision Pi nodes are not yet
  uniformly expressed as the same `PiWorkerCall` lifecycle.
- The Python `WorkUnitContract` compatibility shape still leaks into the
  Pi call path. It can remain as an adapter projection, but it should not be
  the conceptual center.
- Permission enforcement is partially split between Python-side policy and
  `workers/pi-agent-runtime`. The final authority model needs one explicit
  contract for read, write, command, network, env, and unsupported hard policy
  checks.
- Session, savepoint, and event artifacts exist, but MissionForge's durable
  truth should be an append-only ledger of contract, packet, call, validation,
  judge, repair, revision, and final-package records.
- Several docs are stale relative to code. For example, some plans still
  describe live Judge PiWorker and FrontDesk PiWorker execution as future work
  even though `PiAgentJudgeNode` and `FrontDeskPiNodeRunner` exist.
- The public API remains broad because legacy MissionIR/runtime/steering
  symbols are still exported beside the newer TaskContract path.

## Non-Negotiable Shape

MissionForge must not become another thick agent framework.

It must not:

- reimplement Pi's agent loop;
- expose a public provider zoo or general multi-worker registry;
- make executor self-report into acceptance authority;
- let Pi sessions, summaries, or compaction replace frozen contracts;
- put product semantics into `src/missionforge`;
- treat prompt instructions as the security boundary;
- use interactive human confirmation as the primary runtime safety boundary;
- let skills, profiles, or rubrics become hidden authority;
- mutate a frozen contract without an explicit revision record.
- keep MissionIR as the default execution authority after the TaskContract path
  is complete;
- let controlled steering, metrics, dashboards, or operator commands become
  acceptance or routing authority.

It must:

- treat frozen `TaskContract` or explicit revision as task truth;
- treat every intelligent step as a bounded `PiWorkerCall`;
- validate refs, hashes, schemas, required artifacts, and permissions in code;
- use independent judge authority for semantic acceptance;
- preserve evidence and metrics as refs, not raw transcripts or secret-bearing
  payloads;
- keep product-specific compilation outside core.

## Minimal Complete Architecture

### 1. FrontDesk Boundary

Purpose: convert messy user conversation into a product-neutral intent bundle.

Core output:

```text
FrontDeskIntentBundle
```

Allowed intelligence:

- requirement grilling;
- hidden constraint discovery;
- solution sketching;
- intent bundle authoring.

Boundary:

- FrontDesk Pi nodes are `PiWorkerCall(role=frontdesk_author_piworker)`;
- output is schema-validated and refs-bound;
- FrontDesk does not freeze final task authority.

### 2. Product Integration Boundary

Purpose: compile product meaning into a task contract.

Core output:

```text
TaskContract
WorkspacePolicy
PermissionManifest
JudgeRubric fragments or refs
FinalPackage expectations
```

Boundary:

- product semantics live in integrations, profiles, rubrics, and fixtures;
- `src/missionforge` never branches on product names or task types;
- product integration may author hard checks, but core only executes declared
  checks and validates refs/results.

### 3. Contract Kernel

Purpose: freeze durable task authority.

Core objects:

```text
TaskContract
TaskContractRevision
ContractClause
contract_hash
```

Responsibilities:

- deterministic serialization and hashing;
- source refs and product refs;
- explicit revision policy;
- rejection of malformed, unsafe, stale, or non-ref-safe contract payloads.

### 4. Projection Layer

Purpose: derive role-specific views without changing authority.

Core projections:

```text
TaskContract -> WorkerBrief
TaskContract -> JudgeRubric
JudgeReport -> RepairBrief | TaskRevisionRequest
```

Responsibilities:

- executor sees what to produce and where it may write;
- judge sees what to inspect and how to decide;
- repair sees a frozen-contract-preserving fix request;
- revision drafter sees only enough evidence to propose a new contract
  version.

### 5. PiWorkerCall Boundary

Purpose: define one bounded unreliable intelligence call.

Every intelligent node must pass through:

```text
PiWorkerCall
  -> Pi runtime input
  -> Pi agent loop
  -> PiWorkerCallResult
  -> deterministic validation
```

Canonical roles:

- `frontdesk_author_piworker`
- `executor_piworker`
- `judge_piworker`
- `repair_piworker`
- `revision_drafter_piworker`

The call result is boundary evidence only. It never grants final semantic
acceptance.

### 6. Runtime Boundary

Purpose: adapt `PiWorkerCall` into the actual Pi runtime.

Current implementation:

```text
PiWorkerCall -> WorkUnitContract -> workers/pi-agent-runtime
```

Target implementation:

```text
PiWorkerCall -> PiAgentRuntimeInput -> workers/pi-agent-runtime
```

`WorkUnitContract` can remain as a compatibility adapter until the direct input
contract is complete. It should not keep accumulating new authority.

### 7. Permission And Workspace Boundary

Purpose: make tool authority executable in code.

Core objects:

```text
WorkspacePolicy
PermissionManifest
PermissionDecision
RunWorkspace
```

Responsibilities:

- path containment;
- readable refs;
- writable refs;
- denied refs;
- command allowlist;
- network policy;
- environment allowlist;
- secret exclusion;
- unsupported hard-policy fail-closed behavior.

Prompt text may explain the rules. Only code enforces them.

### 8. Ledger And Evidence Boundary

Purpose: preserve durable truth independent of Pi memory.

Canonical append-only records:

```text
contract_frozen
projection_written
packet_issued
piworker_call_started
tool_boundary_decision
piworker_call_result
output_validation
hard_check_result
judge_report
repair_ticket
revision_request
contract_revision_frozen
final_package
```

Rules:

- ledger entries cite refs and hashes;
- raw prompts, transcripts, stdout/stderr bodies, provider payloads, artifact
  bodies, and secrets are not ledger truth;
- Pi compaction and summaries are continuation aids only.

### 9. Validation And Judge Boundary

Purpose: separate deterministic validity from semantic judgment.

Deterministic validation checks:

- schema version and shape;
- contract hash binding;
- packet hash binding;
- refs are safe and authorized;
- expected artifacts exist;
- expected outputs are under writable refs;
- required hard checks are present and passed;
- no forbidden authority fields in metadata;
- no executor acceptance claim.

Semantic judgment:

- only `judge_piworker` may return `accepted`, `repair`,
  `revision_required`, or `rejected`;
- judge output must be schema-validated and bound to the frozen contract,
  packet, hard-check refs, artifact refs, and execution report.

### 10. Repair And Revision Boundary

Purpose: keep failure recovery explicit.

Repair:

- contract remains valid;
- executor output is insufficient;
- create `RepairBrief`;
- run `PiWorkerCall(role=repair_piworker)` or executor follow-up with a repair
  packet;
- judge again.

Revision:

- contract is wrong, incomplete, impossible, unsafe, or materially stale;
- create `TaskRevisionRequest`;
- require product/user/operator authority according to revision policy;
- freeze a new `TaskContract` revision before continuing.

### 11. Final Package And Observation Boundary

Purpose: expose completion without turning UI, CLI, dashboard, or metrics into
authority.

Core output:

```text
FinalPackage
DecisionLedger tail
Run replay summary
Operator observation envelope
```

Responsibilities:

- package accepted artifact refs, judge report refs, hard-check refs, metrics,
  and contract hash;
- allow operator inspection and replay from refs;
- keep public output concise and refs-only by default;
- never embed raw Pi transcripts, provider payloads, stdout/stderr bodies, or
  artifact bodies.

## PiWorkerCall Interface Target

The target call contract should stay small:

```text
PiWorkerCall
  call_id
  role
  contract_id
  contract_hash
  contract_ref
  objective
  visible_refs
  writable_refs
  expected_output_refs
  permission_manifest_ref
  source_packet_ref
  source_packet_hash
  evidence_refs
  output_schema_ref
  validation_policy_ref
  runtime_budget
  metadata
```

The target result contract should stay equally small:

```text
PiWorkerCallResult
  result_id
  call_id
  role
  contract_id
  contract_hash
  contract_ref
  status
  output_refs
  runtime_refs
  evidence_refs
  metric_refs
  validation_report_ref
  error_ref
  started_at
  completed_at
  metadata
```

Required invariants:

- completed result must include every expected output ref;
- every output ref must be under writable refs;
- every visible or evidence ref must be authorized readable input;
- result status cannot be `accepted` or any semantic equivalent;
- metadata cannot carry `accepted`, `decision`, `judge_decision`,
  `semantic_acceptance`, or similar authority;
- validation report is required before a result can feed judge or final
  packaging.

## Orthogonal Module Map

Keep each module with one authority:

| Authority | Owns | Must not own |
| --- | --- | --- |
| FrontDesk | intent discovery | final contract truth |
| ProductIntegration | product compilation | runtime execution |
| Contract Kernel | frozen task truth | worker prompt behavior |
| Projection | role views | contract mutation |
| PiWorkerCall | bounded intelligent invocation | semantic acceptance |
| Pi Runtime Adapter | Pi process/session/tool loop | product semantics |
| Permission Boundary | executable authority checks | prompt wording |
| Workspace | filesystem refs and containment | semantic validation |
| Ledger/Evidence | durable refs and hashes | chat memory |
| Validator | deterministic correctness | product taste judgment |
| Judge | semantic acceptance | permission expansion |
| Repair | fix under same contract | contract weakening |
| Revision | explicit contract change | silent runtime mutation |

## Development Plan

### Phase 0: Freeze The Target Shape

Goal: make this plan the controlling convergence document and align stale
status claims.

Tasks:

- keep this document as the short canonical plan;
- mark older phase docs as historical or subordinate where needed;
- document that `PiWorkerCall` is the conceptual center;
- update module docs only where they conflict with this plan.
- update stale docs that still describe implemented Pi judge or FrontDesk Pi
  nodes as future work;
- record that the project is now in cutover/convergence, not architecture
  discovery.

Acceptance:

- a new agent can read this document plus `AGENTS.md` and understand the target;
- no new runtime behavior is required;
- no plan claims that MissionForge should reimplement Pi.
- no active plan tells an implementer to rebuild functionality already present
  in `PiAgentJudgeNode`, `FrontDeskPiNodeRunner`, or the TaskContract runtime
  preset.

### Phase 1: Make The TaskContract Path The Default Lane

Goal: expose one normal MissionForge path around TaskContract-native Pi calls.

Tasks:

- make the default product-neutral flow:
  `TaskContract -> projections -> PiWorkerCall executor -> validation ->
  PiWorkerCall judge`;
- keep MissionIR runtime as compatibility-only during the transition;
- expose one public facade for the TaskContract-native path;
- prevent public API confusion by documenting which legacy exports are
  compatibility surfaces.

Acceptance:

- a product-neutral TaskContract run uses Pi-backed executor and judge nodes by
  default;
- compatibility paths still pass tests but are not described as the primary
  architecture;
- public docs do not present MissionIR as the default task authority;
- import-boundary tests still prevent adapter internals and product semantics
  from leaking into core.

### Phase 2: Promote PiWorkerCall To The Single Intelligent RPC

Goal: route every intelligent node through `PiWorkerCall`.

Tasks:

- ensure FrontDesk authoring nodes, executor, judge, repair, and revision
  drafting all build `PiWorkerCall`;
- add missing constructors for repair and revision roles;
- add `output_schema_ref`, `validation_policy_ref`, and runtime budget fields
  if needed;
- make `PiWorkerCallResult` the required normalized result envelope.

Acceptance:

- tests prove each intelligent role emits a valid `PiWorkerCall`;
- no role directly invokes `PiAgentRuntimeAdapter` without a call envelope;
- executor call result cannot express acceptance;
- result validation rejects missing expected outputs and unauthorized output
  refs.
- every call result has a validation report ref before it can feed judge,
  repair, revision, or final package logic.

### Phase 3: Make Direct Pi Runtime Input Native

Goal: stop treating `WorkUnitContract` as the conceptual runtime API.

Tasks:

- define `PiAgentRuntimeInput` directly from `PiWorkerCall`;
- keep `WorkUnitContract` projection only as a temporary compatibility layer;
- move call id, visible refs, writable refs, expected refs, permission
  manifest, output schema, and validation policy into the Pi runtime input;
- keep provider config and secrets environment-only.

Acceptance:

- `workers/pi-agent-runtime` can consume direct call-shaped input in faux mode;
- existing WorkUnit path still works during migration;
- tests prove no secret appears in input, output, metrics, ledger, or evidence;
- adapter output always normalizes to `PiWorkerCallResult`.

### Phase 4: Harden Permission Membrane

Goal: make tool authority fail closed at the boundary.

Tasks:

- route Pi file reads, writes, and shell requests through permission checks;
- record `PermissionDecision` entries for denied and high-risk operations;
- separate readable refs, writable refs, runtime-owned refs, and denied refs;
- make unsupported hard policies block execution instead of becoming comments;
- clarify command policy format beyond exact string allowlist where required.

Acceptance:

- attempted path traversal fails;
- writes outside writable refs fail;
- writes to runtime-owned refs fail;
- denied refs override allowed roots;
- unsupported hard policies fail closed;
- shell/network/env behavior is either hard-enforced or explicitly unsupported.

### Phase 5: Build The Authoritative Ledger And Replay Surface

Goal: make MissionForge truth independent of Pi sessions and summaries.

Tasks:

- define append-only ledger event schema;
- record contract freeze, projection, packet issue, call start/result,
  validation, judge, repair, revision, and final package events;
- bind every event to refs and hashes;
- treat Pi session tree/savepoints as runtime refs inside the ledger, not as
  task authority.
- add a run replay summary that can reconstruct the current state from ledger
  refs and hashes.

Acceptance:

- a run can be reconstructed from ledger refs and hashes;
- no ledger event embeds raw transcript, provider payload, artifact body, or
  secret;
- compaction/session summaries are present only as continuation refs;
- final package cites contract, judge report, hard checks, artifacts, and
  ledger tail.
- replay can explain whether the run is accepted, repair-needed,
  revision-required, rejected, or blocked without reading Pi chat memory.

### Phase 6: Normalize Judge, Repair, And Revision

Goal: close the loop without adding orchestration thickness.

Tasks:

- judge always consumes a validated execution call result and hard-check refs;
- repair is created only from judge decision or deterministic validation
  failure;
- revision is created only through explicit `TaskRevisionRequest`;
- repair/revision Pi nodes reuse the same `PiWorkerCall` boundary.

Acceptance:

- judge cannot accept failed or missing hard checks;
- judge cannot accept artifacts not produced by the executor call;
- repair preserves the same contract hash;
- revision changes the contract only after a new revision is frozen;
- final acceptance always comes from validated judge output, not executor
  report, CLI status, metrics, or Pi session summary.

### Phase 7: Close SkillFoundry On The TaskContract Path

Goal: prove the kernel with one real integration without polluting core.

Tasks:

- make SkillFoundry compile FrontDesk/ProductIntegration output into
  TaskContract-native refs;
- route its default execution through the TaskContract PiWorkerCall path;
- keep any MissionIR facade explicitly compatibility-only;
- ensure SkillFoundry tests do not require product branches in
  `src/missionforge`.

Acceptance:

- SkillFoundry integration passes on the TaskContract-native path;
- MissionForge core contains no SkillFoundry-specific semantic branches;
- SkillFoundry final package cites contract, artifacts, judge report, hard
  checks, metrics, and ledger refs;
- compatibility MissionIR behavior is either removed or clearly demoted.

### Phase 8: Cut Legacy Expansion Paths

Goal: keep MissionForge small after the new path works.

Tasks:

- demote legacy MissionIR/runtime paths to compatibility or remove them only
  after equivalent tests exist;
- remove stale docs that imply MissionForge is a broad workflow engine;
- keep SkillFoundry as an integration, not a core branch;
- avoid adding new product-specific benchmark lanes to core.

Acceptance:

- `src/missionforge` has no product-specific semantic branches;
- tests cover the new PiWorkerCall path as the default path;
- legacy modules are either explicitly compatibility-only or gone;
- validation remains green after cleanup.

### Phase 9: Tighten Public API And Operator Surface

Goal: make the final shape hard to misuse.

Tasks:

- split or demote broad root exports from `src/missionforge/__init__.py`;
- expose the TaskContract/PiWorkerCall kernel as the main public surface;
- keep adapter internals out of root exports;
- ensure operator commands inspect and control refs, not hidden runtime state.

Acceptance:

- root public API makes the intended path obvious;
- tests prove adapter internals and product integrations are not exported as
  core primitives;
- operator output remains refs-only and cannot mark acceptance by itself.

## Verification Strategy

Each phase must verify the boundary it changes.

Minimum command for code changes:

```bash
MISSIONFORGE_SKIP_NPM_CI=1 ./scripts/validate.sh
```

Focused tests should be added before broad validation:

- `tests/test_piworker_call.py`
- `tests/test_pi_agent_runtime_adapter.py`
- `tests/test_frontdesk_pi_node_runner.py`
- `tests/test_agentic_flow.py`
- `tests/test_permissions.py`
- SkillFoundry TaskContract-path integration tests
- `workers/pi-agent-runtime/tests/*.test.mjs`

Docs-only edits do not require full validation, but must not contradict
`AGENTS.md` or this plan.

## Completion Definition

MissionForge reaches the desired shape when this full path works without
special-case orchestration:

```text
FrontDeskIntentBundle
  -> ProductIntegration.compile_task_contract()
  -> freeze TaskContract
  -> project WorkerBrief + JudgeRubric + PermissionManifest
  -> PiWorkerCall(role=executor)
  -> Pi runtime
  -> PiWorkerCallResult + deterministic validation
  -> hard checks
  -> PiWorkerCall(role=judge)
  -> JudgeReport
  -> accepted | repair | revision_required | rejected
  -> RepairBrief or TaskRevisionRequest or FinalPackage
  -> append-only ledger
```

At that point MissionForge is not "smart by itself". It is reliable because it
delegates smart work to Pi through a narrow, inspectable, enforceable contract.

## Largest Engineering Risks

The main risks are not algorithmic. They are boundary drift.

Risk: MissionForge grows into an agent framework.

Mitigation: keep Pi as the only first-class intelligent loop and keep
`PiWorkerCall` as the only intelligent invocation boundary.

Risk: product semantics creep into core.

Mitigation: require ProductIntegration, profiles, rubrics, fixtures, or tests
for product-specific behavior. Core only validates declared contracts and refs.

Risk: permission enforcement is overclaimed.

Mitigation: every shell, network, env, and hard-policy feature must be either
hard-enforced in code or marked unsupported and fail closed.

Risk: MissionIR and TaskContract both look primary.

Mitigation: make TaskContract-native PiWorkerCall path the default, then demote
MissionIR to compatibility-only or remove it after equivalent tests exist.

Risk: judge independence weakens.

Mitigation: judge consumes frozen contract, rubric, hard-check refs, execution
report, call result, and artifact refs. It must not rely on executor prose or
shared conversational memory.

Risk: ledger is incomplete.

Mitigation: completion and recovery must be explainable from append-only ledger
refs and hashes, not from Pi session summaries.

Risk: stale docs drive duplicate work.

Mitigation: Phase 0 explicitly aligns documentation status before more runtime
implementation.

## Third-Party Review Notes

This plan was prepared with a third-party `gpt-5.5` xhigh architecture review
agent requested as an independent reviewer. The reviewer inspected the current
code and docs without modifying files, focusing on TaskContract, WorkerBrief,
JudgeRubric, PermissionManifest, Pi runtime adapter, PiWorkerCall,
FrontDesk/executor/judge/repair, ledger/session, ref policy, and validation.

Reviewer conclusion:

- MissionForge is already a solid thin-kernel implementation, not just a design
  sketch.
- The main gap is convergence: default TaskContract path, documentation
  alignment, final ledger/final package/replay, repair/revision closure, and
  legacy API demotion.
- The recommended shape is exactly one unreliable intelligent RPC:
  `PiWorkerCall -> Pi runtime -> PiWorkerCallResult -> deterministic
  validation`, with independent judge authority after that boundary.
