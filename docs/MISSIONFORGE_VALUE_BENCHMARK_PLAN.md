# MissionForge Value Benchmark Plan

Last updated: 2026-05-30

Status: planning standard for value-validation development.

## Purpose

MissionForge is valuable only if it improves accepted deliverable outcomes over
strong ordinary chat-agent usage. The benchmark must therefore measure whether
MissionForge is faster, cheaper, more stable, easier to recover, and less likely
to leak defects or private context than a direct PiWorker chat workflow.

This document defines the execution plan for building that benchmark. Later
development should follow this plan unless a new measurement finding proves the
plan wrong.

## Core Question

The benchmark answers one question:

```text
With the same PiWorker model, tools, workspace, task, and budget, does the
MissionForge workflow produce accepted deliverables with better cost, time,
stability, and defect-leakage behavior than direct chat?
```

The comparison is not:

```text
MissionForge worker vs another worker
```

It is:

```text
PiWorker direct chat
  vs
MissionForge orchestration using the same PiWorker
```

PiWorker remains the only production LLM worker. The benchmark must not
introduce a general worker marketplace, alternate LLM abstraction, or
non-PiWorker production path.

## Value Hypotheses

MissionForge should beat direct chat when tasks have any of these properties:

- user intent starts vague, incomplete, or self-contradictory;
- product-specific acceptance is stricter than ordinary code completion;
- long execution needs verifier-driven repair, resume, and evidence tracking;
- product semantics must compile into generic MissionIR without polluting core;
- repeated task variants need comparable metrics and failure diagnosis;
- raw conversation, private context, and product internals must stay out of
  runtime artifacts.

MissionForge may not beat direct chat on tiny tasks. That is acceptable. The
benchmark must show where the protocol overhead pays for itself and where it
does not.

## Existing-State Audit

### What Is Already Ready

The current codebase already has several important measurement surfaces:

- `workers/pi-agent-runtime` is the dedicated PI Agent runtime worker.
- `EvidenceRecorder` writes PI runtime events, sessions, metrics, and
  savepoints.
- Current PI runtime metrics include turn count, tool count, token count,
  input/output tokens, commands run, tests run, stop reason, and duration.
- PI Agent events expose `turn_start`, `turn_end`, `message_*`, and
  `tool_execution_*`, enough to derive per-tool latency and failures.
- `@earendil-works/pi-ai` usage objects include input, output, cache read,
  cache write, total token, and cost fields.
- `MetricEvent`, `MetricProjection`, and `MetricStore` already provide a
  refs-first metric ledger.
- `missionforge.worker.pi_agent` is already a supported metric namespace.
- Runtime metric-boundary tests already protect against runtime routing based
  on adapter-private metric values.
- `ProductIntegration` and `ProductGate` provide generic refs-only product
  envelopes.
- FrontDesk now treats LLM/PiWorker authoring as mandatory for semantic work
  and fails closed without PiWorker-authored artifacts.
- SkillFoundry lives under `integrations/skillfoundry` and is the correct
  reference product integration.

### What Is Not Ready Yet

The benchmark cannot make a defensible value claim until these gaps are closed
or explicitly marked as experimental:

- There is no direct PiWorker baseline runner that avoids MissionForge WorkUnit
  prompts while keeping the same model and tools.
- PI runtime metrics do not yet persist cache tokens, cost, tool latency, tool
  error count, command exit summaries, or time-to-first-artifact.
- There is no benchmark trial schema or aggregate report schema.
- There is no shared trial harness that can run both direct chat and
  MissionForge modes from the same task fixture.
- There is no standard hidden acceptance/reviewer pack format.
- FrontDesk live PiWorker authoring must be wired before full FrontDesk
  benchmark runs are meaningful.
- SkillFoundry blocking product acceptance must compile into MissionIR or a
  MissionIR-visible gate before product-grade benchmark claims are meaningful.
