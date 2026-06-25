# Ref-Addressed Agent Toolkit Development Plan

Status: active plan for `feature/ref-addressed-agent-toolkit`

Last updated: 2026-06-24

Related documents:

- `STATUS.md`
- `docs/TOOLKIT_DATA_CONTEXT_ARCHITECTURE_PROPOSAL.md`
- `docs/KERNEL_API_DESIGN.md`
- `docs/INTERACTION_PORT.md`
- `docs/CONTEXT_MANAGEMENT_SHORT_TERM_PLAN.md`
- `docs/CAPABILITY_GRANT_SANDBOX_UPGRADE_PLAN.md`
- `docs/PRIMITIVE_REFERENCE.md`
- `docs/DEEP_RESEARCH_ROADMAP.md`

## Goal

MissionForge should become a small, product-neutral toolkit for building
bounded, inspectable, sandboxed agent systems from ordinary Python code.

It should not become a workflow framework, a graph DSL, a product-specific
reasoning system, or a deterministic semantic judge.

Target shape:

```text
trusted host Python
  -> MissionForge core primitives
  -> bounded PiWorker calls and tools
  -> refs, hashes, context views, events, ledgers
  -> independent judge boundary
```

The main architectural correction is:

```text
refs-first authority model
!=
disk-first data transport
```

Refs remain the durable identity and permission unit. The filesystem becomes one
materialization backend, not the conceptual data model.

## Architecture Boundaries

### MissionForge Core Owns

- frozen task authority;
- explicit contract revision;
- permission manifests;
- sandbox profiles and workspace projections;
- ref validation;
- artifact identity, hashes, versions, and provenance;
- read/write gates;
- tool gateway decisions;
- context projection boundaries;
- PiWorker call/result envelopes;
- execution, decision, and audit ledgers;
- role separation and independent judge boundary.

### Kernel API Owns

Kernel API is a developer-friendly facade over core primitives.

It may provide:

- `Step` declarations;
- compact `Flow` convenience for simple product-neutral routing;
- artifact descriptors;
- toolset descriptors;
- projection descriptors;
- failure policy descriptors;
- refs-first step and flow records.

It must not become:

- a general workflow engine;
- a graph DSL;
- a scheduler;
- a product semantic router;
- a hidden state manager;
- a domain-quality judge.

Kernel API should compile declarations into core objects:

```text
Step
  -> PiWorkerCall
  -> PermissionManifest
  -> ArtifactRecord expectations
  -> ContextView
  -> sandbox/tool gateway configuration
  -> step record and ledger events
```

### Product Integrations Own

- user-facing workflow choices;
- prompts, manuals, and rubrics;
- domain schemas;
- report or artifact style;
- semantic review criteria;
- final product packaging;
- product-specific CLIs, TUIs, and APIs.

DeepResearch is one product integration and one pressure test. It must not leak
research semantics into `src/missionforge`.

## Core Principles

- Raw chat is not operational task truth.
- A frozen `TaskContract`, or explicit revision, remains durable task authority.
- PiWorker is the first-class intelligent worker.
- Execution workers may not self-accept their own work.
- Code can reject malformed, unsafe, unauthorized, stale, unreferenced, or
  invalidly shaped outputs.
- Code must not pretend to judge product-level semantic quality.
- Runtime records should cite refs, hashes, versions, and event ids by default.
- Raw prompts, provider payloads, tool output bodies, stdout/stderr bodies, and
  secrets must not be embedded in operator-facing durable state by default.
- Context compaction may manage structure, but semantic summarization must be an
  explicit PiWorker/Judge-authored artifact.
- Host Python is trusted orchestration. Agents and tools are bounded actors.

## Target Primitive Set

The core should stay small. Proposed active primitives:

```text
TaskContract
TaskContractRevision
PermissionManifest
SandboxProfile
ArtifactRecord
ArtifactStore
ReadGate
WriteGate
ToolGateway
ContextSegment
ContextView
PiWorkerCall
PiWorkerCallResult
DecisionLedger
RunEvent
RunSnapshot
ControlPort
```

