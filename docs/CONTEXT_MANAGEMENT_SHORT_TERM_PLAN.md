# Context Management Short-Term Plan

## Goal

Build the smallest useful context-management feature branch without disturbing
MissionForge's current PiWorker runtime boundaries. The design should stay
minimal, orthogonal, and white-box.

The first implementation should prove one thing:

```text
large tool output can be preserved as raw refs while later model context sees a
deterministic projection instead of repeated low-density blobs.
```

This branch does not try to build a memory system, a semantic ranking system, or
a context budget system. It only establishes the raw evidence plane and the
active model context projection plane.

## Phase 1: Baseline Audit

Status: complete. The detailed ADR was removed during the kernel slimming
pass; the retained contract is the runtime observation/projection boundary
tested in the Pi agent runtime suite.

- Map current Pi runtime context flow:
  - `Agent` construction
  - `agent.state.messages`
  - `transformContext`
  - `EvidenceRecorder`
  - savepoints/resume
  - ToolGateway decisions
- Identify exactly where tool results enter `agent.state.messages`.
- Confirm current read/bash output behavior:
  - Pi tool truncation limits
  - bash temp full-output behavior
  - MissionForge evidence summaries
- Document the gap between evidence recording and model-context projection.

Exit condition:

- A short implementation note identifies the single best insertion point for
  ToolObservation capture and ContextProjector projection.

## Phase 2: ToolObservation Envelope

Status: implemented for runtime-side observation capture. Phase 3 projection is
also implemented in its minimal deterministic form.

- Add a minimal `ToolObservation` schema in the TS runtime.
- Capture tool result metadata:
  - `tool_call_id`
  - `tool_name`
  - status/error flag
  - size bytes/lines
  - content hash
  - raw/source refs
  - inline policy
- For file reads, prefer `source_ref` plus range/hash rather than duplicating the
  file.
- For bash output, write stdout/stderr or combined output into the MissionForge
  attempt artifact area before returning to the agent.
- Record observations in events/savepoints without embedding raw bodies.

Exit condition:

- Tests prove large bash/read output creates refs and does not leak raw bodies
  into durable operator state.
- Runtime output exposes the observation index ref as evidence while keeping
  raw context artifacts discoverable through that index.

## Phase 3: Deterministic ContextProjector

Status: minimal deterministic stubbing, configurable large-observation
thresholds, and refs-only projection diagnostics are implemented.

- Extend the existing `transformContext` path rather than adding a separate
  memory engine.
- Project old large tool results into deterministic stubs:
  - keep recent/current-turn output intact
  - demote older `demote_after_turn` outputs
  - render `ref_only` outputs as metadata plus preview
- Do not create semantic summaries in the projector.
- Make projector behavior configurable only where it directly affects
  deterministic projection. The first `ContextProjectionConfig` covers
  `large_observation_bytes`.
- Keep authority context untouched:
  - TaskContract
  - WorkerBrief
  - JudgeRubric
  - PermissionManifest
  - SandboxProfile
- Write a refs-only `context/projection.json` diagnostic artifact with counts,
  demoted observations, active observations, and warnings. Do not include raw
  tool-result bodies.

Exit condition:

- A test creates a large tool result, advances a turn, and verifies the next LLM
  context receives a stub with raw ref/hash instead of the full output.

## Phase 4: ContextSnapshot Tool

Status: minimal read-only `context_snapshot` tool is implemented.

- Add a read-only context inspection tool if it can be done without expanding
  core semantics.
- Return:
  - observation ids and tool metadata
  - active large observations
  - demoted observations
  - refs available for re-read
  - current permission status for each raw/source ref
- Do not allow this tool to mutate context in the first version.
- Do not return raw tool-result bodies, file bodies, provider payloads, or
  semantic summaries.

Exit condition:

- PiWorker can ask which large observations were demoted and which cited refs
  can be re-read under the current PermissionManifest.

## Phase 6: Runtime Pressure Boundary

Status: implemented as a Pi agent runtime boundary.

- `ContextProjectionConfig` now includes:
  - `large_observation_bytes`
  - `soft_compact_ratio` defaulting to `0.8`
  - `hard_compact_ratio` defaulting to `0.9`
  - `cache_aware`
- `context/projection.json` records provider-view diagnostics:
  estimated input tokens, model context window, pressure ratio, cache
  read/write tokens, projection strategy, and recommended action.
- At a completed-turn safe point, the runtime writes an explicit refs-only
  `missionforge.runtime_context_checkpoint.v1` artifact at
  `attempts/<call_id>/context/context_pressure_checkpoint.json` when pressure
  reaches the soft boundary.
- When pressure reaches the hard boundary, the runtime stops before the next
  provider request, marks the run `cancelled`, and recommends resume with the
  context checkpoint ref.

