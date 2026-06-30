# MissionForge ContextEngine Architecture

Status: package-managed architecture with Phase 7-9 runtime slice implemented

Last updated: 2026-06-27

## Implementation Status

The package-managed ContextEngine baseline is now partially implemented in
core:

- Kernel compiles `ContextCompileRequest` automatically before provider turns.
- Kernel writes refs-only checkpoint, source snapshot, epoch, pressure, cache
  layout, turn boundary, and compile-result records.
- Hard context pressure invokes a MissionForge-managed
  `context_reducer_piworker` without host code.
- Runtime repeated-read diagnostics from Pi agent tool observations are carried
  into the next Kernel safe point and can invoke the same managed reducer path
  by policy.
- Valid reducer output is boundary-validated, recorded as a state transition and
  compaction record, and followed by a fresh recompile before the executor
  PiWorker is called.
- Invalid or failed reducer output blocks safely with refs-only diagnostics and
  leaves the previous context view/epoch active.
- `ContextManagementPolicy` controls the default mechanical thresholds and
  reducer enablement.

Still intentionally incomplete:

- no product-specific reducer prompts or semantics live in core;
- broader observation coverage and long-running soak/restart validation remain
  to be hardened;
- richer working-set state semantics remain product/integration responsibility.

## Purpose

MissionForge needs a real context engine, not a larger prompt builder.

The current refs-first architecture gives MissionForge strong authority,
permission, evidence, and audit boundaries. The problem is that refs-first can
easily degenerate into disk-first context transport: every piece of information
is written to files, every agent turn must rediscover or reread too much state,
and long-running products such as DeepResearch become slow and context-heavy.

This document defines a small product-neutral `ContextEngine` that keeps
MissionForge's existing philosophy while borrowing the strongest ideas observed
in opencode's session runtime:

- stable context sources;
- immutable cache-friendly context epochs;
- safe provider-turn boundaries;
- bounded tool-output projection;
- durable compaction/checkpoint events;
- provider-aware cache diagnostics.

The goal is not to copy opencode. opencode is a coding-agent session runtime.
MissionForge is a bounded PiWorker toolkit with frozen contracts, refs,
permission manifests, sandbox profiles, role separation, and independent judge
boundaries. The correct design is to extract the general mechanism and adapt it
to MissionForge's authority model.

MissionForge is also intended to be used as a Python package and embedded
toolkit. Context management pressure must not be pushed to ordinary package
users. A host should be able to define contracts, steps, permissions, and
artifacts, then rely on MissionForge to manage context compilation, projection,
checkpointing, compaction lifecycle, and recovery by default. Product
integrations may improve semantic reduction, but they must not be required for
baseline ContextEngine safety and usability.

## Non-Goals

The first ContextEngine design must not become:

- a graph framework;
- a LangGraph replacement;
- a memory database;
- a vector retrieval product;
- a product-semantic reducer;
- a hidden prompt mutation system;
- an in-memory dataflow runtime that bypasses refs and permissions;
- a requirement that package users hand-maintain checkpoints, working sets, or
  compaction records.

MissionForge core should compile, validate, filter, project, checkpoint, and
observe context. It must not decide what a research paper means, which evidence
is important, whether a product report is insightful, or whether a user need is
satisfied.

## Design Principles

### 1. Context Is Compiled, Not Concatenated

An LLM request should be treated as a compiled artifact:

```text
authority refs
  + role/task projections
  + permitted context sources
  + recent user/tool events
  + explicit summaries/checkpoints
  -> durable ContextView / cache layout
  -> ephemeral provider request rendering
```

The compiler owns ordering, cache strata, token budget, demotion, omission, and
diagnostics. Product integrations own the semantic meaning of the facts being
compiled.

`ContextView` is durable refs-only layout and diagnostics. It does not store raw
prompt text, provider messages, tool bodies, or artifact bodies. The actual
provider prompt is an ephemeral rendering produced immediately before the
provider turn, after permission filtering and bounded projection. That rendering
may include excerpts or summaries needed for working context, but it is not the
durable task authority and must not be written into runtime state by default.

### 2. Refs-First Does Not Mean Disk-Only

Refs are identity and authority handles. They do not require every intermediate
context decision to be stored as a large file body.

The durable truth remains refs, hashes, versions, permission manifests, ledgers,
and artifacts. Runtime context assembly can use typed records, snapshots, and
small in-memory views as long as final authority and replay points are
recoverable from explicit refs.

### 3. Permission Filtering Happens Before Context Selection

No retrieval, projection, summarization, or replay step may expose a ref that the
current role cannot read.

The ContextEngine must call through `ReadGate`-compatible checks before a source
is selected for a role. Denied refs remain visible only as denial metadata when
needed for diagnostics, never as content or previews.

### 4. Stable Prefix Is an Economic Primitive

Prompt cache hit rate is part of architecture, not billing afterthought.

MissionForge should keep stable authority context byte-identical across repeated
turns where possible:

- frozen `TaskContract`;
- `WorkerBrief` or `JudgeRubric`;
- `PermissionManifest`;
- sandbox/tool policy;
- stable manuals or role instructions;
- stable tool definitions.

Dynamic information belongs after the stable prefix. Context changes should be
admitted at safe provider-turn boundaries rather than rewriting the stable
prefix every turn.

### 5. Tool Output Is Not Context

A tool result has at least three representations:

```text
raw output / full artifact body
  -> durable ref + hash + size

structured observation
  -> machine-readable facts for runtime/product reducers

model projection
  -> bounded text or ref stub included in the LLM context
```

The model projection must be bounded. Large raw output should be available
through explicit refs and permissions, not replayed endlessly in every turn.

### 6. Compaction Is a Boundary Event

Context compaction must not silently rewrite task truth.

A compaction/checkpoint should be a durable boundary event with:

- reason;
- input context refs and hashes;
- output summary/checkpoint refs;
- context hash before/after;
- producing role;
- permission manifest ref;
- failure behavior.

If compaction fails, the previous active context remains valid. The runtime must
not publish half-compacted state.

### 7. Refs Are Evidence Handles, Not Model Memory

Refs are necessary for permission, audit, recovery, citation, and replay. They
are not sufficient as model-visible working memory.

An LLM call is stateless. If a previous turn read artifact A, but the current
turn only sees `A_ref` and no extracted fact, excerpt, summary, or reason why A
matters, then the model does not actually know A. This creates ref thrashing:

```text
read A -> read B based on A -> read C based on B
  -> A/B facts leave the active context
  -> model cannot reason over A+B+C
  -> model rereads A or B
```

MissionForge must therefore distinguish:

```text
durable evidence plane
  refs, hashes, versions, permissions

compiled working context
  bounded facts, excerpts, summaries, active hypotheses, why-it-matters notes

product semantic state
  research_state, claim_index, evidence_map, todo/progress, reviewer notes
```

The ContextEngine succeeds only if it preserves enough compiled working context
for the model to continue reasoning without repeatedly rediscovering the same
evidence.

### 8. Context Management Is MissionForge-Owned

MissionForge should provide ContextEngine as managed package infrastructure, not
as a burden transferred to host applications.

The default path should be:

```text
host defines contract / step / permissions
  -> Kernel prepares context automatically
  -> ContextEngine compiles and checks pressure
  -> Kernel checkpoints or invokes managed reduction when needed
  -> PiWorker receives bounded context
```

Users may configure policy thresholds or replace reducer prompts, but they
should not need to understand prompt-cache strata, repeated-read diagnostics,
checkpoint records, or working-set maintenance for ordinary use.

This does not mean deterministic Python core should become a semantic expert.
MissionForge owns the lifecycle and hard boundaries. Semantic compression, when
needed, is produced by an internal MissionForge-managed PiWorker reducer or by
an optional product integration. Core validates refs, permissions, hashes,
schemas, roles, and lifecycle transitions.

## Lessons Extracted From opencode

The opencode source audit produced six reusable ideas.

### Context Source

opencode models each context contribution as a stable-keyed source with:

- key;
- codec;
- loader;
- baseline renderer;
- update renderer;
- optional removal renderer;
- snapshot comparison.

MissionForge should keep the same conceptual shape, but the loader must be
permission-aware and ref-aware.

MissionForge adaptation:

```text
ContextSource
  key
  source_refs
  load_metadata()
  load_projection(read_gate, role)
  baseline()
  update(previous, current)
  removed(previous)
  cache_policy
  permission_scope
```

The source value should be small structured metadata or a bounded projection.
Raw artifact bodies remain behind refs.

### Context Epoch

opencode preserves an immutable baseline system context inside a context epoch.
That is the core mechanism behind cache-friendly provider requests.

MissionForge adaptation:

```text
ContextEpoch
  epoch_id
  role
  contract_hash
  baseline_ref
  baseline_hash
  source_snapshot_ref
  baseline_seq
  permission_manifest_ref
  provider_cache_profile
```

An epoch is replaced only when:

- the contract is revised;
- the role or permission manifest changes incompatibly;
- a completed compaction starts a new epoch;
- the host explicitly resets the run/session.

Ordinary dynamic changes should produce mid-turn/update segments after the
baseline, not mutate the baseline.

### Safe Provider-Turn Boundary

opencode admits context changes immediately before a provider call, after
pending inputs and tool settlements are durable.

MissionForge should make this an explicit runtime safe point:

```text
settle user intervention
settle tool observations
record artifacts
refresh permitted context sources
compile ContextView
estimate pressure
maybe checkpoint / invoke managed reducer / compact
emit RunEvent.CONTEXT_PROJECTED
invoke PiWorker/provider
```

This is where MissionForge can support pause, cancel, inject-message, request
revision, force checkpoint, and debug stepping without corrupting a provider
turn.

Bounded retries may reuse a compiled provider-turn boundary only when the retry
attempt records that it is using the same preflight boundary and cites the
parent call, compile result, turn boundary, and epoch refs. A retry that needs
different authority, permissions, or context must return to the safe point and
compile a new boundary instead of silently inheriting stale context metadata.

### Bounded Tool Output

opencode stores full oversized tool output separately and replays only a
bounded projection with a pointer to the complete output.

MissionForge should formalize this as:

```text
ToolOutputRecord
  tool_call_id
  tool_name
  status
  raw_ref
  structured_ref or structured_metadata
  projection_ref
  content_hash
  content_bytes
  content_lines
  permission_manifest_ref
  projection_policy
```

Current `ToolObservation` is already close to this. The missing part is a
first-class bounded projection record and a consistent lifecycle across all
tools.

### Durable Compaction

opencode compacts before a provider turn when the projected request exceeds
budget. It emits durable started/ended events and keeps the previous context if
compaction fails.

MissionForge should split compaction into three layers:

