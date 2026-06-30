# MissionForge Kernel API Design

Status: draft design, flow MVP in use

MissionForge should expose a small white-box LLM runtime API. Product authors
should be able to assemble an independent system from a few primitives, prompts,
artifact contracts, and tool grants, then run it by configuring provider URL and
key. They should not need to understand or copy the low-level MissionForge core
objects.

The goal is not to hide MissionForge boundaries. The goal is to make them easier
to declare:

```text
product author declares intent
kernel compiles workspace, refs, permissions, tools, and attempts
core runtime enforces boundaries and records evidence
```

Current MVP scope is intentionally narrow:

- implemented: data contracts, `Step` -> `PiWorkerCall` /
  `PermissionManifest` compilation, minimal `run_step(...)` execution,
  refs-first `StepRecord` writing, minimal `run_flow(...)` execution, decision
  artifact route extraction, refs-first `FlowResult` writing, conservative
  artifact-boundary resume/skip, bounded PiWorker boundary retry, runtime-owned
  projection execution, extension lock writing, and minimal refs-first flow
  ledger writing;
- proven with fixtures: a thin DeepResearch v2 product flow can run
  `researcher -> reviewer -> judge -> accepted`
  through Kernel `Step`/`Flow` declarations, with acceptance routed only from a
  judge-role step and reviewer/judge repair routed back to the same researcher
  workspace owner;
- not implemented yet: richer run-ledger views and semantic resume plans beyond
  artifact-boundary skip/retry.

## Design Pressure

DeepResearch exposed the current gap. MissionForge can white-box a single
PiWorker call, but product integrations still hand-write too much multi-worker
coordination: review loops, permission manifests, repair retries, progress,
artifact projections, resume checks, and judge handoff. That makes products grow
into their own frameworks.

Kernel API success means DeepResearch v2 can be a thin package:

- request/profile definitions;
- role briefs and rubrics;
- artifact contracts;
- extension grants;
- a compact flow declaration.

If DeepResearch v2 still needs thousands of lines of orchestration code, the
kernel API is not good enough.

The current DeepResearch v2 prototype lives in
`integrations/deepresearch/src/missionforge_deepresearch/kernel_v2.py`. It is a
product-layer proof, not a new core feature: the product writes the academic
request, role briefs, rubrics, artifact refs, and tool grants; Kernel compiles
and executes the bounded PiWorker calls, permission manifests, extension locks,
route ledger, retry policy, and artifact-boundary resume checks.

## Layers

```text
Layer 1: Core runtime
  PiWorkerCall, workspace policy, permission manifest, capability grant,
  tool gateway, context management, execution report, metrics, ledgers.

Layer 2: Kernel API
  Step, Flow, Artifact, Toolset, Projection, FailurePolicy.

Layer 3: Product package
  Prompts, rubrics, schemas, source profiles, report shape, CLI/API wrapper.
```

Core remains product-neutral. Product meaning never moves into `src/missionforge`.
The kernel API can be product-neutral because it models work boundaries, not
research, finance, support, coding, or any other domain.

Only `Step` and `Flow` are execution concepts. `Artifact`, `Toolset`,
`Projection`, and `FailurePolicy` are descriptors that keep the `Step`/`Flow`
declaration explicit without forcing product authors to hand-write core
runtime objects.

## Relationship To Existing Core

The Kernel API is a facade over the existing core, not a replacement for it.

It must not rewrite or weaken:

- `TaskContract` as frozen task authority;
- `WorkspacePolicy` and `PermissionManifest` as permission authority;
- `PiWorkerCall` as the bounded intelligence RPC;
- `CapabilityGrant`, sandbox profile, and tool gateway enforcement;
- refs-first execution reports, metrics, ledgers, and package records.

The first implementation lives under `src/missionforge/kernel/` and should not
be exported from the package root until DeepResearch v2 proves the surface.
Kernel `Flow` is the product-neutral facade for authors who need several
PiWorker steps, decision routes, projections, and artifact-boundary resume
without hand-writing orchestration.

Kernel runs are always bound to a frozen contract ref and contract hash. A flow
may produce a contract revision request, but it must not silently broaden the
contract through a step, route, expansion plan, or tool grant.

Provider configuration is a runtime binding, not product semantics. Kernel
should accept the existing PiWorker provider config mechanisms such as
environment variables or `codex_current`, then pass them to the adapter layer.
Product packages should not need to parse provider auth files or duplicate
adapter configuration logic.

