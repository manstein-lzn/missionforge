# MissionForge Architecture

MissionForge is a generic mission execution substrate. It accepts a structured
Mission IR, expands it through reusable capability profiles, freezes a verified
mission contract, and drives a fixed adaptive loop until the mission reaches
verified closure, review, redesign, stop, escalation, or failure.

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

MissionForge has five planes.

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

Profiles expand domain or capability concepts into mission primitives before
freeze. Runtime decisions use expanded constraints and validators, not task
names or profile-name branches.

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

### 4. Worker Plane

MissionForge is PiWorker-first and PiWorker-only for the first formal design
cycle. This is a deliberate constraint, not an accident.

The worker plane is inspired by the PI GitHub project runtime model and by the
PiWorker integration lessons from SkillFoundry. PI is MIT-licensed; MissionForge
must preserve attribution if PI code is copied or adapted in the future.

Other worker abstractions can be discussed after the PiWorker contract is
stable. Until then, "worker adapter" means PiWorker adapter.

PiWorker consumes a bounded work-unit contract derived from Mission IR and
returns refs-only execution evidence.

### 5. Adaptive Plane

The adaptive loop is fixed:

```text
validate mission
resolve profiles
expand mission
freeze contract
propose work unit
execute worker
collect observation
verify evidence
route: complete | continue | repair | redesign | review | stop | escalate | fail
emit result
```

Routing is based on structured verification and failed constraint IDs, not
string matching over logs.

## Optional Hosts

LangGraph, CLIs, services, notebooks, or another agent framework may call
MissionForge. The core runtime must remain host-independent.

The intended host adapter shape is:

```text
host state -> MissionIR -> MissionRuntime -> MissionResult -> host state
```

## Core Rule

MissionForge core code must not special-case named missions. Domain complexity
belongs in Mission IR, ProfileSpec data, validator data, evidence data, and
generated artifacts.

Worker self-report is never acceptance. Completion must come from a locked
FrozenMissionContract, EvidenceLedger records, and VerificationResult.

## Documentation Rule

MissionForge follows a docs-first, docs-last discipline:

- every module starts with a module document under `docs/modules/`
- implementation should cite the module document it is satisfying
- after behavior changes, the module document must be updated before the work is
  considered complete
- module documents track goal, scope, current status, open questions, invariants,
  and verification evidence