1. Product-neutral lifecycle boundary owned by core:
   - checkpoint and compaction attempt records;
   - input/output context refs and hashes;
   - source snapshot refs;
   - permission manifest refs;
   - started/ended/failed status;
   - failure behavior;
   - epoch replacement only after successful completion.

2. MissionForge-managed generic reduction:
   - frozen contract and role projection refs;
   - current working-set refs;
   - recent bounded projections;
   - repeated-read diagnostics;
   - tool observation refs;
   - generic progress/blocker/decision/next-step summaries produced by an
     internal reducer PiWorker.

3. Optional product-specific semantic reduction:
   - DeepResearch `research_state`;
   - source packet;
   - claim index;
   - evidence gap map;
   - reviewer/judge observations.

Core owns lifecycle schemas, boundary events, permission checks, and state
replacement rules. It does not infer goal, progress, blockers, decisions, or
relevance from raw chat or transcripts with Python branching logic. Those fields
must be populated from frozen contract refs, explicit user event refs, a
MissionForge-managed reducer PiWorker, or product-authored summary artifacts.

Product integrations own only product-specialized reduction. They are not a
prerequisite for baseline compaction and checkpoint safety.

### Working Set And Anti-Thrashing

opencode avoids code-reading thrash through a practical stack:

- locator tools such as glob/grep return file paths, line numbers, and short
  previews instead of full files;
- read is paged and bounded;
- recent tool results remain model-visible as current working context;
- oversized outputs become bounded previews plus managed output refs;
- compaction keeps goal, constraints, progress, key decisions, critical
  context, next steps, and relevant files;
- a todo tool persists task-level working memory.

MissionForge should adapt the pattern, not the exact coding-agent product.

For any long task, the model needs a bounded active working set:

```text
what was read
why it matters
which current claim/hypothesis it supports or refutes
what remains unresolved
which refs can recover the full evidence
```

The generic core should provide the working-set container, policy hooks,
diagnostics, and state replacement rules. MissionForge's managed reducer should
be able to populate a generic working set from admitted projections and explicit
refs. Product integrations may populate richer product-specific facts and
interpretations, but ordinary package users should not need to do so.

## Target Architecture

```text
Host Python
  -> Kernel Step / Flow / TaskContract / PermissionManifest
  -> Kernel safe provider-turn boundary
      -> ContextEngine.compile(...)
          -> permission-filtered source snapshots
          -> ContextEpoch baseline/reconcile
          -> ToolOutput projection/demotion
          -> ContextView
          -> ContextPressureDiagnostics
          -> ContextCheckpoint when needed
      -> if pressure/thrash requires reduction:
          -> MissionForge-managed ContextReducer PiWorker
          -> ContextReductionResult
          -> ContextCompactionRecord
          -> new ContextWorkingSet / summary refs
          -> recompile before provider call
      -> PiWorkerCall
  -> ToolGateway settlements
  -> RunEvent / RunSnapshot / DecisionLedger
  -> independent Judge PiWorker boundary when acceptance is required
```

The ContextEngine is not a workflow framework. Kernel owns when to call it at
safe boundaries. ContextEngine returns records and decisions that Kernel can
apply mechanically. MissionForge may invoke its own internal reducer PiWorker
for managed context maintenance, but that reducer is infrastructure, not product
acceptance authority and not a requirement pushed to host applications.

## Core Primitives

MissionForge already has useful first slices:

- `ContextSegment`
- `ContextView`
- `ContextPressureDiagnostics`
- `ContextReplayPlan`
- `ToolObservation`
- `ContextSummaryArtifact`
- `ArtifactRecord`
- `ArtifactStore`
- `ReadGate`
- `WriteGate`
- `RunEvent`
- `RunSnapshot`
- `ControlPort`

The next architecture should add only the following small primitives.

### ContextSource

Product-neutral typed source descriptor.

Responsibilities:

- declare stable source identity;
- declare source refs;
- expose metadata/projection through a loader;
- render baseline/update/removal text or refs;
- declare cache and inline policy;
- carry required permission scope.

It must not:

- perform product ranking;
- summarize domain content by itself;
- bypass `ReadGate`;
- embed raw prompt or tool bodies in durable records.

### ContextSourceSnapshot

Durable refs-only comparison state for one admitted source.

Fields:

- source key;
- source refs;
- source hashes;
- projection hash;
- token estimate;
- removal text ref if needed;
- version or sequence;
- metadata.

### ContextEpoch

Cache-friendly baseline generation for one role under one contract/permission
boundary.

Fields:

- epoch id;
- run id / call id;
- role;
- contract hash;
- permission manifest ref;
- baseline ref;
- baseline hash;
- snapshot ref;
- baseline event sequence;
- provider cache profile.

The baseline may be inline provider text at request time, but durable runtime
records should store it through refs and hashes.

### ContextCompileRequest

Host-to-engine request:

- role;
- contract ref/hash;
- permission manifest;
- sandbox/tool policy refs;
- visible refs;
- recent user event refs;
- tool observation refs;
- summary/checkpoint refs;
- token budget;
- provider cache profile.

### ContextCompileResult

Engine output:

- `ContextView`;
- optional `ContextEpoch`;
- `ContextPressureDiagnostics`;
- admitted update refs;
- omitted/demoted refs;
- cache layout diagnostics;
- required action:
  - continue;
  - prepare checkpoint;
  - checkpoint before next turn;
  - blocked by unavailable authority context;
  - blocked by denied required source.