## Public Primitives

### Step

`Step` is one white-box PiWorker work unit.

It declares:

- role and brief;
- input refs;
- output refs;
- readable roots;
- writable roots;
- toolsets;
- runtime budget;
- expected control artifact, if any;
- failure policy.

Example:

```python
Step(
    id="reviewer",
    brief="Review the report and write a routing observation.",
    inputs=[
        "contract/task_contract.json",
        "reports/final_report.md",
        "sources/source_packet.json",
        "rubrics/reviewer.md",
    ],
    outputs=["reviews/round_01/reviewer_observation.json"],
    read=["contract", "reports", "sources", "rubrics"],
    write=["reviews"],
    tools=["read", "write"],
    route_on="reviews/round_01/reviewer_observation.json",
)
```

Kernel compiles this into low-level MissionForge objects:

- `PiWorkerCall`;
- `PermissionManifest`;
- step spec ref;
- step record ref;
- `CapabilityGrant`;
- workspace view;
- attempt directory;
- progress events;
- execution report;
- metrics refs.

The product author controls permissions through the high-level declaration. The
core runtime still enforces permissions through the existing hard boundary.

Step compilation must fail closed when:

- an input ref is outside the declared readable roots;
- an output ref is outside the declared writable roots;
- a runtime-owned, product-owned, input, projection, or ledger artifact is
  declared as PiWorker-writable;
- a tool is requested without a matching core tool or extension grant;
- `bash` is requested without an explicit command allowlist;
- the step attempts to change the frozen contract without an explicit revision
  artifact and route.

The compiled `PiWorkerCall` exposes only the frozen contract ref and declared
step input refs as worker-visible refs. Kernel-internal refs such as the step
spec and permission manifest are durable audit records, not task inputs the
worker must read. Their refs and hashes stay in call metadata and step records.
The adapter also fails closed if a visible ref is not readable through the
effective permission manifest.

### Step Batch

`run_steps_batch(...)` runs a caller-supplied list of independent `Step`
declarations concurrently through the existing `run_step(...)` path.

It is a fan-out/fan-in primitive, not a graph runtime:

- each step receives a derived batch ref prefix under
  `kernel/{flow_id}/batches/{batch_id}/steps/{NNN}-{step_id}/`;
- each step receives a distinct PiWorker `call_id`;
- declared `outputs` and `write` refs are conflict-checked before any step
  starts;
- ContextEngine compile records, permission manifests, step records, evidence
  stores, and progress sinks remain per-step;
- partial failures are collected structurally in `StepBatchResult`.

The batch wrapper does not merge outputs, reduce shared state, infer product
semantics, or add parallel route semantics to `run_flow(...)`. If several step
outputs need synthesis, the product or host Python should declare a later
explicit synthesis, writer, reviewer, or judge step.

### Flow

`Flow` composes steps and routes between them.

Example:

```python
Flow(
    id="deepresearch_v2",
    steps=[planner, source_expander, section_writer, editor, reviewer, judge],
    routes={
        "reviewer.ready_for_judge": "judge",
        "reviewer.bounded_revision": "revision",
        "reviewer.major_research_expansion": "expansion_planner",
        "reviewer.blocked": Flow.stop("blocked"),
        "judge.accepted": Flow.stop("accepted"),
        "judge.repair": "repair",
    },
)
```

The route key is a small control value from a decision artifact. Python does not
read reviewer prose, rank sources, infer semantic quality, or choose domain
concepts. PiWorker-authored control artifacts own semantic routing intent.

Routing should be declared over a specific decision artifact field, not over
free-form Markdown. MVP route extraction should support only simple JSON paths
such as `decision` or `decision + revision_scope`; product code may define the
allowed values, but the kernel only checks that the value is present, typed, and
listed in the route table.

Flow declaration validation fails closed when:

- a route source step does not declare `route_on`;
- `route_on` is not one of that step's outputs;
- the `route_on` artifact is not declared as a PiWorker-owned `decision`
  artifact;
- a route source step does not declare `route_fields`;
- a route source or route target step is unknown;
- a terminal `accepted` route does not come from a judge-role step;
- a terminal `accepted` route is not based on at least one prior non-judge step
  output visible to that judge step;
- a projection output is not declared as a runtime-owned projection artifact.

This preserves the MissionForge law that an execution worker may not self-accept
its own work. Product-specific route values still belong to product artifacts
and schemas; the kernel only validates the boundary shape.

