# Implementation Status And Next Phases

Last updated: 2026-05-29

Status: `reference`

## Document Role

This document summarizes the current MissionForge implementation after the
Phase 12-16 decoupling work and the Phase 15 runtime revision repair.

Its purpose is to make future development decisions easier:

- distinguish implemented first slices from the long-term target;
- keep MissionForge task-independent and PiWorker-first;
- prevent product integrations from patching MissionForge internals;
- identify the next development phases that reduce real coupling rather than
  adding broad new concepts.

This is a planning and audit reference, not a new architecture fork. The
authoritative design documents remain:

- `docs/ARCHITECTURE.md`
- `docs/MISSION_IR.md`
- `docs/DESIGN_PROGRAM.md`
- `docs/PRODUCT_INTEGRATION_BOUNDARY.md`
- `docs/PHASE12_TO_16_DECOUPLING_ROADMAP.md`
- `docs/PHASE15_REVISION_RUNTIME_REPAIR_PLAN.md`
- `docs/PHASE17_TO_21_IMPLEMENTATION_GUIDE.md`
- `docs/modules/*.md`

Update note:

Phase 17-21 first slices have now been implemented. This document remains the
status and rationale record; `docs/PHASE17_TO_21_IMPLEMENTATION_GUIDE.md` is
the concise development reference for the landed boundaries and follow-on
rules.

## Executive Position

MissionForge is now a working generic mission runtime substrate. It can run
structured Mission IR through PiWorker/PI Agent execution, evidence gates,
controlled steering proposals, verifier-owned closure, metric projection, and
conservative mission revision.

However, the current implementation should be read as:

```text
Phase 12-16 first slices implemented
```

not:

```text
the final long-running mission platform is complete
```

The architecture direction is right. The next work should be hardening and
convergence, not a new layer of broad abstractions.

## Current Architecture Target

The stable MissionForge substrate should remain explainable as:

```text
MissionIR + Profiles + FrozenMissionContract
  -> WorkUnitContract
  -> PiWorker
  -> EvidenceLedger + MetricLedger
  -> Verifier
  -> MissionRun + Revision
  -> MissionResult
```

Core rules:

1. Mission semantics live in Mission IR, profiles, validators, evidence
   requirements, and external integrations.
2. Runtime code must not branch on product names, mission names, benchmarks, or
   customer scenarios.
3. PiWorker/PI Agent remains the only LLM worker direction.
4. Metrics are diagnostics, never acceptance evidence or route authority.
5. LLM output is proposal, hypothesis, or review evidence; it is never closure.
6. Revision is a controlled state transition, not a workflow engine.
7. JSON remains the default backend until store protocols are stable enough to
   justify another backend.
8. Users should extend MissionForge through profiles, validators, evidence
   contracts, and external integrations, not by modifying runtime or adapters.

## Current Implementation Status

| Area | Status | Judgment |
| --- | --- | --- |
| Mission IR, profiles, freeze | Implemented kernel | Sound base, but profile ecosystem is still small |
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
| FrontDesk authoring | Implemented product module | Natural-language authoring now produces approved MissionIR, freeze manifests, CLI handoff, runtime feedback, and SkillFoundry dogfood |
| Product boundary | Implemented and tested | SkillFoundry is external under `integrations/skillfoundry/` |
| Operator surface | Implemented refs-only core | Useful for run/inspect/diagnose/resume/review/frontdesk, not yet a complete visual operator product |

## Verification Snapshot

The current working tree was validated with:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
# Ran 292 tests: OK (skipped=2)

MISSIONFORGE_SKIP_NPM_CI=1 ./scripts/validate.sh
# Node runtime: 4 tests passed
# Python: Ran 232 tests: OK (skipped=2)
# MissionForge validation passed

./scripts/validate_integrations.sh skillfoundry
# Ran 48 tests: OK (skipped=1)

