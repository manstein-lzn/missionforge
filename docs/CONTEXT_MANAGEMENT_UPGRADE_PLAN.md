# Runtime Context Management Upgrade Plan

## Status

Phase A-D core implementation landed, and Phase D2 now has the default Mem0
adapter boundary plus initial DeepResearch single-agent opt-in wiring. This
plan treats the long-memory provider boundary as required for a complete
long-context system, not as a nice-to-have extension. The runtime core accepts
and validates a bounded provider-neutral `LongMemoryPacket`; products decide
whether to build one and pass it through the runtime input.

This document supersedes the older naming and product-shape guidance that used
runtime-generated `ContextSummaryArtifact(kind=compaction)` files. The current
runtime direction is strict:

- no automatic LLM session compaction in MissionForge core;
- no runtime-authored semantic summaries;
- no hidden memory that can override a frozen contract;
- no product-specific context logic under `src/missionforge`.

## Goal

Build a practical context-management system that fits MissionForge's taste:
small, orthogonal, white-box, and PiWorker-centered.

The runtime should prevent context explosion while preserving PiWorker agency,
and it should make long-running work cost-aware. It should manage context
shape, refs, budgets, checkpoints, long-memory packet boundaries, and
permission boundaries. It should not decide what content means.

There are two different guarantees:

- **Context pressure safety** can be provided by MissionForge runtime alone
  through stable prefixes, projection, refs, budgets, checkpoints, and resume.
- **High-quality long-context recall** requires a long-memory provider such as
  Mem0 or an equivalent adapter. Without that provider, the system must run in
  an explicit degraded mode that relies on refs and segment catalogs only.

The target active context shape is:

```text
[stable authority prefix]
+ [current contract / role / permission / objective refs]
+ [small advisory long-memory packet, if enabled]
+ [middle history projection with refs]
+ [recent tail with full detail within budget]
```

## Current Baseline

Already implemented or partially implemented:

- `ToolObservation` capture for completed tool calls.
- Raw/source refs, hashes, sizes, and projection metadata.
- Deterministic projection of stale large tool results through
  `ContextProjector`.
- Read-only `context_snapshot` inspection.
- Context pressure diagnostics with soft and hard ratios.
- Completed-turn safe-point stop before the next provider call at hard pressure.
- Extension declaration, lock, load report, and runtime tool mounting for
  PiWorker tools.

Current minimal upgrade status:

- Runtime pressure now writes
  `attempts/<call_id>/context/context_pressure_checkpoint.json` using
  `missionforge.runtime_context_checkpoint.v1`.
- Resume input accepts `checkpoint_refs`; legacy `summary_artifact_refs` remain
  accepted only for explicit semantic artifacts and compatibility.
- Projection diagnostics include budget diagnostics and memory-layer
  diagnostics.
- Older long sessions can emit a flat segment catalog and metadata-only segment
  envelopes.
- Runtime input accepts an optional `long_memory_packet_ref` under the attempt
  directory.
- Runtime core validates `missionforge.long_memory_packet.v1` packets for
  advisory-only authority, source refs, scope, confidence/status, and budget.
- Valid long-memory packets are injected after authority context and before
  archived/middle/recent history projection.
- Missing packet/provider state is surfaced as explicit degraded-mode
  diagnostics.

Remaining maturity gaps:

- Provider token budgeting still uses conservative estimates when provider
  usage is unavailable.
- Short/middle projection is still count-based, not fully token-budget based.
- Operator-facing progress does not yet surface long-memory degraded mode
  outside projection diagnostics.
- DeepResearch long memory is wired for the initial researcher call only; the
  reviewer-guided update loop still needs explicit product wiring if it should
  receive role-scoped packets.
- Resume from a context-pressure checkpoint is explicit and refs-first, but it
  is not yet a polished product flow.

## Non-Goals

- Do not add Pi/OpenCode automatic session compaction to MissionForge core.
- Do not make runtime summarize old conversations.
- Do not let memory become task authority.
- Do not build a product-specific research, coding, finance, or customer
  context manager in core.
- Do not make Judge nodes depend on executor-authored subjective memory.
- Do not make extension tooling part of this upgrade; the extension mounting
  mechanism already exists and should remain separate.

## Design Laws

1. Frozen contracts and explicit revisions are the task authority.
2. Memory is advisory context, not truth.
3. Evidence lives in refs, artifacts, ledgers, source packets, and hashes.
4. Runtime manages budgets and projections; PiWorker manages meaning.
5. Long memory must be queryable by flat indexes and packets, not chained refs.
6. Recent context can be rich, but never unbounded.
7. Older context can be projected or archived, but never silently rewritten as
   semantic truth.
