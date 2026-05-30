# MissionForge Value Benchmark Pilot 01

Last updated: 2026-05-30

This document defines the first executable value experiment for MissionForge.
It is a pilot, not a final statistical claim.

## Purpose

Validate that the value-benchmark harness can run a real comparison between:

- direct PiWorker chat
- MissionForge runtime-only
- MissionForge full product flow

The first question is not "does MissionForge always win". The first question is
whether the benchmark pipeline can produce a defensible, leak-free comparison
on one representative task with the same worker, same budget, and same task
text.

## Pilot Hypothesis

- Direct chat is the baseline.
- Runtime-only isolates the value of compiled MissionIR, verifier closure, and
  accepted-deliverable accounting.
- Full product flow should add value when vague user intent needs FrontDesk,
  ProductIntegration, and ProductGate.
- Non-comparable trials must not influence cost/time winners or comparison
  metrics.

## Pilot Fixture

Use the neutral dogfood fixture:

- task: `benchmarks/tasks/complex-method-skill-001/task.json`
- user statement: colloquial productization request for a reusable local skill
  package
- hidden checks: evaluator-only
- public checks: worker-safe
- blind review rubric: present

The worker-visible task payload must not contain Codexarium hints. The task id,
task family, and refs are neutral on purpose.

## Modes Under Test

Run these modes against the same `BenchmarkTask`:

- `direct_piworker_chat`
- `missionforge_runtime_only`
- `missionforge_full_product_flow`

## Required Environment

- Current branch: `value-benchmark`
- Current commit baseline: `3b770e3`
- Same PiWorker stack for all arms
- Same workspace snapshot for all arms
- Same budget for all arms
- No hidden checks in worker-visible prompts
- No raw prompt/transcript/provider payload/stdout/stderr/secrets in public
  artifacts

If live PiWorker configuration is unavailable, stop closed and report the
blocking environment gap. Do not switch to a different production worker.

## Execution Shape

Run the pilot in two stages.

### Stage 1: Smoke

- one seed only
- confirm all three modes can execute end to end
- confirm hidden acceptance is joined after execution
- confirm reports and aggregates are written
- confirm public artifacts stay refs-first and leak-free

### Stage 2: Pilot

- three seeds if smoke passes
- use the same task fixture and the same mode set
- compare only the resulting accepted-deliverable metrics

## Required Artifacts

For each run, the worker should verify that these exist under
`benchmarks/runs/<run_id>/`:

- `manifest.json`
- `aggregate.json`
- `report.md`
- `mode_comparisons.json`
- `table_data.json`
- `multiseed_result.json`
- hidden acceptance result refs for each trial

## Primary Metrics

Use these metrics as the main readout:

- `success_rate_within_budget`
- `comparable_accepted_count`
- `cost_per_accepted_deliverable_usd`
- `avg_time_to_accepted_deliverable_ms`
- `p95_time_to_accepted_deliverable_ms`
- `non_comparable_trial_count`
- `repair_count`
- `product_gate_status`
- `frontdesk_node_count`
- `frontdesk_worker_call_count`
- `product_clarification_count`
- `product_acceptance_coverage_passed`

## Decision Rules

### Pass for pilot expansion

- at least one mode produces accepted deliverables
- hidden acceptance is joined only after the worker run
- comparison metrics are stable and readable
- no leak of raw prompt/transcript/provider payload/secrets into public outputs

### Stop and repair

- any public artifact leaks hidden prompt or provider content
- a mode becomes non-comparable because of environment failure
- the direct baseline cannot be executed cleanly
- no mode can produce accepted deliverables on the smoke run
- aggregate/report surfaces still let non-comparable trials influence comparison
  winners

### Stop and redesign

- the pilot shows the baseline is too weak to be a fair comparison
- the task fixture is too small or too specific to produce signal
- the live environment cannot support a same-worker comparison

## What The Worker Should Report Back

The worker should return a short result packet with:

- the run id used
- whether smoke passed
- whether the 3-seed pilot passed
- per-mode accepted/comparable counts
- the winner by success rate, cost per accepted deliverable, and accepted
  deliverable time
- whether any artifact leaked hidden data
- whether any mode was non-comparable and why
- the main next step recommendation

## Interpretation

Do not treat this pilot as a final MissionForge value verdict.

The goal is to establish a clean comparative harness first. Only after this
pilot is stable should we expand to additional fixtures and larger sample sizes.
