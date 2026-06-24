# MissionForge Toolkit Data And Context Architecture Proposal

Status: review draft

Date: 2026-06-24

Audience: MissionForge architecture review

Related documents:

- `docs/ARCHITECTURE.md`
- `docs/KERNEL_API_DESIGN.md`
- `docs/CONTEXT_MANAGEMENT_SHORT_TERM_PLAN.md`
- `docs/CAPABILITY_GRANT_SANDBOX_UPGRADE_PLAN.md`
- `docs/modules/piworker.md`
- `missionforge_update_plan.md`

## Executive Summary

MissionForge should become a Python SDK for building bounded, inspectable,
cache-aware, multi-agent industrial systems.

The package should provide primitives for task authority, data movement,
context projection, PiWorker execution, permission enforcement, evidence,
repair, revision, and judgment. Product authors should compose those primitives
with ordinary Python control flow. MissionForge should not become a closed
workflow engine, a product-specific reasoning layer, or a Python system that
pretends to understand semantic quality through deterministic branches.

The current refs-first architecture is directionally correct, but the current
disk-first implementation is too heavy as the default data path. Refs-first
should mean that information has stable identity, hash, provenance, permission
scope, role ownership, and auditability. It should not mean every intermediate
value must synchronously materialize as a filesystem file before another agent
can use it.

The proposed architecture separates five concerns:

```text
Authority Plane   frozen contract, role, permission, rubric, revision
Data Plane        ref, version, hash, artifact body, channel, reducer
Context Plane     role-specific, cache-aware model context projection
Runtime Plane     PiWorkerCall, ToolGateway, sandbox, provider loop
Audit Plane       WAL, ledger, checkpoint, async materialization
```

The main upgrade is a memory-first, ref-addressed `ArtifactStore` and
`ContextView` system:

```text
Python orchestration
  -> MissionForge primitives
  -> PiWorker semantic work inside hard boundaries
  -> independent Judge PiWorker acceptance
  -> refs-first audit and final package
```

## Review Decision Requested

Architecture review should decide whether MissionForge should adopt the
following direction:

1. Treat MissionForge as a Python package/toolbox rather than as a top-level
   workflow product.
2. Keep `TaskContract`, `PermissionManifest`, `PiWorkerCall`, role separation,
   refs-first evidence, explicit revision, and independent judge as hard
   invariants.
3. Replace disk-first data movement with a memory-first, versioned,
   permission-aware data plane.
4. Treat filesystem artifacts as one materialization backend, not as the
   conceptual data plane.
5. Build a first-class context plane around `ContextSegment`, `ContextView`,
   prompt-cache-aware projection, tool observation, and explicit compaction.
6. Continue to use Pi as the agent loop and tool-call substrate, while keeping
   MissionForge responsible for contracts, permissions, evidence, and
   judgment boundaries.

## Current Position

The active architecture is already centered on PiWorker:

```text
ProductIntegration
  -> TaskContract
  -> WorkerBrief + JudgeRubric + WorkspacePolicy + PermissionManifest
  -> PiWorkerCall(role=executor_piworker)
  -> artifact refs + execution report
  -> PiWorkerCall(role=judge_piworker)
  -> accepted | repair | revision_required | rejected
  -> DecisionLedger + FinalPackage
```

This direction is correct. The issue is the current implementation bias:
most information transfer happens through filesystem refs. That produces a
strict and inspectable system, but it also makes multi-agent collaboration,
state refinement, context projection, and high-frequency intermediate data
movement more cumbersome than necessary.

The desired correction is not to abandon refs-first. It is to separate ref
identity from storage backend.

```text
Wrong abstraction:
  ref == filesystem path

Better abstraction:
  ref == authorized, versioned, content-addressed information identity
  filesystem path == one possible materialized location
```

## Non-Negotiable Architecture Laws

The proposal must preserve these laws:

- Raw chat is not operational task truth.
- A frozen `TaskContract`, or an explicit revision, is durable task authority.
- MissionForge core remains product-neutral.
- Product semantics belong in integrations, manuals, contracts, rubrics,
  artifacts, and product gates.
- Code may reject malformed, unauthorized, stale, missing, unsafe, or
  unreferenced outputs.
- Code must not pretend to perform product-level semantic judgment.
- An execution worker may not self-accept its own work.
- Semantic acceptance must come from a separate judge role or product-owned
  accepted artifact.
