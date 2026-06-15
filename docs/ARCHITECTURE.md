# MissionForge Architecture

MissionForge is a minimal delegation kernel around PiWorker.

PiWorker owns semantic work. MissionForge owns durable task authority, workspace
boundaries, permission checks, refs-first evidence, role separation, independent
judgment, repair, revision, and replay.

The runtime boundary is not just a manifest check. Long-lived autonomy requires a
capability-grant layer and a per-agent sandbox boundary so different agents can
see different file trees, network access, command sets, and resource budgets
inside one outer run.

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

## Thin Product Integrations

MissionForge should make product integrations smaller, not push programmers
toward large deterministic workflow engines. A product integration should look
more like a bounded manual plus tool surface than a second application runtime:

```text
manuals + contracts + rubrics + bounded tools + refs
  -> PiWorker semantic work
  -> hard validation and independent judgment
```

If product-specific Python grows into thousands of lines of semantic planning,
ranking, synthesis, or acceptance logic, the design is likely fighting the
architecture. Move that intelligence into PiWorker-readable manuals, prompts,
rubrics, and explicit artifacts. Keep code responsible for contracts,
permissions, refs, tool execution, ledgers, repair, revision, and structural
validation.

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

For fine-grained autonomy, the runtime should treat a `CapabilityGrant` as the
short-lived authority that selects a sandbox profile and workspace view. The
grant is not the sandbox; it is the ticket that creates one. Multiple agents in
the same outer job should normally receive separate sandboxes and exchange only
refs or promoted artifacts.

The bundled Pi runtime has started this migration at the tool boundary:
`read`, `write`, `edit`, and `bash` all pass through a worker-side
`ToolGateway` decision layer that records refs-first audit evidence. The
runtime input envelope now carries a `CapabilityGrant` and `SandboxProfile`,
and the worker-side tool boundary uses the profile as the effective execution
view. Bash commands are still exact-allowlist gated, and execute through a
`bubblewrap` sandbox view instead of the host shell. The next runtime-control
step is the full per-agent process sandbox lifecycle and grant revocation
flow.

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