Deferred primitives:

```text
Channel
Reducer
Superstep
Barrier
async materialization queue
external object store backend
public graph adapter
```

These deferred concepts may become useful later, but adding them now would push
MissionForge toward framework and database complexity before the core boundary
model is proven.

## Workstream 1: Data Plane

Status: first minimal slice implemented on 2026-06-24.

### Objective

Separate ref identity from filesystem path without weakening auditability or
permissions.

### Deliverables

1. Done for first slice: add `ArtifactRecord`.
2. Done for first slice: add explicit ref versioning through
   `ArtifactVersionRef`.
3. Add materialization state:
   - `volatile`
   - `durable`
   - `materialized`
   - `dirty`
4. Done for first slice: add filesystem-compatible `ArtifactStore` protocol and
   `FileArtifactStore`.
5. Done for first slice: add memory-backed store only for tests and
   non-authoritative intermediate data.

### Rules

- A committed artifact version is immutable.
- `latest` is a view, not a mutable body.
- Final outputs, judge inputs, contracts, permission manifests, and decision
  artifacts must reach durable state.
- Memory-only bodies may be used for small transient state, but must not become
  final authority.
- Hashes must be computed over canonical bytes or canonical structured
  serialization.

### Exit Criteria

- Existing filesystem refs still work.
- Tests prove that ref identity does not equal path identity.
- Tests prove versioned updates preserve previous versions.
- Tests prove durable artifacts survive process restart in the filesystem-backed
  store.
- Tests prove memory-backed artifacts stay volatile and non-authoritative.
- Tests prove rejected filesystem commits do not leave unindexed bodies that
  poison the next valid version.
- Tests prove committed record provenance cannot be mutated through returned
  record objects or original input containers.
- Tests prove durable body corruption is rejected when reading or reloading the
  filesystem-backed store.
- Tests prove serialized artifact records carry an explicit matching
  `version_ref`.

## Workstream 2: Permission Gates

Status: Phase 1 implemented on 2026-06-24.

### Objective

Move permission enforcement into explicit gates before changing the data
transport layer.

### Deliverables

1. Done: add `ReadGate`.
2. Done: add `WriteGate`.
3. Done: route PiWorker read/write operations through gate-compatible checks.
4. Done for Phase 1: runtime-owned roots are rejected for PiWorker writes.
5. Done for tool/runtime gateway paths: permission decisions remain refs-first.

### Rules

- Denied refs override readable and writable roots.
- Workers cannot write contract, permission, ledger, projection, or runtime-owned
  records unless explicitly allowed by a runtime path.
- Judge access to raw tool observations must be explicit.
- A visible ref must be readable through the effective permission manifest.

### Exit Criteria

- Covered by gate tests: executor-visible refs must be readable through the
  effective manifest.
- Covered by context snapshot tests: judge manifests do not inherit executor raw
  observation refs unless explicitly granted.
- Covered by `WriteGate`: PiWorker cannot write runtime-owned refs.
- Covered by runtime tests: a malformed or unauthorized write becomes a boundary
  failure, not a Python
  traceback.

## Workstream 3: Tool Gateway And Sandbox

Status: Phase 1 allowed-tools boundary implemented on 2026-06-24.

### Objective

Ensure all tool effects pass through enforceable permission and sandbox
boundaries.

### Deliverables

1. Done: allowed tool names are a hard `PermissionManifest` and
   `SandboxProfile` field.
2. Done: shell-like tools require both `allowed_tools` and exact command
   allowlist entries.
3. Done: environment and secret scrubbing remains explicit.
4. Done: tool gateway decisions record refs, hashes, status, and safe reasons
   without raw command/env/body values.
5. Done for Phase 1: sidecar tool mounting and sandbox profile projection are
   aligned with `PermissionManifest.allowed_tools`.
6. Done for Phase 1: extension tools cannot shadow core tool names and are
   gateway-wrapped before execution.

### Exit Criteria

