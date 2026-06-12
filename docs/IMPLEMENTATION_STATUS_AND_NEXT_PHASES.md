# Implementation Status And Next Phases

Last updated: 2026-06-12

Status: `reference`

## Document Role

This document summarizes the current MissionForge implementation after the
PiWorker kernel cutover. Older Phase 12-23 notes remain useful as historical
and compatibility context, but the active architecture is now
TaskContract/PiWorker-first.

Its purpose is to make future development decisions easier:

- distinguish implemented first slices from the long-term target;
- keep MissionForge task-independent and PiWorker-first;
- prevent product integrations from patching MissionForge internals;
- identify the next development phases that reduce real coupling rather than
  adding broad new concepts.

This is a planning and audit reference, not a new architecture fork. The
authoritative active design documents are:

- `AGENTS.md`
- `README.md`
- `docs/MISSIONFORGE_AGENTIC_CONSTITUTION.md`
- `docs/PIWORKER_KERNEL_CUTOVER_DEVELOPMENT_PLAN.md`
- `docs/CURRENT_BRANCH_DEVELOPMENT_PLAN.md`
- `docs/API_BOUNDARY.md`
- `docs/USER_MANUAL.md`
- `docs/PRIMITIVE_REFERENCE.md`
- `docs/modules/*.md`

Update note:

Phase 17-23 work remains part of the repository history. The current branch has
since cut over to the smaller PiWorker kernel shape: product integrations
compile to `TaskContract`, MissionForge enforces deterministic boundaries,
PiWorker nodes execute and judge semantic work, and repair/revision are
durable refs-first continuations.

## Executive Position

MissionForge is now a working TaskContract-native PiWorker delegation kernel.
It can run product-neutral contracts through Pi Agent execution, independent
judge acceptance, same-contract repair, explicit contract revision, refs-first
decision ledgers, and external product integrations such as SkillFoundry.

However, the current implementation should be read as:

```text
PiWorker kernel cutover implemented and validated
```

not:

```text
the final long-running mission platform is complete
```

MissionIR, old runtime, steering, work-unit, and metric-dict surfaces remain as
compatibility and migration surfaces. New product work should start with the
TaskContract/PiWorker path.

## Current Architecture Target

The stable MissionForge substrate should now be explainable as:

```text
ProductIntegration
  -> TaskContract
  -> WorkerBrief + JudgeRubric + WorkspacePolicy + PermissionManifest
  -> PiWorker executor
  -> artifact refs + execution report
  -> independent Judge PiWorker
  -> accepted | repair | revision_required | rejected
  -> refs-first DecisionLedger + FinalPackage
```

Core rules:

1. Product semantics live in external integrations, inquiry profiles,
   `TaskContract`, judge rubrics, product hard checks, fixtures, and product
   gates.
2. Core code must not branch on product names, mission names, benchmarks, or
   customer scenarios.
3. PiWorker/PI Agent remains the only LLM worker direction.
4. The frozen `TaskContract`, or an explicit revision of it, is task truth.
5. Executor completion is boundary evidence, never acceptance.
6. Acceptance requires an independent judge role.
7. Repair preserves the same contract hash.
8. Revision creates explicit new task authority before continuation.
9. Metrics are diagnostics and cost evidence, never semantic route or
   acceptance authority.
10. Runtime and operator state should cite refs instead of embedding raw
    prompts, transcripts, provider payloads, stdout/stderr bodies, artifact
    bodies, or secrets.

## Current Implementation Status

