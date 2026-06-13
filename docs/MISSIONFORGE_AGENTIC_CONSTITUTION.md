# MissionForge Agentic Constitution

Last updated: 2026-06-13

Status: guiding constitution for the simplified PiWorker-centered system shape.

## Document Role

This document preserves the durable philosophy from the earlier MissionForge,
SkillFoundry, controlled-steering, and MetaLoop-inspired design work while
redirecting implementation toward a smaller, harder, PiWorker-centered system.

The goal is not to discard the old architecture. The goal is to keep the
general laws and remove the accidental weight: deterministic code should not
try to understand arbitrary products, user pain, semantic completion, or repair
strategy through expanding Python branches.

MissionForge should become a thin but hard substrate around intelligent agents:

```text
LLM owns meaning.
Code owns boundaries.
Contract owns obligation.
Workspace owns artifacts.
Ledger owns memory.
Judge owns acceptance.
Product Integration owns domain.
MissionForge core owns no product semantics.
```

## Why This Constitution Exists

The value-benchmark work showed an important boundary: giving PiWorker raw
MissionIR as a direct prompt did not prove faster, cheaper, or more reliable
than a well-structured brief under the same final acceptance pressure.

That does not make contracts useless. It changes where the value is.

MissionForge's value is not prompt compression. MissionForge's value is the
stable work system around the prompt:

- requirements are separated from casual conversation;
- domain contracts are explicit;
- workspaces and permissions are bounded by hard rules;
- execution and judgment roles are separated;
- artifacts, decisions, revisions, and costs are inspectable;
- repair does not silently weaken the job;
- products can integrate without modifying MissionForge core.

## Preserved Principles

The following principles from the older documents remain constitutional.

### Product-Neutral Core

MissionForge core must not special-case named tasks, products, customers,
benchmarks, or domains.

Product complexity belongs in:

- Product Integration packages;
- ProductInquiryProfile data;
- TaskContract fields;
- WorkerBrief projections;
- JudgeRubric projections;
- PermissionManifest and WorkspacePolicy data;
- product-provided artifacts and fixtures;
- product-level tests and gates.

If a change adds product behavior to `src/missionforge`, it should be rejected
or moved to an integration.

### FrontDesk Is Real Intelligence

FrontDesk is not a form parser. It is the high-intelligence
requirements-discovery and intent-authoring surface.

FrontDesk may:

- talk to the user in natural language;
- push beyond surface statements;
- infer likely hidden needs;
- ask focused follow-up questions;
- organize pain, constraints, users, non-goals, risks, and desired outcomes;
- fill product inquiry slots when a ProductInquiryProfile is present;
- produce a FrontDeskIntentBundle for Product Integration.

FrontDesk code may collect turns, persist state, validate schemas, preserve
refs, and fail closed. It must not use regexes, keyword maps, or product
branches to pretend that it understands a user's actual problem.

If the required LLM/PiWorker authoring node is unavailable, the authoring flow
stops with an explicit configuration failure.

### Product Integration Owns Domain Compilation

Generic FrontDesk output is not enough for every domain. A SkillFoundry request,
a financial research request, and a codebase migration request may all need
different downstream contracts even if the user speaks casually.

Therefore:

```text
FrontDesk discovers intent.
Product Integration compiles domain obligation.
MissionForge core executes product-neutral boundaries.
```

Product Integration may provide:

- ProductInquiryProfile;
- domain contract compiler;
- default output shapes;
- product-specific judge rubric fragments;
- product-specific hard checks;
- packaging rules;
- product-level acceptance expectations.

Product Integration may not require MissionForge core to import product logic.

### Raw Chat Is Not Task Truth

Conversation is provenance, not authority.

The system may retain a raw or redacted conversation log when policy allows,
but runtime truth should come from a sanitized, frozen, reviewable contract.

The future contract shape should be minimal:

```text
TaskContract
  stable objective
  context and assumptions
  non-goals
  required artifacts
  hard constraints
  semantic acceptance criteria
  permissions and workspace policy refs
  judge rubric refs
  revision policy
```

Legacy MissionIR remains useful as a high-detail historical shape, but new work
should avoid treating MissionIR as both canonical contract, worker prompt, and
judge rubric at the same time.

### Contract Freeze And Explicit Revision

Once execution starts, the system must know which contract is being attempted.

Repair may improve the implementation. Repair may not quietly lower the bar.
If the bar is wrong, incomplete, unsafe, or impossible, the system must record a
revision request or redesign request.

This rule exists to protect the user from task drift and to protect the agent
from ambiguous success.

### PiWorker Is The Intelligent Worker

MissionForge is PiWorker-first and PiWorker-only for the planned system shape.

This is a deliberate product decision:

- one worker family keeps the mental model small;
- open-source runtime control makes hard permission enforcement possible;
- provider metrics and tool events can be observed consistently;
- the project avoids becoming a generic worker marketplace.

Internal boundaries may exist for testability, but they must not grow into a
public multi-provider worker registry.

### Code Handles Hard Boundaries

Code should do the things code is good at:

- schema validation;
- safe relative refs;
- workspace layout;
- permission manifests;
- path containment;
- secret exclusion;
- immutable contract hashes;
- role separation;
- artifact existence;
- command exit status;
- cost and token metrics;
- append-only ledgers;
- checkpoint and resume state.