- Covered by compiler and sidecar tests: a step requesting an ungranted tool
  fails closed.
- Covered by sidecar tests: shell commands outside the allowlist are denied.
- Tool events expose refs, hashes, sizes, status, and safe summaries by default.
- Secret values do not appear in durable operator-facing records.

## Workstream 4: Context Plane

Status: Phase 3 first slice implemented on 2026-06-24.

### Objective

Replace ad hoc file concatenation with role-specific, permission-aware,
cache-friendly context projection.

### Deliverables

1. Done for first slice: add `ContextSegment`.
2. Done for first slice: add `ContextView`.
3. Done for first slice: split diagnostic context into:
   - `stable_prefix`
   - `semi_stable_context`
   - `volatile_tail`
   - `omitted_segments`
4. Done for first slice: add context projection diagnostics.
5. Done for first slice: add tool observation demotion policy.
6. Done for first slice: add context pressure safe-point policy.

Current integration:

- Kernel `run_step` writes a refs-only `context_projection.json`.
- Step records include `context_projection_ref` and `context_hash`.
- Runtime behavior and provider-facing prompts are not changed by this slice.

### Rules

- Authority segments are stable and not rewritten by compaction.
- Volatile data stays out of the stable prefix.
- Large tool output is represented by ref/hash/preview unless explicitly
  requested and authorized.
- Runtime compaction may create stubs and checkpoints.
- Semantic summaries must be explicit PiWorker/Judge artifacts with source refs
  and hashes.

### Exit Criteria

- Stable prefix projection is deterministic across equivalent runs.
- Context diagnostics are refs-only by default.
- Tool output demotes to observation stubs after the immediate useful window.
- A user can inspect why a role did or did not see a ref.

## Workstream 5: Observation And Control Plane

Status: Phase 4 first slice implemented on 2026-06-24.

### Objective

Make MissionForge transparent, debuggable, interruptible at safe points, and
usable as an embedded subsystem.

### Deliverables

1. Done for first slice: add structured `RunEvent` records for Kernel
   boundaries:
   - run started;
   - step compiled;
   - context projected;
   - route decided;
   - safe point reached;
   - user intervention received;
   - step completed;
   - judge accepted/rejected;
   - run stopped.
2. Done for first slice: add `RunSnapshot`.
3. Done for first slice: add `ControlPort` operations:
   - pause;
   - cancel;
   - inject message;
   - request revision;
   - resume;
   - stop after current turn;
   - force checkpoint.
4. Done for first debug slice: add fixture-flow debug stepping support:
   - compile next step;
   - inspect permissions;
   - inspect context;
   - run one explicit step;
   - route one explicit decision artifact.
5. Done for first inspect slice: add a product-neutral Kernel run inspection
   helper over flow result, run snapshot, run events, flow ledger, step records,
   context projection refs, artifact refs, metric refs, and execution report
   refs.

Current integration:

- Kernel `run_flow` writes execution-scoped
  `observation/run_events.jsonl` and `observation/run_snapshot.json`.
- Flow result metadata includes `run_events_ref` and `run_snapshot_ref`.
- `missionforge.kernel.inspect_kernel_run()` gives host applications a
  refs-only summary without expanding artifact bodies, prompts, execution
  reports, provider payloads, tool bodies, or safe-point user text.
- `python -m missionforge.adapters.cli tui` / `status` gives host applications
  and operators a read-only status surface over the same refs-only inspection
  result.
- `preview_flow_step()`, `run_flow_step_once()`, and `read_flow_route()` provide
  a minimal no-cursor debug stepping trio. They do not schedule a Flow, run
  until completion, auto-repair, auto-accept, or create production flow records.
- `stop_after_current_turn` lets the visible step run and then blocks before
  route progression.
- User text remains in the interaction plane; observation records only carry
  refs, counts, ids, status, phase, and safe metadata.

### Rules

- Control requests do not mutate a running tool invocation by default.
- User events are interventions, not task authority.
- Contract-changing interventions must produce revision requests or explicit
  revision records.
