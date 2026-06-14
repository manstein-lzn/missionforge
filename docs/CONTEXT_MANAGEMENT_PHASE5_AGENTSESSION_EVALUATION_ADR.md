# ADR: Phase 5 Pi AgentSession and Compaction Evaluation

## Status

Accepted recommendation: do not migrate the production PiWorker runtime to Pi
`AgentSession` yet.

This evaluation is based on the local Pi packages used by the runtime:

- `@earendil-works/pi-agent-core@0.76.0`
- `@earendil-works/pi-ai@0.76.0`
- `@earendil-works/pi-coding-agent@0.76.0`

## Context

MissionForge currently uses the low-level Pi `Agent` directly. That gives the
runtime direct control over:

- runtime-owned system/user prompt construction
- `PermissionManifest` and sandbox-bound MissionForge tools
- `Agent.afterToolCall` observation capture
- `Agent.transformContext` deterministic projection
- refs-first `EvidenceRecorder`, savepoints, and output contracts

Pi `AgentSession` is a higher-level lifecycle abstraction. It manages session
persistence, model/settings state, tool registries, extension hooks,
auto-compaction, branch summaries, session switching, and runtime replacement.

The question for Phase 5 is whether MissionForge should move the production
runtime onto `AgentSession`, or keep the low-level `Agent` and selectively
borrow concepts.

## Findings

### Low-Level Agent Fit

`pi-agent-core` documents the exact hooks MissionForge needs:

- `afterToolCall` runs after tool execution and before `tool_execution_end` and
  final tool-result messages.
- `transformContext` runs before message conversion and provider calls.
- `shouldStopAfterTurn` can stop a run at a clean turn boundary.
- `prepareNextTurn` can update context/model/thinking before the next provider
  request.

These hooks match MissionForge's desired boundary: deterministic evidence
capture and projection without handing session ownership to Pi.

### AgentSession Capabilities

`AgentSession` adds useful infrastructure:

- JSONL session files with tree entries and session ids
- automatic persistence on message events
- session switching, import, fork, and branch navigation
- custom tools, base tool overrides, and tool-name allowlists
- manual and automatic compaction
- branch summarization
- extension event hooks around compaction and tree navigation
- context usage diagnostics

Those are useful patterns, but they are broader than the current
MissionForge sidecar responsibility.

### Compaction Semantics

Pi compaction is LLM summary based. It:

- chooses cut points around recent-token and turn-boundary rules
- summarizes older messages with a model call
- appends a `CompactionEntry` containing summary text, `firstKeptEntryId`,
  token counts, and optional file-tracking details
- reloads the session view from summary plus kept messages

That is a good UX/session mechanism, but it is not the same as MissionForge's
first-class evidence boundary. A Pi compaction summary is not automatically a
MissionForge semantic artifact because it does not inherently cite
`ToolObservation` refs, raw/source hashes, permission manifests, and role.

### Mismatches With MissionForge Core

`AgentSession` would bring several responsibilities MissionForge should not
adopt implicitly in this phase:

- Session persistence defaults to Pi's session model, not MissionForge attempt
  refs and ledgers.
- Built-in tool registries and extension hooks would need careful wrapping to
  preserve MissionForge `PermissionManifest`, sandbox, and evidence semantics.
- Auto-compaction creates LLM summaries as runtime state. MissionForge requires
  semantic summaries to be explicit artifacts with cited source refs.
- Session switching/fork/import is not aligned with a single frozen
  `PiWorkerCall` attempt.
- Settings, auth storage, model registry, prompt templates, skills, and
  extensions duplicate or bypass MissionForge's runtime input contract unless
  explicitly disabled or wrapped.
- `executeBash({ excludeFromContext: true })` can keep command output out of
  model context, but it does not create MissionForge raw refs,
  `ToolObservation` records, or adapter evidence by itself.

## Decision

Keep the production PiWorker runtime on low-level `Agent` for now.

Do not migrate to `AgentSession` until MissionForge has:

- an explicit semantic compaction artifact schema, if semantic compaction is
  needed
- a stronger resume/replay story for explicit compaction and summary artifacts
- a tested mapping from Pi session entries to MissionForge refs and ledgers
- a tool override strategy that proves Pi built-ins/extensions cannot bypass
  MissionForge permissions

## Reuse Now

Continue using:

- `Agent.afterToolCall` for `ToolObservation`
- `Agent.transformContext` for `ContextProjector`
- Pi read/bash truncation behavior as model-visible immediate output
- Pi bash `fullOutputPath` only as an input copied into MissionForge raw refs

## Borrow Next

Borrow these concepts without migrating:

- Turn-boundary cut rules from Pi compaction.
- Low-level `shouldStopAfterTurn` only if MissionForge later needs a boundary
  that the current `Agent.transformContext` provider-request hook cannot
  express.
- `prepareNextTurn` if projection needs to update the provider-view context
  before continuing a run.
- Session JSONL tree ideas for future MissionForge attempt replay, while
  keeping MissionForge refs as the authority.
- Context usage diagnostics, but rendered into `context/projection.json` or a
  future refs-only snapshot artifact.

## Avoid

Avoid these in MissionForge core:

- default Pi auto-compaction as hidden runtime memory
- background LLM summary synthesis without explicit source refs
- default Pi session storage as MissionForge task authority
- product-specific compaction or ranking rules
- built-in Pi tools that bypass MissionForge `ToolGateway`

## Future Migration Conditions

Reconsider `AgentSession` only if a spike proves all of the following:

1. Session persistence can be rooted under `attempts/<call_id>/` or exported as
   refs-only MissionForge artifacts.
2. All built-in tools are disabled or replaced with MissionForge gateway tools.
3. `afterToolCall` and `transformContext` remain enforceable under the session
   wrapper.
4. Auto-compaction is disabled by default, or replaced with explicit
   MissionForge artifact production.
5. Judge and executor roles receive separate session/projection boundaries.
6. Adapter output still cites refs and hashes instead of raw prompts,
   transcripts, provider payloads, or raw tool bodies.

## Recommended Next Implementation Work

The next implementation should stay on low-level `Agent` and add one runtime
primitive at a time. The current context-management branch deliberately keeps
token/window budget enforcement out of scope and focuses on raw refs,
deterministic projection, and permission-bounded inspection.

1. Extend `ContextProjectionConfig` only with deterministic runtime thresholds
   that are needed by tests or observed runs.
2. Use `ContextSummaryArtifact` when PiWorker/Judge-authored semantic summaries
   are needed. The schema stays separate from runtime projection and must cite
   `ToolObservation` ids, raw/source refs, hashes, producing role, and
   permission manifest ref.
3. Keep completed-turn resume refs-only. Full replay/hydration from explicit
   compaction or summary artifact savepoints should be added only when a
   concrete workflow needs it.
4. Revisit lower-level Pi loop hooks only if the `transformContext` boundary is
   too coarse for a concrete runtime requirement.

This keeps MissionForge's context boundary inspectable and product-neutral.