- ProductGate output is not yet joined into a cross-mode benchmark summary.
- Cost currently needs either provider-reported `usage.cost` capture or a
  deterministic pricing table fallback.

## Non-Negotiable Benchmark Rules

1. Both arms use the same PiWorker stack, model, provider, reasoning level, tool
   set, workspace snapshot, task text, and budget.
2. Direct chat must be a strong baseline, not a strawman.
3. Direct chat may ask clarifying questions if the task protocol allows user
   interaction.
4. MissionForge may use FrontDesk, ProductIntegration, MissionIR, runtime,
   verifier, repair, and ProductGate only through their normal contracts.
5. Direct chat and MissionForge must be evaluated by the same acceptance
   checks, hidden tests, ProductGate policy, and review rubric.
6. Metrics are diagnostics, not acceptance evidence.
7. Worker self-report is never acceptance.
8. Raw prompts, raw transcripts, provider payloads, stdout/stderr bodies,
   artifact bodies, and secrets must not be embedded in metric events.
9. Codexarium may be the first demanding benchmark subject, but benchmark code
   must not contain Codexarium-specific branches.
10. SkillFoundry product semantics must stay under `integrations/skillfoundry`.
11. MissionForge core must stay task-independent.
12. Any live-provider benchmark is opt-in and must record provider, model,
    reasoning, budget, and environment metadata without serializing secrets.

## Compared Modes

### Mode A: Direct PiWorker Chat

Purpose:

```text
Measure what a strong ordinary PiWorker coding/chat workflow can do without
MissionForge orchestration.
```

Required properties:

- uses the same PI Agent packages as MissionForge;
- uses the same workspace guard and tool family where possible;
- does not use MissionIR, WorkUnitContract, FrontDesk, ProductIntegration,
  verifier repair, or ProductGate feedback during the run;
- may receive the same user task text and allowed source refs;
- writes final artifacts into the same declared output area;
- writes comparable event, session, metric, changed-ref, and summary artifacts.

Direct chat should not run through `runMissionForgePiAgent()` because that
injects MissionForge WorkUnit prompts. It needs a dedicated benchmark-only
direct runner that uses PiWorker but not MissionForge runtime semantics.

### Mode B: MissionForge Runtime Only

Purpose:

```text
Isolate the value of MissionIR, WorkUnit contracts, verifier closure, repair,
resume, and metric ledger when the user intent is already compiled.
```

Required properties:

- starts from a prepared MissionIR fixture;
- bypasses FrontDesk;
- runs through normal MissionForge runtime and PiWorker adapter;
- uses the same acceptance checks as direct chat.

This mode is an ablation. It helps separate runtime value from FrontDesk value.

### Mode C: MissionForge Full Product Flow

Purpose:

```text
Measure the full product experience: messy user statement -> FrontDesk ->
ProductIntegration -> MissionIR -> runtime -> verifier repair -> ProductGate.
```

Required properties:

- starts from the same natural-language user pain as direct chat;
- uses PiWorker-backed FrontDesk nodes;
- uses ProductInquiryProfile data, not core product branches;
- compiles through the external product integration;
- runs through MissionForge runtime;
- closes through the same generic verifier plus product gate.

For the first product benchmark, this should be SkillFoundry. Codexarium-like
tasks can be used as difficult task fixtures, but Codexarium-specific knowledge
must not be encoded in MissionForge or SkillFoundry benchmark logic.

## Primary Metrics

The benchmark should optimize for accepted deliverables, not attractive logs.

### Outcome Metrics

- `accepted`: final artifact passed all required gates.
- `generic_verifier_passed`: MissionForge verifier passed.
- `product_gate_status`: ProductGate result status.
- `hidden_acceptance_passed`: hidden evaluator passed.
- `review_score`: blind reviewer score when manual review is part of the task.
- `defect_leakage_count`: defects discovered after a passed status.
- `blocking_surprise_count`: blocking product failures discovered outside the
  expected verifier/product-gate location.
