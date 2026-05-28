# Follow-On Goals

This document defines the next `/goal` contracts after the deterministic
runtime kernel.

The Phase 1 through Phase 5 kernel is complete when the runtime vertical slice
is `completed_verified`. Phase 6 work must be started as separate follow-on
goals so adapter concerns do not leak back into MissionForge core.

## Ordering

Recommended order:

```text
Goal 6.0: Adapter Boundary Preflight
Goal 6A: Faux PiWorker Adapter
Goal 6B: SkillFoundry MissionIR Compiler
Goal 6C: Optional Host Adapter Shell
```

Only Goal 6.0 and Goal 6A are prerequisites for a real PiWorker smoke. Goal 6B
can run after 6.0, but it must not import SkillFoundry into MissionForge core.
Goal 6C is optional and should remain read-only/control-intent oriented.

## Global Adapter Rules

- MissionForge core must not import adapter modules.
- Adapters consume and produce MissionForge contracts.
- No adapter may mutate a frozen mission contract.
- Adapter output is evidence, not acceptance.
- Completion still comes from `VerificationResult.status`.
- Product, host, provider, and worker names must not become runtime branches.
- Live resources require explicit follow-on scope and focused smoke tests.

## Goal 6.0: Adapter Boundary Preflight

Status: `completed_verified`

Intent:

```text
Define adapter package boundaries, import rules, shared adapter contracts, and
tests that prove MissionForge core remains adapter-free.
```

Primary documentation:

- `docs/COMPONENT_DEVELOPMENT_PLAN.md`
- `docs/COMPONENT_ACCEPTANCE_MATRIX.md`
- `docs/modules/adapter_contracts.md`
- `docs/modules/piworker.md`
- `docs/modules/host_adapters.md`
- `docs/modules/skillfoundry_adapter.md`

Primary modules, if implemented in this goal:

- `src/missionforge/adapters/__init__.py`
- `src/missionforge/adapters/contracts.py`
- `tests/test_adapter_import_boundaries.py`

Non-goals:

- no real PiWorker execution
- no SkillFoundry adapter behavior
- no LangGraph adapter
- no HTTP service
- no live LLM

Acceptance:

- adapter package exists outside core runtime imports
- core modules do not import `missionforge.adapters`
- package root does not import or re-export adapter modules
- shared adapter contracts are refs-only and JSON-compatible
- adapter contracts reject raw payload, body, prompt, transcript, and
  secret-shaped fields
- default tests pass
- docs define the next 6A and 6B goals clearly enough to start

Suggested `/goal` prompt:

```text
/goal 使用 $metaloop 按 docs/FOLLOW_ON_GOALS.md 的 Goal 6.0 推进
MissionForge Adapter Boundary Preflight。只定义 adapter package 边界、
import-boundary tests 和共享 adapter contracts；不要接真实 PiWorker、
SkillFoundry、LangGraph、HTTP 或 live LLM。
```

## Goal 6A: Faux PiWorker Adapter

Status: `completed_verified`

Intent:

```text
Implement a deterministic faux PiWorker adapter that consumes committed
WorkUnitContract objects, maps worker-like events into evidence records and
ExecutionReport objects, and proves the adapter can replace FakeWorker without
granting acceptance authority.
```

Primary modules:

- `src/missionforge/adapters/piworker.py`
- `src/missionforge/workers.py`
- `tests/test_piworker_adapter_contracts.py`
- `tests/test_faux_piworker_adapter.py`
- `tests/test_piworker_import_boundaries.py`

Public contracts:

- `WorkerAdapter`
- `WorkerAdapterResult`
- `PiWorkerInput`
- `PiWorkerEvent`
- `PiWorkerOutput`
- `PiWorkerMetrics`
- `ContractAdjustmentEvidence`

Non-goals:

- no live PiWorker process
- no provider credentials
- no live LLM steering
- no multi-worker abstraction
- no acceptance or verifier replacement inside the adapter
- no copied PI source unless attribution and license handling are explicit

Acceptance:

- adapter consumes `WorkUnitContract`, not `MissionIR` or `SteeringProposal`
- adapter rejects output outside `WorkUnitContract.allowed_scope`
- event stream maps to evidence refs
- execution report is refs-only
- provider/tool/cache metrics are recorded as metrics/evidence only
- worker-requested contract adjustment becomes evidence, not mutation
- verifier status still owns completion
- MissionForge core has no PiWorker imports

Implemented in this goal:

- generic worker adapter protocol in `src/missionforge/workers.py`
- deterministic faux PiWorker adapter in
  `src/missionforge/adapters/piworker.py`
- contract round-trip tests, adapter behavior tests, and PiWorker-specific
  import-boundary tests
- refs-only `ExecutionReport` output with event evidence refs and optional
  contract-adjustment evidence refs