MVP `run_flow(...)` semantics:

- starts from the first declared step;
- executes each step through `run_step(...)`;
- reads route values only from the step's declared `route_on` JSON artifact;
- supports `route_fields=["decision"]` and multi-field keys joined with `+`,
  such as `decision+revision_scope`;
- routes only through the declared route table;
- stops at `Flow.stop(status)`, an unrouted decision, a failed/blocked step, or
  `max_steps` exhaustion;
- treats a missing, malformed, or unsafe decision artifact as a blocked flow and
  writes the flow result and ledger instead of surfacing a Python traceback;
- records each step under an attempt-specific prefix so loops do not overwrite
  prior step records;
- carries bounded `ToolOutputProjection` record refs from a completed step into
  the next step's ContextEngine compile request, without granting raw-output
  access or bypassing the next step's read permissions;
- writes `kernel/{flow_id}/runs/{run_id}/executions/{NNN}/flow_ledger.jsonl`
  with refs-first events for start, step record, route, projection, and stop
  boundaries. Each rerun gets a new execution ledger/result ref.

The flow runner does not read Markdown, inspect reviewer prose, infer report
quality, rank evidence, or decide product semantics. It only executes declared
step boundaries and follows explicit PiWorker-authored decision artifacts.

### Artifact

`Artifact` describes product-visible and control-visible files.

Simple users can pass string refs. Advanced users can declare artifact roles:

```python
Artifact("reports/final_report.md", role="output", owner="piworker")
Artifact("reviews/reviewer_observation.json", role="decision", owner="piworker")
Artifact("state/research_state.json", role="state", owner="piworker")
Artifact("reports/evidence_index.md", role="projection", owner="runtime")
```

Artifact roles are not product semantics. They tell the kernel how to handle
ownership, validation, routing, and resume.

MVP artifact roles:

- `input`: durable context provided to a step;
- `output`: PiWorker-authored user/product artifact;
- `decision`: PiWorker-authored control artifact used for routing;
- `state`: PiWorker-authored recovery/posterior artifact;
- `projection`: runtime-authored mechanical artifact;
- `ledger`: runtime-authored audit record.

Projection outputs must be declared explicitly as runtime-owned projection
artifacts. Undeclared projection outputs fail closed; this keeps product
semantic generation in PiWorker steps and reserves runtime projections for
mechanical, inspectable artifacts.

### Toolset

`Toolset` declares tools available to steps.

Core tools stay minimal:

```text
read
write
edit
bash
```

Product tools enter through extensions:

```python
Toolset(
    id="academic",
    package="local:extensions/pi-academic-sources",
    tools=["academic_search", "academic_fetch", "citation_lookup", "repo_search"],
    network=True,
)
```

The kernel compiles toolsets into extension grants and extension locks. Tool
calls remain white-boxed through gateway decisions, observations, metrics, and
attempt artifacts. Tool output is observation, not truth.

Kernel does not introduce a second tool schema. `Toolset` is a product-author
facade over the existing `ExtensionGrant` and `ExtensionLock` authority:

- `Toolset.tools` is preserved as extension grant metadata and lock metadata;
- steps with extension grants write `kernel/{flow_id}/steps/{step_id}/extension_lock.json`
  by default;
- an externally supplied `extension_lock_ref` is accepted only when it satisfies
  the compiled `PermissionManifest`;
- default mode is `verify-installed`, so Kernel does not perform hidden network
  installs;
- product runners may explicitly choose `install` mode and provide or accept an
  installer.

MVP note: current `ExtensionGrant` authority is package/capability scoped.
`Toolset.tools` is recorded in grant metadata for inspection and future gateway
enforcement, but it is not yet a hard per-tool allowlist. Do not treat a tool
name list as a security boundary until the core gateway has a first-class
allowed-tools field.

### Projection

`Projection` is runtime-owned artifact generation.

Use it for mechanical artifacts that should not consume PiWorker output budget:

```python
Projection(
    output="reports/evidence_index.md",
    from_=["sources/source_packet.json", "reports/final_report.md"],
    projector="citation_index",
)
```

Projections make artifact ownership explicit:

```text
PiWorker owns semantic artifacts.
Runtime owns mechanical indexes, refs views, package summaries, and audits.
```

MVP projection execution is deliberately small:

- the product supplies a `projector` callable by name;
- the kernel checks that all declared source refs exist;
- the kernel passes workspace-safe source paths to the callable;
- the callable returns a string or JSON-compatible value;
- the kernel writes the projection output and a `ProjectionRecord`;
- the record stores source refs, source hashes, output ref, output hash, and
  projection metadata.

The kernel does not know how to build a citation index, package summary, report
outline, or any other product-specific projection. It only owns the ref/hash
boundary and the runtime-owned artifact record. Failed or blocked flows do not
run projections, so projection failures do not hide the original step failure.

### FailurePolicy

`FailurePolicy` controls bounded retry and terminal status.

MVP:

```python
FailurePolicy(retries=2, on_exhausted="blocked")
FailurePolicy(retries=0, on_exhausted="failed")
```

Implemented MVP semantics:

- `retries` is the number of extra PiWorker boundary attempts after the first
  failed or blocked result;
- each retry uses an attempt-specific `call_id`, `piworker_call.json`, and
  `piworker_call_result.json` so attempt artifacts do not overwrite each other;
- the step still exposes stable `piworker_call.json` and
  `piworker_call_result.json` refs at the step boundary;
- a worker-reported `completed` call is checked against the workspace: every
  expected output ref must exist as a file. Missing files turn the attempt into
  `invalid_output`, write `output_validation.json`, and can be retried by the
  same failure policy;
- a later completed attempt makes the step `completed`;
- exhausted non-completed attempts become `on_exhausted`, currently `failed` or
  `blocked`;
- retry metadata is refs-first: attempt refs, attempt count, and final attempt
  ref, not raw provider payloads.
- when a step has already compiled a ContextEngine provider-turn boundary, retry
  attempts reuse that same preflight boundary explicitly with
  `context_boundary_reuse: "same_preflight_boundary"` and parent compile/turn
  refs. Retry does not silently imply a fresh context compile.

Do not add broad recovery semantics initially. Product-specific repair should be
another explicit step, not hidden controller magic.

## Resume Semantics

Every step records:

- step spec hash;
- permission manifest hash;
- input refs and input content hashes;
- extension lock ref and hash when the step uses extension grants;
- expected output refs;
- attempt call/result refs;
- execution report ref;
- metrics refs.

MVP skip rule:

```text
skip a step if step spec hash matches, input ref hashes match,
permission manifest hash matches, extension lock ref/hash matches,
and all required output refs exist and validate
```

The implemented MVP records input and output hashes in `StepRecord`. A rerun
skips a step only when:

- the prior record is `completed` or `skipped`;
- step id, step spec hash, contract ref, and contract hash match;
- permission manifest hash matches;
- extension lock ref and hash match for extension steps;
- input refs and input hashes match;
- all expected output refs are present in the prior output refs;
- the output files still exist and their hashes match the prior record.

If an extension lock is expected but missing or unreadable, the step does not
skip. It prepares or verifies the lock before invoking PiWorker. If any
condition is uncertain, the step runs again. Kernel resume is an artifact-boundary
optimization, not a semantic claim that the product task is complete.

A prior failed or blocked step may be recovered as a skipped artifact boundary
only when the same strict hashes still match, every expected output ref is both
reported and present, and any `route_on` decision artifact can be parsed through
the declared route fields. This handles tail failures after durable artifacts
were written without letting Python judge the artifacts' semantic quality.

Skip records are written beside the original completed record under
`reuse_records/{NNN}.json`; the original completed `step_record.json` remains
unchanged. Flow-level ledgers/results are also append-only by execution id. This
keeps artifact-boundary resume auditable instead of rewriting the evidence that
made resume possible.

Provider/model identity should be recorded but not part of the default skip
rule. Changing providers should not force recomputation when durable artifacts
are already valid.

Failed steps remain inspectable and retryable from their artifact boundary.
MissionForge should not discard completed upstream steps.

## Permission Model

Kernel API must preserve MissionForge's original permission design.

Product authors declare high-level access:

```python
Step(
    id="source_expander",
    read=["contract", "reviews", "sources", "tools"],
    write=["sources", "state"],
    tools=["read", "write", "academic"],
    network=True,
)
```

Kernel compiles this into:

- readable refs;
- writable refs;
- denied refs;
- command allowlist;
- network policy;
- extension grants;
- env allowlist;
- sandbox profile.

The compiled permission manifest and all tool gateway decisions remain durable
evidence. A product author should not need to hand-write the manifest, but they
must be able to inspect it.

## Run Records

Kernel must emit small refs-first run records. Otherwise each product will
recreate incompatible result and resume formats.