This phase remains deliberately non-semantic. The runtime estimates pressure,
records refs and hashes, writes savepoints, and routes on explicit diagnostics.
It does not decide what content matters, synthesize hidden memory, or weaken
permissions. Prompt cache economics are preserved by delaying projection until
the boundary requires it and by keeping dynamic context in refs/diagnostics
rather than rewriting stable authority prompts.

## Raw Ref Recovery Policy

- `source_ref` recovery uses the existing `read` tool and only succeeds when the
  current PermissionManifest permits that source ref.
- `raw_ref` values under `context/raw` are durable audit evidence by default;
  they are not automatically added to readable refs for the same worker or for a
  later Judge.
- If a product integration, contract, or repair flow needs raw evidence re-read,
  it must explicitly grant the relevant `context/raw` ref or directory in the
  role-specific PermissionManifest.
- `context_snapshot` may expose ref/hash/size metadata for a raw/source ref, but
  it only emits `read_args` when the current PermissionManifest allows the ref.
- Unreadable refs are reported with normalized denial reasons, not with raw
  contents, previews, provider payloads, or semantic summaries.

## Orthogonality Rules

- `ToolObservation` records evidence metadata; it does not decide importance.
- `ContextProjector` renders a provider-view copy; it does not mutate session
  truth, summarize content, or change permissions.
- `context_snapshot` is read-only inspection; it does not compact or recover
  content.
- `ContextSummaryArtifact` is an explicit PiWorker/Judge-authored semantic
  artifact schema. Runtime pressure handling writes refs-only context
  checkpoints instead; it must not contain raw tool output, prompts,
  transcripts, provider payloads, artifact bodies, or secrets.
- Context token/window budget enforcement is a runtime pressure boundary, not a
  semantic route or acceptance authority.

## Phase 5: Pi AgentSession Evaluation

Status: complete. See
`docs/CONTEXT_MANAGEMENT_PHASE5_AGENTSESSION_EVALUATION_ADR.md`.

Decision: do not migrate the production PiWorker runtime to Pi `AgentSession`
yet. Continue using low-level `Agent` and selectively borrow compaction/session
concepts.

- Separately evaluated whether MissionForge should move from low-level `Agent`
  usage to Pi `AgentSession` or `AgentHarness`.
- Confirmed migration should wait until MissionForge has explicit summary
  artifact schemas, a stronger resume/replay story, and a tested
  MissionForge ref/ledger mapping for Pi session entries.
- The evaluation covered:
  - current low-level runtime control
  - AgentSession compaction hooks
  - session tree compatibility
  - permission/sandbox integration cost
  - evidence refs and redaction guarantees

Exit condition:

- An ADR recommends staying on low-level `Agent` with selected Pi helpers and
  concepts.

## Guardrails

- Do not add product-specific semantics to `src/missionforge`.
- Do not introduce hidden memory or hidden prompt injection.
- Do not let code judge product-level meaning.
- Do not weaken sandbox/profile/manifest enforcement.
- Do not store raw prompts, transcripts, tool outputs, provider payloads, or
  secrets in operator-facing state by default.
- Keep changes narrow and testable.

## Implemented Test Coverage

- Large bash output is captured to raw ref.
- Large bash output is projected as a stub after the immediate follow-up turn.
- Small tool output remains inline.
- Read output for existing workspace files records source ref and range/hash.
- Demoted output exposes re-read args only for currently permitted refs.
- Denied refs cannot be exposed through observation metadata.
- Judge context projection does not include Worker-only hidden or unauthorized
  material.
- `ContextSummaryArtifact` schema validation requires observation ids,
  raw/source refs, hashes, producing role, and permission manifest refs while
  rejecting hidden raw bodies.
- Completed-turn resume envelopes can carry explicit context checkpoint refs
  without reading them automatically or changing permissions. Legacy semantic
  summary artifact refs remain accepted for compatibility.
- Projection diagnostics expose context pressure and cache read/write evidence.
- Hard context pressure stops at a completed-turn safe point and emits an
  explicit refs-only context checkpoint for resume.

## Remaining Test Candidates

- Full replay/hydration remains a later step beyond the current refs-only
  replay planning helper; explicit checkpoint refs and optional Pi-authored
  semantic summaries are the intended next layer.

## Open Questions

- Whether provider-specific token estimators should replace the current
  conservative chars-per-token runtime estimate.
- Whether raw refs should be scoped per branch/attempt to prevent cross-branch
  leakage.
- How to use Pi turn-boundary cut rules without adopting hidden Pi
  auto-compaction.
- How much of `pi-lean-ctx` should be optional integration versus copied
  concept.
- Whether `context/raw` should become readable to the same worker by default,
  or remain audit evidence unless a contract/manifest explicitly grants it.