PYTHONPATH=src python3 -m unittest \
  tests/test_frontdesk_schema.py \
  tests/test_frontdesk_state.py \
  tests/test_frontdesk_workspace.py \
  tests/test_frontdesk_compiler.py \
  tests/test_frontdesk_freeze_gate.py \
  tests/test_frontdesk_profile_integration.py \
  tests/test_frontdesk_service.py \
  tests/test_frontdesk_elicitor.py \
  tests/test_frontdesk_planner.py \
  tests/test_frontdesk_auditor.py \
  tests/test_frontdesk_llm_boundaries.py \
  tests/test_frontdesk_cli.py \
  tests/test_frontdesk_runtime_feedback.py
# Ran 44 tests: OK

PYTHONPATH=src python3 -m unittest tests/test_adapter_import_boundaries.py tests/test_pi_agent_runtime_import_boundaries.py tests/test_piworker_runtime_boundary.py
# Ran 10 tests: OK

PYTHONPATH=src python3 -m unittest tests/test_metrics_contracts.py tests/test_metric_store.py tests/test_runtime_metric_boundaries.py tests/test_operator_metric_projection.py tests/test_store_contracts.py tests/test_json_store_backend.py tests/test_runtime_store_integration.py tests/test_mission_revision_contracts.py tests/test_mission_revision_workflow.py tests/test_revision_authority_boundaries.py tests/test_runtime_revision_preservation.py tests/test_operator_revision_surface.py tests/test_runtime_revision_consumption.py
# Ran 25 tests: OK

git diff --check
# passed
```

## Distance To The Vision

Approximate current maturity against the long-term vision:

| Vision slice | Current maturity | Notes |
| --- | --- | --- |
| Task-independent core | High | Import-boundary tests protect the product boundary |
| PiWorker-only LLM worker direction | High | Construction is isolated behind a PiWorker-specific factory |
| Verifier-owned closure | High | Worker and LLM output still cannot close missions |
| Metric decoupling | Medium-high | Ledger/projection drives operator diagnosis; compatibility dicts remain only as envelopes |
| Runtime maintainability | Medium | Helpers exist, but `RuntimeEngine` remains the main complexity hotspot |
| Mission revision | Medium | Conservative durable revision works; richer contract evolution is future work |
| Store abstraction | Medium | Main durable writes route through `JsonWorkspaceStore`; legacy state read helpers still preserve layout compatibility |
| Arbitrary long-running complex tasks | Medium | Core primitives, profile packs, run audit, and stale-ref diagnosis exist; replay and richer revision remain future work |

## Important Current Gaps

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

### 5. Public API Surface Is Slightly Too Wide

The package root no longer re-exports `RuntimeContractView` or
`ActiveMissionContract`. Stable, experimental, and internal surfaces are
documented in `docs/API_BOUNDARY.md`.

`RuntimeEngine` remains exported as an experimental low-level surface. Product
integrations should default to `MissionRuntime`, Mission IR, profiles,
validators, evidence refs, metric events, and mission revision.

### 6. Profiles Are Not Yet Strong Enough To Prevent Core Patching

The profile system is conceptually right: reusable task features should be
declared as capability or verification profiles instead of product-specific
runtime branches.

Phase 20 added `ProfilePack` and the external extension kit documented in
`docs/PROFILE_EXTENSION_KIT.md`. The built-in profile set remains small by
design; richer task semantics should live in external packs and integrations.

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
- allow product integrations to compile task facts into MissionIR and profile
  refs without importing into `missionforge`;
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

- an external integration can generate MissionIR plus profile refs without core
  changes;
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

1. If it is a task fact, put it in `MissionIR`.
2. If it is a reusable task feature, make it a profile.
3. If it is a completion check, make it a validator or evidence requirement.
4. If it is product-specific compilation, put it under `integrations/`.
5. If it is an external protocol, make an adapter that emits core contracts.
6. If it is diagnostic, make a metric event and projection.
7. If it changes a frozen contract, make a mission revision.
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
