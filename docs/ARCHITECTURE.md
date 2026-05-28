# MissionForge Architecture

MissionForge is a generic mission execution substrate. It accepts a structured
Mission IR, expands it through reusable capability and verification profiles,
freezes a verified mission contract, and drives a fixed adaptive loop until the
mission reaches verified closure, review, redesign, stop, escalation, or
failure.

The architecture is informed by SkillFoundry's adaptive steering lessons and
MetaLoop's lightweight control protocol. MissionForge should absorb their
stable control primitives without becoming a SkillFoundry rewrite or a
MetaLoop runtime clone.

## Product Boundary

MissionForge is not:

- a skill generator
- a LangGraph framework
- a prompt template collection
- a benchmark-specific harness
- a direct port of SkillFoundry internals

MissionForge is:

- a Mission IR runtime
- an evidence-first worker harness
- an adaptive verifier/repair loop
- a contract-freezing and verification substrate
- a reusable node that other orchestrators may call

## Planes

MissionForge has six planes.

### 1. Mission Plane

The Mission IR is the canonical task truth at authoring time. It contains
objective, environment, contract, capabilities, evidence, verification rules,
adaptation policy, budget, and observability requirements.

Chat history is not task truth. FrontDesk-like systems may compile chat into
Mission IR, but the runtime consumes the IR.

Mission Plane objects are layered:

```text
MissionIR -> ExpandedMission -> FrozenMissionContract -> MissionRun
```

Profiles expand domain, capability, and verification-language concepts into
mission primitives before freeze. Runtime decisions use expanded constraints,
validators, evidence requirements, and authority rules, not task names or
profile-name branches.

### 2. Context Plane

The context plane carries the ContextForge lessons:

- frozen mission contract
- evidence refs
- source provenance
- raw input exclusion boundaries
- contract manifest
- verification gate
- ledger and checkpoint refs

The context plane must be durable and inspectable.

### 3. Harness Plane

The harness plane carries the ForgeUnit lessons:

- attempt input manifest
- work-unit contract
- worker invocation record
- execution report
- command/tool boundary
- metrics and timing
- output artifact refs

The harness plane does not understand product-specific mission semantics.

### 4. Controlled Steering Plane

The controlled steering plane carries the SkillFoundry controlled LLM steering
direction and the MetaLoop control-point discipline:

```text
LLM proposes.
Harness validates boundaries.
Runtime commits state.
Verifier proves facts.
Reviewer arbitrates quality and authority.
```

This plane owns proposal and control vocabulary:

- steering proposals
- observation signals
- contract adjustment requests
- state corrections
- decision ledger entries
- reviewer decisions
- explicit control requests
- safe-point checks

LLM-backed components may propose, interpret, or review. They may not mutate a
frozen contract, commit runtime state, expand authority, verify truth, or close
a mission. Default runtime behavior must remain deterministic/offline until the
proposal protocol is testable without live model calls.

### 5. Worker Plane

MissionForge is PiWorker-first and PiWorker-only for the first formal design
cycle. This is a deliberate constraint, not an accident.

The worker plane is inspired by the PI GitHub project runtime model and by the
PiWorker integration lessons from SkillFoundry. PI is MIT-licensed; MissionForge
must preserve attribution if PI code is copied or adapted in the future.

Other worker abstractions can be discussed after the PiWorker contract is
stable. Until then, "worker adapter" means PiWorker adapter.

PiWorker consumes a bounded work-unit contract derived from Mission IR and
returns refs-only execution evidence.

### 6. Adaptive Plane

The adaptive loop is fixed:

```text
validate mission
resolve profiles
expand mission
freeze contract
estimate state
propose or select work unit
validate proposal and authority
commit work unit
execute worker
collect observation
verify evidence
record state correction
route: complete | continue | repair | redesign | review | stop | escalate | fail
emit result
```

Routing is based on structured verification and failed constraint IDs, not
string matching over logs. LLM interpretation can become an observation signal,
but it is never accepted as fact without evidence and verifier support.

The Phase 5 vertical slice implements the first deterministic version of this
loop with a frozen contract ref, deterministic proposal, validated work unit,
fake worker artifact, evidence ledger, and verifier-routed `MissionResult`.
The fake worker records artifacts and execution reports only; completion still
comes from `VerificationResult.status`.

## Optional Hosts

LangGraph, CLIs, services, notebooks, or another agent framework may call
MissionForge. The core runtime must remain host-independent.

The intended host adapter shape is:

```text
host state -> MissionIR -> MissionRuntime -> MissionResult -> host state
```

## Core Rule

MissionForge core code must not special-case named missions. Domain complexity
belongs in Mission IR, capability profile data, verification profile data,
validator data, evidence data, and generated artifacts.

Worker self-report is never acceptance. Completion must come from a locked
FrozenMissionContract, EvidenceLedger records, and VerificationResult.

LLM self-report is also never acceptance. LLM output is proposal, hypothesis, or
review evidence according to its recorded trust level and authority boundary.

## Documentation Rule

MissionForge follows a docs-first, docs-last discipline:

- every module starts with a module document under `docs/modules/`
- implementation should cite the module document it is satisfying
- after behavior changes, the module document must be updated before the work is
  considered complete
- module documents track goal, scope, current status, open questions, invariants,
  and verification evidence