- `privacy_violation_count`: raw transcript, secret, or private context leaked
  into prohibited artifacts.
- `boundary_violation_count`: writes/imports/branches outside allowed product
  or runtime boundaries.

### Efficiency Metrics

- `time_to_first_artifact_ms`
- `time_to_generic_verifier_pass_ms`
- `time_to_product_gate_pass_ms`
- `time_to_accepted_deliverable_ms`
- `wall_duration_ms`
- `piworker_turn_count`
- `tool_call_count`
- `input_tokens`
- `output_tokens`
- `cache_read_tokens`
- `cache_write_tokens`
- `total_tokens`
- `provider_reported_cost_usd`
- `estimated_cost_usd`
- `cost_per_accepted_deliverable_usd`
- `user_turn_count`
- `clarification_turn_count`

### Stability Metrics

- `success_rate_within_budget`
- `p50_time_to_acceptance_ms`
- `p95_time_to_acceptance_ms`
- `p50_cost_per_acceptance_usd`
- `p95_cost_per_acceptance_usd`
- `repair_count`
- `resume_count`
- `retry_count`
- `failed_attempt_count`
- `tool_error_count`
- `command_failure_count`
- `test_failure_count`
- `timeout_count`
- `variance_across_seeds`

### Product and FrontDesk Metrics

- `frontdesk_node_count`
- `frontdesk_worker_call_count`
- `frontdesk_missing_slot_count`
- `frontdesk_slot_conflict_count`
- `intent_bundle_ready`
- `product_compile_status`
- `product_clarification_count`
- `product_acceptance_coverage_passed`
- `product_gate_blocking_finding_count`
- `product_grade_registered`

Product-specific metrics should use `integration.<product>` namespaces, for
example `integration.skillfoundry`. They must not appear under
`missionforge.*`.

## Metric Trust

Every benchmark summary should preserve trust source:

- `provider_reported`: values from PiWorker/provider usage, such as provider
  token usage or provider cost.
- `adapter_diagnostic`: values produced by MissionForge or direct runner
  adapters, such as duration and tool counts.
- `harness_diagnostic`: cross-trial values computed by benchmark harness.
- `reviewer_reported`: manual or blind-review scores.
- `integration_diagnostic`: ProductIntegration or ProductGate summaries.

When provider cost is unavailable, the benchmark may compute
`estimated_cost_usd` from a versioned pricing table. It must not label that
value as provider-reported cost.

## Benchmark Artifact Layout

Each trial should write a complete refs-first record:

```text
benchmarks/
  tasks/
    <task_id>/
      task.json
      user_script.json
      acceptance/
        public_checks.json
        hidden_checks.json
        review_rubric.md
  runs/
    <benchmark_run_id>/
      manifest.json
      trials/
        <task_id>/
          <mode>/
            seed-<n>/
              trial.json
              piworker_metrics.json
              metric_events.jsonl
              summary.json
              artifacts/
              review_packet.json
              reviewer_result.json
      aggregate.json
      report.md
```

The benchmark may store raw direct-run session logs as private evidence refs,
but summary metrics must remain safe and refs-first. Public reports must not
embed raw conversation or provider payloads.

## Required Schemas

### BenchmarkTask

```json
{
  "schema_version": "missionforge.benchmark_task.v1",
  "task_id": "skillfoundry-code-runtime-001",
  "task_family": "skillfoundry",
  "difficulty": "medium",
  "initial_user_text_ref": "benchmarks/tasks/.../user_statement.txt",
  "allowed_source_refs": [],
  "expected_output_refs": ["package/SKILL.md"],
  "budget": {
    "max_wall_minutes": 45,
    "max_total_tokens": 250000,
    "max_cost_usd": 10.0,
    "max_user_turns": 6
  },
  "acceptance_refs": [
    "benchmarks/tasks/.../acceptance/public_checks.json",
    "benchmarks/tasks/.../acceptance/hidden_checks.json"
  ]
}
```

