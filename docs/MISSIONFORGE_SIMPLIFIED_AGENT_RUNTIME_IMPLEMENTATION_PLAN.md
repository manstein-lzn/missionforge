# MissionForge Simplified Agent Runtime Implementation Plan

Last updated: 2026-05-31

Status: development plan for converging from the current implementation to the
simplified PiWorker-centered system shape.

## Goal

Implement the architecture described in
`docs/MISSIONFORGE_AGENTIC_CONSTITUTION.md` and
`docs/MISSIONFORGE_FINAL_SYSTEM_SHAPE.md` without losing the useful guarantees
from the existing MissionIR, runtime, steering, evidence, metric, and revision
work.

The plan intentionally avoids a large rewrite. It builds the new thin path next
to the current system, proves it with SkillFoundry as the first product
integration, then retires or demotes legacy code only after equivalent
boundaries are covered.

## Success Criteria

The implementation is successful when MissionForge can run a product task
through this path:

```text
FrontDeskIntentBundle
  -> ProductIntegration.compile_task_contract()
  -> TaskContract freeze
  -> WorkerBrief / JudgeRubric / WorkspacePolicy / PermissionManifest
  -> Executor PiWorker
  -> hard boundary checks
  -> Judge PiWorker
  -> accepted | repair | revision_required | rejected
  -> ledgered final package
```

Required properties:

- no product-specific behavior in `src/missionforge`;
- no deterministic user-need inference;
- no executor self-acceptance;
- refs-only durable state by default;
- explicit revision for contract changes;
- permission enforcement is hard where implemented and honest where not yet
  implemented;
- SkillFoundry can integrate through external integration code;
- benchmark infrastructure can compare direct chat, contract-only runtime, and
  full product flow without changing core semantics.

## Phase S0: Guardrails And Documentation

Purpose: lock the new direction before more code is added.

Deliverables:

- root `AGENTS.md`;
- `docs/MISSIONFORGE_AGENTIC_CONSTITUTION.md`;
- `docs/MISSIONFORGE_FINAL_SYSTEM_SHAPE.md`;
- this implementation plan;
- optional README pointer to the new direction.

Acceptance:

- future agents can read one root instruction file and avoid expanding legacy
  deterministic orchestration;
- docs clearly distinguish preserved principles from demoted implementation
  forms;
- no source behavior changes are required in this phase.

## Phase S1: Minimal Contract Kernel

Purpose: add the small contract shape without deleting legacy MissionIR.

Candidate files:

```text
src/missionforge/task_contract.py
src/missionforge/task_projection.py
tests/test_task_contracts.py
tests/test_task_projections.py
```

Core objects:

- `TaskContract`
- `TaskContractRevision`
- `WorkerBrief`
- `JudgeRubric`
- `WorkspacePolicy`
- `PermissionManifest`

Implementation notes:

- Use simple dataclasses or typed dictionaries consistent with existing
  project style.
- Reuse existing safe-ref, stable-json, hashing, and validation helpers where
  possible.
- Keep schemas small. Do not port the full MissionIR complexity.
- Include conversion helpers from legacy MissionIR only if they are needed for
  compatibility and can stay product-neutral.

Acceptance tests:

- contract round trip;
- stable hash;
- duplicate or missing IDs fail;
- unsafe refs fail;
- contract freeze is deterministic;
- WorkerBrief and JudgeRubric projections do not mutate source contract;
- TaskContract can cite ProductIntegration refs without importing product code.

## Phase S2: Workspace And Permission Manifests

Purpose: make the workspace and permission boundary first-class.

Candidate files:

```text
src/missionforge/workspace_runtime.py
src/missionforge/permissions.py
tests/test_workspace_runtime.py
tests/test_permission_manifest.py
```

Core objects:

- `RunWorkspace`
- `WorkspaceLayout`
- `PermissionManifest`
- `PermissionCheckResult`

Implementation notes:

- Start with filesystem path policy, readable roots, writable roots, denied
  paths, artifact roots, and refs.
- Model command and network policy even if enforcement is initially partial.
- Enforcement must be honest: if bash policy is not hard-enforced yet, record
  that as unsupported or advisory instead of claiming security.
- Integrate with `workers/pi-agent-runtime` only after Python contract tests
  are stable.

