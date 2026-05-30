# MissionForge Value Benchmark Completion Runbook

Last updated: 2026-05-31

Status: executable follow-on plan from the current `value-benchmark` branch.

## Purpose

This document is the runbook for getting from the current clean Pilot 01 result
to a complete MissionForge value benchmark report.

The target is not another planning artifact. The target is a reproducible report
that can answer this question with evidence:

```text
With the same PiWorker model, tools, workspace, task, and budget, does
MissionForge produce accepted deliverables faster, cheaper, more reliably, or
with lower defect/privacy leakage than direct PiWorker chat?
```

The final result must compare MissionForge against direct PiWorker use, not
against another model or another worker. PiWorker remains the only LLM worker.

## Current Baseline

The current branch already has these prerequisites:

- direct PiWorker benchmark runner;
- MissionForge runtime-only benchmark runner;
- full FrontDesk + SkillFoundry product-flow benchmark runner;
- hidden acceptance joining;
- aggregate JSON report, Markdown report, mode-comparison data, and table data;
- token/cost projection infrastructure through `BenchmarkPricingTable`;
- `cost_source` preservation, so unavailable cost is not treated as cheap cost;
- Pilot 01 Stage 2 `final3` clean packet for one SkillFoundry fixture.

The current Pilot 01 result is useful as a harness proof. It is not enough for a
MissionForge value claim because it covers one fixture only and has no
pricing-table-backed cost projection.

## Definition Of A Complete Report

The complete report is done only when all of these artifacts exist:

```text
docs/reports/value_benchmark_<YYYYMMDD>/
  README.md
  final_report.md
  fixture_manifest.json
  run_index.json
  pricing_table.json
  aggregate.json
  mode_comparisons.json
  table_data.json
  failure_taxonomy.json
  leakage_audit.json
  blind_review_summary.md
  reviewer_packet_index.json
  reproduction.md
```

The report must include:

- task inventory and why each task is in the benchmark;
- compared modes and exact fairness controls;
- provider, model, pricing table id, seed list, budget, and run ids;
- success rate within budget;
- cost per accepted deliverable with explicit `cost_source`;
- wall time and accepted-deliverable time;
- p50/p95 time and cost for the stability subset;
- hidden acceptance pass/fail counts;
- ProductGate pass/fail counts;
- defect leakage and privacy leakage audit results;
- failure taxonomy by mode and task;
- blind review result if manual quality review is used;
- clear conclusion categories:
  - where MissionForge wins;
  - where direct PiWorker wins;
  - where results are inconclusive;
  - what must be fixed before stronger claims.

Do not call the report complete if any cost winner is selected from
`cost_source=unavailable`, if hidden checks were worker-visible, or if
SkillFoundry-specific logic entered `src/missionforge`.

## Non-Goals

Do not do these while completing the benchmark:

- add a general worker marketplace;
- introduce a second production LLM worker;
- expose Codexarium source or private implementation details to benchmark
  workers;
- encode benchmark answers in ProductIntegration code;
- treat worker self-report as acceptance;
- commit raw run artifacts from `benchmarks/runs/`;
- make runtime routing depend on private adapter metrics;
- add direct-chat disadvantages that make the baseline weak.

## Required New Work

The remaining work is execution infrastructure and experiment content, not core
MissionForge architecture.

### 1. Add A Benchmark Driver

Create a committed driver script:

```text
scripts/run_value_benchmark.py
```

Required behavior:

- load a task manifest;
- load a pricing table;
- select modes;
- select seeds;
- instantiate the direct PiWorker, runtime-only, and full-product-flow runners;
- pass the same provider/model/budget controls into all comparable modes;
- write results under `benchmarks/runs/<run_id>/`;
- fail closed when hidden acceptance files would become worker-visible;
- fail closed when a requested pricing table is missing;
- write an execution summary ref that can be copied into the final report pack.

Expected command shape:

```bash
env PYTHONPATH=src:integrations/skillfoundry/src:integrations/skillfoundry/tests \
python3 scripts/run_value_benchmark.py \
  --run-id vb-stage3-<date> \
  --task-manifest benchmarks/tasks/value_benchmark_manifest.json \
  --pricing-table benchmarks/pricing/pi-pricing-<date>.json \
  --modes direct_piworker_chat,missionforge_full_product_flow \
  --seeds 1,2,3 \
  --provider-mode live
```

If live provider configuration is unavailable, the script must stop with a
clear unavailable-provider result. It must not silently fall back to faux mode
for a live value claim.

### 2. Add A Report Pack Builder

Create a committed report pack builder:

```text
scripts/build_value_benchmark_report.py
```

Required behavior:

- read one or more `benchmarks/runs/<run_id>/` directories;
- copy sanitized aggregate/report/table artifacts into
  `docs/reports/value_benchmark_<YYYYMMDD>/`;
- write `run_index.json` with run ids, modes, tasks, seeds, provider metadata,
  pricing table id, and local artifact refs;
- write `reproduction.md` with exact commands;
- reject raw prompt, transcript, provider payload, stdout/stderr body, or secret
  fields in publishable artifacts;
- preserve links to ignored local run artifacts without copying raw bodies.

### 3. Add A Pricing Table Fixture

Create:

```text
benchmarks/pricing/pi-pricing-<YYYYMMDD>.json
```

Required schema:

```json
{
  "schema_version": "missionforge.benchmark_pricing_table.v1",
  "pricing_table_id": "pi-pricing-YYYYMMDD",
  "currency": "USD",
  "effective_date": "YYYY-MM-DD",
  "model_prices": {
    "<model-id>": {
      "model": "<model-id>",
      "input_per_1m_tokens_usd": 0.0,
      "output_per_1m_tokens_usd": 0.0,
      "cache_read_per_1m_tokens_usd": 0.0,
      "cache_write_per_1m_tokens_usd": 0.0
    }
  }
}
```

The table may use placeholder prices only for dry runs. A value claim requires
the table to reflect the actual model used in the live benchmark.

## Fixture Plan

The next benchmark pack should contain at least five tasks:

| id | purpose | expected winner hypothesis |
| --- | --- | --- |
| `sf-simple-skill-001` | Simple prompt-only SkillFoundry package | direct PiWorker competitive |
| `sf-ambiguous-skill-001` | Vague user pain requiring FrontDesk grilling | MissionForge advantage |
| `sf-product-gate-001` | Product acceptance stricter than generic verifier | MissionForge advantage |
| `codexarium-dogfood-001` | Codexarium-like need, no source exposure | MissionForge advantage if FrontDesk works |
| `codexarium-dogfood-002` | Rust/performance/product-boundary pain, no private facts | MissionForge advantage if ProductIntegration works |

Each task directory must follow this layout:

```text
benchmarks/tasks/<task_id>/
  task.json
  user_statement.txt
  allowed_sources/
    source_manifest.json
  acceptance/
    public_checks.json
    hidden_checks.json
  review_rubric.md
```

Task text rules:

- user statement must be colloquial and pain-driven;
- it may describe desired outcomes and constraints;
- it must not include Codexarium source paths, internal architecture, or hidden
  expected answers;
- hidden checks must be written before live runs;
- public checks may verify only visible contract basics;
- review rubric must be mode-blind.

## Execution Stages

### Stage A: Preflight

Goal:

```text
Confirm the repo, scripts, pricing table, and fixtures are ready before live
costly runs.
```

Actions:

1. Implement `scripts/run_value_benchmark.py`.
2. Implement `scripts/build_value_benchmark_report.py`.
3. Add pricing table fixture.
4. Add the first fixture manifest.
5. Run unit and integration tests.

Required commands:

```bash
env PYTHONPATH=src:integrations/skillfoundry/src:integrations/skillfoundry/tests \
python3 -m unittest discover -s tests -p 'test*.py'

env PYTHONPATH=src:integrations/skillfoundry/src:integrations/skillfoundry/tests \
python3 -m unittest discover -s integrations/skillfoundry/tests -p 'test*.py'

git diff --check
```