### BenchmarkTrial

```json
{
  "schema_version": "missionforge.benchmark_trial.v1",
  "benchmark_run_id": "bench-20260530-001",
  "task_id": "skillfoundry-code-runtime-001",
  "mode": "missionforge_full_product_flow",
  "seed": 1,
  "workspace_ref": "benchmarks/runs/.../workspace",
  "started_at": "2026-05-30T00:00:00Z",
  "completed_at": "2026-05-30T00:10:00Z",
  "status": "accepted",
  "artifact_refs": [],
  "metric_events_ref": "benchmarks/runs/.../metric_events.jsonl",
  "summary_ref": "benchmarks/runs/.../summary.json",
  "review_packet_ref": "benchmarks/runs/.../review_packet.json"
}
```

### BenchmarkSummary

```json
{
  "schema_version": "missionforge.benchmark_summary.v1",
  "task_id": "skillfoundry-code-runtime-001",
  "mode": "direct_piworker_chat",
  "seed": 1,
  "accepted": true,
  "time_to_accepted_deliverable_ms": 600000,
  "estimated_cost_usd": 2.15,
  "provider_reported_cost_usd": 0,
  "total_tokens": 180000,
  "tool_call_count": 42,
  "repair_count": 0,
  "user_turn_count": 4,
  "privacy_violation_count": 0,
  "boundary_violation_count": 0,
  "defect_leakage_count": 0,
  "failure_taxonomy": []
}
```

## Infrastructure To Build

### Python Benchmark Package

Recommended files:

```text
src/missionforge/benchmark/__init__.py
src/missionforge/benchmark/contracts.py
src/missionforge/benchmark/task_loader.py
src/missionforge/benchmark/workspace.py
src/missionforge/benchmark/trial_runner.py
src/missionforge/benchmark/direct_piworker.py
src/missionforge/benchmark/missionforge_modes.py
src/missionforge/benchmark/collector.py
src/missionforge/benchmark/acceptance.py
src/missionforge/benchmark/aggregate.py
src/missionforge/benchmark/report.py
```

Responsibilities:

- validate task fixtures;
- create clean trial workspaces;
- dispatch direct PiWorker and MissionForge modes;
- collect PI runtime metrics, MissionForge metrics, ProductGate results, hidden
  checks, and reviewer results;
- compute safe summary metrics;
- write aggregate reports;
- fail closed when artifacts or metrics are missing.

### Direct PiWorker Benchmark Runner

Recommended files:

```text
workers/pi-agent-runtime/src/direct-benchmark-runtime.ts
workers/pi-agent-runtime/src/direct-benchmark-contract.ts
workers/pi-agent-runtime/tests/direct-benchmark-runtime.test.mjs
```

Responsibilities:

- run PiWorker in direct-chat mode with the same tools and provider config;
- avoid MissionForge WorkUnit system prompts;
- preserve workspace guardrails;
- emit event/session/metric/changed-ref artifacts comparable to
  `runMissionForgePiAgent`;
- support faux/offline tests and live opt-in tests;
- record the same usage/cost/tool timing metrics as MissionForge runtime.

This runner is benchmark infrastructure, not a new production worker path.

### PI Runtime Observability Patch

Patch `workers/pi-agent-runtime/src/evidence-recorder.ts` to record:

- `cache_read_tokens`
- `cache_write_tokens`
- `input_cost_usd`
- `output_cost_usd`
- `cache_read_cost_usd`
- `cache_write_cost_usd`
- `provider_reported_cost_usd`
- `tool_error_count`
- `tool_latency_ms_total`
- `tool_latency_ms_by_name`
- `command_count`
- `test_command_count`
- `command_failure_count` when available from tool result details
- `time_to_first_tool_ms`
- `time_to_first_artifact_ms` when changed refs reveal artifact creation

Patch `src/missionforge/adapters/pi_agent_runtime.py` only to project the new
safe metrics and refs. Do not let runtime routing depend on the new metric
values.