This result is diagnostic/control information. It is not a semantic route.

### ContextWorkingSet

Bounded, model-visible work memory for the current phase.

Fields:

- working set id;
- role;
- phase label;
- entries;
- token estimate;
- token cap;
- entry ordering policy;
- omitted entry ids;
- permission manifest ref.

### ContextWorkingSetEntry

One bounded piece of active work memory.

Fields:

- entry id;
- source ref;
- source range or locator metadata;
- source hash/version;
- projection ref;
- projection hash;
- why ref or product-authored note ref;
- phase label;
- claim/hypothesis link refs;
- producing observation ids;
- token estimate;
- token cap;
- pin policy:
  - pinned_until_phase_end;
  - pinned_until_checkpoint;
  - evictable;
- freshness:
  - current_turn;
  - active_phase;
  - checkpointed;
  - stale;
- eviction reason when omitted;
- permission manifest ref.

The working set may cite product-semantic artifacts, but it must not invent their
meaning in core. For example, DeepResearch may populate the working set with
claim/evidence summaries. Core only validates refs, hashes, roles, and
permission boundaries.

The working set exists to prevent pure-ref context from becoming unusable. It is
not a memory database.

An entry is model-visible only through its bounded projection. The full source
body remains behind the cited ref and must pass `ReadGate` again before being
read or rendered.

### ContextTurnBoundary

One safe provider-turn boundary record.

Fields:

- boundary id;
- run id / call id / turn id;
- role;
- safe-point ref;
- pre-view ref;
- post-view ref;
- admitted user event refs;
- settled tool observation refs;
- context epoch ref;
- checkpoint ref if created;
- status:
  - ready;
  - blocked;
  - checkpoint_required;
  - cancelled;
  - revision_requested.

This record is the bridge between `ControlPort`, tool settlement, context
projection, and PiWorker invocation. It must not contain provider messages,
prompt bodies, raw tool output, or product-semantic conclusions.

### ToolOutputProjection

Bounded model-visible projection of a tool result.

Fields:

- projection id;
- tool observation id;
- raw ref;
- structured ref or metadata;
- projection ref;
- content hash;
- original size;
- projection size;
- policy:
  - keep;
  - bounded_preview;
  - ref_stub;
  - omitted;
- permission manifest ref.

### ContextCheckpoint

Durable safe-point recovery record.

Fields:

- checkpoint id;
- reason;
- role;
- run id/call id;
- source snapshot ref;
- context view ref;
- context hash;
- summary refs;
- recent refs;
- tool observation refs;
- permission manifest ref;
- created by runtime or PiWorker role.

Checkpoint records may cite semantic summaries, but the core checkpoint itself
must stay refs-first.

### ContextReductionRequest

MissionForge-managed request for an internal reducer PiWorker.

Fields:

- reduction id;
- reason:
  - pressure_soft;
  - pressure_hard;
  - repeated_read_thrashing;
  - operator_checkpoint;
  - before_resume;
- role being maintained;
- contract ref/hash;
- worker brief or judge rubric ref when applicable;
- permission manifest ref;
- current context view ref/hash;
- source snapshot ref;
- pressure diagnostics ref;
- thrash diagnostics refs;
- current working-set ref;
- recent bounded projection refs;
- tool observation refs;
- checkpoint refs;
- expected output refs for reducer artifacts.

This request is generated by MissionForge infrastructure. Host applications may
configure policy, but they should not need to author this request directly.

### ContextReductionResult

Refs-only result from a MissionForge-managed reducer PiWorker.

Fields:

- reduction id;
- status:
  - completed;
  - failed;
  - invalid_output;
  - skipped;
- input request ref;
- checkpoint ref;
- working-set ref when updated;
- summary artifact refs;
- pinned refs;
- evicted refs;
- omitted refs;
- source refs;
- denied source refs;
- compaction record ref;
- validation report ref;
- permission manifest ref;

Core must validate that all cited refs are readable or writable according to the
reducer's permission manifest and that bounded projections remain within policy.
Core must not judge whether the reducer's semantic summary is insightful.

### ContextCompactionRecord

Durable lifecycle record for a compaction attempt.

Fields:

- record id;
- status:
  - started;
  - ended;
  - failed;
- reason;
- input epoch ref;
- output epoch ref when completed;
- input context view ref;
- output context view ref when completed;
- checkpoint ref;
- summary artifact refs;
- source refs;
- denied source refs;
- producing role;
- permission manifest ref.

The record captures the boundary event, not the semantic summary body. Summary
content belongs in explicit `ContextSummaryArtifact` or product-specific
artifacts produced by a PiWorker/Judge role.

## Provider Cache Layout

ContextEngine should compile a provider-neutral cache layout first:

```text
stable_prefix
  contract authority
  role brief / rubric
  stable manuals
  stable tool definitions
  permission and sandbox summaries

semi_stable_context
  active working set
  active product-state refs
  accepted summaries
  source maps
  recent checkpoints

volatile_tail
  latest user message
  latest tool calls/results
  current-turn observations
  runtime control injection

omitted_segments
  demoted raw outputs
  denied refs
  superseded checkpoints
  archive stubs
```

Volatile user events and runtime control injections are context evidence only.
They do not change operational task truth. If a user event changes task goals,
constraints, deliverables, permissions, or acceptance criteria, the product
integration must create an explicit `TaskContractRevision` flow before that
change becomes authority for the next PiWorker call.

Each cache bucket must have deterministic implementation rules:

- stable ordering by bucket, priority, segment id, then source ref;
- canonical JSON serialization for durable layout hashes;
- separate strata hash for each bucket;
- rendered-prefix hash for the ephemeral provider prefix;
- token estimate per segment and per bucket;
- explicit epoch invalidation when contract hash, role, permission manifest,
  sandbox/tool policy, or stable source hash changes;
- provider lowering must never render `omitted_segments`, denied refs, raw
  prompt bodies, raw tool output, provider payloads, or artifact bodies.

Provider adapters then lower this layout:

- Anthropic-style providers may receive explicit cache breakpoints subject to
  provider limits.
- OpenAI-style providers should preserve byte-identical prefixes and record
  `cached_tokens` from usage.
- Providers with no cache support still benefit from bounded context.

The cache policy is therefore not hardcoded to one vendor. It is a provider
capability profile.

## Tool Result Lifecycle

All tool results should follow one lifecycle:

```text
tool call requested
  -> ToolGateway permission check
  -> sandbox/tool execution
  -> raw output capture
  -> structured observation extraction
  -> bounded model projection
  -> ToolObservation / ToolOutputProjection records
  -> ContextEngine demotion after safe boundary
```

Rules:

- The full raw output is never repeatedly appended to model history.
- The first immediate turn may keep a bounded result inline if useful.
- Older large outputs are demoted to refs.
- Materialized bounded projection records may feed the next provider-turn
  compile request, but the next role's permission manifest still controls
  whether projection records and projection text refs are admitted.
- Product integrations may request semantic summaries, but those summaries must
  cite raw/source refs and permission manifests.
- Judge roles do not automatically inherit executor raw refs.

## Anti-Ref-Thrashing Strategy

ContextEngine must make repeated rereads observable and correctable.

### Locator Before Body

Tools should prefer low-cost locators before large bodies:

- search result ids before full page bodies;
- grep/path/line hits before whole files;
- repository file maps before code bodies;
- paper metadata before full paper text.

The ContextEngine does not perform the search. It standardizes how locator
results enter context as bounded projections with recoverable refs.

### Pin Active Evidence

Evidence that the current phase depends on should stay in the working set as
bounded content, not only as refs.

Examples:

- a source's extracted key fact;
- a code symbol's role;
- a paper's method/result/limitation note;
- a contradiction or gap that drives the next search;
- a source-to-claim mapping.

Pinned evidence can still be compacted. It must not disappear into an opaque ref
without a replacement summary or working-set note.

### Detect Repeated Reads

The runtime should track repeated reads of the same ref/range/query identity
within a phase. Repeated reads are not always wrong, but they are a signal:

- if the ref changed, reread is expected;
- if a write/edit requires fresh contents, reread is expected;
- if the same unchanged source is read repeatedly without new state, context is
  thrashing.

Repeated-read diagnostics should trigger one of:

- keep the source's bounded projection pinned;
- ask the PiWorker to write/update a `ContextSummaryArtifact`;
- checkpoint before another broad search wave;
- surface a warning in `RunSnapshot` / TUI.

Query identity must be refs-first. Diagnostics should record `query_ref`,
`query_hash`, normalized tool metadata, counts, source refs, source hashes, and
denial reasons. They must not expose raw user text, secrets, provider payloads,
tool bodies, or product-specific query prose.

### Preserve Why-It-Matters

Every demoted source should keep enough metadata to avoid rediscovery:

```text
ref
hash/version
bounded projection ref
why it mattered
phase/claim/hypothesis links
last-read turn
permission manifest ref
```

The "why" may be product-authored. Core should preserve and project it, not
generate it.

### Recent Context Plus Summary

Compaction should not replace all history with a flat summary. It should keep:

- structured summary/checkpoint refs;
- a token-bounded recent tail;
- active working-set projections;
- relevant source refs and why-it-matters notes.

This mirrors opencode's practical split between summary and recent context, but
keeps MissionForge's refs and permission model.

## Context Explosion Avoidance

MissionForge should avoid context explosion with layered controls.

### Deterministic Budgeting

Before a provider call:

- estimate stable prefix tokens;
- estimate semi-stable tokens;
- estimate volatile tail tokens;
- reserve output headroom;
- compare against model context window;
- emit `ContextPressureDiagnostics`.

This is mechanical. It does not decide semantic importance.

### Demotion

Low-density or old segments move from inline/preview to ref stubs:

- old tool outputs;
- large search results;
- superseded observations;
- runtime logs;
- repeated source fetch bodies.

### Checkpointing

At soft pressure, MissionForge should prepare a checkpoint and may invoke the
managed reducer when policy allows it.

At hard pressure, MissionForge should stop at a completed safe point before the
next provider call, write a checkpoint record, and then try a managed reduction
pass if a reducer adapter is available. If reduction succeeds, Kernel recompiles
context and continues. If reduction fails or is unavailable, the previous active
context remains valid and the step blocks with actionable diagnostics.

The host should not be required to write checkpoint or compaction records by
hand. Host policy may disable automatic reduction, change thresholds, or provide
a custom reducer, but the default package behavior should be managed by
MissionForge.

### Managed And Product-Specific Reduction

MissionForge should ship a generic reducer path that can maintain baseline
working context without product integration. The generic reducer may summarize:

- frozen objective and constraints from contract/brief refs;
- progress visible from bounded projections and explicit artifacts;
- current blockers;
- recent decisions;
- next-step notes;
- refs needed to recover full evidence.

