# ADR: Context Management Phase 1 Baseline

## Status

Accepted baseline for context-management insertion points.

Phase 2 `ToolObservation` capture is implemented in the Pi runtime sidecar.
Phase 3 minimal `ContextProjector` stubbing and refs-only projection diagnostics
are implemented for stale large tool results.
Phase 4-lite read-only `context_snapshot` tooling is implemented for
observation, projection, ref, and permission inspection.

## Decision Summary

MissionForge should keep the current low-level `Agent` integration for the
first context-management implementation.

The first insertion points are:

- Capture `ToolObservation` in `Agent.afterToolCall`, before
  `tool_execution_end` and before the final `toolResult` message is emitted.
- Store bash raw output and read source metadata under the existing attempt
  directory as refs plus hashes.
- Implement `ContextProjector` by extending the existing `transformContext`
  path, composed with the current `stripUnreplayableResponsesReasoning`
  transform.
- Keep `EvidenceRecorder` focused on refs-first operator evidence and metrics.
  It should record observation refs and summaries, not raw bodies.

Do not migrate to Pi `AgentSession`, add semantic memory, or introduce LLM
summary compaction in this phase.

## Implementation Status

Implemented in Phase 2:

- TS runtime input/output schemas carry `context_observations_ref`,
  `context_projection_ref`, and `context_raw_dir_ref`.
- `Agent.afterToolCall` captures a metadata-only `ToolObservation` record for
  each completed tool call.
- Large bash output is copied into the MissionForge attempt raw evidence area
  when Pi exposes a safe `fullOutputPath`; otherwise large inline bash text is
  written to a raw ref.
- Read observations prefer `source_ref`, requested range, source hash, and
  source size instead of duplicating file bodies.
- Runtime events and savepoints cite the observation index ref without
  embedding raw tool output bodies.
- Python adapter reports the observation index as verifier evidence and enforces
  the sidecar-assigned observation ref.

Implemented in Phase 3:

- Runtime `transformContext` composes the existing OpenAI Responses reasoning
  cleanup with a deterministic `ContextProjector`.
- `demote_after_turn` tool results remain fully visible for the immediate
  follow-up provider request, then become metadata-only stubs in later model
  context.
- Projection stubs cite observation id, tool id/name, status, inline policy,
  hash, size, raw/source refs, and range metadata when present.
- Projection returns a provider-view copy and does not mutate
  `agent.state.messages` or write semantic summaries.
- Projection writes a refs-only diagnostic artifact at `context_projection_ref`
  with active/demoted observation metadata and warnings. The Python adapter
  validates and surfaces the same ref, and writes an empty fallback diagnostic
  only when the sidecar did not emit one.

Implemented in Phase 4-lite:

- Runtime tools include a read-only `context_snapshot` tool.
- The tool returns observation ids, tool metadata, inline policy, projection
  state, raw/source refs, hashes, sizes, ranges, and current read permission
  status.
- For readable refs, the tool returns deterministic `read_args`; for unreadable
  refs, it returns a normalized denial reason.
- The tool does not return raw tool-result bodies, file bodies, provider
  payloads, semantic summaries, or mutate runtime state.

Not implemented yet:

- Default same-worker readability for `context/raw` refs.
- Semantic summaries or memory artifacts.

## Implemented Context Flow

The Python adapter in `src/missionforge/adapters/pi_agent_runtime.py` builds a
`PiAgentRuntimeInput`, writes runtime-owned refs under `attempts/<call_id>/`,
invokes the TS sidecar, then normalizes the sidecar output into
`ExecutionReport` evidence refs and metrics. The runtime-owned refs now include
`context/tool_observations.jsonl`, `context/projection.json`, and the
`context/raw` directory.

The TS runtime in `workers/pi-agent-runtime/src/runtime.ts` constructs:

- a system prompt from `RuntimeInput`, `TaskContract`-derived refs, permission
  refs, expected outputs, and role-specific repair or resume refs
- a user prompt that names visible refs but does not inline their bodies
- MissionForge tools from `createMissionForgeTools`, including read-only
  `context_snapshot`
- a `ToolObservationRecorder` and deterministic `ContextProjector`
- a low-level Pi `Agent` whose `transformContext` composes
  `stripUnreplayableResponsesReasoning` with `ContextProjector.project`

The tool path is:

1. `createMissionForgeTools` creates Pi `read`, `edit`, `write`, and optional
   `bash` tools.
2. `ToolGateway` authorizes paths, commands, cwd, and env before operation.
   It records permission decisions but does not see complete tool results.
3. Pi `agent-loop` emits `tool_execution_start`.
4. The Pi tool executes and returns a result containing `content` and
   optional `details`.
5. MissionForge `Agent.afterToolCall` records a `ToolObservation`, copies large
   bash output into `context/raw` when available, records read `source_ref`
   metadata when permitted, and appends a refs-only runtime event.
6. Pi emits `tool_execution_end`.
7. Pi creates the final `toolResult` message from the result.
8. `Agent.processEvents` appends the final message to `agent.state.messages`
   on `message_end`.