| Area | Status | Judgment |
| --- | --- | --- |
| TaskContract/PiWorker kernel | Implemented and validated | Primary path for new product work |
| Mission IR, profiles, freeze | Compatibility kernel | Useful legacy/high-detail shape, no longer the conceptual center |
| Evidence and verifier | Implemented | Strongest architecture anchor; verifier still owns closure |
| Controlled steering | Implemented first product-neutral slice | Default remains deterministic; provider mode is opt-in |
| Phase 12 metric ledger | Implemented first slice | Typed events and projection exist; dict compatibility remains |
| Phase 13 runtime decomposition | Implemented minimal extraction | Attempt assembly and state writing moved out; runtime loop is still central |
| Phase 14 PiWorker boundary | Implemented | `PiWorkerRuntimeFactory` isolates PI Agent construction without a worker registry |
| Phase 15 mission revision | Implemented conservative workflow | Active revised contracts are consumed on resume; broader revision workflows remain future work |
| Phase 16 store interface | Implemented first slice | Protocols and JSON backend exist; not all runtime storage is wired through them |
| Phase 17 store wiring | Implemented first slice | Runtime, steering, revision, metric, and CLI writes route through `JsonWorkspaceStore` in the main durable paths |
| Phase 18 API hardening | Implemented first slice | Package root no longer re-exports active runtime contract internals |
| Phase 19 metric dict sunset | Implemented first slice | Operator diagnosis reads typed metric projection rather than loose route keys |
| Phase 20 profile extension kit | Implemented first slice | `ProfilePack` supports external data-first profile packs |
| Phase 21 run audit | Implemented first slice | `MissionRunAudit` provides refs-only stale/missing ref diagnostics |
| FrontDesk authoring | Implemented product module with spec-grill and intent-bundle slices | FrontDesk records conversation, scouts workspace/profile facts, validates semantic/intent artifacts, emits `FrontDeskIntentBundle`, supports Product Integration compilation, and now fails closed before need grilling, solution architecture, MissionIR mapping, or intent bundle authoring when LLM/PiWorker-authored artifacts are absent. |
| Product boundary | Implemented and tested | SkillFoundry is external under `integrations/skillfoundry/` |
| Product context boundary | Implemented Phase 22 first slice | `ProductInquiryProfile`, `FrontDeskIntentBundle`, `ProductIntegration`, `ProductCompileResult`, and generic `ProductGate` contracts are implemented and tested. SkillFoundry provides the reference external bridge. |
| Repair and revision | Implemented TaskContract-native lifecycle | Repair rejudges under the same contract; revision requires pending, applied, revised execution, rejudge, and revised result records |
| SkillFoundry dogfood | Implemented and live-validated | TaskContract-native facade completed a fresh live product-grade run outside core |
| Operator surface | Implemented refs-only core | Useful for run/inspect/diagnose/resume/review/frontdesk, not yet a complete visual operator product |

## Verification Snapshot

The current working tree was validated with:

```bash
MISSIONFORGE_SKIP_NPM_CI=1 ./scripts/validate.sh
# Node runtime: 8 tests passed
# Python: Ran 511 tests: OK (skipped=5)
# MissionForge validation passed

./scripts/validate_integrations.sh skillfoundry
# Ran 112 tests: OK (skipped=1)

PYTHONPATH=src python3 -m unittest tests.test_public_api_boundary tests.test_agentic_ledger tests.test_agentic_flow tests.test_piworker_call tests.test_piworker_runtime_boundary
# Ran 43 tests: OK (skipped=1)

PYTHONPATH=src python3 -m unittest tests.test_agentic_repair_controller tests.test_agentic_ledger
# Ran 36 tests: OK

git diff --check
# passed
```

Opt-in live validation also passed on 2026-06-12:

- product-neutral TaskContract live smoke:
  `tests.test_agentic_flow.AgenticFlowTests.test_live_codex_current_default_task_contract_flow_accepts`
  passed with `provider_config_source="codex_current"`;
- SkillFoundry live dogfood completed at
  `/tmp/mf-skillfoundry-live-xxxbuoj9` with
  `outcome_category=completed`, `run_status=completed`,
  `product_grade=true`, registry status `product_grade_registered`, and
  MissionForge ledger replay status `accepted`.

## Distance To The Vision

Approximate current maturity against the long-term vision:

| Vision slice | Current maturity | Notes |
| --- | --- | --- |
| Product-neutral core | High | Import-boundary tests and source search keep product branches out of core |
| PiWorker-only LLM worker direction | High | Default factories and live runtime use PiWorker/Pi Agent, not a provider zoo |
| TaskContract authority | High | New product work starts from frozen TaskContract plus projections |
| Independent acceptance | High | Executor completion cannot self-accept; judge packets/reports are separate |
| Repair/revision lifecycle | High | Same-contract repair and explicit revised-contract continuation are covered |
| Refs-first evidence | High | Ledgers, final packages, runtime projections, and dogfood reports cite refs |
| SkillFoundry product dogfood | High | Fresh live dogfood reached product-grade registration outside core |
| Legacy compatibility | Medium | MissionIR/runtime/steering paths remain and must not receive new feature gravity |
| Product-aware FrontDesk | Medium | FrontDesk intent remains important; live authoring ergonomics can improve without moving product semantics into core |