The generic reducer must cite source refs and hashes. It must not change task
authority or acceptance criteria. If a user event changes task truth, normal
contract revision rules still apply.

DeepResearch should keep research state in product artifacts:

- `research_state.json`;
- `source_packet.json`;
- `claim_index.json`;
- `insight_map.json`;
- reviewer observations;
- judge report.

Those artifacts are product semantic memory. The generic ContextEngine knows how
to cite and project them, and the generic reducer can preserve their refs, but
DeepResearch-specific interpretation remains in the integration.

## Target Capability Level

MissionForge should aim to match opencode's core context-management level, not
its whole coding-agent product.

The target is:

- stable cache-friendly authority context;
- bounded model-visible working context;
- no repeated replay of large tool outputs;
- explicit managed refs for full evidence;
- automatic pressure diagnostics before provider turns;
- durable compaction/checkpoint lifecycle records;
- package-managed generic reduction when pressure or thrash requires it;
- repeated-read/ref-thrashing diagnostics;
- product-authored semantic state where available, not core-authored semantic
  judgment.

Out of scope:

- universal semantic memory;
- automatic domain ranking;
- a provider zoo;
- a graph workflow engine;
- full coding-agent file mutation UX parity with opencode.
- requiring ordinary package users to implement context reducers before
  MissionForge can run long tasks safely.

## Success Metrics

The architecture should be judged by measurable behavior, not by the number of
new abstractions.

For a long DeepResearch run, compare before and after:

- repeated read/fetch/search count for unchanged refs;
- total tool calls;
- input tokens;
- cached input tokens;
- output tokens;
- context pressure over time;
- number of hard context stops;
- number of checkpoint/resume successes;
- final report claim-to-source coverage;
- reviewer/judge rejection causes;
- user-visible blocked diagnostics quality.

Minimum success condition:

```text
For equivalent tasks, ContextEngine should reduce repeated unchanged-source
reads and context-pressure blocks without reducing evidence coverage.
```

If tool calls drop but evidence coverage degrades, the design failed. If evidence
coverage improves but repeated rereads remain high, the working-set policy is
still insufficient.

## DeepResearch Adaptation

DeepResearch should use ContextEngine as follows:

1. FrontDesk creates a research request document and contract.
2. Kernel uses MissionForge's default ContextEngine policy unless DeepResearch
   provides a stricter product policy.
3. Source mapper/researcher tools emit raw outputs and structured observations.
4. ContextEngine demotes raw search/fetch/code-audit outputs after their
   immediate utility window.
5. The managed reducer preserves generic progress, blockers, decisions, and
   active evidence refs when pressure or thrash requires it.
6. Researcher PiWorker updates `research_state` and source artifacts explicitly.
7. Reviewer sees the research artifacts and selected evidence refs, not the
   entire tool transcript.
8. Judge sees final report, claim/evidence indexes, reviewer observation, and
   explicit source refs.

This should reduce the current failure mode where a single PiWorker carries a
large research process in its conversational tail.

## Module Placement

Recommended minimal placement:

```text
src/missionforge/context.py
  existing ContextSegment, ContextView, pressure/replay diagnostics

src/missionforge/context_engine.py
  ContextSource
  ContextSourceSnapshot
  ContextEpoch
  ContextWorkingSet
  ContextCheckpoint
  ContextReductionRequest
  ContextReductionResult
  ContextCompileRequest
  ContextCompileResult
  ContextTurnBoundary
  ContextCompactionRecord
  compile_context_view(...)
  reconcile_context_epoch(...)
  build_context_reduction_request(...)
  validate_context_reduction_result(...)

src/missionforge/tool_projection.py
  ToolOutputProjection
  bound_tool_output(...)
  build_tool_observation_segment(...)

src/missionforge/context_policy.py
  ContextManagementPolicy
  pressure / thrash thresholds
  reducer enablement
  token caps and projection caps

src/missionforge/context_reducer.py
  build managed reducer PiWorkerCall
  validate reducer outputs
  apply reducer result as refs-only state transition

src/missionforge/kernel/compiler.py
  compile Step -> ContextCompileRequest

src/missionforge/kernel/runner.py
  call ContextEngine at safe provider-turn boundary
  write ContextView / pressure / checkpoint refs
  invoke managed reducer when policy requires it
  recompile after successful reduction before provider call

src/missionforge/adapters/pi_agent_runtime.py
  translate runtime tool events into ToolObservation / ToolOutputProjection

integrations/deepresearch/...
  optional product semantic reducers and prompts only
```

If `context_engine.py` and `tool_projection.py` remain small, they can later be
merged into `context.py`. Keep them separate while the architecture is still
settling.

`context_engine.py` should contain data contracts and pure boundary helpers, not
a stateful runtime object. Kernel API remains responsible for orchestration at
safe boundaries. Host Python should not need to orchestrate context maintenance
directly.

`context_reducer.py` is a small infrastructure bridge, not a second workflow
engine. It should build one bounded reducer call, validate refs-only outputs,
and return a state transition that Kernel either applies completely or rejects
without mutating active context.

## Implementation Plan

### Phase 1: Design Lock And Tests First

Deliverables:

- this architecture document;
- public primitive list update;
- tests that assert new records are refs-only;
- tests that denied refs cannot be selected as context sources.

Exit criteria:

- no product semantics added to `src/missionforge`;
- no raw prompt/tool/provider body appears in context diagnostics.