9. The next model call runs the composed `transformContext` over
   `agent.state.messages`; stale large observations are rendered as
   metadata-only projection stubs before messages are sent to the provider.

`EvidenceRecorder` subscribes to Agent events. It records metrics, redacted
event summaries, redacted session summaries, and savepoints. It intentionally
does not serialize raw prompts, raw provider payloads, full artifact bodies, or
full tool-result bodies into operator-facing state.

Current Pi tool behavior:

- `read` returns text content truncated from the head to 2000 lines or 50KB.
  It includes continuation hints for large files. It does not return a
  MissionForge source ref or source hash.
- `bash` returns combined stdout/stderr truncated from the tail to 2000 lines
  or 50KB. When output is truncated, Pi persists full output to a temp file
  outside the MissionForge artifact plane and returns that temp path in
  `details.fullOutputPath`.
- Both results remain in `agent.state.messages` until the runtime ends.

Resume currently works as a follow-up prompt that cites savepoint/session/event
refs. It does not hydrate prior `agent.state.messages` from a savepoint.

The direct benchmark runner mirrors the same low-level Agent shape. It should
be kept out of the first production runtime change unless parity is explicitly
needed.

## Baseline Gaps Addressed By Phases 2-4

At the Phase 1 baseline there was no durable raw evidence plane for tool
results.

- Bash full output may exist only as a Pi temp file, not a MissionForge ref.
- Read output does not record `source_ref`, range, source hash, or source size.
- ToolGateway decisions prove permission checks, but they are not result
  observations and they are not keyed to raw output hashes.

At the Phase 1 baseline there was no active context projection boundary.

- `transformContext` only strips OpenAI Responses reasoning blocks.
- Large tool outputs stored in `agent.state.messages` are still candidates for
  every later provider request.
- Evidence redaction protects operator artifacts but does not change model
  context.
- There was no inline policy such as `keep`, `demote_after_turn`, or `ref_only`.
- There was no context snapshot or deterministic projection report.

At the Phase 1 baseline there was no durable observation index.

- Savepoints do not cite observation counts or observation refs.
- Runtime output does not expose a context-observation index ref.
- Downstream judge/repair nodes cannot audit which raw refs backed projected
  tool-result stubs.

## Minimal First Implementation Scope

Phase 2 should add observation capture only.

1. Add a `ToolObservationRecorder` in the TS sidecar.
2. Configure `Agent.afterToolCall` in `runMissionForgePiAgent`.
3. For every finalized tool result, write one `ToolObservation` JSONL record.
4. For bash results:
   - copy Pi `details.fullOutputPath` into the attempt raw evidence directory
     when present
   - otherwise write the result text to a raw ref when it crosses the raw
     capture threshold
   - record combined-output hash, size, line count, exit/error status, raw ref,
     and inline policy
5. For read results:
   - prefer `source_ref` plus requested range, source hash, and source size
   - fall back to a raw ref only when a stable permitted source ref cannot be
     derived or the result is not file text
6. Record an event summary that cites the observation id and ref/hash only.
7. Keep small tool results inline. Do not change model-visible behavior until
   Phase 3 except for explicit `ref_only` cases if they are configured.

Phase 3 should add deterministic projection.

1. Replace the current transform with a composed context transform:
   `ContextProjector.project(stripUnreplayableResponsesReasoning(messages))`.
2. Match `toolResult` messages by `toolCallId`.
3. Preserve authority context and recent/current-turn messages.
4. Replace stale large tool results with deterministic stubs containing:
   observation id, tool name, status, hash, size, raw/source ref, range if any,
   and a bounded preview if policy permits.
5. Do not write semantic summaries in the projector.
6. Do not mutate `agent.state.messages`; projection returns a model-view copy.
7. Define `demote_after_turn` precisely as: keep the full tool result visible
   through the immediate follow-up provider request that can use it, then stub
   it for later provider requests.

Keep the first projector focused on large-observation thresholds and
deterministic stubs. Token/window budget enforcement is out of scope until the
raw evidence and projection boundary is stable and a concrete runtime need
justifies it.

## Schemas To Add

TS sidecar schemas:

- `missionforge.pi_agent_tool_observation.v1`
  - `observation_id`
  - `call_id`
  - `turn_index`
  - `tool_call_id`
  - `tool_name`
  - `status`: `ok` or `error`
  - `created_at`
  - `content_hash`
  - `content_bytes`
  - `content_lines`
  - `raw_ref` for copied raw output, if any
  - `source_ref` for workspace source files, if any
  - `source_range` with line offset/limit when known
  - `source_hash` when `source_ref` is used
  - `inline_policy`: `keep`, `demote_after_turn`, or `ref_only`
  - `preview` with bounded text only when permitted
  - `projection_note` for deterministic stub text
- `missionforge.pi_agent_context_projection.v1`
  - diagnostic record for demoted observations, active observations, projected
    refs, and warnings