- verifier authority regression proving adapter `completed` status and metrics
  do not grant completion

Suggested `/goal` prompt:

```text
/goal 使用 $metaloop 按 docs/FOLLOW_ON_GOALS.md 的 Goal 6A 实现
MissionForge Faux PiWorker Adapter。实现 deterministic faux adapter、
event-to-evidence mapping、refs-only ExecutionReport、import-boundary tests。
不要接 live PiWorker、provider credentials、live LLM、LangGraph、HTTP 或
SkillFoundry adapter。
```

## Goal 6B: SkillFoundry MissionIR Compiler

Status: `completed_verified`

Intent:

```text
Implement a SkillFoundry-facing adapter that compiles FrontDesk-style artifacts
into MissionIR and profile refs, while keeping SkillFoundry product semantics
outside MissionForge core.
```

Primary modules:

- `src/missionforge/adapters/skillfoundry.py`
- `tests/test_skillfoundry_adapter_contracts.py`
- `tests/test_skillfoundry_compiler.py`
- `tests/test_skillfoundry_import_boundaries.py`

Public contracts:

- `SkillFoundrySourceBundle`
- `SkillFoundryCompileResult`
- `FrontDeskArtifactRef`
- `SkillPackageTarget`

Non-goals:

- no SkillFoundry runtime dependency in MissionForge core
- no registry publishing
- no product-specific runtime branches
- no capability bundle special cases in `RuntimeEngine`
- no live LLM
- no PiWorker execution

Acceptance:

- FrontDesk artifacts compile into valid `MissionIR`
- capability-bundle behavior is expressed through capability and verification
  profiles
- compile output is refs-only
- adapter rejects raw transcript input unless represented as an allowed
  sanitized source ref
- generated MissionIR freezes deterministically
- MissionForge core has no SkillFoundry imports

Implemented in this goal:

- deterministic SkillFoundry adapter contracts and compiler in
  `src/missionforge/adapters/skillfoundry.py`
- FrontDesk-style fixture compiler producing valid MissionIR and frozen
  contract refs
- refs-only `SkillFoundryCompileResult`
- raw transcript and raw payload/body/prompt field rejection
- fail-closed rejection for source bundles that omit capability profile refs
- tests proving profile-based capability behavior, deterministic freezing, and
  SkillFoundry import boundaries

Suggested `/goal` prompt:

```text
/goal 使用 $metaloop 按 docs/FOLLOW_ON_GOALS.md 的 Goal 6B 实现
SkillFoundry MissionIR Compiler。只做 adapter 层把 FrontDesk artifacts 编译成
MissionIR/profile refs，并证明 core 不 import SkillFoundry。不要做 registry
publishing、runtime product branch、live LLM、PiWorker 或 HTTP。
```

## Goal 6C: Optional Host Adapter Shell

Status: `completed_verified`

Intent:

```text
Expose MissionForge through optional host shells without making those hosts core
runtime dependencies.
```

Candidate modules:

- `src/missionforge/adapters/cli.py`
- `src/missionforge/adapters/langgraph.py`
- `src/missionforge/adapters/observation.py`

Non-goals:

- no required LangGraph dependency
- no HTTP service unless explicitly split into its own goal
- no host-owned verifier or runtime semantics
- no dashboard-owned mutation

Acceptance:

- Python API remains the primary integration surface
- CLI or host shell passes `MissionIR` in and receives `MissionResult` out
- observation surfaces are read-only
- control surfaces write `ControlRequest` intent only
- optional host dependencies are isolated from core imports

Implemented in this goal:

- optional CLI/Python shell in `src/missionforge/adapters/cli.py`
- read-only observation and control-intent writer in
  `src/missionforge/adapters/observation.py`
- host shell passes MissionIR refs into `MissionRuntime` and writes
  MissionResult refs out
- observation creates read-only `MissionRunView` summaries
- control writes explicit `ControlRequest` halt intent only
- tests proving no required LangGraph/HTTP/network dependency and no core host
  adapter imports

Suggested `/goal` prompt:

```text
/goal 使用 $metaloop 按 docs/FOLLOW_ON_GOALS.md 的 Goal 6C 设计并实现
MissionForge optional host adapter shell。保持 host adapter 可选，core 不依赖
LangGraph/HTTP；observation read-only，control 只写 ControlRequest intent。
```

## Review Policy

Use independent reviewer gates for every follow-on goal because adapter work
changes trust and dependency boundaries.

Reviewers must check:

- import boundaries
- refs-only result boundaries
- evidence trust semantics
- no acceptance shortcut
- no product-specific runtime branch
- no live resource use outside the goal contract

## Completion Standard

A follow-on goal is complete only when:

- focused tests pass
- default tests pass
- `git diff --check` passes
- docs-last updates are complete
- import-boundary checks prove core remains independent
- the goal's non-goals remain unimplemented