- Repair must not weaken the frozen contract.
- Contract changes after execution starts require explicit revision records.
- Runtime and operator state should cite refs, hashes, and records by default.
- Raw prompts, transcripts, provider payloads, stdout/stderr bodies, artifact
  bodies, and secrets should not be embedded in durable operator state by
  default.
- Metrics are diagnostics and cost evidence, not semantic route or acceptance
  authority.
- Permission and workspace boundaries must be enforced by code and runtime
  tooling, not by prompt wording.

## Python Package Positioning

MissionForge should expose primitives that programmers compose with ordinary
Python.

```text
Python code owns orchestration.
MissionForge owns boundaries.
PiWorker owns semantic work.
Judge owns semantic acceptance.
```

Python is allowed and expected to do:

- loops;
- branching;
- fan-out and fan-in;
- retry;
- scheduling;
- queue integration;
- service APIs;
- hard checks;
- schema validation;
- permission validation;
- deterministic routing over structured decision artifacts.

Python should not do:

- infer arbitrary product intent in MissionForge core;
- rank papers, judge reports, or decide domain sufficiency in core;
- accept executor output semantically;
- silently broaden or weaken a frozen contract;
- encode product-specific branches in `src/missionforge`;
- hide semantic quality decisions behind validators.

The package root should eventually feel like this to product authors:

```python
from missionforge import (
    ArtifactStore,
    Channel,
    ContextProjector,
    PermissionManifest,
    PiWorkerCall,
    TaskContract,
    ToolGateway,
)
```

`missionforge.kernel.Flow` can remain useful as a convenience facade, but it
should not be the only way to build systems. The core SDK should be useful to
programmers who want to write their own orchestration in Python.

## What Pi Provides

MissionForge is built around PiWorker, but Pi and MissionForge should keep
separate responsibilities.

Pi provides the agent execution substrate:

- agent loop;
- model/provider adapter shape;
- tool-call protocol;
- tool result message handling;
- parallel tool execution support;
- event stream;
- usage and cache metrics;
- coding-agent tool factories such as read, write, edit, and bash;
- hooks such as context transformation, after-tool-call observation, and
  stop-after-turn decisions;
- faux provider support for deterministic wiring tests.

MissionForge provides the industrial boundary layer:

- frozen task contract authority;
- workspace and permission manifests;
- capability grants and sandbox profiles;
- tool gateway enforcement;
- ref, hash, and evidence records;
- role separation;
- independent judge boundary;
- repair and explicit revision;
- product-neutral SDK primitives;
- context projection policy;
- audit and recovery records.

The intended relationship is:

```text
MissionForge builds the world.
PiWorker acts inside the world.
Pi runs the actor.
```

Pi should remain the default intelligent runtime lane:

```text
PiWorkerCall
  -> PiAgentRuntimeInput
  -> workers/pi-agent-runtime
  -> PiWorkerCallResult
```

MissionForge should not try to replace Pi's agent loop unless there is a
specific boundary or evidence requirement that cannot be achieved by wrapping
Pi's hooks.

## Disk-First Problem Statement

The current implementation uses filesystem refs as both identity and transport.
This has strong audit properties, but it creates several problems:

- High-frequency intermediate data requires synchronous file writes.
- Small structured decisions are treated like heavyweight artifacts.
- Multi-agent collaboration requires filesystem materialization even for
  ephemeral state deltas.
- Context construction becomes file scanning and string assembly instead of
  projection from typed records.
- Prompt cache stability is harder because volatile metadata and generated
  file views can churn.
- Tool observations, raw evidence, semantic summaries, and active model context
  are all too easily conflated as "files".
- Parallel and iterative agent systems need explicit state merge semantics,
  which raw filesystem paths do not provide.

The key design correction:

```text
ref-first != disk-first
```

Refs-first should mean:

- stable ref identity;
- content hash;
- version;
- owner role;
- producing step;
- contract hash;
- permission scope;
- schema/type;
- provenance;
- storage pointer;
- audit record.

It should not require immediate durable body materialization for every
intermediate value.

## Proposed Layer Model

### Authority Plane

The authority plane defines what is allowed and what counts as task truth.

Primitives:

- `TaskContract`
- `TaskContractRevision`
- `WorkerBrief`
- `JudgeRubric`
- `WorkspacePolicy`
- `PermissionManifest`
- `CapabilityGrant`
- `SandboxProfile`

Authority artifacts should remain stable, explicitly versioned, and
prompt-cache friendly. They should not be rewritten as part of context
compaction.

### Data Plane

The data plane manages information identity, versioning, body storage, and
agent-to-agent data transfer.

Primitives:

- `ArtifactStore`
- `ArtifactRecord`
- `ArtifactBody`
- `RefVersion`
- `Channel`
- `Reducer`
- `ReadGate`
- `WriteGate`
- `StorageBackend`
- `MaterializationPolicy`

### Context Plane

The context plane turns authorized data into model input.

Primitives:

- `ContextSegment`
- `ContextView`
- `ContextProjector`
- `ContextBudget`
- `ContextCheckpoint`
- `ContextSummaryArtifact`
- `ToolObservation`

The context plane should be cache-aware, permission-aware, ref-aware, and
compaction-aware.

### Runtime Plane

The runtime plane runs PiWorker calls and tools inside hard boundaries.

Primitives:

- `PiWorkerCall`
- `PiWorkerCallResult`
- `PiWorkerCallAdapter`
- `ToolGateway`
- `SandboxRunner`
- `ExtensionGrant`
- `ExtensionLock`

### Decision Plane

The decision plane records structured routing and semantic acceptance.

Primitives:

- `JudgeReport`
- `DecisionArtifact`
- `DecisionLedger`
- `FinalPackage`
- `RepairRequest`
- `RevisionRequest`
- `RevisionAppliedRecord`

### Audit Plane

The audit plane makes the system replayable and inspectable without embedding
large bodies or secrets by default.

Primitives:

- write-ahead log;
- flow ledger;
- step record;
- permission decision record;
- tool observation record;
- checkpoint;
- async materialization record;
- redaction policy.

## Data Plane Proposal

### ArtifactRecord

An artifact record is the authoritative metadata for one committed ref version.

```python
ArtifactRecord(
    ref="reports/final_report.md",
    version=3,
    content_hash="sha256:...",
    schema_id="markdown.report.v1",
    media_type="text/markdown",
    owner_role="executor_piworker",
    created_by_step="researcher",
    created_by_call="deepresearch-researcher-attempt-001",
    contract_id="contract-001",
    contract_hash="sha256:...",
    permission_manifest_ref="kernel/steps/researcher/permission_manifest.json",
    source_refs=["sources/source_packet.json", "state/research_state.json"],
    source_hashes={"sources/source_packet.json": "sha256:..."},
    storage_class="memory",
    body_pointer="mem://run/artifacts/...",
    materialized_refs=[],
    created_at="2026-06-24T00:00:00Z",
    metadata={},
)
```

The record is durable authority for the artifact version. The body may live in
memory, disk, blob storage, or an external system.

### ArtifactBody

`ArtifactBody` stores the actual bytes or structured value.

Body storage classes:

- `memory`: current process memory, useful for small structured data;
- `disk`: workspace filesystem materialization;
- `blob`: content-addressed object store;
- `external`: durable source outside MissionForge, referenced by signed or
  verified pointer;
- `virtual`: mechanically projected value, recomputable from source refs.

Storage class is an implementation detail. Authorization must be based on
refs, versions, roles, and permission manifests, not on whether a value is
currently on disk.

### RefVersion

Refs should become versioned.

```text
reports/final_report.md@v1
reports/final_report.md@v2
reports/final_report.md@latest
```

Rules:

- A committed version is immutable.
- Updating a ref creates a new version.
- `latest` is a view, not a mutable body.
- Judge inputs should normally bind to explicit versions or to a flow snapshot
  that resolves refs to versions.
- A repair creates new versions under the same contract hash.
- A revision creates new versions under a new contract hash only after an
  explicit revision-applied record.

### WriteGate

`WriteGate` validates writes before commit.

It checks:

- output ref is under `writable_refs`;
- ref is not denied;
- writer role is allowed to produce that artifact role;
- contract hash matches current authority;
- schema/type validation passes when declared;
- runtime-owned refs cannot be written by PiWorker;
- product-owned refs are not overwritten by runtime unless explicitly allowed;
- expected output constraints are satisfied where applicable.

Write flow:

```text
PiWorker output
  -> WriteGate
  -> schema/type check
  -> content hash
  -> ArtifactRecord
  -> WAL append
  -> StateStore update
  -> async materialization
```

### ReadGate

`ReadGate` creates role-specific views.

It checks:

- requested ref is under `readable_refs`;
- ref is not denied;
- requested version belongs to the allowed contract or explicit evidence set;
- raw refs are not exposed unless explicitly granted;
- hidden scratch or private role data does not leak across roles.

Read flow:

```text
Role + PermissionManifest + requested refs
  -> ReadGate
  -> authorized ArtifactRecord set
  -> ContextProjector or tool read operation
```

### Channel

Channels solve typed multi-step and multi-agent state transfer.

```python
Channel(
    name="source_packet",
    schema=SourcePacket,
    reducer="merge_by_source_id",
    owner_policy="researcher",
    visibility_policy=["researcher", "reviewer", "judge"],
)
```

Channel rules:

- Channel writes create immutable versions.
- Reducers run in the trusted MissionForge process.
- Reducers must be deterministic.
- Reducers are structural, not semantic judges.
- Reducer output is a new artifact version with provenance to inputs.
- Agent roles exchange state through channel versions, not shared mutable
  Python dictionaries.

Candidate built-in reducers:

| Reducer | Semantics | Use case |
| --- | --- | --- |
| `last_value` | latest valid version wins | decisions |
| `append_delta` | append ordered deltas | research state |
| `merge_by_id` | merge records by stable id | source packets |
| `set_union` | deterministic set union | discovered refs |
| `list_append` | ordered append | notes or observations |
| `no_merge` | fail on concurrent writes | exclusive outputs |

### Memory-First Store

`ArtifactStore` should use memory as the fast path for small and medium
structured values.

```text
Small structured data:
  decision JSON, reviewer observation, state deltas
  -> memory + WAL + async materialization

Medium artifacts:
  source packets, reports, claim indexes
  -> memory metadata + optional memory body + async disk/blob body

Large artifacts:
  raw tool output, PDFs, crawled documents, full stdout
  -> blob/disk body + memory metadata
```

The synchronous durability boundary is the WAL commit, not full body flush.

### WAL And Async Materialization

The write-ahead log records the minimum recovery authority:

```python
WalEntry(
    entry_id="wal-000001",
    run_id="run-001",
    step_id="researcher",
    ref="reports/final_report.md",
    version=2,
    content_hash="sha256:...",
    schema_id="markdown.report.v1",
    owner_role="executor_piworker",
    contract_hash="sha256:...",
    source_hashes={...},
    body_storage_class="memory",
    body_pointer="mem://...",
    previous_entry_hash="sha256:...",
    entry_hash="sha256:...",
)
```

Crash recovery:

```text
WAL written, async body not materialized:
  recover metadata, mark body dirty if body is unavailable, rerun producing step

WAL not written:
  step is not committed, rerun step

Body materialization interrupted:
  detect hash mismatch, mark materialization incomplete, rerun or rematerialize
```

This preserves the current artifact-boundary resume principle while avoiding
full synchronous filesystem writes for every intermediate output.

### Multi-Agent Collaboration Example

```text
researcher writes source_packet@v1
researcher writes final_report@v1
reviewer reads source_packet@v1 + final_report@v1
reviewer writes reviewer_observation@v1(decision=revise_report)
researcher reads reviewer_observation@v1
researcher writes final_report@v2
judge reads source_packet@v1 + final_report@v2 + reviewer_observation@v1
judge writes judge_report@v1(decision=accepted)
```

No worker mutates another worker's private state. Coordination is explicit,
versioned, permission-gated, and auditable.

## Context Plane Proposal

The most important large-model application problem is context management.
MissionForge should not treat context as "read files and concatenate text".
Context is a role-specific, budgeted, cache-aware projection over authorized
state.

```text
ArtifactStore / ObservationStore
  -> ReadGate
  -> ContextProjector
  -> ContextView
  -> PiWorker runtime
```

### ContextSegment

`ContextSegment` is the unit of model-context assembly.

