# ADR: Context Management Phase 2-4 Runtime Boundary

## Status

Accepted milestone for the `feature/context-management-primitives` branch.

This ADR records the first implemented context-management boundary after the
Phase 1 audit. It is intentionally narrow: raw evidence capture, deterministic
projection, and refs-only inspection. It does not add semantic memory, hidden
LLM compaction, or a context budget system.

## Decision

MissionForge now treats tool-result context as two separate planes:

- Raw evidence plane: durable refs, hashes, sizes, and observation records.
- Active model context plane: deterministic provider-view projection rendered
  by the TS runtime before each model request.

The boundary is implemented inside the Pi runtime sidecar, not in product
integrations and not in deterministic product-semantic code.

## Implemented Scope

### ToolObservation

`ToolObservationRecorder` records one metadata envelope per finalized tool call
from `Agent.afterToolCall`.

The record includes:

- call id, turn index, tool call id, tool name, and status
- content hash, byte count, and line count
- inline policy: `keep`, `demote_after_turn`, or `ref_only`
- `raw_ref` for copied bash/full-output evidence when available
- `source_ref`, source range, source hash, and source size for permitted read
  observations

Large bash/read outputs, including large bash/read error outputs, use
`demote_after_turn`. Small outputs stay inline.

### Raw Evidence Refs

Large bash output is copied into:

```text
attempts/<call_id>/context/raw/
```

The raw directory is not listed as a produced artifact and is not automatically
added to readable refs. Raw refs are discoverable through
`context/tool_observations.jsonl`.

Read observations prefer source refs and source hashes. They do not duplicate
file bodies into `context/raw` when a permitted source ref is available.

### ContextProjector

`ContextProjector` is composed through the existing low-level Pi
`transformContext` hook:

```text
stripUnreplayableResponsesReasoning(messages)
  -> ContextProjector.project(messages)
```

Projection does not mutate `agent.state.messages`. It returns a provider-view
copy where stale `demote_after_turn` tool results become deterministic stubs.

Projection stubs include observation id, tool id/name, status, inline policy,
hash, size, raw/source refs, and range metadata. They do not include raw bodies
or semantic summaries.

The current demotion rule is:

```text
keep the full result through the immediate follow-up provider request;
stub it in later provider requests.
```

### ContextProjectionConfig

The runtime input carries:

```text
missionforge.pi_agent_context_projection_config.v1
```

The first config is intentionally numeric and deterministic:

- `large_observation_bytes`: controls when bash/read output is treated as a
  large observation and demoted after the immediate follow-up turn

Token/window budget thresholds and overflow stop behavior are intentionally not
part of this milestone. Projection diagnostics stay focused on refs, counts,
and observation state.

### Projection Diagnostics

Each run writes:

```text
attempts/<call_id>/context/projection.json
```

The projection diagnostic contains counts, configured large-observation
thresholds, projected observation metadata, active observation metadata, and
warnings. It is refs-only and body-free.

The Python adapter also writes a minimal fallback diagnostic if the sidecar
fails before producing one.

### ContextSnapshot

The runtime exposes a read-only `context_snapshot` tool.

It returns:

- observation ids and tool metadata
- projection state
- raw/source refs, hashes, sizes, and ranges
- current read permission status
- deterministic `read_args` only when the current `PermissionManifest` permits
  the ref

It does not return raw tool output, file bodies, provider payloads, semantic
summaries, or mutate runtime state.

### Python Adapter Contract

`PiAgentRuntimeInput` and `PiAgentRunResult` now carry:

- `context_observations_ref`
- `context_projection_ref`
- `context_raw_dir_ref` on input only

The adapter enforces that sidecar-owned context refs match runtime-owned refs,
surfaces the observation index and projection diagnostic as verifier evidence,
and keeps raw evidence behind the observation index.

## Explicit Non-Scope

These are intentionally not implemented in this milestone:

- semantic memory
- hidden prompt injection
- hidden LLM summary compaction
- token-window budget enforcement or overflow fail-closed behavior
- default same-worker or judge readability for `context/raw`
- product-specific importance ranking
- Pi `AgentSession` migration
- direct benchmark runtime parity
- binary/image raw evidence policy

## Permission Rule

`raw_ref` and `source_ref` are metadata until the current role-specific
`PermissionManifest` authorizes a read.

Executor raw refs are not inherited by Judge calls. A product integration,
repair flow, or judge packet must explicitly grant the raw ref or directory if
raw evidence re-read is required.

## Tests

The implemented boundary is covered by tests for:

- large bash output raw-ref capture
- bash `fullOutputPath` copy into MissionForge refs
- large bash error demotion
- read source ref/range/hash capture
- unauthorized read metadata not exposing source/raw refs
- stale large output projection into stubs
- projection diagnostics without raw bodies
- configured large-observation thresholds
- `context_snapshot` readable/unreadable refs
- Judge manifest not inheriting executor raw refs
- Python adapter context refs in input/output/report evidence
- runtime output filtering raw context artifacts from `changed_refs`

## Acceptance Criteria

This milestone is complete when:

- every PiWorker run has stable context observation and projection refs
- large bash/read results can be preserved as raw refs or source refs
- later model context sees deterministic stubs instead of repeated large bodies
- operator-facing state remains refs-first and redacted
- role-specific permissions continue to govern re-read access
- the runtime remains white-box and does not synthesize hidden memory

Those conditions are met by the current implementation.