Acceptance:

- all tests pass;
- driver dry-run can load fixture manifest and pricing table;
- no task fixture leaks hidden acceptance into worker-visible fields;
- publishable artifacts pass raw-payload scan.

Stop if:

- live provider/model is not configured;
- pricing table does not include the configured model id;
- hidden checks appear in direct or MissionForge worker inputs.

### Stage B: Stage 3 Dogfood Shakedown

Goal:

```text
Run the smallest live dogfood experiment that can expose benchmark design
problems before the larger A/B matrix.
```

Recommended matrix:

```text
2 tasks x 2 modes x 3 seeds = 12 trials
```

Modes:

- direct PiWorker chat;
- MissionForge full product flow.

Actions:

1. Run `codexarium-dogfood-001` and `sf-ambiguous-skill-001`.
2. Use live provider mode and the pricing table.
3. Build a temporary report pack under `docs/reports/value_benchmark_stage3_<date>/`.
4. Inspect failures and classify every failed trial.
5. Repair only harness, fixture, or clear product-contract bugs.

Acceptance:

- at least one full direct-vs-MissionForge task pair is comparable;
- every summary has `cost_source=pricing_table` or a documented unavailable
  reason;
- hidden acceptance joins into summaries;
- no public report embeds raw user text beyond task refs and short allowed
  descriptions;
- failure taxonomy is explainable.

Stop and repair before Stage C if:

- more than one third of trials are non-comparable due to harness errors;
- all MissionForge full-flow failures are FrontDesk artifact missing errors;
- all direct failures come from an unfair prompt or missing allowed context;
- cost is unavailable for any accepted comparable trial.

### Stage C: Stage 4 Initial Multi-Task A/B

Goal:

```text
Produce the first serious value report across simple, medium, and complex
tasks.
```

Recommended matrix:

```text
5 tasks x 3 modes x 3 seeds = 45 trials
```

Modes:

- direct PiWorker chat;
- MissionForge runtime only where a prepared MissionIR fixture exists;
- MissionForge full product flow.

Actions:

1. Run all five tasks with seeds `1,2,3`.
2. Build report pack under `docs/reports/value_benchmark_stage4_<date>/`.
3. Run leakage audit across publishable artifacts.
4. Generate table data for success, time, cost, repairs, and failure taxonomy.
5. Write an interpretation section that separates simple, medium, and complex
   task behavior.

Acceptance:

- at least four tasks have comparable direct-vs-full-flow pairs;
- at least three tasks have all three modes comparable, or missing modes are
  explicitly justified;
- cost winners are selected only from available cost sources;
- no hidden acceptance leak;
- no raw provider payload leak;
- product-grade claims have ProductGate evidence refs;
- every non-comparable trial has an explicit reason.

Stage C output is the first report that can support directional value claims.
It is still not a stability claim.

### Stage D: Stage 5 Stability Study

Goal:

```text
Measure whether the Stage 4 signal is stable across more seeds.
```

Recommended matrix:

```text
3 representative tasks x 2 primary modes x 5 seeds = 30 trials
```

Primary modes:

- direct PiWorker chat;
- MissionForge full product flow.

Task selection:

- one task MissionForge appeared to win;
- one task direct PiWorker appeared to win or tie;
- one task with mixed or failure-heavy behavior.

Actions:

1. Run seeds `1,2,3,4,5` unless Stage C already used some seeds and artifacts
   can be safely reused.
2. Compute p50 and p95 for time and cost.
3. Compute failure-taxonomy distributions.
4. Audit defect leakage after accepted status.
5. Compare stability against Stage C.

Acceptance:

- every included task has at least five comparable direct/full-flow attempts or
  a documented reason for exclusion;
- p50/p95 values are present for success, time, and cost;
- report states whether Stage 4 conclusions strengthened, weakened, or changed;
- every accepted task has leakage audit status.

### Stage E: Blind Review

Goal:

```text
Add product-quality judgment without revealing which mode produced which
artifact.
```

Use blind review only for tasks where deterministic hidden checks are not
enough to judge quality.