- Observation defaults are safe: refs, hashes, sizes, phases, and status before
  raw bodies.

### Exit Criteria

- Done for first inspect slice: a host UI can show current phase, step, role,
  latest refs, observation refs, and last safe point from refs-only Kernel
  inspection.
- Done for first debug slice: a developer can preview one explicit fixture
  step, run it once under a debug prefix, and inspect the route target.
- Done for first host cookbook slice: a product-neutral example shows ordinary
  Python code using preview, debug-run, flow execution, route inspection, and
  refs-only run inspection without DeepResearch semantics.
- Done for first host observer slice: a read-only adapter CLI can render a
  `MissionRunView` from `inspect_kernel_run()` as JSON or compact terminal
  text.
- Still open: richer tool activity, context pressure display, usage display,
  and replay helpers.
- A user can pause before the next step.
- A user can inject guidance that becomes visible through explicit safe-point
  input refs.
- A developer can single-step a fixture flow.

## Workstream 6: Kernel API Alignment

### Objective

Keep Kernel API as the ergonomic declaration layer while moving authority into
the new primitives.

### Deliverables

1. Compile `Step` into:
   - `PiWorkerCall`
   - `PermissionManifest`
   - expected `ArtifactRecord` declarations
   - `ContextView`
   - sandbox and tool gateway policy
2. Keep `Flow` minimal and product-neutral.
3. Preserve route extraction only from structured decision artifacts.
4. Done for first inspect slice: add refs-only inspection hooks to Kernel runs.
5. Done for first debug slice: add fixture-flow debug stepping primitives.
6. Done for first host cookbook slice: add a minimal product-neutral example.
7. Deferred: replay helpers.

### Rules

- Flow must not inspect Markdown or free-form prose to route.
- Accepted terminal status must come from a judge-role step or explicit
  product-owned accepted artifact.
- Flow may coordinate, but it may not judge semantic sufficiency.

### Exit Criteria

- DeepResearch can remain thin over Kernel API.
- Done for first host cookbook slice: a tiny example can use Kernel API without
  copying DeepResearch internals.
- Kernel API docs explain the boundary between convenience and authority.

## Workstream 7: DeepResearch Integration

### Objective

Use DeepResearch as a product-level pressure test without moving research logic
into core.

### Deliverables

1. Keep DeepResearch role prompts, rubrics, source tools, and report contracts
   in `integrations/deepresearch`.
2. Consume `ContextView` diagnostics for better long-run stability.
3. Consume observation/control events for TUI progress and interruption.
4. Keep final paths, usage summary, and report exports visible to users.

### Exit Criteria

- DeepResearch standard and intensive runs can use the new core boundaries
  without product semantics entering `src/missionforge`.
- The TUI can show project-level state, not just raw tool events.
- Reports and source artifacts remain easy to locate after completion.

## Implementation Phases

### Phase 0: Documentation And Baseline

Status: active.

Deliverables:

- maintain `STATUS.md`;
- maintain this development plan;
- keep `docs/TOOLKIT_DATA_CONTEXT_ARCHITECTURE_PROPOSAL.md` as review input,
  not an implementation contract;
- preserve current passing tests.

Exit criteria:

- project direction is visible from the repository root;
- next implementation work has explicit non-goals and exit criteria.

### Phase 1: Gates Before Storage

Deliverables:

- `ReadGate`;
- `WriteGate`;
- tool allowlist enforcement;
- permission decision records;
- focused tests for role and owner boundaries.

Exit criteria:

- filesystem-backed behavior remains compatible;
- unauthorized access is rejected at the gate layer;
- tests cover executor/judge separation and runtime-owned refs.

### Phase 2: Artifact Records

Status: first minimal slice implemented on 2026-06-24.

Deliverables:

- `ArtifactRecord`;
- versioned refs;
- filesystem-compatible artifact store;
- artifact commit records;
- durability/materialization state.

Exit criteria:

- all existing refs can be represented as artifact records;
- durable refs survive reload;
- old file-based workflows still pass.