```python
ContextSegment(
    segment_id="authority.contract",
    role_scope=["executor_piworker", "judge_piworker"],
    contract_hash="sha256:...",
    source_refs=["contract/task_contract.json"],
    source_hashes={"contract/task_contract.json": "sha256:..."},
    content_kind="authority",
    cache_policy="stable",
    inline_policy="inline",
    token_estimate=1200,
    priority=1000,
    created_by="runtime",
    body_pointer="mem://context/authority.contract",
)
```

Content kinds:

- `authority`: contract, role, permissions, rubric;
- `instruction`: product manuals and role briefs;
- `artifact_preview`: report/source/state preview;
- `artifact_ref`: ref and hash only;
- `tool_observation`: tool metadata and preview;
- `runtime_diagnostic`: context pressure and budget diagnostics;
- `semantic_summary`: PiWorker/Judge-authored summary artifact;
- `archive_stub`: pointer to archived message segment.

Cache policies:

- `stable`: should stay byte-stable across turns and attempts;
- `semi_stable`: changes occasionally, for manuals or summaries;
- `volatile`: current turn objective, recent tool results, latest decisions;
- `no_cache`: timestamps, transient diagnostics, progress messages.

Inline policies:

- `inline`: include full body;
- `preview`: include bounded preview plus ref/hash;
- `ref_only`: include metadata only;
- `windowed`: include selected byte/line/token range;
- `omitted`: keep out of model context but available through tools if
  permitted.

### ContextView

`ContextView` is the complete provider-facing input plan for one PiWorker call.

```python
ContextView(
    view_id="ctx-researcher-0001",
    role="executor_piworker",
    contract_hash="sha256:...",
    permission_manifest_ref="kernel/steps/researcher/permission_manifest.json",
    token_budget=96000,
    stable_prefix=[...],
    semi_stable_context=[...],
    volatile_tail=[...],
    omitted_segments=[...],
    context_hash="sha256:...",
    diagnostics_ref="attempts/.../context/projection.json",
)
```

The same `ArtifactStore` should produce different `ContextView` values for
executor, reviewer, judge, repair, and revision roles.

### Prompt Cache Strategy

Prompt cache friendliness requires stable prefix discipline.

Stable prefix should include:

- runtime system rules;
- frozen contract ref/hash and concise contract projection;
- role name and role boundary;
- permission summary;
- role brief;
- output schema and expected refs;
- judge rubric for judge role.

Stable prefix should avoid:

- timestamps;
- nondeterministic ordering;
- raw tool output;
- changing progress text;
- generated file listings with unstable metadata;
- context diagnostics;
- retry counters unless required;
- large volatile observations.

Rules:

- Sort refs deterministically.
- Use stable JSON serialization.
- Keep dynamic data in the volatile tail.
- Do not rewrite authority segments during compaction.
- Add summaries as separate segments instead of editing stable authority text.
- Record cache-read and cache-write token metrics as diagnostics only.

### ToolObservation

Tool output should not automatically become full model context.

```python
ToolObservation(
    observation_id="tool-observation-000001",
    call_id="researcher-001",
    turn_index=4,
    tool_call_id="call_x",
    tool_name="bash",
    status="ok",
    content_hash="sha256:...",
    content_bytes=148000,
    content_lines=2400,
    inline_policy="demote_after_turn",
    raw_ref="attempts/.../context/raw/000001-bash-output.log",
    source_ref=None,
    source_range=None,
)
```

Model-facing projection:

```text
[MissionForge tool observation]
observation_id: tool-observation-000001
tool_name: bash
status: ok
content_hash: sha256:...
content_bytes: 148000
raw_ref: attempts/.../context/raw/000001-bash-output.log
note: full body omitted; reread permitted ranges through tools if authorized
```

Tool output policy:

- Small output can stay inline for the current turn.
- Large output should be captured as raw ref and demoted after the immediate
  follow-up turn.
- File reads should prefer `source_ref`, range, hash, and optional preview.
- Raw refs are audit evidence by default, not automatically readable by later
  roles.
- If judge needs raw evidence, the product contract or permission manifest must
  explicitly grant it.

### Compaction

Compaction must split deterministic projection from semantic summarization.

| Type | Produced by | Semantic authority |
| --- | --- | --- |
| Deterministic projection | runtime | no |
| Semantic summary | PiWorker or Judge | yes, if explicit artifact |

Runtime may do:

- archive old messages as metadata envelopes;
- replace large tool results with ref/hash stubs;
- record pressure diagnostics;
- write context checkpoint refs;
- stop at a completed-turn safe point when pressure is too high.