Acceptance tests:

- allowed read/write refs pass;
- path traversal fails;
- writes outside allowed roots fail;
- denied paths fail even when under readable roots;
- missing permission manifest fails closed for execution;
- unsupported hard policy is surfaced as unsupported, not silently allowed.

## Phase S3: PiWorker Execution And Judge Nodes

Purpose: implement role-separated PiWorker invocation packets.

Candidate files:

```text
src/missionforge/agent_packets.py
src/missionforge/agent_runtime.py
tests/test_agent_packets.py
tests/test_executor_judge_separation.py
```

Core objects:

- `ExecutionPacket`
- `ExecutionReport`
- `JudgePacket`
- `JudgeReport`
- `AgentRole`

Implementation notes:

- Executor input is derived from WorkerBrief and PermissionManifest.
- Judge input is derived from TaskContract, JudgeRubric, hard-check results,
  ExecutionReport, and artifact refs.
- The executor report cannot mark final acceptance.
- JudgeReport can recommend accepted, repair, revision_required, or rejected.
- Code validates JudgeReport schema, refs, role identity, and hard-check
  preconditions.

Acceptance tests:

- executor cannot set final accepted status;
- judge cannot cite artifacts outside the workspace;
- judge cannot accept when mandatory hard checks failed;
- malformed judge report fails closed;
- role IDs and packet IDs are recorded in the ledger.

## Phase S4: Minimal Offline Agentic Flow, Ledger, And Checkpoints

Purpose: prove the new runtime shape with a product-neutral offline flow, while
replacing implicit runtime memory with small refs-only records.

Candidate files:

```text
src/missionforge/agentic_flow.py
docs/modules/agentic_flow.md
tests/test_agentic_flow.py
```

Core objects:

- `AgenticFlowRunner`
- `AgenticFlowRefs`
- `AgenticFlowResult`
- `AgenticFlowStatus`
- `AgentExecutorNode`
- `AgentJudgeNode`

Implementation notes:

- Keep this phase offline: no live PiWorker invocation, no provider calls, no
  network, and no product-specific fake behavior.
- Compose the existing S1-S3 primitives rather than adding a new semantic
  runtime.
- Project WorkerBrief and JudgeRubric through the projection helpers.
- Build packets and reports through `agent_packets.py` and call the existing
  cross-object validators.
- Enforce worker output refs through `RunWorkspace` and `PermissionManifest`.
- Fail closed when the permission manifest declares unsupported hard policies.
- Passed hard checks must cite explicit hard-check refs.
- Passed hard-check refs must exist in the run workspace.
- Passed hard-check refs are runtime-owned evidence and must be denied for
  executor/judge writes.
- Judge acceptance requires passed hard checks and completed execution.
- Judge acceptance requires required artifact refs to be produced, accepted, and
  present in the run workspace.
- Executor and judge workspaces must deny writes to runtime-owned packets,
  reports, ledgers, checkpoints, and contract/policy refs.
- Ledger and checkpoint entries must be refs-first.
- Include event kind, contract hash, packet refs, report refs, timestamps, and
  compact status.
- Do not embed raw provider payloads, transcripts, or artifact bodies.
- Add a separate ledger/checkpoint module later only if replay or richer event
  querying is needed; the S4 runner API must already expose append-only ledger
  behavior for this path.

Acceptance tests:

- accepted offline executor-then-judge path writes the expected workspace refs;
- required artifact refs outside worker writable roots fail closed;
- executor reports outside workspace or permission roots fail closed;
- executor or judge attempts to write runtime-owned control refs fail closed;
- judge acceptance with failed hard checks fails closed;
- judge acceptance with missing hard-check evidence fails closed;
- judge acceptance with missing or unproduced required artifacts fails closed;
- judge acceptance for artifacts not produced by execution fails closed;
- repair and revision decisions route refs without granting acceptance;
- append-only ledger writes and latest checkpoint writes are produced;
- refs are safe and local to the run workspace;
- raw body fields are rejected or absent from result, checkpoint, and ledger
  payloads.

## Phase S5: SkillFoundry Product Integration On The New Path

Purpose: prove the architecture with the first real product without polluting
core.

Candidate files:

```text
integrations/skillfoundry/src/missionforge_skillfoundry/task_contract_compiler.py
integrations/skillfoundry/src/missionforge_skillfoundry/judge_rubrics.py
integrations/skillfoundry/tests/test_task_contract_compiler.py
integrations/skillfoundry/tests/test_agentic_skillfoundry_flow.py
```

Implementation notes:

- SkillFoundry provides ProductInquiryProfile and compiles
  FrontDeskIntentBundle into TaskContract.
- SkillFoundry defines skill-specific required outputs and judge rubric
  fragments.
- MissionForge core sees these as data refs and contract fields, not product
  branches.

Acceptance tests:

- SkillFoundry contract compilation works from a stored intent bundle;
- core imports do not import SkillFoundry;
- product-specific strings and logic remain in `integrations/skillfoundry`;
- WorkerBrief and JudgeRubric are sufficient for PiWorker execution and judge
  review in a deterministic or fake-provider test.

## Phase S6: Repair And Revision Loop

Purpose: support long-running correction without rebuilding the old heavy
repair engine.

Candidate files:

```text
src/missionforge/agentic_repair.py
src/missionforge/agentic_repair_controller.py
src/missionforge/agentic_revision_controller.py
tests/test_agentic_repair.py
tests/test_agentic_repair_controller.py
```

Core objects:

- `RepairBrief`
- `TaskRevisionRequest`
- `TaskRevisionDecision`
- `RepairTicket`
- `RepairExecutionDirective`
- `RevisionPendingRecord`
- `RevisionAppliedRecord`

Implementation notes:

- RepairBrief keeps the same TaskContract hash.
- TaskRevisionRequest proposes changing the contract and must cite why repair is
  insufficient.
- Approved revision freezes a new TaskContract revision.
- Rejected revision routes back to repair, rejection, or user/operator review
  depending on policy.
- Repair controller records are refs-only, idempotent, and content-bound to the
  immutable `AgenticFlowResult`, judge packet/report, worker brief, and repair
  brief.
- Revision controller records are separate from repair: `revision_required`
  becomes a pending record first; only an approved `TaskRevisionDecision` plus a
  content-bound revised `TaskContract` can write a `TaskContractRevision`.
- `TaskRevisionDecision.authority` must match the pending record's
  `authority_required`; `decided_by` names the actor but does not bypass the
  authority route.

Acceptance tests:

- repair cannot change frozen acceptance;
- revision changes contract hash;
- revision ledger preserves old and new contract refs;
- judge can request repair or revision_required but cannot directly mutate the
  contract.
- repair execution directive prepares the next execution packet without
  invoking a worker;
- stale, checkpoint-based, foreign-run, or content-drifted controller inputs
  fail closed;
- wrong-authority revision approvals fail closed;
- replay returns the same durable record and deterministic-id conflicts fail
  closed.

Status note:

- The first S6 slice has landed as `RepairBrief`, `TaskRevisionRequest`, and
  `TaskRevisionDecision` plus flow-level validation for repair/revision
  artifacts.
- The controller slice has now landed as `RepairTicket`,
  `RepairExecutionDirective`, `RevisionPendingRecord`, and
  `RevisionAppliedRecord`. It deliberately stops at durable control records and
  packet refs; it does not invoke PiWorker, perform product semantic repair, or
  mutate runtime state implicitly.

## Phase S7: PiWorker Runtime Hardening

Purpose: enforce the permission model as close to tools as possible.

Candidate areas:

```text
workers/pi-agent-runtime/src/
workers/pi-agent-runtime/tests/
src/missionforge/piworker_runtime.py
```

Implementation notes:

- File tools should enforce read/write roots through hard path containment.
- Bash/tool execution needs explicit policy. Guarding only cwd is not enough
  for a formal permission model.
- Network and environment policy should be explicit even if initial
  enforcement is limited.
- Provider secrets must remain environment-only and must never be serialized
  into packets, reports, ledgers, or docs.

Acceptance tests:

- file read/write outside manifest fails;
- denied roots fail;
- command execution without permission fails;
- disallowed environment variables are not exposed;
- runtime reports unsupported hard policy honestly when enforcement is not yet
  implemented.

Status note:

- The first S7 slice has landed in `workers/pi-agent-runtime`: runtime input now
  carries a required `permission_manifest`, file tools enforce readable,
  writable, and denied refs before touching the filesystem, bash requires an
  exact `allowed_commands` match, and bash environment variables are filtered by
  `env_allowlist`.
- Tool path checks reject symlink components before read/write/edit/mkdir so an
  allowed lexical ref cannot escape the workspace through a filesystem link.
- Runtime-owned writes also reject symlink components before writing output,
  session, event, metric, savepoint, startup-failure, and direct benchmark
  artifacts.
- The direct benchmark path now rejects symlink components for `workspace_ref`,
  initial user text refs, allowed source refs, and expected output existence
  checks so benchmark comparison code cannot become a looser side door.
- Runtime session and event artifacts now store structure summaries for
  messages, tool args, and tool results rather than raw transcript text, write
  bodies, or provider/tool payload bodies by default.
- Runtime `worker_claims` store length summaries rather than raw final
  assistant text. The Python adapter also re-summarizes non-whitelisted
  `worker_claims` during ingestion before writing execution reports.
- The Python `PiAgentRuntimeAdapter` emits a legacy-compatible derived
  permission manifest from `WorkUnitContract` so older WorkUnit entry points do
  not bypass the Pi runtime boundary.
- Broad search/listing tools are intentionally not exposed by the hardened tool
  set until they have permission-aware implementations that cannot leak denied
  roots.
- Network `restricted` and unknown `unsupported_hard_policies` fail closed and
  are reported through the normal runtime output instead of being silently
  ignored.

## Phase S8: Legacy Runtime Demotion

Purpose: reduce complexity only after the new path proves the same important
guarantees.

Candidates for demotion or compatibility-only status:

- legacy MissionIR-as-worker-input path;
- heavy deterministic verifier routing where JudgeRubric is the better fit;
- broad controlled-steering proposal machinery not used by the simplified
  path;
- multi-adapter abstractions that imply non-PiWorker workers.

Rules:

- do not delete useful tests until equivalent new-path tests exist;
- preserve public compatibility surfaces if they are still used by benchmark
  reports or integrations;
- update docs before removing or demoting modules;
- keep metrics, evidence, and revision invariants.

Acceptance:

- reduced core code path for new product work;
- old path documented as legacy or compatibility;
- validation still passes;
- product integrations use the new path by default.

## Phase S9: Value Benchmark Re-Run

Purpose: validate that the new architecture improves the user-visible system,
not just internal taste.

Comparisons:

- direct PiWorker with raw/structured brief;
- PiWorker with TaskContract-derived WorkerBrief only;
- full product flow with FrontDesk, ProductIntegration, Executor, Judge;
- repair-required cases;
- revision-required cases.

Metrics:

- acceptance rate;
- repair success rate;
- revision correctness;
- wall time;
- token count and estimated cost;
- number of user turns;
- hidden acceptance pass/fail;
- judge consistency;
- boundary violations;
- product contamination in core;
- reproducibility from ledger.

Expected conclusion criteria:

- MissionForge does not need to beat direct chat on every token metric;
- it should show better contract stability, repeatability, repair discipline,
  auditability, product boundary cleanliness, and long-task control;
- if it is slower or more expensive, the report must show what value was bought
  by the extra structure.

## Migration Strategy

Use additive implementation first:

1. Add TaskContract and projections.
2. Add workspace and permission manifests.
3. Add executor/judge packet path.
4. Prove SkillFoundry integration externally.
5. Run benchmark.
6. Demote legacy runtime pieces only after evidence exists.

Avoid:

- big-bang rewrite;
- deleting legacy evidence before replacement tests exist;
- expanding old deterministic runtime while building the new path;
- mixing product-specific logic into core for convenience.

## Near-Term Development Order

The next concrete engineering goals should be:

1. Implement Phase S1 minimal TaskContract and projections.
2. Implement Phase S2 workspace and permission manifest contracts.
3. Implement Phase S3 executor/judge packet schema and role-separation tests.
4. Wire a fake/offline PiWorker path for executor and judge reports.
5. Compile one SkillFoundry fixture intent bundle into TaskContract.
6. Run a small end-to-end offline flow.

This gives the project a usable skeleton before touching deeper PiWorker
runtime hardening.