Code should not pretend to do the things LLMs are needed for:

- understanding messy user pain;
- deciding product strategy;
- mapping vague desires to a useful solution;
- judging semantic quality of an artifact;
- choosing a repair strategy from ambiguous evidence.

### Runtime Capability Leases And Sandboxed Agents

MissionForge should separate three concepts that are easy to blur:

- capability profiles: reusable capability descriptions compiled from product
  or mission context;
- permission manifests: declarative policy inputs for read, write, command,
  network, and environment scope;
- capability grants: short-lived runtime authority for one role, one workspace
  view, one sandbox profile, and one time window.

Capability grants are not the security boundary by themselves. The sandbox is
the boundary. The grant selects and authenticates the sandbox. Tool calls should
flow through a ToolGateway and execute inside an isolated sandbox process.

```text
CapabilityGrant -> ToolGateway -> SandboxRunner -> isolated agent process
```

The runtime topology should support:

- one outer run hosting multiple sandboxes;
- one sandbox per role, agent, or phase by default;
- refs-only handoff between sandboxes;
- revocation or privilege changes by minting a new grant and, when needed, a
  new sandbox;
- no in-place privilege escalation of a live sandbox.

This is how MissionForge gives maximum freedom inside a precisely defined
world instead of relying on soft rules around a shared process.

### Execution Worker Does Not Self-Accept

The old law "worker self-report is never acceptance" remains valid, but the
new architecture refines it.

Execution may be performed by a PiWorker role. Semantic acceptance may also be
performed by a PiWorker role, but it must be a separate Judge role with a
separate prompt, separate input packet, and explicit authority.

```text
Executor PiWorker:
  produces artifacts and execution report

Judge PiWorker:
  reads TaskContract, JudgeRubric, artifact refs, evidence refs
  decides accepted | repair | revision_required | rejected
```

Code enforces that the executor's own completion claim is not enough.

### Evidence Is Refs-First

MissionForge should record evidence by reference.

Default runtime state should not embed:

- raw prompts;
- raw transcripts;
- provider payloads;
- secrets;
- large artifact bodies;
- stdout/stderr bodies;
- product-private source text.

It should record stable refs, hashes where useful, trust levels, role names,
decision IDs, and timestamps.

### Metrics Are Diagnostics

Token counts, wall time, retries, failure types, cache hits, tool calls, and
estimated costs are valuable. They are not acceptance authority.

Metrics answer:

- How expensive was this?
- Where did it fail?
- What should be optimized?
- Which product flow is more stable?

They do not answer whether a product artifact satisfies a semantic contract.

### Safe Points And Resume

Long-running agent work needs explicit recovery surfaces:

- current contract ref;
- current revision;
- current workspace policy;
- current permission manifest;
- last completed execution step;
- last judge decision;
- pending repair or revision request;
- cost and risk status.

MissionForge does not need a complex in-memory brain to provide this. It needs
a disciplined workspace and append-only ledgers.

## Updated Authority Model

The future system should use this authority split.

| Authority | Owner | Notes |
| --- | --- | --- |
| Need discovery | FrontDesk PiWorker | High-AI, conversational, fail-closed when unavailable. |
| Domain compilation | Product Integration | Product-specific, outside core. |
| Contract authority | TaskContract + revisions | Frozen, hashable, inspectable. |
| Semantic execution | Executor PiWorker | Works inside workspace and permission boundaries. |
| Semantic acceptance | Judge PiWorker | Separate role; reads contract, rubric, artifacts, evidence. |
| Hard rejection | MissionForge code | Invalid schema, unsafe ref, forbidden path, missing artifact, secret risk, stale contract. |
| Final packaging | Product Integration or operator surface | Product-specific final shape. |
| Audit memory | Decision ledger | Append-only refs and decisions. |

## What To Stop Expanding

The following old implementation directions should be treated cautiously:

- deterministic code that tries to infer user intent;
- Python branches for product-level semantic routing;
- large validator registries that try to replace a judge;
- adapter abstractions that imply many LLM worker families;
- treating raw MissionIR as the natural worker prompt;
- making metrics influence semantic routing;
- adding repair machinery that weakens contracts automatically.

These ideas may exist as historical code or compatibility surfaces, but new
development should converge away from them.

## What To Build Instead

The simplified system should center on a small set of durable objects:

```text
FrontDeskIntentBundle
ProductInquiryProfile
TaskContract
WorkerBrief
JudgeRubric
WorkspacePolicy
PermissionManifest
ExecutionPacket
ExecutionReport
JudgePacket
JudgeReport
RepairBrief
RevisionRequest
DecisionLedger
FinalPackage
```

The objects should be simple enough to inspect and stable enough to support
long-running work, product integrations, benchmark comparison, and future
compiled enforcement layers.

## Constitutional Test

Before accepting a new feature, ask:

1. Does this keep MissionForge core product-neutral?
2. Does this use PiWorker for semantic work instead of code pretending to
   understand?
3. Does this add a hard boundary that code can enforce?
4. Does this preserve frozen contract authority and explicit revision?
5. Does this keep execution and judgment roles separate?
6. Does this record evidence by ref?
7. Does this make the system smaller or clearer rather than expanding legacy
   orchestration?

If the answer is mostly no, the feature does not belong in the new core.