Runtime must not do:

- decide which sources are important;
- summarize domain meaning as hidden memory;
- rewrite contract, rubric, or role authority;
- expose hidden raw bodies to roles without permission.

Semantic summaries should be explicit artifacts:

```python
ContextSummaryArtifact(
    summary_ref="state/context_summary_round_02.md",
    source_refs=["sources/source_packet.json", "reports/final_report.md"],
    source_hashes={...},
    producing_role="executor_piworker",
    contract_hash="sha256:...",
    confidence="medium",
    supersedes=["state/context_summary_round_01.md"],
    conflicts_with=[],
)
```

### Context Pressure Boundary

Context pressure should be treated as runtime pressure, not semantic route.

Policy:

- At soft threshold, write refs-only checkpoint diagnostics.
- At hard threshold, stop at the next completed-turn boundary before another
  provider request.
- Resume should use checkpoint refs and optional explicit semantic summaries.
- Context pressure metrics should never accept, reject, or route semantic work
  by themselves.

## Runtime And Tool Boundary

The PiWorker call remains an unreliable intelligent RPC inside deterministic
constraints.

`PiWorkerCall` declares:

- role;
- contract id/hash/ref;
- visible refs;
- writable refs;
- expected outputs;
- permission manifest ref;
- evidence refs;
- runtime budget;
- output schema or validation policy refs.

`PiWorkerCallResult` records:

- boundary status;
- output refs;
- runtime refs;
- evidence refs;
- metric refs;
- validation report ref;
- error ref.

It does not grant semantic acceptance.

### ToolGateway

All tool access should pass through `ToolGateway`.

ToolGateway should:

- authorize reads, writes, commands, cwd, environment, and network;
- use effective sandbox profile as the execution view;
- record permission decisions as refs-first evidence;
- deny unsupported hard policies;
- avoid embedding raw command bodies, stdout/stderr bodies, environment values,
  provider payloads, or secrets into operator-facing state.

### Sandbox

Each agent role should be able to receive a distinct sandbox view:

```text
outer run
  -> researcher sandbox
  -> reviewer sandbox
  -> judge sandbox
  -> repair sandbox
```

Rules:

- no shared mutable process memory as the coordination mechanism;
- no live privilege escalation;
- new permissions require a new grant and usually a new sandbox;
- cross-agent transfer happens through committed refs, channel versions, or
  promoted artifacts.

## LangGraph Lessons

MissionForge should borrow engineering ideas from LangGraph, but not its
authority model.

Borrow:

- channel/reducer-style typed state declarations;
- superstep/barrier parallelism;
- checkpoint and replay discipline;
- explicit interrupt/safe-point concepts;
- streaming progress concepts.

Do not borrow:

- shared mutable state as the security boundary;
- arbitrary Python route functions as semantic authority;
- single-process node execution as the default trust model;
- hidden memory that rewrites task truth;
- acceptance without an independent judge role.

MissionForge should implement a stricter variant:

```text
LangGraph-style convenience
  + MissionForge immutable channels
  + role-specific ReadGate
  + PermissionManifest
  + PiWorkerCall boundary
  + independent Judge acceptance
```

## Proposed Programmer API Shape

This is illustrative, not a final API commitment.

```python
from missionforge import (
    ArtifactStore,
    Channel,
    ContextProjector,
    PermissionManifest,
    PiWorkerCall,
    PiWorkerCallRole,
    TaskContract,
    run_piworker_call,
)

store = ArtifactStore.memory_first(workspace="./runs/research-001")

contract = TaskContract(
    contract_id="research-001",
    product_id="deepresearch",
    objective="Produce a sourced research report.",
    required_outputs=[...],
    semantic_acceptance=[...],
)

source_packet = Channel(
    name="source_packet",
    schema="missionforge_deepresearch.source_packet.v1",
    reducer="merge_by_source_id",
)

with store.run(contract=contract) as run:
    researcher_view = ContextProjector().project(
        role="executor_piworker",
        refs=[
            "contract/task_contract.json",
            "manuals/researcher.md",
            "sources/initial_source_packet.json",
        ],
        token_budget=96000,
        cache_policy="stable_prefix",
    )

    researcher_call = PiWorkerCall(
        call_id="researcher-001",
        role=PiWorkerCallRole.EXECUTOR,
        contract_id=contract.contract_id,
        contract_hash=contract.contract_hash,
        contract_ref="contract/task_contract.json",
        objective="Gather evidence and write the report package.",
        visible_refs=researcher_view.visible_refs,
        writable_refs=["sources", "reports", "state"],
        expected_output_refs=[
            "sources/source_packet.json",
            "reports/final_report.md",
            "state/researcher_control.json",
        ],
        permission_manifest_ref="policy/researcher_permissions.json",
    )

    researcher_result = run_piworker_call(researcher_call, workspace=run.workspace)
    run.commit_result(researcher_result)

    decision = run.read_decision("state/researcher_control.json")
    if decision["decision"] == "ready_for_review":
        # Ordinary Python owns orchestration. MissionForge owns boundaries.
        pass
```