- `missionforge.pi_agent_context_snapshot.v1`
  - read-only tool response with observation ids, projection state, raw/source
    refs, hashes, sizes, ranges, and permission-aware re-read status
- `ContextProjectionConfig`
  - numeric thresholds for keep/demote/ref-only behavior

Python adapter/runtime schemas:

- Add refs generated by `_pi_agent_refs`:
  - `context_observations`: `attempts/<call_id>/context/tool_observations.jsonl`
  - `context_raw_dir`: `attempts/<call_id>/context/raw`
  - `context_projection`: `attempts/<call_id>/context/projection.json`
- Add top-level optional fields to `PiAgentRuntimeInput` and the TS
  `RuntimeInput` parser for the observation index and raw directory refs.
- Add `context_observations_ref` and `context_projection_ref` to
  `PiAgentRunResult` / TS `RuntimeOutput` so the adapter can surface the
  context index and projection diagnostics as verifier evidence without
  listing every raw artifact body.
- Keep raw refs discoverable through the observation index rather than adding a
  large raw-ref array to operator-facing output.

These schemas remain product-neutral and role-neutral.

## Tests To Add

TS sidecar tests:

- Large bash output writes a MissionForge raw ref and an observation record.
- Bash output copied from Pi `fullOutputPath` does not leave only a temp path.
- Small tool output remains inline and records `inline_policy: keep`.
- Read output for a permitted workspace file records `source_ref`,
  `source_range`, and `source_hash`.
- Projection keeps a large `demote_after_turn` result for the immediate
  follow-up provider request and stubs it after the turn boundary.
- Projection stubs include ref/hash/size metadata but not the raw body.
- Denied read/bash attempts do not expose unauthorized refs in observation
  metadata.
- `context_snapshot` exposes re-read args only for currently permitted refs and
  does not include raw bodies.
- Existing redaction tests still prove events/session/metrics do not contain
  raw bodies or secrets.

Python tests:

- `_pi_agent_refs` and `PiAgentRuntimeInput` include context observation,
  projection, and raw-dir refs under the attempt directory.
- `PiAgentRunResult` accepts and validates `context_observations_ref` and
  `context_projection_ref`.
- Adapter evidence refs include the observation index and projection diagnostic
  refs but not raw bodies.
- Judge/runtime role separation still prevents worker-only or unauthorized
  refs from entering judge context projections.

## Raw Ref Recovery Decision

`raw_ref` recovery is permission-gated, not automatic.

- `source_ref` and `raw_ref` values are metadata until the current
  PermissionManifest authorizes a re-read.
- `context_snapshot` emits deterministic `read_args` only for readable refs.
- `context/raw` remains audit evidence by default, even for the worker that
  produced it.
- A product integration, repair flow, or judge packet must explicitly grant
  `context/raw` refs when raw evidence re-read is required.
- Judge calls must not inherit executor-only raw refs unless those refs are
  intentionally included in the judge role's PermissionManifest.

## Pi Ecosystem Use

Reuse now:

- Low-level `Agent.afterToolCall` for observation capture.
- Low-level `Agent.transformContext` for deterministic projection.
- Existing Pi read/bash truncation behavior as the first-pass model-visible
  output.
- Pi bash `details.fullOutputPath` as an input to copy into MissionForge raw
  evidence, not as durable evidence itself.

Borrow concepts:

- Pi compaction token-estimation helpers and recent-turn preservation rules.
- Pi content offload patterns: hash, bounded preview, and reversible ref.
- Pi context inspection ideas for the read-only `context_snapshot` tool.

Avoid in MissionForge core:

- Pi `AgentSession` migration before Phase 2-4 prove the MissionForge evidence
  and permission boundary.
- Pi automatic LLM compaction summaries as hidden runtime memory.
- RPC `excludeFromContext` as the primary answer, because it hides output from
  context without creating MissionForge raw refs and observation records.
- Any product-specific semantic ranking, memory synthesis, or acceptance logic.

## Risks Deferred

- Projection may reduce provider prefix-cache efficiency because older messages
  are rendered differently after demotion.
- Exact `read` source-ref capture can be ambiguous if only `afterToolCall` sees
  raw args. If deterministic path reconstruction is not enough, wrap the read
  tool execute path so the authorized source ref is captured with `toolCallId`.
- Pi bash combines stdout and stderr. Split-stream evidence would require a
  deeper `BashOperations` wrapper and is not required for the first version.
- Raw refs may contain secrets legitimately visible to the worker. Operator
  state must cite refs/hashes and remain redacted by default.
- `context/raw` refs are not automatically made readable to the same worker;
  product contracts or permission manifests must decide when raw evidence can
  be re-read.
- Image/binary read observations need a separate policy and are out of scope
  for the first text-focused implementation.
- Resume currently cites previous session/savepoint refs but does not reload
  prior messages. Context projection does not solve resume hydration by itself.
- Token/window fail-closed behavior is intentionally deferred; the current
  branch does not need it to prove the raw evidence/projection boundary.
- Direct benchmark runtime parity is useful but not required for the production
  PiWorker context boundary.