### Benchmark Metric Projection

Use existing `MetricEvent` and `MetricStore` instead of inventing another
metrics store.

Recommended namespaces:

```text
missionforge.harness
missionforge.worker.pi_agent
missionforge.runtime
missionforge.verifier
integration.skillfoundry
```

If a future implementation needs `missionforge.benchmark`, add it deliberately
to the metric namespace allowlist and docs. The first implementation can use
`missionforge.harness` for benchmark trial metrics.

### Acceptance and Review Harness

Build acceptance around independent checks:

- public checks visible to both modes;
- hidden checks created before trials and not shown to workers;
- ProductGate checks for product-specific readiness;
- blind review packets where manual judgment is required;
- defect-leakage audit after apparent success.

Review packets should include artifact refs, diff stats, check results, and
rubric refs. They should not reveal whether the artifact came from direct chat
or MissionForge.

### SkillFoundry Patches Required For Fair Product Benchmarks

Before claiming SkillFoundry product-grade results, finish or explicitly gate:

- MissionIR-first acceptance coverage for all blocking product checks;
- compile-time failure for uncovered blocking ProductAcceptanceMatrix items;
- ProductGradeGate classification of post-verifier blocking failures as
  coverage misses;
- product reports that distinguish verifier failure, product-gate failure,
  coverage miss, candidate registration, and product-grade registration;
- no SkillFoundry branches in `src/missionforge`.

Without these patches, MissionForge may appear to pass while SkillFoundry later
rejects the bundle. That would be a compiler coverage problem, not a fair
MissionForge value measurement.

### FrontDesk Patches Required For Full-Flow Benchmarks

Before full FrontDesk benchmarks:

- PiWorker-backed NeedGriller, SolutionArchitect, and IntentBundleAuthor nodes
  must be runnable through `FrontDeskPiNodeRunner`;
- output artifacts must be content-hash-bound to node execution records;
- deterministic code must keep failing closed when PiWorker artifacts are
  missing or stale;
- ProductInquiryProfile hashes must be bound to the authoring run;
- FrontDesk metrics must count clarification turns, missing slots, conflicts,
  and node executions without embedding raw conversation.

## Test Plan

### Stage 0: Offline Contract Tests

Goal:

```text
Prove benchmark schemas, artifact layout, and metric safety without live LLM.
```

Required tests:

- benchmark task schema round trip;
- trial schema round trip;
- summary schema round trip;
- unsafe refs are rejected;
- raw prompt/transcript/payload/body/secret metric fields are rejected;
- direct runner faux mode writes comparable metrics;
- MissionForge mode faux run writes comparable summary;
- aggregate report is deterministic;
- benchmark report does not embed raw session bodies.

### Stage 1: Single-Task Smoke

Goal:

```text
Run one tiny task through direct PiWorker and MissionForge runtime-only modes.
```

Acceptance:

- both modes use the same model/provider config;
- both write `summary.json`;
- both summaries contain token, time, tool, status, and acceptance fields;
- hidden check result is joined into summary;
- cost is either provider-reported or explicitly estimated.

### Stage 2: SkillFoundry Product Smoke

Goal:

```text
Run one SkillFoundry package task through MissionForge full product flow.
```

Acceptance:

- FrontDesk starts from user-like pain text;
- SkillFoundry ProductIntegration compiles intent into MissionIR;
- MissionForge verifier catches blocking product checks inside the runtime
  loop where possible;
- ProductGate produces a result refs-only;
- summary joins FrontDesk, runtime, verifier, and ProductGate metrics.

### Stage 3: Codexarium-Like Dogfood

Goal:

```text
Use a Codexarium-like task as a hard product benchmark without exposing
Codexarium source or project-private facts to the worker.
```

Rules:

- task text should be colloquial and pain-driven;
- no Codexarium source details or internal implementation facts in the prompt;
- direct chat and MissionForge see the same initial user text;
- hidden acceptance checks are prepared before both runs;
- reviewers are blind to mode;
- failure analysis must distinguish worker failure, FrontDesk failure,
  ProductIntegration coverage miss, runtime/verifier failure, and ProductGate
  failure.

### Stage 4: Initial Multi-Task A/B

Recommended first matrix:

```text
6 tasks x 3 modes x 3 seeds = 54 trials
```

Task mix:

- 2 simple tasks where direct chat should be competitive;
- 2 medium tasks with ambiguous requirements and product acceptance;
- 2 complex tasks requiring repair, multiple artifacts, or product-gate
  coverage.

Modes:

- direct PiWorker chat;
- MissionForge runtime only;
- MissionForge full product flow.

This is enough for directional evidence. It is not enough for strong
statistical claims.

### Stage 5: Stability Study

After the initial matrix is stable:

```text
10 to 20 tasks x 2 primary modes x 5 seeds
```

Primary modes:

- direct PiWorker chat;
- MissionForge full product flow.

Report:

- success rate within budget;
- median and p95 time;
- median and p95 cost;
- repair distribution;
- defect leakage distribution;
- failure taxonomy;
- confidence intervals or bootstrap intervals where sample size supports them.

## Failure Taxonomy

Every failed or non-accepted trial should classify failure as one or more of:

- `task_fixture_invalid`
- `provider_unavailable`
- `budget_exceeded`
- `direct_runner_failure`
- `frontdesk_missing_llm_artifact`
- `frontdesk_semantic_gap`
- `product_compile_needs_clarification`
- `product_compile_failed_closed`
- `mission_ir_invalid`
- `runtime_worker_failed`
- `runtime_verifier_failed`
- `repair_exhausted`
- `product_gate_failed`
- `product_acceptance_coverage_miss`
- `hidden_acceptance_failed`
- `reviewer_rejected`
- `privacy_violation`
- `boundary_violation`
- `metric_collection_failed`

Failure taxonomy matters because MissionForge value is not only pass/fail. It
should make failures easier to locate and repair.

## Fairness Controls

For every comparable trial pair:

- same repo snapshot or fixture snapshot;
- same dependency lockfiles;
- same model id;
- same provider base URL;
- same reasoning level;
- same max turns;
- same tool timeout;
- same wall-clock budget;
- same token/cost budget;
- same public task instructions;
- same hidden acceptance checks;
- same reviewer rubric;
- same post-run evaluator;
- clean workspace per trial;
- no context carryover between trials;
- no manual artifact edits during a trial;
- same retry policy unless a mode's whole point is verifier-driven repair.

When a fairness control cannot be met, the trial summary must mark the trial as
non-comparable.

## Anti-Cheating Controls

The benchmark must prevent accidental self-deception:

- Direct chat baseline must be allowed to use tools well.
- MissionForge must not receive hidden acceptance checks as worker-visible
  context.
- Direct chat and MissionForge must not share transcripts or intermediate
  artifacts across trials.
- Codexarium-specific facts must not be encoded in prompts, ProductIntegration
  code, validators, or reviewers except as predeclared hidden acceptance
  criteria.
- ProductIntegration may encode product semantics, but not benchmark answers.
- Benchmark reports must separate provider outages from system failures.
- Human reviewers should be blind to mode when possible.

## Development Phases

### Phase VB1: Benchmark Contracts and Offline Harness

Deliver:

- benchmark task, trial, summary, aggregate schemas;
- artifact layout writer;
- safe metric event writer for harness metrics;
- deterministic aggregate report;
- unit tests and docs.

Acceptance:

- offline tests pass;
- unsafe refs and raw metric payloads are rejected;
- aggregate output is deterministic.

### Phase VB2: PI Runtime Observability

Deliver:

- cache/cost usage capture;
- tool start/end latency capture;
- tool error count;
- richer command/test summaries;
- adapter projection of safe metrics;
- tests for no secret/raw payload leakage.