Actions:

1. Build reviewer packets from artifact refs, rubrics, and sanitized summaries.
2. Remove mode names and run ids that reveal mode.
3. Ask an independent reviewer agent or human reviewer to score each packet.
4. Record reviewer outputs as refs-only summaries.
5. Join `review_score` into the final report.

Acceptance:

- reviewer packet does not reveal mode;
- reviewer does not see hidden acceptance expected strings;
- reviewer result has clear score and blocking findings;
- review findings do not overwrite deterministic acceptance, but may explain
  quality differences.

### Stage F: Final Report Assembly

Goal:

```text
Publish one complete, reproducible, sanitized report pack.
```

Actions:

1. Choose the final Stage C and Stage D run ids.
2. Build `docs/reports/value_benchmark_<YYYYMMDD>/`.
3. Write `final_report.md`.
4. Include `reproduction.md` with exact commands and environment requirements.
5. Include `run_index.json`, aggregate files, table data, pricing table, and
   leakage audit.
6. Run final tests.
7. Commit and push.

Final validation commands:

```bash
env PYTHONPATH=src:integrations/skillfoundry/src:integrations/skillfoundry/tests \
python3 -m unittest discover -s tests -p 'test*.py'

env PYTHONPATH=src:integrations/skillfoundry/src:integrations/skillfoundry/tests \
python3 -m unittest discover -s integrations/skillfoundry/tests -p 'test*.py'

git diff --check
```

The final report must include a "Claims We Can Make" section and a "Claims We
Cannot Make Yet" section.

## Report Interpretation Rules

Use these rules when writing `final_report.md`:

- MissionForge wins a task only when it has better or equal acceptance and a
  defensible advantage in at least one of cost, time, stability, repairability,
  defect leakage, or product-grade confidence.
- Direct PiWorker wins a task when it reaches accepted output faster or cheaper
  without worse hidden/product/reviewer outcomes.
- If MissionForge has higher success but higher cost, state the tradeoff
  instead of declaring a simple win.
- If cost is unavailable, do not report a cost winner.
- If ProductGate rejects an artifact after generic verification passed, count
  that as a product-contract or product-quality failure, not as accepted work.
- If a mode fails because provider access was unavailable, mark the trial
  non-comparable unless both modes suffered the same provider condition.
- If the task fixture was ambiguous in a way that invalidates both modes, mark
  the fixture invalid and repair before rerun.

## Timeline

The following assumes live provider access works and no major product-contract
bug is discovered:

| milestone | expected elapsed time | output |
| --- | ---: | --- |
| Stage A preflight | 0.5 day | driver, report builder, pricing table, fixtures ready |
| Stage B shakedown | 0.5-1 day | first dogfood report |
| Stage C initial A/B | 1-2 days | first serious value report |
| Stage D stability | 1-2 days | p50/p95 stability report |
| Stage E/F review and final assembly | 0.5-1 day | complete final report pack |

Fast path:

```text
2 to 3 days
```

Conservative path:

```text
4 to 5 days
```

The main schedule risks are live PiWorker runtime duration, provider outages,
FrontDesk artifact failures, and fixture hidden-check repairs.

## Completion Checklist

Do not mark the benchmark complete until every item is checked:

- [ ] committed benchmark driver exists;
- [ ] committed report builder exists;
- [ ] committed pricing table exists;
- [ ] at least five task fixtures exist;
- [ ] hidden checks are not worker-visible;
- [ ] direct and MissionForge modes use the same PiWorker model/provider;
- [ ] Stage B shakedown completed;
- [ ] Stage C initial A/B completed;
- [ ] Stage D stability study completed;
- [ ] leakage audit completed;
- [ ] blind review completed or explicitly waived with rationale;
- [ ] every non-comparable trial has a reason;
- [ ] every cost comparison has `cost_source != unavailable`;
- [ ] final report pack exists under `docs/reports/`;
- [ ] final test commands pass;
- [ ] final claims are separated from non-claims;
- [ ] branch is committed and pushed.