## Important Current Gaps

### 0. FrontDesk Product Context Is Implemented As A First Slice

FrontDesk can still assemble intent bundles and product compile results from
existing FrontDesk artifacts, but it no longer fabricates those artifacts
through deterministic service fallback. Generic draft behavior must sit behind
the same LLM/PiWorker-authored artifact boundary as product-aware flows.
The product-aware boundary is:

```text
FrontDesk + ProductInquiryProfile
  -> FrontDeskIntentBundle
  -> ProductIntegration
  -> ProductContract
  -> TaskContract
  -> ProductGateSpec
```

SkillFoundry proves the external Product Integration path. The remaining gap is
quality, not architecture: product-specific slot authoring is not yet wired to
live PiWorker. The first slice can preserve explicit profile defaults and
report missing slots, but it must not extract slot meaning from raw
conversation in deterministic Python. Future PiWorker-assisted slot authoring
must still be bounded by the same schemas, refs, clarification routes, and
product-neutral core boundary.

### 1. Store Interface Is Not Fully Wired

`RunStore`, `ArtifactStore`, `EventLogStore`, and `JsonWorkspaceStore` exist.
The JSON backend preserves the current file layout and validates workspace refs.

Phase 17 routed the main durable write paths through this boundary:

- runtime state;
- attempts;
- artifact hygiene;
- metric events and projection;
- revision artifacts and MissionRun activation;
- steering artifacts and decision ledger;
- CLI JSON/text result artifacts.

The remaining low-level direct file helpers are mostly layout-compatible reads,
workspace ref resolution, and artifact scanning. They should not become a second
write path. A later store-only migration can tighten those reads once it can do
so without circular imports or layout churn.

### 2. Runtime Is Still The Main Complexity Hotspot

Phase 13 deliberately avoided creating a coordinator family. That was the
right first move. `RuntimeAttemptRunner` and `RuntimeStateWriter` remove the
most repeated mechanics.

The main loop still owns verifier routing, review routing, repair, observation,
steering, result assembly, and next-action computation. This remains readable,
but future controlled steering and revision work will keep increasing pressure
unless the next extractions are chosen carefully.

### 3. Metrics Are Typed But Not Fully Removed From Compatibility Dicts

`MetricEvent`, `MetricProjection`, and `MetricStore` now exist. Operator
diagnosis reads projection flags rather than arbitrary runtime-private metric
keys.

For compatibility, `MissionResult.metrics` and `MissionRun.metrics` still carry
summary fields such as contract hash, attempt counts, revision refs, and metric
refs. Tests now mutate loose metric dict route keys to prove they do not change
operator diagnosis. The remaining work is gradual compatibility-envelope
reduction, not a runtime behavior change.

### 4. Mission Revision Is Conservative Only

The current revision workflow can safely record conservative changes such as
shrink, split, reorder, and review-required routes. Runtime consumption of the
active revised contract is repaired.

Future complex missions will need richer revision paths, including profile
changes, validator additions, scope expansion under reviewer or human authority,
and possibly new run branches. Those should be added incrementally under
authority gates, not as a general workflow engine.

### 5. Public API Surface Is TaskContract/PiWorker-First

The package root no longer re-exports `RuntimeContractView` or
`ActiveMissionContract`. Stable, experimental, and internal surfaces are
documented in `docs/API_BOUNDARY.md`.

`RuntimeEngine`, MissionIR, steering, and work-unit surfaces remain exported for
compatibility. Product integrations should default to `TaskContract`,
`WorkspacePolicy`, `PermissionManifest`, `WorkerBrief`, `JudgeRubric`,
`create_default_task_contract_flow(...)`, repair/revision primitives, and
refs-first ledgers.

### 6. Profiles Are Not Yet Strong Enough To Prevent Core Patching

The profile system is conceptually right: reusable task features should be
declared as capability or verification profiles instead of product-specific
runtime branches.

Phase 20 added `ProfilePack` and the external extension kit documented in
`docs/PROFILE_EXTENSION_KIT.md`. The built-in profile set remains small by
design; richer task semantics should live in external packs and integrations.

### 7. FrontDesk Spec-Grill Is Implemented As A First Product Slice