8. Hard context pressure stops at a completed-turn safe point unless an
   explicit future policy says otherwise. It never triggers automatic compact.
9. Prompt-cache stability matters: stable authority prefixes should not be
   rewritten each turn.
10. Full long-context quality requires a long-memory provider boundary. A refs
    catalog alone is a degraded fallback, not the complete system.
11. Mem0 may be the default long-memory adapter, but MissionForge core only
    accepts MissionForge `LongMemoryPacket` data and provider-neutral requests.

## Target Memory Layers

### Stable Authority Prefix

Always present, always first, and kept as stable as possible:

- system/runtime rules;
- MissionForge agent instructions;
- frozen `TaskContract` refs and hashes;
- role-specific `WorkerBrief` or `JudgeRubric` refs;
- permission manifest and workspace policy refs;
- current objective and expected outputs;
- context policy statement.

This layer should be small. It should cite refs rather than embed large bodies.

### Short-Term Memory

Recent turns remain fully visible where budget permits.

The first implementation may use turn counts, but the target should be token
budget based:

- keep the most recent completed turns intact;
- keep tool-use/tool-result pairs together;
- preserve the immediate follow-up turn after a tool result;
- enforce per-message and total short-tail budgets;
- large outputs may be visible only if they fit within the short-tail budget.

Short-term memory is the working set. It is allowed to be detailed, but it is
not allowed to be infinite.

### Middle-Term Memory

Middle history keeps conversational shape but projects low-density large
content:

- user and assistant turns remain visible as message envelopes;
- old large tool results are replaced with deterministic metadata stubs;
- stubs include observation id, tool name, status, hash, size, source/raw refs,
  and read/search hints when permitted;
- artifact refs, source refs, and decision refs remain explicit;
- no semantic summary is generated by runtime.

Middle-term memory should be deterministic and reversible through refs.

### Long-Term Memory

Long-term memory is not a ref chain. A flat segment catalog is necessary for
traceability, but it is not sufficient for high-quality long-context recall.
The model should not spend expensive turns walking nested refs to rediscover
old conclusions.

The minimum long-term layer is:

- immutable raw session/event/artifact refs;
- a flat segment catalog;
- optional memory cards written by PiWorker or a dedicated memory worker;
- a default external long-memory provider adapter, initially Mem0;
- equivalent providers are allowed only if they can produce the same
  MissionForge packet contract.

Active context should receive only a small memory packet:

```json
{
  "schema_version": "missionforge.long_memory_packet.v1",
  "budget_tokens": 2000,
  "memories": [
    {
      "memory_id": "mem-001",
      "statement": "Memory is advisory and cannot override frozen contracts.",
      "scope": "project",
      "source_refs": ["attempts/WU-000001/session.jsonl#turn-42"],
      "confidence": "high",
      "status": "active",
      "why_relevant": "Current task concerns runtime context management."
    }
  ],
  "catalog_hits": [
    {
      "segment_ref": "attempts/WU-000001/context/segments/0001.jsonl",
      "turn_range": [1, 8],
      "topics": ["context management", "MissionForge runtime"],
      "artifact_refs": ["docs/CONTEXT_MANAGEMENT_SHORT_TERM_PLAN.md"],
      "hash": "sha256:..."
    }
  ]
}
```

The packet is advisory. Important claims should be validated against source
refs before they affect final artifacts or judge decisions. If no valid packet
is available, the runtime should continue only in degraded mode and say so in
projection diagnostics and operator-facing progress.

## Long-Memory Provider Boundary

Mem0 should be the first default long-memory adapter because it is small enough
to integrate, has an existing agent-memory shape, and avoids MissionForge
inventing a semantic memory engine. Mem0 still must not enter MissionForge core
as a semantic dependency.

MissionForge core owns the provider-neutral boundary. It does not depend on
Mem0 SDK types, Mem0 storage semantics, or Mem0's internal memory graph. Core
accepts only MissionForge requests and packets. A Mem0 adapter maps between
Mem0 and those contracts.

MissionForge should define a thin provider boundary:

```text
LongMemoryProvider.add(record) -> MemoryWriteResult
LongMemoryProvider.search(request) -> MemorySearchResult
LongMemoryProvider.get(memory_id, scope) -> MemoryRecord
LongMemoryProvider.build_packet(request) -> LongMemoryPacket
```

Provider rules:

- Mem0 is the default adapter when a long-memory provider is enabled;
- long-memory provider use is explicit in the runtime profile or permission
  manifest;
- missing provider means degraded mode, not silent best-effort behavior;
- no unbounded auto-capture in core;
- every stored memory must carry source refs;
- secrets and raw provider payloads are rejected;
- memory scope must include role, project, mission, or user boundaries;
- Judge memory access must be isolated from executor subjective memory unless
  the product explicitly grants it as evidence.

An external provider can implement extraction, retrieval, deduplication, and
conflict handling. MissionForge core only validates packets, refs, scopes, and
budgets.

Required packet contract:

```json
{
  "schema_version": "missionforge.long_memory_packet.v1",
  "provider": "mem0",
  "packet_ref": "attempts/WU-000001/context/long_memory_packet.json",
  "advisory_only": true,
  "budget_tokens": 2000,
  "scope": {
    "project_id": "missionforge",
    "mission_id": "contract-001",
    "role": "executor_piworker"
  },
  "memories": [
    {
      "memory_id": "mem_001",
      "statement": "Runtime memory is advisory and cannot override frozen contracts.",
      "why_relevant": "The current task changes runtime context management.",
      "source_refs": ["attempts/WU-000001/session.jsonl#turn-42"],
      "confidence": "high",
      "status": "active",
      "created_at": "2026-06-17T00:00:00.000Z"
    }
  ]
}
```

Providers that cannot supply source refs, scopes, confidence, status, and a
bounded canonical packet are not compatible with the MissionForge runtime
boundary.

## Budget Policy

Replace the current rough pressure ratio with a budget allocator:

```text
usable_input_budget =
  min(model_input_limit, model_context_window - reserved_output_tokens)
  - reserved_runtime_buffer
```

Suggested first budgets:

- stable authority prefix: fixed cap;
- long-memory packet: 1k-3k tokens;
- middle projection: bounded by remaining budget after recent tail;
- recent tail: protected minimum, then grows until budget pressure;
- tool schemas and system overhead: explicitly reserved;
- hard stop: before the next provider request when projected input would exceed
  the hard boundary.

Provider-reported token counts should be preferred when available. Conservative
estimation remains the fallback.

## Prompt Cache Policy

- Keep stable authority prefix deterministic and early.
- Put contract, role, permission, and objective refs immediately after the
  stable authority prefix and keep their rendering canonical.
- Put dynamic long-memory packets after authority refs and before projected
  history. They are useful but cache-unstable.
- Put projection diagnostics and recent history after stable/cacheable layers.
- Avoid rewriting historical messages unless crossing a defined projection
  boundary.
- Prefer deterministic stubs over semantic summaries for runtime projection.
- Record cache read/write tokens as diagnostics only.

Target ordering for cache efficiency:

```text
stable authority prefix
current contract / role / permission / objective refs
long-memory packet, small and advisory
middle history projection / segment catalog
recent full tail
```

The first two layers should change rarely within a mission. The long-memory
packet and recent tail are expected to change more often and should not be
placed before stable authority text.

## Pressure Behavior

Soft pressure:

- write projection diagnostics;
- archive old turns into segment refs if needed;
- project old large tool outputs;
- refresh the long-memory packet only if a provider is explicitly enabled;
- if no long-memory provider is available, mark long-memory as degraded rather
  than pretending refs-only catalogs are equivalent;
- continue only if projected input remains under the hard boundary.

Hard pressure:

- stop at a completed-turn safe point;
- write a refs-only runtime context checkpoint;
- mark the run as requiring explicit resume;
- do not run automatic compaction;
- do not generate a runtime semantic summary.

## Artifact Renaming

Rename runtime-generated compaction markers to checkpoint language.

Target names:

- `attempts/<call_id>/context/context_pressure_checkpoint.json`
- event type: `context_pressure_checkpoint`
- savepoint field: `context_checkpoint`
- resume field: `checkpoint_refs`

Keep `ContextSummaryArtifact` for explicit PiWorker/Judge-authored semantic
artifacts only. Runtime checkpoints should use a separate schema:

```json
{
  "schema_version": "missionforge.runtime_context_checkpoint.v1",
  "call_id": "WU-000001",
  "turn_index": 12,
  "reason": "hard_context_pressure",
  "savepoints_ref": "attempts/WU-000001/savepoints.jsonl",
  "session_ref": "attempts/WU-000001/session.jsonl",
  "events_ref": "attempts/WU-000001/events.jsonl",
  "context_observations_ref": "attempts/WU-000001/context/tool_observations.jsonl",
  "context_projection_ref": "attempts/WU-000001/context/projection.json",
  "segment_catalog_ref": "attempts/WU-000001/context/segments/catalog.json",
  "metadata": {
    "estimated_input_tokens": 0,
    "usable_input_budget": 0,
    "pressure_ratio": 0.0,
    "cache_read_tokens": 0,
    "cache_write_tokens": 0
  }
}
```