Acceptance:

- faux runtime tests pass;
- adapter tests include new metrics;
- metric-boundary tests still prove runtime routing does not depend on them.

### Phase VB3: Direct PiWorker Baseline

Deliver:

- direct benchmark runtime under `workers/pi-agent-runtime`;
- Python wrapper/collector;
- direct-mode trial summaries;
- faux tests and live opt-in smoke.

Acceptance:

- direct mode can complete a small task and emit comparable metrics;
- direct mode does not use MissionForge WorkUnit prompts;
- direct mode remains benchmark-only.

### Phase VB4: MissionForge Runtime-Only Mode

Deliver:

- prepared MissionIR task fixtures;
- runtime-mode trial runner;
- verifier/product-gate result joining where applicable.

Acceptance:

- runtime-only mode runs from a fixture and emits the same summary schema;
- repair count and verifier status are captured.

### Phase VB5: Full FrontDesk + SkillFoundry Mode

Deliver:

- full-flow trial runner;
- FrontDesk PiWorker node metric capture;
- SkillFoundry ProductIntegration result capture;
- ProductGate result capture;
- product acceptance coverage status capture.

Acceptance:

- one SkillFoundry task starts from colloquial user text and reaches either
  accepted output or a correctly classified failure;
- no product-specific code enters `src/missionforge`.

### Phase VB6: Codexarium-Like Dogfood Pack

Deliver:

- task fixture set using user-like pain statements;
- hidden acceptance checks;
- review rubric;
- no source leakage;
- direct and MissionForge comparable runs.

Acceptance:

- direct and MissionForge arms run from the same initial user text;
- aggregate report identifies winner by accepted-deliverable metrics, not
  narrative quality.

### Phase VB7: Multi-Seed Aggregate Reporting

Deliver:

- multi-task, multi-seed runner;
- aggregate JSON and Markdown report;
- effect-size tables;
- failure taxonomy summary;
- cost/time/stability charts or table-ready data.

Acceptance:

- `success_rate_within_budget`, `cost_per_accepted_deliverable`, and
  `time_to_accepted_deliverable` are computed for each mode;
- non-comparable trials are excluded from direct comparison and explained.

## Definition Of Done For The Benchmark Infrastructure

The infrastructure is complete when:

- a direct PiWorker baseline and MissionForge full flow can run the same task;
- both modes produce the same summary schema;
- PI usage/cost/tool metrics are captured or explicitly marked unavailable;
- hidden checks and ProductGate results are joined into summaries;
- aggregate reports compute accepted-deliverable time, cost, and success rate;
- raw prompt/transcript/provider payloads do not enter public metrics;
- SkillFoundry product-grade claims are backed by MissionIR-visible acceptance
  coverage or clearly classified coverage misses;
- MissionForge core remains product-independent;
- the first multi-task A/B report can be reproduced from committed fixtures and
  recorded run artifacts.

## Decision Rules

After the first serious benchmark, interpret results as follows:

- If MissionForge wins on complex tasks but loses on tiny tasks, the system is
  valuable and should expose task-fit guidance.
- If MissionForge wins on success rate but loses on cost, optimize FrontDesk
  turns and verifier/repair loops before expanding features.
- If MissionForge loses on product-grade tasks due to ProductGate surprises,
  fix ProductIntegration coverage before judging runtime value.
- If direct chat wins consistently on accepted cost/time/stability, stop adding
  architecture and study which MissionForge components create overhead.
- If results are inconclusive, increase task count and improve evaluator
  independence before making product claims.

## Immediate Next Step

Start with Phase VB1 and VB2. They provide the minimum durable substrate for
all later claims:

```text
benchmark contracts + offline harness
PI runtime observability patch
```

Do not start with a large live Codexarium run. Without comparable summaries,
cost capture, and hidden acceptance joining, a live run will produce anecdotes
instead of evidence.