FrontDesk now has the spec-grill schema and product-context first slices
implemented, but the service facade no longer runs an offline deterministic
authoring path. It may scout metadata offline; when need grilling, solution
planning, MissionIR mapping, or intent bundle authoring needs LLM-authored
artifacts and they are absent, it fails closed with `configure_frontdesk_llm`.

The next FrontDesk architecture work should follow the TaskContract/PiWorker
kernel shape. Direct MissionIR mapping inside FrontDesk is compatibility
fallback behavior, while product integrations provide ProductInquiryProfile
metadata and compile final product-domain `TaskContract` authority.

Follow-on hardening after the boundary work:

- richer live PiWorker-backed node execution beyond the current contract
  helper;
- additional product dogfood scenarios outside core;
- stronger PiWorker-authored semantic extraction beyond the current
  fail-closed contract shell;
- optional visual/operator UX on top of the refs-first CLI/API.

## Phase 17-21 First-Slice Targets

### Phase 17: Store Wiring / Transaction Boundary

Intent:

Make the store boundary real enough that runtime, revision, steering, metrics,
and operator code stop growing direct backend-specific file I/O.

Primary goals:

- route new durable writes through `JsonWorkspaceStore` or small store facades;
- keep JSON as the only backend;
- add transaction-like helpers for revision activation so partial writes cannot
  move `MissionRun` to an incomplete contract;
- preserve current file layout and public refs;
- keep store protocols small.

Candidate files:

- `src/missionforge/json_store.py`
- `src/missionforge/stores.py`
- `src/missionforge/runtime_state_writer.py`
- `src/missionforge/revision_store.py`
- `src/missionforge/steering_store.py`
- `src/missionforge/state.py`
- `src/missionforge/adapters/cli.py`
- `tests/test_store_contracts.py`
- `tests/test_runtime_store_integration.py`
- new focused tests for revision atomicity and store-boundary usage

Acceptance:

- runtime state writes use the JSON store boundary for JSON/JSONL writes;
- revision request, decision, contract, mission, revision, and MissionRun update
  have a fail-closed activation order;
- operator inspect and diagnose remain compatible;
- no SQLite, remote store, HTTP service, dashboard, or migration tool;
- full validation passes.

Suggested goal prompt:

```text
/goal 使用 $metaloop 实现 Phase17 Store Wiring / Transaction Boundary。
目标是让 runtime/revision/steering/operator 的新增持久化路径统一走
JsonWorkspaceStore 或小 store facade，保留 JSON 文件布局和 refs 兼容，
并为 revision activation 增加更强的 fail-closed 写入顺序测试。不要引入
SQLite、remote store、HTTP service、dashboard、通用数据库框架或迁移工具。
```

### Phase 18: Public API And Internal Boundary Hardening

Intent:

Shrink or clearly classify package-root exports so application developers see
the stable extension surface, not runtime internals.

Primary goals:

- define public, experimental, and internal API lists;
- remove or stop re-exporting internal helpers where feasible;
- preserve compatibility for core public contracts such as `MissionIR`,
  `MissionRuntime`, `MissionResult`, `MetricEvent`, `MetricProjection`,
  `MissionRevision`, `JsonWorkspaceStore`, and store protocols;
- document how product integrations should depend on MissionForge.

Candidate files:

- `src/missionforge/__init__.py`
- `docs/API_BOUNDARY.md`
- `docs/PRODUCT_INTEGRATION_BOUNDARY.md`
- `tests/test_public_api_boundary.py`
- integration import-boundary tests

Acceptance:

- package root does not expose adapter classes or task integration symbols;
- internal runtime helper exports are either removed or explicitly documented as
  experimental;
- SkillFoundry integration continues to pass without importing internals;
- no behavior change to `MissionRuntime.run()` or `resume()`.

### Phase 19: Metric Dict Sunset Plan

Intent:

Finish measurement decoupling by making the typed metric ledger and projection
the only cross-module diagnostic contract.

Primary goals:

- keep `MissionResult.metrics` as a compatibility envelope, but reduce routing
  and diagnosis reliance on arbitrary dict keys;
- ensure operator diagnose only reads `MetricProjection` and structured run
  state;
- prevent adapter-private metric keys from becoming runtime or CLI semantics;
- add tests that mutate loose metric dict values and prove runtime/operator
  behavior does not change except for explicitly compatible fields.

Candidate files:

- `src/missionforge/runtime_state_writer.py`
- `src/missionforge/metrics.py`
- `src/missionforge/metric_store.py`
- `src/missionforge/adapters/cli.py`
- `tests/test_runtime_metric_boundaries.py`
- `tests/test_operator_metric_projection.py`
- new `tests/test_metric_dict_sunset.py`

Acceptance:

- runtime routing does not read `MetricEvent.values`;
- operator diagnosis does not read arbitrary `MissionRun.metrics` keys;
- metric projection remains deterministic and rebuildable;
- compatibility metrics cite ledger refs and active contract refs only.

### Phase 20: Profile And Validator Extension Kit

Intent:

Prevent application teams from modifying MissionForge core by giving them a
stable external way to express reusable task features.

Primary goals:

- document external profile pack shape;
- document validator pack shape and trust/authority requirements;
- allow product integrations to compile task facts into TaskContract-native
  refs, or compatibility MissionIR/profile refs when migration requires them,
  without importing into `missionforge`;
- keep profile names capability-oriented, not product-oriented;
- add a second non-SkillFoundry fixture to prove reuse.

Candidate files:

- `src/missionforge/profiles.py`
- `src/missionforge/validators.py`
- `docs/modules/profiles.md`
- new `docs/PROFILE_EXTENSION_KIT.md`
- integration fixtures under `integrations/`
- tests for external profile/validator packs

Acceptance:

- an external integration can generate TaskContract-native refs, or
  compatibility MissionIR/profile refs, without core changes;
- unknown executable validators still fail closed;
- manual and unsupported validators route to review/human/unsupported states;
- no product names appear under `missionforge.*` namespaces or core runtime
  branches.

### Phase 21: Long-Run Operation Hardening

Intent:

Make long-running complex missions safer without adding a workflow engine.

Primary goals:

- improve replay and inspectability of MissionRun, attempts, steering artifacts,
  metric events, revisions, controls, and safe points;
- define compact run summaries that do not expose raw transcripts or secrets;
- add recovery tests for interrupted runs and stale refs;
- keep operator surfaces refs-only;
- avoid daemon/dashboard-owned mutation.

Candidate areas:

- run replay summary
- current contract and revision audit
- evidence freshness checks
- stale ref diagnostics
- safe-point resume hardening
- compact operator report artifacts

Acceptance:

- a run can be inspected and diagnosed from durable refs only;
- stale or missing refs fail closed with actionable diagnosis;
- no dashboard, scheduler, daemon, or workflow DSL is introduced;
- long-run summaries do not embed raw prompts, transcripts, stdout/stderr
  bodies, provider payloads, artifact bodies, or secrets.

## What Not To Do Next

Avoid these until the Python contract surface stabilizes further:

- Rust rewrite of the runtime;
- SQLite or remote store backend;
- public worker registry or non-PI LLM worker support;
- dashboard platform or host-owned mutation;
- generic workflow engine;
- product-specific adapters under `src/missionforge/adapters`;
- business-specific metric namespaces under `missionforge.*`;
- exposing more runtime internals through the package root.

Rust or a compiled core remains a valid later direction for hashing, ref
validation, metric projection, event replay, and distribution hardening. It
should come after the Python contracts stop moving quickly.

## Development Decision Rules

When a new requirement arrives:

1. If it is a task obligation, put it in `TaskContract` or an explicit
   `TaskContractRevision`.
2. If it is workspace or tool authority, put it in `WorkspacePolicy` or
   `PermissionManifest`.
3. If it is semantic execution or judgment, delegate it to a PiWorker role.
4. If it is a completion check, make it a judge rubric, hard-check ref,
   validator, or product gate outside core.
5. If it is product-specific compilation, put it under `integrations/`.
6. If it is an external protocol, make an adapter that emits core contracts.
7. If it is diagnostic, make a metric event/projection or refs-first report.
8. If it requires runtime branching by product name, reject the design.

## Near-Term Definition Of Done

For the next development phase to be considered done:

- docs are updated before final claim;
- focused tests cover the new boundary;
- full Python tests pass;
- `MISSIONFORGE_SKIP_NPM_CI=1 ./scripts/validate.sh` passes;
- SkillFoundry integration validation passes when product-boundary behavior is
  touched;
- `git diff --check` passes;
- no product-specific runtime or adapter branch is introduced;
- no new broad abstraction is added without removing real coupling.