### Phase 3: Context View Diagnostics

Status: first slice implemented on 2026-06-24.

Deliverables:

- `ContextSegment`;
- `ContextView`;
- stable prefix discipline;
- tool observation stubs;
- context projection diagnostics.

Exit criteria:

- no major runtime behavior change is required;
- diagnostics explain context composition and omitted segments;
- prompt-cache-sensitive prefix is deterministic.

### Phase 4: Observation And Control

Status: first observation/control, inspect, and debug stepping slices implemented on 2026-06-24.

Deliverables:

- structured event stream;
- run snapshot;
- safe-point control operations;
- refs-only Kernel run inspection;
- debug stepping for fixture flows.

Exit criteria:

- done for first slice: host applications can observe Kernel runs through
  `RunEvent`, `RunSnapshot`, and `inspect_kernel_run()` without parsing raw
  logs;
- done for first slice: interruption remains safe-point based;
- done for first debug slice: fixture-flow stepping covers explicit preview,
  run-once, and route-read operations;
- deferred: replay helpers and host cookbook examples.

### Phase 5: Kernel And Product Migration

Status: first alignment slice implemented on 2026-06-24.

Deliverables:

- done for first slice: Kernel API writes `ContextView` diagnostics and
  observation refs without becoming a scheduler or semantic router;
- done for first inspect slice: Kernel API exposes a read-only, refs-only
  inspection helper for host UIs and debuggers;
- done for first debug slice: Kernel API exposes stateless fixture debug
  stepping helpers without becoming a scheduler;
- done for first host cookbook slice: `examples/kernel_host_toolkit_example.py`
  shows host-Python orchestration through public/kernel APIs;
- done for first host observer slice: `missionforge.adapters.cli` exposes a
  read-only status observer over Kernel run refs;
- done for first slice: DeepResearch result packages expose Kernel
  `run_events_ref` and `run_snapshot_ref`;
- docs and cookbook show host-Python orchestration patterns.

Exit criteria:

- done for first slice: DeepResearch remains a thin product integration;
- done for first slice: core package remains product-neutral;
- done for first host cookbook slice: docs and example show host-Python
  orchestration patterns.
- done for first host observer slice: host adapters can show project state from
  refs without driving orchestration.

## Explicit Non-Goals For This Branch

- No LangGraph dependency.
- No LangGraph clone.
- No graph DSL.
- No general-purpose scheduler.
- No public multi-worker registry.
- No semantic reducers.
- No full database or object-store implementation.
- No memory-only authority for final outputs.
- No product semantics in `src/missionforge`.

## Verification Plan

Always keep these checks green unless a phase explicitly updates the contract:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
PYTHONPATH=src:integrations/deepresearch/src python3 -m unittest discover -s integrations/deepresearch/tests
git diff --check
```

Before merge to `main`, also run the broader validation scripts when practical:

```bash
MISSIONFORGE_SKIP_NPM_CI=1 ./scripts/validate.sh
./scripts/validate_integrations.sh deepresearch
```

Live PiWorker runs remain opt-in and should not become mandatory CI.

## Code Size Discipline

New core code should justify itself as a reusable primitive. If a behavior is
specific to DeepResearch, FrontDesk, report writing, academic search, or a
domain product, it belongs outside `src/missionforge`.

Every new core module should answer:

- What boundary does this enforce?
- What authority does this preserve?
- What product-neutral primitive does this expose?
- Can this be expressed as host Python instead?
- Can this stay internal until two integrations need it?

If the answer is unclear, do not add it to core.

## Open Questions

1. What is the exact durable commit rule for small structured bodies?
2. Should `ArtifactStore` gain an adapter boundary after two integrations prove
   the minimal protocol?
3. Should `ContextView` be passed to Pi runtime as a first-class envelope or
   compiled into existing runtime input fields for compatibility?
4. What raw tool observations should a judge see by default, if any?
5. What is the minimum useful debug stepping API for host applications?
6. Which second small integration should prove the toolkit shape after
   DeepResearch?
