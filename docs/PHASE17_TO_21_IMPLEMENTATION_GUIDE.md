# Phase 17-21 Implementation Guide

Last updated: 2026-05-29

Status: `implementation reference`

## Purpose

This guide converts `docs/IMPLEMENTATION_STATUS_AND_NEXT_PHASES.md` into a
harder development reference for the next MissionForge work.

The target is not a broader framework. The target is to make the existing
MissionForge substrate harder to accidentally couple:

```text
MissionIR + Profiles + FrozenMissionContract
  -> WorkUnitContract
  -> PiWorker / PI Agent
  -> EvidenceLedger + MetricLedger
  -> Verifier
  -> MissionRun + Revision
  -> MissionResult
```

The implementation rule is:

```text
reduce hidden coupling before adding runtime behavior
```

MissionForge remains task-independent. Product or task-specific facts must
enter through Mission IR, profile packs, validator packs, evidence refs, metric
events under `integration.*`, or external integrations. They must not enter
through `missionforge` runtime branches or adapter product branches.

## Non-Goals

These phases explicitly avoid:

- SQLite or remote stores;
- Rust or compiled-core rewrites;
- a public multi-worker registry;
- non-PI LLM workers;
- dashboard-owned mutation;
- a scheduler, daemon, or workflow DSL;
- product-specific adapters under `src/missionforge/adapters`;
- business-specific namespaces under `missionforge.*`;
- exposing lower-level runtime contract mechanics through the package root.

PiWorker / PI Agent remains the only LLM worker direction. The boundary exists
to keep runtime truth independent from worker internals, not to invite worker
pluggability.

## Phase 17: Store Wiring / Transaction Boundary

### Problem

Phase 16 introduced store protocols and `JsonWorkspaceStore`, but several
runtime paths still wrote files directly. Direct `Path.write_text()` calls make
later replay, crash recovery, store validation, and backend experiments harder.

### First-Slice Implementation

Durable writes now route through `JsonWorkspaceStore` for the paths that matter
most:

- runtime state writing;
- attempts JSONL;
- artifact hygiene JSON;
- metric projection and events;
- mission revision request, decision, mission, contract, revision, and
  MissionRun update;
- controlled steering artifacts and decision ledger;
- CLI JSON/text command artifacts.

The JSON layout is unchanged. Existing refs remain valid.

Revision activation is fail-closed:

- request and decision may be written before approval is known;
- unapproved revisions do not write `revision.json`;
- `MissionRun.current_contract_ref`, `current_contract_hash`, and
  `revision_refs` are updated only after mission, contract, and revision refs
  exist;
- a failed revision write leaves the previous active contract untouched.

### Development Rule

New durable JSON or JSONL writes should use `JsonWorkspaceStore` or a small
facade built on it. Low-level read helpers in `state.py` may remain as legacy
layout compatibility until a later store-only migration avoids circular imports.

## Phase 18: Public API And Internal Boundary Hardening

### Problem

MissionForge should expose stable extension contracts, not internal runtime
mechanics. Over-exposing internals encourages application teams to depend on
implementation details and then patch core when their task evolves.

### First-Slice Implementation

The package root no longer re-exports:

- `ActiveMissionContract`
- `RuntimeContractView`

Those remain importable from `missionforge.runtime_contract` for internal code,
but they are not part of the public root contract.

The package root keeps stable application-facing contracts such as:

- `MissionIR`
- `MissionRuntime`
- `MissionResult`
- `MetricEvent`
- `MetricProjection`
- `MissionRevision`
- `JsonWorkspaceStore`
- `RunStore`, `ArtifactStore`, `EventLogStore`
- `ProfilePack`, `ProfileRegistry`
- `MissionRunAudit`, `build_run_audit`

`RuntimeEngine` remains exported for now as an experimental low-level surface.
Do not build new product integrations around it without a specific reason.

See `docs/API_BOUNDARY.md`.

## Phase 19: Metric Dict Sunset

### Problem

`MetricEvent`, `MetricStore`, and `MetricProjection` decouple measurement from
runtime behavior, but compatibility dicts still exist on `MissionResult.metrics`
and `MissionRun.metrics`.

The risk is that loose dict keys become a hidden cross-module API.

### First-Slice Implementation

Operator diagnosis now treats typed projection and durable run state as the
diagnostic contract:

