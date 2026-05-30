# MissionForge Value Benchmark Pilot 01 Smoke Report

Last updated: 2026-05-30

Status: smoke executed, pilot expansion stopped.

## Run IDs

- sandbox diagnostic run: `vb-pilot-01-smoke-20260530T000000Z`
- live smoke run: `vb-pilot-01-smoke-20260530T010000Z`

The sandbox diagnostic run failed all live worker calls with connection errors.
The live smoke run used escalated network access and is the meaningful result.

Run artifacts are local under:

```text
benchmarks/runs/vb-pilot-01-smoke-20260530T010000Z/
```

Run artifacts are intentionally ignored by git through `benchmarks/runs/`.

## Outcome

The smoke run did not pass. The 3-seed pilot was not run.

| mode | accepted | comparable | outcome |
| --- | ---: | ---: | --- |
| `direct_piworker_chat` | 0 | 1 | produced package files, failed hidden acceptance |
| `missionforge_runtime_only` | 1 | 1 | accepted |
| `missionforge_full_product_flow` | 0 | 1 | failed closed during FrontDesk |

Runtime-only was the only accepted mode in this smoke.

## What Worked

- Live PiWorker configuration was present.
- The neutral fixture `complex-method-skill-001` was runnable.
- Hidden acceptance refs were not passed into worker-visible task payloads.
- Hidden acceptance results were joined after execution.
- Required run-level artifacts were produced:
  - `manifest.json`
  - `aggregate.json`
  - `report.md`
  - `mode_comparisons.json`
  - `table_data.json`
  - `multiseed_result.json`
  - `pilot_result_packet.json`

## Findings

### 1. Runtime-Only Is Currently The Only Clean Accepted Path

`missionforge_runtime_only` produced all required package refs and passed hidden
acceptance. This proves the runtime/product contract path can close this fixture
when the MissionIR/product contract is already prepared.

### 2. Direct Baseline Is Not Fair Enough Yet

`direct_piworker_chat` produced all requested files, but the generated
`skillfoundry.bundle.json` did not match the SkillFoundry bundle schema expected
by the fixture. This is not enough evidence that direct chat is weak; it also
shows that the current direct baseline did not receive a sufficiently explicit
public product contract.

Before scaling, direct mode should receive worker-safe public product
requirements through generic benchmark inputs, not hidden acceptance checks and
not MissionForge runtime internals.

### 3. Hidden Leak Pattern Is Too Ambiguous

The smoke leak scan flagged occurrences of the phrase `provider payload`. In
several generated artifacts this was a policy statement, not an embedded
provider payload. The benchmark should distinguish sensitive sentinel markers
or raw provider bodies from harmless policy wording.

Before rerun, hidden checks and leak scans should avoid failing merely because a
worker says it will not store provider payloads.

### 4. Full Product Flow Needs Stronger Live Node Contracts

`missionforge_full_product_flow` failed at the first FrontDesk node. The live
NeedGriller wrote artifacts, but the node did not produce schema-valid
FrontDesk outputs and failed closed before ProductIntegration compilation.

The generated output shows two protocol gaps:

- the live node spec did not expose enough exact output schema guidance;
- the conversation/source-admission rules caused the worker to treat the user
  request as unavailable for need extraction, even though FrontDesk is supposed
  to use the conversation for elicitation while keeping it out of product truth.

Before rerun, FrontDesk PiWorker node specs should make this distinction
explicit and include compact schema templates for node outputs.

### 5. Cost/Time Winner Logic Had A Real Bug

The smoke comparison selected `direct_piworker_chat` as
`winner_by_cost_per_acceptance` because zero-accepted modes had zero cost per
accepted deliverable. That is not a valid accepted-deliverable winner.

This has been repaired after the smoke: cost/time winners now ignore modes with
`comparable_accepted_count == 0`.

## Required Repairs Before Rerun

1. Make direct baseline worker-visible inputs include a clear public product
   contract for required SkillFoundry bundle structure.
2. Tighten leak checks so policy wording does not count as leaked provider
   payload content.
3. Add schema guidance to live FrontDesk PiWorker node specs, starting with
   NeedGriller and SolutionArchitect.
4. Preserve the repaired winner rule: cost/time winners must require at least
   one comparable accepted deliverable.
5. Rerun Stage 1 smoke only after these repairs.

## Decision

Do not run the 3-seed pilot yet.

The first smoke was useful because it validated that the harness can execute
live and that runtime-only can close the fixture, but it also showed the direct
baseline and full product flow need protocol repairs before the comparison is
fair enough to scale.
