# MissionForge Context Management Target

## Purpose

MissionForge should treat context management as a first-class runtime boundary.
The goal is not to make deterministic code decide what information is
semantically important. The goal is to keep every PiWorker call supplied with a
high-density, auditable, permission-bounded context while preserving raw evidence
as refs.

The model is a stateless function. Agent continuity is created by explicit
runtime projection from contracts, visible refs, observations, artifacts, and
role-specific permissions. MissionForge must own that assembly boundary without
inventing hidden memory.

This system is deliberately minimal and orthogonal:

- Evidence capture records what happened.
- Projection renders what the model may see now.
- Permission manifests decide what may be re-read.
- Semantic interpretation belongs to PiWorkers and explicit artifacts.

## Target Shape

```text
Frozen TaskContract
  + WorkerBrief / JudgeRubric
  + WorkspacePolicy / PermissionManifest / SandboxProfile
  + visible refs
  + ContextProjector view
  -> PiWorker call
  -> ToolObservation refs + artifacts
  -> session/events/metrics/savepoints
  -> Judge / repair / revision flow
```

## Core Principles

- Raw chat is not operational truth. Frozen contracts and explicit revisions
  remain the durable authority.
- Raw evidence and active model context are separate planes.
- Large tool output may be temporarily visible, but it must not silently become
  permanent working context.
- Deterministic code controls refs, permission, visibility, and projection.
  PiWorkers own semantic interpretation.
- Semantic summaries are explicit artifacts, not hidden runtime mutations.
- Runtime state remains refs-first and redacted by default.
- Any context feature that injects hidden product semantics into core is out of
  bounds.
- Context management is not a budget system. Token/window controls may be added
  later only as a separate runtime policy when there is a concrete need.

## Pi Ecosystem Position

MissionForge should stand on Pi's context infrastructure, not rebuild it from
scratch.

Reuse or study:

- Pi `AgentSession` session tree, compaction triggers, and event hooks.
- Pi native compaction cut rules and explicit recovery mechanics.
- `pi-lean-ctx` for deterministic stubbing and reversible context reduction
  concepts.
- `pi-content-offloader` for offload/hash/preview patterns.
- `pi-context-tools` for model-visible context inspection and explicit compact
  controls.

Avoid in MissionForge core:

- Background LLM memory synthesis.
- Hidden memory-policy or hidden prompt injection.
- Product-specific semantic memory.
- Probabilistic state mutation that cannot be traced to refs and artifacts.

## Minimal Primitives

### ToolObservation

A structured record for every tool result that crosses the ToolGateway.

Required intent:

- preserve raw evidence as `raw_ref` or `source_ref`
- record size, hash, tool name, call id, status, and visibility policy
- define how much content can enter the active context

Initial policies:

- `keep`: small/high-signal output can remain inline
- `demote_after_turn`: visible in the current turn, projected as a stub later
- `ref_only`: raw output is stored, active context receives only metadata and a
  preview

These policies are visibility mechanics, not semantic importance rankings.

### ContextProjector

A deterministic view renderer that turns durable session state plus
ToolObservations into the message list sent to the model.

It should not judge semantics. It should:

- preserve contract and permission authority
- replace stale large tool outputs with refs/stubs
- keep recent turns intact unless deterministic projection policy says a tool
  result should be stubbed
- request explicit compaction or summary artifacts rather than synthesizing
  hidden memory

It should not:

- score importance
- summarize content
- change permissions
- decide product meaning

### ContextSnapshot

A refs-first diagnostic artifact or tool response that exposes current
projection state:

- large active observations
- projected refs
- demoted observation metadata
- current read permission status for cited refs

### ContextSummaryArtifact

An optional semantic artifact written by a PiWorker or Judge when a workflow
needs durable working knowledge derived from raw evidence.

It must cite source refs, observation ids, hashes, producing role, and relevant
permission manifest refs. It stays separate from runtime authority.

## Success Criteria

- A PiWorker can inspect and process large files or logs without permanently
  poisoning subsequent context.
- Raw tool output remains recoverable through refs.
- The active prompt stays high-density and auditable.
- MissionForge core remains product-neutral.
- Worker and Judge receive role-specific context projections.
- No hidden semantic memory enters core.
- Existing permission and sandbox guarantees continue to fail closed.

## Non-Goals

- Building a general-purpose memory database.
- Automatically deciding product-level meaning in deterministic code.
- Replacing Pi's agent loop with a new MissionForge agent engine.
- Adding a provider zoo or multi-agent registry.
- Optimizing every token before the raw evidence and projection model is stable.
- Making `context/raw` automatically readable without an explicit manifest
  grant.