No raw tool output, prompts, transcript bodies, provider payloads, or secrets
belong in this checkpoint.

## Implementation Phases

### Phase A: Rename And Re-Schema Runtime Checkpoints

Status: minimal implementation landed.

- Add `runtime_context_checkpoint.v1`.
- Replace runtime-generated `compaction_summary.json` with
  `context_pressure_checkpoint.json`.
- Preserve backwards compatibility by accepting old `summary_artifact_refs`
  temporarily, but prefer `checkpoint_refs`.
- Update docs and tests to stop calling runtime checkpoints summaries.

Exit condition:

- Runtime pressure artifacts are refs-only checkpoints and cannot be confused
  with semantic compaction.

### Phase B: Budget Allocator

Status: minimal diagnostics implementation landed.

- Add a `ContextBudgetAllocator`.
- Compute usable input budget from model context, output reserve, runtime
  buffer, tool schema estimate, and provider-reported usage when available.
- Keep current ratio fields as diagnostics, not as the only decision source.
- Add tests for small, medium, and hard-pressure runs.

Exit condition:

- Runtime can explain why each layer received its budget.

### Phase C: Layered History Projector

Status: minimal count-based implementation landed.

- Extend `ContextProjector` from tool-result projection to full layered
  projection.
- Preserve stable authority prefix.
- Keep recent tail full within budget.
- Render middle turns with large outputs as refs.
- Archive older turns into segment refs and inject a flat segment catalog.
- Preserve tool-use/tool-result pairing.

Exit condition:

- A long synthetic session projects into stable prefix, catalog, middle stubs,
  and recent full tail without semantic summaries.

### Phase D: Long-Memory Packet Interface

Status: implemented for the provider-neutral runtime core boundary.

- Define provider-neutral `LongMemoryPacket` schema.
- Add optional packet injection after authority context and before history.
- Validate memory ids, source refs, scopes, confidence, status, and budget.
- Add degraded-mode diagnostics when no provider or packet is available.
- Keep provider implementation outside core. Mem0 is the first default adapter,
  but runtime core must only depend on `LongMemoryProvider` requests and
  `LongMemoryPacket`.

Implemented notes:

- TypeScript runtime input parses `long_memory_packet_ref` and requires it to
  stay inside `attempt_dir_ref`.
- Python `PiAgentRuntimeConfig` and `PiAgentRuntimeInput` pass the packet ref
  through to the Node sidecar without importing provider-specific semantics.
- `long-memory.ts` loads, validates, renders, budgets, and diagnoses advisory
  packets.
- `ContextProjector` injects the rendered memory packet before archived history
  stubs and reports long-memory diagnostics.

Exit condition:

- Runtime can accept or reject a bounded advisory memory packet without
  depending on Mem0 or any product-specific semantics.
- Missing long-memory provider is visible as degraded mode.
- Judge calls do not receive executor private memory unless explicitly granted.

### Phase D2: Default Mem0 Adapter

Status: implemented for the provider boundary and initial DeepResearch
single-agent product wiring. Reviewer-guided product wiring remains a later
product choice.

- Implement `Mem0LongMemoryProvider` outside MissionForge core runtime logic.
- Map Mem0 add/search/get results into MissionForge `LongMemoryPacket`.
- Disable unbounded auto-capture.
- Require source refs on writes and packets.
- Respect project, mission, user, and role scopes.
- Keep Mem0 provider payloads out of durable runtime state by default.

Implemented notes:

- `missionforge.adapters.long_memory` defines provider-neutral Python
  contracts plus `Mem0LongMemoryProvider`.
- The Mem0 adapter lazy-loads the optional `mem0ai` package and supports client
  injection for tests and custom hosts.
- Mem0 records are accepted only when they map to MissionForge records with
  explicit `source_refs`.
- Built packets use the same `missionforge.long_memory_packet.v1` contract that
  runtime core validates; provider payloads are not embedded.
- The `mem0ai` dependency is optional through the `mem0` package extra.

Exit condition:

- Long-running products can opt into the default Mem0 adapter and receive a
  valid packet through the same core boundary used by any future provider.

### Phase D3: Product Wiring Guardrails