### Phase 2: ContextSource And Epoch Records

Deliverables:

- `ContextSource`;
- `ContextSourceSnapshot`;
- `ContextEpoch`;
- epoch reconcile helper;
- file-backed epoch record refs.

Exit criteria:

- unchanged stable source produces unchanged baseline hash;
- changed volatile source produces update segment, not baseline rewrite;
- unavailable non-initial source keeps previous admitted state;
- unavailable initial authority source blocks safely.

### Phase 3: ToolOutputProjection

Deliverables:

- bounded projection helper;
- projection record schema;
- integration with existing `ToolObservation`;
- configurable max bytes/lines;
- head/tail preview or product projection hook ref.

Exit criteria:

- large tool output stores full raw ref but model projection is bounded;
- projection cites raw ref/hash/size;
- storage failure for optional raw retention does not fabricate success;
- judge role cannot read executor raw output unless explicitly granted.

### Phase 4: Context Compile Request/Result

Deliverables:

- `ContextCompileRequest`;
- `ContextCompileResult`;
- `ContextWorkingSet`;
- provider-neutral cache layout diagnostics;
- pressure action output.

Exit criteria:

- stable/semi-stable/volatile/omitted buckets are deterministic;
- active-phase working set remains visible as bounded projections;
- cache layout stays stable when only volatile tail changes;
- pressure diagnostics do not route semantic decisions.

### Phase 5: Anti-Thrashing Diagnostics

Deliverables:

- repeated-read counters by ref/range/query identity;
- diagnostics in `ContextCompileResult` or pressure record;
- warning when unchanged refs are repeatedly read without new working-set state;
- optional recommendation to pin, summarize, or checkpoint.

Exit criteria:

- repeated unchanged reads are detectable in tests;
- expected rereads after content changes or edit failures are not flagged as
  pathological;
- diagnostics cite refs, hashes, normalized metadata, and counts, not raw
  queries, user text, prompts, provider payloads, or raw bodies.

### Phase 6: Kernel Safe Boundary Integration

Deliverables:

- Kernel runner calls ContextEngine before PiWorker invocation;
- writes context view, epoch, pressure, and checkpoint refs;
- emits `RunEvent.CONTEXT_PROJECTED`;
- respects `ControlPort` pause/cancel/inject/revision before provider call.

Exit criteria:

- debug stepping can show compiled context without executing PiWorker;
- user interruption lands at a safe boundary;
- failed compaction/checkpoint leaves previous context active.

### Phase 7: Package-Managed Checkpoint Records

Implementation status: implemented for Kernel `run_step()` soft/hard pressure
boundaries.

Deliverables:

- first-class `ContextCheckpoint` contract;
- Kernel writes checkpoint records at soft/hard pressure according to policy;
- turn boundary and compile result cite checkpoint refs;
- runtime pressure checkpoint artifacts are either aligned with or wrapped by
  `ContextCheckpoint`;
- inspection/status surfaces checkpoint refs without expanding bodies.

Exit criteria:

- ordinary `run_step()` callers do not manually create checkpoint records;
- checkpoint records are refs-only and permission-bound;
- hard pressure stops before provider invocation with a checkpoint ref;
- checkpoint write failure leaves previous context active and produces
  actionable diagnostics.

### Phase 8: Managed Generic ContextReducer

Implementation status: implemented as a bounded infrastructure PiWorker call
boundary. The default path builds `ContextReductionRequest`, grants a scoped
maintenance permission manifest, validates `ContextReductionResult`, and never
treats reducer output as task acceptance.

Deliverables:

- internal infrastructure reducer role or equivalent managed reducer call path;
- `ContextReductionRequest`;
- `ContextReductionResult`;
- default reducer prompt/brief packaged with MissionForge;
- reducer permission manifest limited to admitted context and maintenance output
  refs;
- reducer output validation for working-set, summary, checkpoint, pinned,
  evicted, and omitted refs.

Exit criteria:

- package users get automatic reduction without writing product integrations;
- reducer cannot read denied refs or write outside context maintenance roots;
- invalid reducer output blocks safely without changing active context;
- reducer summaries cite source refs/hashes and do not change task authority;
- reducer result is not treated as semantic task acceptance.

### Phase 9: Compaction Lifecycle And Recompile

Implementation status: implemented for hard-pressure Kernel preflight. Valid
reducer output produces a completed state transition and compaction record, then
Kernel recompiles before invoking the original worker. Invalid or failed reducer
output writes failed diagnostics and blocks without publishing a new active
context.

Deliverables:

- `ContextCompactionRecord` is written for started, ended, and failed attempts;
- successful reduction can produce a new working set and summary refs;
- Kernel recompiles context after successful reduction;
- epoch replacement occurs only after completed compaction/reduction;
- failed compaction leaves old context view, epoch, and working set active.

Exit criteria:

- hard pressure can be resolved by managed reduction and recompile in tests;
- failed reduction/compaction produces a blocked result with refs-only
  diagnostics;
- no partial context mutation is published;
- retry attempts either reuse the same preflight boundary explicitly or return
  to a fresh safe boundary.

### Phase 10: Policy-Controlled Working Set And Anti-Thrashing

Implementation status: partially implemented. `ContextManagementPolicy` now
controls default pressure thresholds and reducer enablement, and reducer-created
working-set/summary refs can be admitted into the fresh compile after
validation. Repeated-read diagnostics exist as refs-only contracts, but full
policy routing from live read observations into reducer requests is still future
work.