Minimum records:

```text
runs/{flow_id}/steps/{step_id}/step_spec.json
runs/{flow_id}/steps/{step_id}/step_record.json
runs/{flow_id}/executions/{NNN}/flow_result.json
```

`step_record.json` should include:

- step id and step spec hash;
- contract ref/hash;
- input refs and content hashes;
- output refs and validation status;
- permission manifest ref;
- permission manifest hash;
- extension lock ref and hash;
- PiWorker call and result refs;
- bounded retry attempt refs;
- execution report and metric refs;
- status: `skipped`, `completed`, `failed`, or `blocked`;
- failure reason refs, never raw provider payloads.

`flow_result.json` should include:

- flow id;
- contract ref/hash;
- terminal status;
- ordered step record refs;
- final artifact refs;
- decision refs;
- ledger refs;
- resume checkpoint ref.

The implemented MVP writes a minimal `flow_ledger.jsonl` ledger. Each event is
refs-first and product-neutral:

- `started`: run boundary and contract ref;
- `step_started`: step id plus declared input/output refs before the PiWorker
  call starts;
- `step_recorded`: step id, step status, and step record ref;
- `routed`: decision ref, route value, and route target;
- `projections_recorded`: runtime projection record refs;
- `stopped`: final status and stop reason.

The ledger does not embed prompts, transcripts, reports, reviewer prose, tool
outputs, or provider payloads. It is an execution trace, not a semantic quality
judgment. Richer package-level run ledgers and resume checkpoint records remain
future work.

These are kernel records, not product semantic judgments. Final semantic
acceptance still requires an independent judge artifact when the product flow
declares one.

## DeepResearch V2 Shape

DeepResearch v2 should be the first proof of the kernel API.

Current v2 flow:

```text
researcher
  -> reviewer
  -> judge
```

Bounded loop routing:

```text
researcher.ready_for_review -> reviewer
researcher.continue -> researcher
reviewer.ready_for_judge -> judge
reviewer.revise_report -> researcher
reviewer.continue -> researcher
reviewer.blocked -> blocked
reviewer.rejected -> failed
judge.accepted -> accepted
judge.repair -> researcher
judge.revision_required -> blocked
judge.rejected -> failed
```

The researcher step owns the working research workspace: source packet,
research state, evidence index, source gaps, and final report. Reviewer and
judge steps own semantic critique and acceptance. The controller reads only
small decision artifacts and hard runtime status.

MVP limits:

- no automatic contract broadening;
- bounded loops through `max_steps`;
- no Python-side research expertise;
- failed or broad expansion stops as `blocked` unless a PiWorker produces a
  same-contract repair decision.

## What Must Not Move Into Kernel

Do not put product semantics into the kernel:

- research section templates;
- academic source importance;
- paper ranking;
- business domain concepts;
- customer profile meanings;
- report quality judgment;
- judge rubrics;
- reviewer prompts.

The kernel may validate schemas, refs, permissions, hashes, outputs, routes, and
budgets. It must not decide product truth.

## MVP Implementation Order

1. Add a draft `missionforge.kernel` package with `Step`, `Flow`, `Artifact`,
   `Toolset`, `Projection`, `FailurePolicy`, and `StepRecord` data contracts.
2. Compile `Step` into existing `PiWorkerCall` and `PermissionManifest`
   objects, preserving contract/hash, workspace policy, refs, write scopes, and
   extension grants.
3. Prepare or verify extension locks for steps with extension grants.
4. Implement a single-step runner over the existing PiWorker runtime.
5. Add step execution records.
6. Add route-on-control-artifact extraction and minimal `FlowResult` writing.
7. Add artifact-boundary resume/skip.
8. Add bounded PiWorker boundary retry through `FailurePolicy`.
9. Add runtime projections.
10. Add minimal refs-first flow ledger writing.
11. Build DeepResearch v2 as a small product package on top of the kernel API.
12. Keep the existing DeepResearch implementation as a compatibility/learning
   path until v2 proves the API.

## Design Test

The API is acceptable only if it can express these systems without product code
reimplementing runtime scaffolding:

- single worker;
- worker plus reviewer;
- reviewer loop with bounded revision;
- worker plus independent judge;
- plan/sections/editor pipeline;
- expansion from a reviewer decision;
- failure resume from the last completed artifact boundary.

If these cannot be expressed with a small `Step`/`Flow` declaration, the API is
not yet minimal enough.