- `MetricProjection.diagnostic_flags` can influence operator diagnosis;
- arbitrary `MissionRun.metrics` keys do not route diagnosis;
- adapter-private metrics remain diagnostic payloads, not route data;
- compatibility metrics keep refs and summary values only.

Tests mutate loose metric dict values such as `repair_exhausted`,
`redesign_required`, and adapter-private route hints. Diagnosis does not change
unless the typed metric projection changes.

### Development Rule

If a diagnostic needs cross-module meaning, add a typed `MetricEvent` and a
projection rule. Do not teach runtime or CLI code to interpret an adapter-private
metric dict key.

## Phase 20: Profile And Validator Extension Kit

### Problem

If application teams cannot express reusable task features outside core, they
will patch MissionForge runtime or adapters. That would break the main product
goal: MissionForge must stay task-independent.

### First-Slice Implementation

`ProfilePack` now gives external integrations a concrete data shape:

```text
ProfilePack
  -> capability profiles
  -> verification profiles
  -> ProfileRegistry
  -> MissionIR expansion / freeze
```

External packs can be composed with or without built-ins. They can declare:

- capability-oriented constraints;
- required artifacts;
- evidence requirements;
- validator language;
- review questions;
- known gaps.

They do not add runtime branches. They only change the frozen contract through
deterministic profile expansion.

Validator behavior stays fail-closed:

- unknown executable validator implementations still raise
  `ContractValidationError`;
- manual validators route to reviewer or human authority states;
- unsupported validators route to `unsupported_verification_spec`;
- profile names should describe capability semantics, not products.

See `docs/PROFILE_EXTENSION_KIT.md`.

## Phase 21: Long-Run Operation Hardening

### Problem

Long-running missions need compact recovery and inspection surfaces, but adding
a dashboard, scheduler, or workflow engine would add the wrong kind of
complexity.

### First-Slice Implementation

`MissionRunAudit` and `build_run_audit()` provide a refs-only health summary for
a durable run.

The audit checks:

- MissionRun ref;
- attempts ref;
- artifact hygiene ref;
- current contract ref and hash;
- revision refs;
- metric event and projection refs;
- steering artifact refs;
- safe point refs;
- artifact refs.

It reports:

- `passed`;
- `missing_refs`;
- `stale_refs`;
- compact diagnostics;
- ref checks with names and statuses.

It does not embed:

- raw prompts;
- transcripts;
- provider payloads;
- stdout or stderr bodies;
- artifact bodies;
- secrets.

CLI inspect includes the run audit. CLI diagnose fails closed with
`stale_or_missing_refs` when the audit detects missing or stale durable refs.

## Development Decision Rules

Use these rules when adding new behavior:

1. If it is a task fact, put it in `MissionIR`.
2. If it is a reusable task feature, make it a `CapabilityProfile`.
3. If it is a verification language declaration, make it a
   `VerificationProfile`.
4. If it is an external profile bundle, make a `ProfilePack`.
5. If it is a completion check, make a validator or manual gate.
6. If it is evidence, store or reference it through the evidence boundary.
7. If it is diagnostic, emit a `MetricEvent` and project it.
8. If it changes a frozen contract, make a mission revision.
9. If it writes durable state, use `JsonWorkspaceStore` or a facade.
10. If it requires runtime branching by product name, reject the design.

## Acceptance Map

| Phase | Acceptance Signal |
| --- | --- |
| 17 | runtime, steering, revision, and CLI durable writes route through `JsonWorkspaceStore`; revision activation is fail-closed |
| 18 | package root does not expose adapter/product symbols or active runtime contract internals |
| 19 | operator diagnosis reads metric projection, not arbitrary metric dict route keys |
| 20 | external profile packs compose MissionIR and validator language without core product branches |
| 21 | durable runs can be audited from refs only; stale refs produce fail-closed operator diagnosis |

## Verification Commands

Focused tests:

```bash
PYTHONPATH=src python3 -m unittest \
  tests/test_runtime_store_integration.py \
  tests/test_mission_revision_workflow.py \
  tests/test_public_api_boundary.py \
  tests/test_metric_dict_sunset.py \
  tests/test_operator_metric_projection.py \
  tests/test_profile_extension_kit.py \
  tests/test_run_audit.py
```

Full validation:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
MISSIONFORGE_SKIP_NPM_CI=1 ./scripts/validate.sh
./scripts/validate_integrations.sh skillfoundry
git diff --check
```