Deliverables:

- `ContextManagementPolicy` controls thresholds, caps, reducer enablement, and
  retry behavior;
- repeated-read diagnostics are derived from real tool/read observations;
- diagnostics can trigger managed reducer requests;
- reducer-created working-set updates are admitted into the next compile;
- stale entries are evicted only through validated state transitions.

Exit criteria:

- repeated unchanged reads become visible and correctable without host code;
- active evidence remains visible as bounded projections;
- expected rereads after content changes are not flagged as pathological;
- working-set updates preserve refs, hashes, permission manifests, and token
  caps.

### Phase 11: DeepResearch Adoption As Pressure Test

Deliverables:

- DeepResearch uses new diagnostics in TUI;
- source mapper/researcher tool outputs become projections;
- default managed reducer works even without DeepResearch-specific reducers;
- product semantic state remains in integration artifacts;
- reviewer/judge context consumes artifact refs rather than full transcript.

Exit criteria:

- long research run no longer replays massive source/tool transcript;
- final report path, usage summary, context pressure, and checkpoint refs are
  visible to user;
- blocked states expose actionable safe-point diagnostics.

## Tests Required

Core tests:

- `ContextSource` rejects duplicate keys.
- `ContextSourceSnapshot` is refs-only.
- `ContextEpoch` hash is stable across process reload.
- Epoch replacement occurs after contract revision or completed compaction.
- Denied refs are omitted before source loading.
- Unavailable initial authority source blocks.
- Unavailable dynamic source preserves prior admitted snapshot.

Tool projection tests:

- large output becomes bounded projection plus raw ref;
- small output may remain inline;
- structured output remains available separately from model projection;
- projection record rejects raw body fields;
- output demotion happens after safe boundary.

Kernel tests:

- `Step` compiles to `ContextCompileRequest`;
- `run_step` writes context compile refs;
- `preview_flow_step` can inspect context layout;
- hard pressure stops before next provider turn;
- hard pressure writes or cites a `ContextCheckpoint`;
- managed reducer is invoked by policy without host code;
- invalid reducer output does not mutate active context;
- successful reducer output causes a fresh compile before provider invocation;
- compaction failure does not mutate active context.

Policy/reducer tests:

- default `ContextManagementPolicy` requires no product integration;
- reducer permission manifest cannot read denied refs;
- reducer permission manifest can write only context maintenance refs;
- `ContextReductionRequest` and `ContextReductionResult` are refs-only;
- reducer summaries must cite source refs/hashes;
- reducer result is never accepted as task completion or judge approval.

DeepResearch tests:

- source mapper large search output is demoted;
- generic reducer can preserve research progress refs before product-specific
  state exists;
- reviewer sees source packet/claim refs, not raw transcript tail;
- judge sees final report/evidence/claim refs;
- TUI status shows context pressure/checkpoint refs.

## Risks And Mitigations

### Risk: ContextEngine Becomes a Product Brain

Mitigation: keep deterministic semantic judgment outside core. Core may compile
refs, request managed reduction, validate reducer outputs, and apply refs-only
state transitions. The managed reducer may produce generic summaries as a
PiWorker role, but only product integrations decide product-specific meaning and
only independent judge boundaries decide task acceptance.

### Risk: Package Users Inherit Context Burden

Mitigation: Kernel owns the default ContextEngine lifecycle. Ordinary package
users should not manually create working sets, checkpoints, compaction records,
or reducer calls. Expose policy configuration and extension hooks, not required
orchestration steps.

### Risk: Cache Layout Leaks Provider-Specific Complexity

Mitigation: store provider-neutral cache strata in core. Provider adapters lower
them into Anthropic breakpoints, OpenAI stable prefixes, or no-op behavior.

### Risk: In-Memory State Weakens Auditability

Mitigation: allow memory only for transient compile state. Epochs, checkpoints,
summaries, and final context views must be recoverable from refs and hashes.

### Risk: Compaction Hides Important Evidence

Mitigation: compaction output must cite source refs and hashes. Raw evidence
remains accessible through permissions. Failed compaction leaves old context
active.

### Risk: Managed Reducer Silently Changes Task Truth

Mitigation: reducer outputs may create summaries, working-set projections, and
checkpoint refs only. They must not modify frozen contracts, acceptance
criteria, permission manifests, or judge rubrics. Any task truth change still
requires an explicit contract revision.

### Risk: Context Source Loading Bypasses Permissions

Mitigation: `ReadGate` must run before source loading. Source loaders should
receive already-filtered refs or an explicit permission service.

## Architecture Decision

MissionForge should implement a small ContextEngine.

It should borrow opencode's mechanisms:

- stable context source identity;
- immutable context epochs;
- safe provider-turn admission;
- bounded tool-output model projections;
- durable compaction/checkpoint events.

It should not borrow opencode's product assumptions:

- coding-session summary templates;
- provider-native transcript dependence as generic truth;
- session DB as the conceptual authority plane;
- broad session runtime ownership of application semantics.

MissionForge's distinctive value remains:

```text
frozen contract authority
+ permission-filtered refs
+ sandbox/tool gateway boundary
+ observable context compiler
+ package-managed reducer PiWorker for context maintenance
+ PiWorker semantic nodes
+ independent judge
```

The ContextEngine should make that value faster, more cache-friendly, and more
usable for long-running agent products without turning MissionForge into a
large framework or forcing host applications to own context lifecycle plumbing.
