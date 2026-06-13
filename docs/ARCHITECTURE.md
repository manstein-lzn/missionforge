# MissionForge Architecture

MissionForge is a minimal delegation kernel around PiWorker.

PiWorker owns semantic work. MissionForge owns durable task authority, workspace
boundaries, permission checks, refs-first evidence, role separation, independent
judgment, repair, revision, and replay.

The architecture is:

```text
FrontDesk
  -> FrontDeskIntentBundle
  -> ProductIntegration
  -> TaskContract
  -> WorkerBrief + JudgeRubric + WorkspacePolicy + PermissionManifest
  -> PiWorkerCall(role=executor_piworker)
  -> artifact refs + execution report
  -> PiWorkerCall(role=judge_piworker)
  -> accepted | repair | revision_required | rejected
  -> DecisionLedger + FinalPackage
```

## Product Boundary

MissionForge core is product-neutral. It must not contain SkillFoundry,
Codexarium, benchmark, finance, customer, or task-family branches.

Product-specific meaning belongs in external product integrations:

- inquiry profiles;
- task compilers;
- task contracts;
- judge rubrics;
- hard checks;
- product gates;
- package builders;
- tests and fixtures.

Core code treats product ids and check ids as data. It does not branch on them.

## Durable Truth

Raw chat is not operational task truth. A frozen `TaskContract`, or an explicit
revision of that contract, is the durable task authority.

`MissionIR` remains only as a high-detail compatibility data shape for older
mapping paths. It is not the first-class runtime contract for new work.

## Role Separation

MissionForge keeps four roles separate:

- FrontDesk discovers and structures requirements.
- ProductIntegration compiles product meaning into MissionForge primitives.
- Executor PiWorker produces artifacts inside the frozen boundary.
- Judge PiWorker evaluates artifacts against the frozen contract and rubric.

The executor may not accept its own work. Code may reject invalid, unsafe,
unauthorized, malformed, stale, or unreferenced outputs, but code does not
pretend to perform product-level semantic judgment.

## Runtime Boundary

The only first-class intelligent invocation boundary is `PiWorkerCall`.

`PiWorkerCall` is an unreliable intelligent RPC wrapped in deterministic
constraints:

- contract id and contract hash;
- role;
- visible refs;
- writable refs;
- expected output refs;
- permission manifest ref;
- evidence refs;
- exit criteria and stop conditions.

The PI Agent runtime sidecar executes the bounded call. MissionForge validates
the returned `PiWorkerCallResult`, records refs-only evidence, and feeds those
refs into the next deterministic boundary.

## Evidence Plane

Durable state should cite refs instead of embedding raw prompts, transcripts,
provider payloads, stdout/stderr bodies, artifact bodies, or secrets.

Artifacts remain filesystem refs for now. MissionForge does not build an
in-memory dataflow system until the workspace and permission model is stable.

## Repair And Revision

Repair preserves the same frozen contract. A repair path may produce new
artifacts, but it does not weaken acceptance and does not change task truth.

Revision changes task truth only through explicit records:

```text
JudgeReport(decision=revision_required)
  -> TaskRevisionRequest
  -> RevisionPendingRecord
  -> revised TaskContract draft
  -> TaskRevisionDecision
  -> RevisionAppliedRecord
```

Only the revision-applied event is allowed to move execution onto a new contract
hash.

## Operator Surface

The CLI/RPC adapters are operator surfaces for refs-only inspection, diagnosis,
explicit control intent, review records, validation, and FrontDesk authoring.
They are not a product execution facade.

There is no top-level `run` or `resume` command. Product execution should compile
to `TaskContract`, `WorkspacePolicy`, and `PermissionManifest`, then use the
TaskContract/PiWorker flow.

## Invariants

- Product semantics do not enter `src/missionforge`.
- Frozen contract authority is explicit.
- Executor output is evidence, not acceptance.
- Judge acceptance is independent from execution.
- Repair does not weaken the frozen contract.
- Revision is explicit and ledgered.
- Runtime/operator state is refs-first.
- Metrics are diagnostics and cost evidence, not semantic route or acceptance
  authority.
- Permission and workspace checks are enforced by code, not prompt wording.