Lower-level primitives should stay usable without `Flow`. Higher-level
`Flow` can be a convenience layer over the same primitives.

## Implementation Roadmap

### Phase 0: Architecture Freeze

Deliverables:

- Approve or reject this proposal.
- Decide naming: `ArtifactStore`, `StateStore`, `ContextView`,
  `ContextSegment`, `Channel`.
- Decide whether these primitives live under `missionforge.kernel` first or
  under a new internal package such as `missionforge.data`.

Exit criteria:

- No code changes except docs and tests for current invariants.

### Phase 1: ArtifactRecord And Store Interface

Deliverables:

- Add `ArtifactRecord`.
- Add `ArtifactStore` protocol.
- Add memory-backed implementation for tests.
- Add filesystem-backed compatibility implementation.
- Keep existing file refs working.

Exit criteria:

- Existing tests pass.
- New tests prove ref identity is independent from storage backend.
- No product semantics enter core.

### Phase 2: ReadGate And WriteGate

Deliverables:

- Add `ReadGate` over `PermissionManifest`.
- Add `WriteGate` over `PermissionManifest`.
- Validate role, contract hash, readable/writable roots, denied refs, and
  runtime-owned refs.
- Route Kernel `run_step` through gates in compatibility mode.

Exit criteria:

- Permission rejection tests cover memory and filesystem backends.
- Judge cannot read executor-only hidden refs.
- Worker cannot write contract or runtime-owned records.

### Phase 3: WAL And Async Materialization

Deliverables:

- Add minimal WAL record.
- Add chain hash.
- Add async materialization queue.
- Add recovery scan from WAL.
- Keep synchronous filesystem compatibility path behind a feature flag.

Exit criteria:

- Crash simulation tests cover WAL written/not written/materialization partial.
- Step resume remains artifact-boundary safe.
- Disk materialization can lag without changing semantic authority.

### Phase 4: ContextSegment And ContextView

Deliverables:

- Add `ContextSegment`.
- Add `ContextView`.
- Split stable prefix, semi-stable context, and volatile tail.
- Make current Pi runtime context projection produce a `ContextView`
  diagnostic.
- Keep existing `transformContext` implementation as runtime backend.

Exit criteria:

- Prompt-cache-stable prefix tests prove deterministic order and content.
- Tool output demotion still works.
- Runtime diagnostics remain refs-only.
- Authority segments are never rewritten by compaction.

### Phase 5: ToolObservation Store

Deliverables:

- Move current TS `ToolObservation` concept into a cross-runtime schema.
- Store observations in `ArtifactStore` metadata and audit records.
- Preserve raw refs and source refs.
- Add reread capability metadata gated by permission.

Exit criteria:

- Large tool output stays out of durable operator-facing state.
- Context projection emits stubs.
- Context snapshot exposes only permitted reread args.

### Phase 6: Channel And Reducer

Deliverables:

- Add `Channel`.
- Add deterministic built-in reducers.
- Add immutable channel versioning.
- Add provenance records for reduced output.
- Add product-provided reducer registration only through explicit safe hooks.

Exit criteria:

- Parallel writers can merge through declared reducer.
- Reducer cannot inspect hidden unauthorized refs.
- Reducer output is deterministic and hashable.

### Phase 7: Superstep And Barrier

Deliverables:

- Add optional parallel step grouping.
- Run each step with separate permission view and sandbox.
- Merge outputs through channels after barrier.

Exit criteria:

- No shared mutable agent state.
- Barrier does not accept semantic output.
- Judge acceptance still only comes from judge role.

### Phase 8: SDK Surface Review

Deliverables:

- Promote stable primitives to package root only after DeepResearch and one
  smaller example integration prove the surface.
- Update `docs/API_BOUNDARY.md`, `docs/PRIMITIVE_REFERENCE.md`, and
  `docs/COOKBOOK.md`.

Exit criteria:

- A programmer can build a standalone product integration without copying
  DeepResearch internals.

## Test Plan

Contract and authority:

- `TaskContract` hash is stable and bound to all artifact records.
- Contract writes are rejected unless explicit revision path is used.
- Repair output stays under same contract hash.
- Revision output changes contract hash only through revision-applied record.

Permission:

- ReadGate rejects refs outside readable roots.
- WriteGate rejects refs outside writable roots.
- Denied refs override readable/writable roots.
- Runtime-owned records cannot be written by PiWorker.
- Raw tool refs are not visible to judge unless explicitly granted.

Role separation:

- Executor cannot route to accepted.
- Judge accepted route requires prior non-judge output visible to judge.
- Reviewer and judge receive different `ContextView` values.

Data plane:

- In-memory and filesystem backends produce identical hashes.
- Versioned ref updates preserve old versions.
- Reducers are deterministic.
- WAL recovery reconstructs committed records.
- Async materialization hash mismatch is detected.

Context:

- Stable prefix is deterministic across turns.
- Volatile tail changes do not rewrite authority prefix.
- Large tool output demotes to ref/hash stub.
- Context pressure writes refs-only checkpoint.
- Semantic summary artifact requires source refs and hashes.

Audit:

- Ledgers cite refs and hashes.
- Durable records do not embed raw prompts, transcripts, provider payloads,
  stdout/stderr bodies, artifact bodies, or secrets by default.
- Redaction covers environment-provided secrets.

Pi runtime:

- Provider faux mode still validates wiring without live model.
- Live smoke tests remain opt-in.
- ToolGateway decisions are recorded.
- Bubblewrap command allowlist is enforced.

## Open Questions

1. Should `ArtifactStore` be a public root primitive immediately, or incubate
   under `missionforge.kernel`?
2. What is the minimum body-size threshold for memory vs disk/blob storage?
3. Should WAL be required for all stores, including purely in-memory test
   stores?
4. How should product integrations declare schemas for structured artifacts?
5. Should reducers be limited to built-ins initially?
6. How should context token estimation become provider-specific without
   coupling core to provider internals?
7. How much of context segment materialization should be shared between Python
   and the TypeScript Pi sidecar?
8. Should `ContextView` be passed to Pi runtime as a first-class envelope, or
   compiled into existing runtime input fields for compatibility?
9. What is the exact policy for judge access to raw tool observations?
10. How should external object stores be authorized and hashed?
11. How should per-agent sandbox lifecycle interact with memory-first data
   transfer and IPC?
12. What is the minimum stable API that lets product authors build with normal
   Python without copying Kernel internals?

## Architecture Review Checklist

- Does the proposal preserve frozen contract authority?
- Does it keep product semantics out of `src/missionforge`?
- Does it preserve executor/judge role separation?
- Does it prevent runtime compaction from becoming hidden semantic memory?
- Does it make refs independent from disk paths without weakening audit?
- Does it improve prompt cache stability?
- Does it improve tool-call ergonomics without leaking raw output?
- Does it allow ordinary Python orchestration without making MissionForge a
  product workflow engine?
- Does it keep Pi as the agent loop substrate rather than replacing it
  prematurely?
- Does it define enough tests to prevent boundary regressions?

## Bottom Line

MissionForge should not choose between strictness and efficiency. The strict
part is not the filesystem. The strict part is the combination of frozen
contracts, permission manifests, role-specific views, content hashes,
immutable versions, refs-first evidence, and independent judgment.

The proposed direction keeps those strict boundaries while making the system
lighter:

```text
from disk-first refs
to ref-addressed data plane

from file concatenation
to cache-aware ContextView projection

from framework-controlled flow
to Python-composable SDK primitives

from Pi as architecture
to Pi as runtime substrate under MissionForge boundaries
```

This is the path toward a white-box, controllable, efficient, complex, stable
industrial agent system toolkit.