Status: partially implemented for DeepResearch `single-agent-run`.

- Keep long memory opt-in at the product boundary. It should not become hidden
  core behavior.
- Build packets before a PiWorker call and write them inside that call's
  attempt context directory.
- Scope packets by mission and role. Researcher packets must not silently flow
  into reviewer or judge calls.
- Record packet refs as evidence and diagnostics only. A packet is never a
  frozen contract, revision, source packet, or acceptance authority.
- If no provider is configured, surface degraded long-memory diagnostics and
  continue through refs, checkpoints, segment catalogs, and recent context.

Implemented notes:

- DeepResearch `single-agent-run` exposes `--long-memory-provider none|mem0`,
  `--long-memory-budget-tokens`, and `--long-memory-limit`.
- DeepResearch writes researcher packets at
  `attempts/<researcher_call_id>/context/long_memory_packet.json` and passes
  the ref to `PiAgentRuntimeConfig`.

Exit condition:

- Product integrations can choose where memory is useful without making
  MissionForge core product-aware or memory-authoritative.

### Phase E: Resume From Checkpoint

Status: runtime envelope support exists; product-level resume flow remains
pending.

- Add `checkpoint_refs` to resume input.
- Build a fresh call from frozen contract refs, checkpoint refs, segment
  catalog, middle projection, and recent tail.
- Do not hydrate old hidden state.
- Make resume prompt explicit about advisory memory versus authority refs.

Exit condition:

- A hard-pressure stopped run can resume through explicit refs without runtime
  compaction.

### Phase F: DeepResearch State-Driven Loop Integration

Status: initial reviewed-run observation routing implemented.

This product step is not more runtime memory machinery. It makes the
DeepResearch reviewer-guided loop consume explicit state artifacts:

- reviewer writes `reviews/round_XX/reviewer_observation.json`;
- observation decisions are limited to `continue`, `ready_for_judge`,
  `tool_blocked`, `revision_required`, and `rejected`;
- Python routes only on that decision and hard budgets;
- researcher writes `research_state.json` only after a `continue` observation;
- `ready_for_judge` ends the review loop without another revision round;
- `tool_blocked` and `revision_required` become blocked product results;
- `rejected` becomes a failed product result.

This keeps runtime context management orthogonal: memory packets provide
advisory recall, review observations provide explicit loop control, and the
independent judge remains the only product acceptance authority.

Remaining product work:

- exercise the observation loop with live PiWorker reviewer/researcher calls;
- decide whether reviewed revision calls should opt into role-scoped long
  memory packets;
- add a bounded same-contract judge repair/rejudge path only if acceptance
  testing shows it is needed.

## Test Strategy

Required tests:

- stable authority prefix survives all projection modes;
- recent tail remains full under budget;
- large recent output is capped rather than allowed to explode context;
- middle tool results become deterministic stubs with refs and hashes;
- old turns archive into segment refs and a flat catalog;
- runtime checkpoint contains refs and diagnostics only;
- memory packet cannot override contract fields;
- memory packet requires source refs;
- memory packet is rejected when over budget;
- memory packet is injected after authority refs and before history;
- Judge does not receive executor private memory by default;
- missing long-memory provider reports degraded mode;
- Mem0 adapter output maps into the provider-neutral packet without leaking
  provider payloads;
- prompt/cache diagnostics are recorded but never used as semantic authority;
- hard pressure stops before the next provider call.

## Open Questions

- Exact first defaults for token budgets and recent-tail protection.
- Whether segment catalogs should be deterministic only, PiWorker-authored, or
  both.
- Whether same-worker raw refs should become readable by default, or remain
  explicit permission grants.
- Whether Mem0 should be exposed to PiWorker as a search/add tool in addition
  to the default packet provider boundary.
- How much backwards compatibility to keep for existing
  `summary_artifact_refs`.

## Architectural Summary

The upgraded system should feel like this:

```text
MissionForge runtime:
  stable authority prefix
  context budget allocator
  deterministic short/middle/long projection
  provider-neutral long-memory packet validation
  refs-only checkpoints
  pressure diagnostics
  safe-stop/resume

Default Mem0 adapter / equivalent provider:
  advisory search and memory packets
  source refs required
  no authority over contracts
  degraded mode if unavailable

PiWorker:
  understands the task
  decides what to read/search/write
  writes explicit artifacts and memory cards when useful

MissionForge evidence plane:
  raw refs
  source packets
  artifacts
  events
  savepoints
  hashes
  ledgers
```

This keeps the system useful for long-running work without making MissionForge
core a hidden semantic agent.
