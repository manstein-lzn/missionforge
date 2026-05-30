# MissionForge Value Benchmark Next Execution Plan

Last updated: 2026-05-31

Status: executed on 2026-05-31; preserved as the concrete runbook that produced
the complete final benchmark report.

Parent plan: `docs/MISSIONFORGE_VALUE_BENCHMARK_COMPLETION_RUNBOOK.md`

Final report target:

```text
docs/reports/value_benchmark_20260531/
```

Final report status:

```text
docs/reports/value_benchmark_20260531/final_report.md
```

The final measured matrix did not show a MissionForge speed/cost advantage:
direct PiWorker chat won the measured Stage 5 success, projected cost, and p95
time comparisons. This document remains useful as the execution recipe and
acceptance checklist for reproducing or extending the benchmark.

## Purpose

This document is the concrete remaining execution plan after the Stage 3
dogfood shakedown. It is intentionally narrower than the full benchmark plan:
it starts from the current repository state and lists the exact repairs, runs,
report builds, audits, and acceptance gates needed before the benchmark can be
called complete.

The final answer must be evidence-backed:

```text
With the same PiWorker model, provider, tools, workspace shape, tasks, seeds,
and pricing projection, does MissionForge produce accepted deliverables faster,
cheaper, more reliably, or with lower product/privacy risk than direct PiWorker
chat?
```

This plan does not assume MissionForge wins. It is acceptable for the final
report to say that direct PiWorker chat won the measured matrix, that the result
is mixed, or that a MissionForge advantage appears only on some task classes.
The important requirement is that the conclusion is reproducible, sanitized,
and not based on worker self-report.

## Current State

The branch already contains the benchmark execution infrastructure:

- `scripts/run_value_benchmark.py`
- `scripts/build_value_benchmark_report.py`
- `benchmarks/pricing/pi-pricing-20260531.json`
- `benchmarks/tasks/value_benchmark_manifest.json`
- five committed task fixtures:
  - `sf-simple-skill-001`
  - `sf-ambiguous-skill-001`
  - `sf-product-gate-001`
  - `codexarium-dogfood-001`
  - `codexarium-dogfood-002`

The following validation already passed before the live shakedown:

```bash
env PYTHONPATH=src:integrations/skillfoundry/src:integrations/skillfoundry/tests \
python3 -m unittest discover -s tests -p 'test*.py'

env PYTHONPATH=src:integrations/skillfoundry/src:integrations/skillfoundry/tests \
python3 -m unittest discover -s integrations/skillfoundry/tests -p 'test*.py'

git diff --check
```

The Stage 3 shakedown run already exists locally:

```text
benchmarks/runs/vb-stage3-shakedown-20260531T000000Z/
```

Stage 3 matrix:

```text
2 tasks x 2 modes x 3 seeds = 12 trials
```

Modes:

- `direct_piworker_chat`
- `missionforge_full_product_flow`

Stage 3 outcome:

- 12 comparable trials
- 11 accepted trials
- `direct_piworker_chat`: 6 accepted out of 6
- `missionforge_full_product_flow`: 5 accepted out of 6
- current shakedown winners by success, cost, and time: `direct_piworker_chat`
- cost source: `pricing_table`
- provider-reported cost: not available in this run, so cost claims must say
  they are pricing-table projections

The one failed Stage 3 trial is:

```text
task: codexarium-dogfood-001
mode: missionforge_full_product_flow
seed: 3
summary: benchmarks/runs/vb-stage3-shakedown-20260531T000000Z/trials/codexarium-dogfood-001/missionforge_full_product_flow/seed-3/summary.json
failure taxonomy:
  - frontdesk_missing_llm_artifact
  - product_compile_failed_closed
  - hidden_acceptance_failed
```

This failure does not by itself invalidate Stage 3, but it must be classified
before Stage 4 claims are written.

## Critical Blocker Before Larger Runs

The current leakage audit scans too broadly. It scans internal run artifacts
under `benchmarks/runs/`, including MissionForge schema fields and raw execution
records that are not publishable report artifacts. This creates false positives
such as field-name hits for:

```text
raw_prompt
raw_transcript
provider_payload
```

Do not publish any final claim until this is repaired. The benchmark needs two
separate concepts:

- publishable leakage audit: hard blocker for final reports
- internal schema marker inventory: diagnostic only, not a public leakage
  failure by itself

## Execution Contract

### Goal

Produce a complete final report pack under:

```text
docs/reports/value_benchmark_20260531/
```

### Success

Success means all of these are true:

- Stage 3 failure has a written classification.
- Stage 4 multi-task A/B has completed with live PiWorker.
- Stage 5 stability study has completed with live PiWorker.
- The final report pack exists and includes every required file.
- The report pack passes publishable leakage validation.
- Hidden acceptance was not worker-visible.
- Every non-comparable trial has a reason.
- Cost comparisons use `cost_source=pricing_table` or
  `cost_source=provider_reported`; no cost winner is selected from unavailable
  cost.
- Final tests pass.
- Final report states both claims we can make and claims we cannot make yet.
- All committed artifacts are sanitized; ignored raw run artifacts are not
  committed.

### Non-Goals

Do not change these while finishing the benchmark:

- Do not add another production LLM worker.
- Do not add product-specific logic under `src/missionforge`.
- Do not weaken direct PiWorker chat into a strawman baseline.
- Do not expose Codexarium source or private internals.
- Do not make hidden acceptance visible to any worker.
- Do not encode fixture expected answers in runtime, FrontDesk, or
  ProductIntegration code.
- Do not commit `benchmarks/runs/` raw artifacts.
- Do not claim provider-billed cost unless the provider reports it.

## Phase 0: Preflight From Current State

Run this before making any additional change:

```bash
git status --short --branch

env PYTHONPATH=src:integrations/skillfoundry/src:integrations/skillfoundry/tests \
python3 scripts/run_value_benchmark.py \
  --dry-run \
  --run-id vb-dryrun-next-20260531 \
  --stage next_plan_preflight \
  --task-manifest benchmarks/tasks/value_benchmark_manifest.json \
  --pricing-table benchmarks/pricing/pi-pricing-20260531.json \
  --modes direct_piworker_chat,missionforge_runtime_only,missionforge_full_product_flow \
  --seeds 1,2,3 \
  --provider-mode live \
  --provider-config-source codex_current
```

Pass criteria:

- repo is on `value-benchmark`;
- no unrelated dirty files are present;
- dry run succeeds;
- pricing table includes the live model;
- hidden checks are not worker-visible.

If this fails, repair only the failing preflight cause before continuing.

## Phase 1: Repair Publishable Leakage Audit

### Required Code Changes

Patch both scripts:

```text
scripts/run_value_benchmark.py
scripts/build_value_benchmark_report.py
```

Required behavior:

- `scan_run_for_leaks` must not treat every internal run file as a publishable
  leak.
- `build_leakage_audit` must scan only artifacts that are copied into the final
  report pack or explicitly marked publishable.
- Internal files may be scanned into a diagnostic bucket, but diagnostic hits
  must not set final `passed=false` unless they are also publishable hard hits.
- The audit output must separate:
  - `hard_leak_hits`
  - `schema_marker_hits`
  - `publishable_scanned_file_count`
  - `internal_scanned_file_count`
  - `passed`
- The existing `leak_hits` field may remain as an alias for hard hits if needed
  for backward compatibility.
- `validate_publishable_report` must continue to reject raw prompt,
  transcript, provider payload, stdout/stderr body, artifact body, or secret
  markers outside `leakage_audit.json`.

Suggested implementation:

```text
LEAK_MARKERS:
  hard markers:
    - OPENAI_API_KEY
    - MISSIONFORGE_PI_AGENT_API_KEY
    - raw_provider_payload
  schema markers:
    - raw_prompt
    - raw_transcript
    - provider_payload

publishable files:
  - docs/reports/value_benchmark_*/README.md
  - docs/reports/value_benchmark_*/final_report.md
  - docs/reports/value_benchmark_*/*.json
  - docs/reports/value_benchmark_*/reproduction.md
  - docs/reports/value_benchmark_*/blind_review_summary.md

non-publishable internal examples:
  - benchmarks/runs/**/workspace/**
  - benchmarks/runs/**/direct_piworker_events.jsonl
  - benchmarks/runs/**/direct_piworker_output.json
  - benchmarks/runs/**/frontdesk/pi_nodes/**
```

The publishable report must never include raw provider payload bodies, raw
transcripts, secrets, or hidden acceptance contents. It may include marker names
inside `leakage_audit.json` only because that file describes the audit itself.

### Required Tests

Add focused tests for the audit behavior. Prefer a dedicated file:

```text
tests/test_value_benchmark_report_builder.py
```

Minimum coverage:

- a fake internal run file with the text `provider_payload` does not fail the
  publishable audit by itself;
- a publishable report file containing a hard secret marker fails validation;
- `leakage_audit.json` may name configured markers without failing
  `validate_publishable_report`;
- the report builder still rejects report JSON that violates refs-only
  contracts.

### Validation Commands

```bash
env PYTHONPATH=src:integrations/skillfoundry/src:integrations/skillfoundry/tests \
python3 -m unittest discover -s tests -p 'test*.py'

env PYTHONPATH=src:integrations/skillfoundry/src:integrations/skillfoundry/tests \
python3 -m unittest discover -s integrations/skillfoundry/tests -p 'test*.py'

git diff --check
```

Pass criteria:

- all tests pass;
- report builder can build a Stage 3 report pack without false leakage failure;
- the final report does not contain hard leak markers outside
  `leakage_audit.json`.

## Phase 2: Classify Stage 3 Failure And Build Shakedown Report

Inspect the failed FrontDesk execution:

```bash
python3 -m json.tool \
benchmarks/runs/vb-stage3-shakedown-20260531T000000Z/trials/codexarium-dogfood-001/missionforge_full_product_flow/seed-3/summary.json

python3 -m json.tool \
benchmarks/runs/vb-stage3-shakedown-20260531T000000Z/trials/codexarium-dogfood-001/missionforge_full_product_flow/seed-3/full_product_flow_result.json
```

Also inspect the referenced FrontDesk node execution from the result packet.
Do not copy raw node bodies into committed docs.

Classification choices:

- `stochastic_frontdesk_artifact_failure`: PiWorker ran but failed to write the
  required artifact.
- `frontdesk_contract_mismatch`: FrontDesk prompt and schema disagree.
- `product_compile_contract_mismatch`: ProductIntegration rejected a valid
  FrontDesk artifact.
- `harness_bug`: runner lost or misread an artifact.

Repair rule:

- If the failure is stochastic and 5 out of 6 full-flow trials accepted, record
  it and continue.
- If the failure is a prompt/schema mismatch, repair the prompt or schema before
  Stage 4.
- If the failure is harness loss, repair the harness before Stage 4.
- Do not add task-specific if/else extraction, regex semantic extraction, or
  Codexarium-specific handling.

Build a Stage 3 report pack after Phase 1 is fixed:

```bash
env PYTHONPATH=src:integrations/skillfoundry/src:integrations/skillfoundry/tests \
python3 scripts/build_value_benchmark_report.py \
  --report-dir docs/reports/value_benchmark_stage3_20260531 \
  --run-ids vb-stage3-shakedown-20260531T000000Z \
  --primary-run-id vb-stage3-shakedown-20260531T000000Z \
  --task-manifest benchmarks/tasks/value_benchmark_manifest.json \
  --pricing-table benchmarks/pricing/pi-pricing-20260531.json \
  --waive-blind-review \
  --blind-review-rationale "Stage 3 shakedown uses deterministic hidden checks and ProductGate evidence only." \
  --force
```

Stage 3 report pass criteria:

- report pack builds;
- `leakage_audit.json` passes publishable audit;
- `final_report.md` clearly says Stage 3 is shakedown evidence, not final
  value proof;
- the single failed trial is classified in a committed note or in the report.

## Phase 3: Stage 4 Initial Multi-Task A/B

Stage 4 is the first serious value matrix. Run it as one primary run so the
aggregate files cover all five tasks without report-merging ambiguity.

Recommended matrix:

```text
5 tasks x 3 modes x 3 seeds = 45 trials
```

Command:

```bash
env PYTHONPATH=src:integrations/skillfoundry/src:integrations/skillfoundry/tests \
python3 scripts/run_value_benchmark.py \
  --run-id vb-stage4-ab-20260531T000000Z \
  --stage stage4_initial_ab \
  --task-manifest benchmarks/tasks/value_benchmark_manifest.json \
  --pricing-table benchmarks/pricing/pi-pricing-20260531.json \
  --modes direct_piworker_chat,missionforge_runtime_only,missionforge_full_product_flow \
  --seeds 1,2,3 \
  --provider-mode live \
  --provider-config-source codex_current \
  --timeout-seconds 900 \
  --max-turns 16 \
  --tool-timeout-seconds 60
```

Expected duration:

- Stage 3 full-flow accepted trials averaged roughly 7 minutes each.
- Stage 4 includes 15 full-flow trials plus direct and runtime-only trials.
- Expect several hours.

Monitoring:

- keep the process attached;
- record any provider outage or timeout as a trial condition, not as a hidden
  manual correction;
- do not terminate only because direct chat appears to be winning early.

Stage 4 pass criteria:

- at least four tasks have comparable direct-vs-full-flow pairs;
- at least three tasks have all three modes comparable, or missing runtime-only
  modes are explicitly justified;
- hidden acceptance joins into summaries;
- every accepted comparable summary has cost available through the pricing
  table;
- no hidden acceptance leak;
- no product-specific code enters `src/missionforge`;
- every non-comparable trial has a reason.

Build the Stage 4 report:

```bash
env PYTHONPATH=src:integrations/skillfoundry/src:integrations/skillfoundry/tests \
python3 scripts/build_value_benchmark_report.py \
  --report-dir docs/reports/value_benchmark_stage4_20260531 \
  --run-ids vb-stage4-ab-20260531T000000Z \
  --primary-run-id vb-stage4-ab-20260531T000000Z \
  --task-manifest benchmarks/tasks/value_benchmark_manifest.json \
  --pricing-table benchmarks/pricing/pi-pricing-20260531.json \
  --waive-blind-review \
  --blind-review-rationale "Stage 4 uses deterministic hidden checks and ProductGate evidence; blind review is deferred to final interpretation unless deterministic checks are insufficient." \
  --force
```

Stop and repair before Stage 5 if:

- more than one third of Stage 4 trials are harness failures;
- all full-flow failures are `frontdesk_missing_llm_artifact`;
- any accepted comparable trial has `cost_source=unavailable`;
- hidden checks appear in worker-visible refs;
- the report builder cannot build a sanitized report pack.

## Phase 4: Stage 5 Stability Study

Stage 5 measures whether the Stage 4 signal is stable across more seeds. Use
Stage 4 to pick three representative tasks:

- one task where MissionForge appears to win;
- one task where direct PiWorker appears to win or tie;
- one task with mixed or failure-heavy behavior.

If Stage 4 shows no MissionForge win, still select:

- the task where MissionForge is closest;
- the task where direct PiWorker is strongest;
- the task with the highest product or FrontDesk failure rate.

Default matrix:

```text
3 tasks x 2 modes x 5 seeds = 30 trials
```

Run Stage 5 as a self-contained five-seed run rather than only seeds 4 and 5.
This avoids requiring report builder merge semantics for p50/p95 stability.

Template command:

```bash
env PYTHONPATH=src:integrations/skillfoundry/src:integrations/skillfoundry/tests \
python3 scripts/run_value_benchmark.py \
  --run-id vb-stage5-stability-20260531T000000Z \
  --stage stage5_stability \
  --task-manifest benchmarks/tasks/value_benchmark_manifest.json \
  --task-ids <task-a>,<task-b>,<task-c> \
  --pricing-table benchmarks/pricing/pi-pricing-20260531.json \
  --modes direct_piworker_chat,missionforge_full_product_flow \
  --seeds 1,2,3,4,5 \
  --provider-mode live \
  --provider-config-source codex_current \
  --timeout-seconds 900 \
  --max-turns 16 \
  --tool-timeout-seconds 60
```

Stage 5 pass criteria:

- each selected task has five comparable direct/full-flow attempts, or a
  documented exclusion reason;
- p50 and p95 time values are present;
- p50 and p95 cost values are present where accepted comparable trials exist;
- failure taxonomy distribution is explainable;
- report states whether Stage 4 conclusions strengthened, weakened, or
  changed.

Build the Stage 5 report:

```bash
env PYTHONPATH=src:integrations/skillfoundry/src:integrations/skillfoundry/tests \
python3 scripts/build_value_benchmark_report.py \
  --report-dir docs/reports/value_benchmark_stage5_20260531 \
  --run-ids vb-stage5-stability-20260531T000000Z \
  --primary-run-id vb-stage5-stability-20260531T000000Z \
  --task-manifest benchmarks/tasks/value_benchmark_manifest.json \
  --pricing-table benchmarks/pricing/pi-pricing-20260531.json \
  --waive-blind-review \
  --blind-review-rationale "Stage 5 stability uses deterministic hidden checks and ProductGate evidence; independent review is reserved for the final report if needed." \
  --force
```

## Phase 5: Final Report Builder Enhancement

Before assembling the final report, make sure
`scripts/build_value_benchmark_report.py` can represent both Stage 4 and Stage
5 clearly. The current builder copies the primary run's aggregate as
`aggregate.json`, and records other runs in `run_index.json`. For a complete
final report, add a small multi-run summary so Stage 5 stability is visible
without asking the reader to open ignored raw artifacts.

Required new file:

```text
docs/reports/value_benchmark_20260531/stability_summary.json
```

Required content:

- selected Stage 5 task ids;
- modes;
- seed list;
- per-mode accepted count;
- per-mode comparable count;
- per-mode success rate;
- per-mode p50 and p95 time;
- per-mode p50 and p95 cost where available;
- failure taxonomy counts for Stage 5;
- whether Stage 5 strengthened, weakened, or changed Stage 4 conclusions.

Also update:

```text
docs/reports/value_benchmark_20260531/final_report.md
docs/reports/value_benchmark_20260531/README.md
```

Required final report sections:

- Executive Summary
- Experiment Design
- Compared Modes
- Fairness Controls
- Task Inventory
- Stage 4 Multi-Task A/B Result
- Stage 5 Stability Result
- Cost Method
- Failure Taxonomy
- Leakage Audit
- Claims We Can Make
- Claims We Cannot Make Yet
- Reproduction

Do not make the final report rely only on `aggregate.json` from Stage 4 if the
stability study exists. The reader must be able to see the stability evidence
from committed report files.

## Phase 6: Blind Review Decision

The benchmark can waive blind review only if deterministic hidden checks and
ProductGate evidence are sufficient for every final claim.

Waive blind review when all are true:

- claims are about pass/fail, cost, time, stability, leakage, and failure
  taxonomy;
- no claim depends on subjective product taste or ergonomic quality;
- ProductGate evidence is enough for product-grade acceptance.

Run independent blind review when any final claim says:

- one artifact is more useful to a human user;
- one mode produced a better design beyond deterministic checks;
- final output quality differs in a way not captured by hidden checks.

If review is waived, use this final report rationale:

```text
Blind review is waived because this report claims only deterministic acceptance,
ProductGate closure, cost projection, time, stability, and leakage outcomes.
It does not claim subjective artifact quality beyond those gates.
```

If review is used, create sanitized reviewer packets and ensure:

- packets hide mode names;
- packets hide run ids when they reveal mode;
- packets do not include hidden expected answers;
- packets do not include raw transcripts or provider payloads;
- reviewer output is stored as refs-only summaries.

## Phase 7: Final Report Assembly

After Stage 4, Stage 5, and any required builder enhancement are done, build the
final report pack:

```bash
env PYTHONPATH=src:integrations/skillfoundry/src:integrations/skillfoundry/tests \
python3 scripts/build_value_benchmark_report.py \
  --report-dir docs/reports/value_benchmark_20260531 \
  --run-ids vb-stage4-ab-20260531T000000Z,vb-stage5-stability-20260531T000000Z \
  --primary-run-id vb-stage4-ab-20260531T000000Z \
  --task-manifest benchmarks/tasks/value_benchmark_manifest.json \
  --pricing-table benchmarks/pricing/pi-pricing-20260531.json \
  --waive-blind-review \
  --blind-review-rationale "Blind review is waived because this report claims only deterministic acceptance, ProductGate closure, cost projection, time, stability, and leakage outcomes." \
  --force
```

Required final report files:

```text
docs/reports/value_benchmark_20260531/
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
  stability_summary.json
  blind_review_summary.md
  reviewer_packet_index.json
  reproduction.md
```

If `stability_summary.json` is not implemented, do not call the result
complete. Stage 5 would otherwise be present only as a ref, not as a clear final
result.

## Phase 8: Final Validation

Run all final validation commands:

```bash
env PYTHONPATH=src:integrations/skillfoundry/src:integrations/skillfoundry/tests \
python3 -m unittest discover -s tests -p 'test*.py'

env PYTHONPATH=src:integrations/skillfoundry/src:integrations/skillfoundry/tests \
python3 -m unittest discover -s integrations/skillfoundry/tests -p 'test*.py'

git diff --check

python3 /home/mansteinl/.codex/skills/metaloop/scripts/metaloop_kernel.py --workspace . verify
```

Also run publishable report spot checks:

```bash
find docs/reports/value_benchmark_20260531 -type f | sort

if rg -n "OPENAI_API_KEY|MISSIONFORGE_PI_AGENT_API_KEY|raw_provider_payload" \
  docs/reports/value_benchmark_20260531 \
  --glob '!leakage_audit.json'; then
  echo "hard leak marker found in publishable report"
  exit 1
fi

if rg -n "raw_prompt|raw_transcript|provider_payload" \
  docs/reports/value_benchmark_20260531 \
  --glob '!leakage_audit.json'; then
  echo "schema leak marker found outside leakage_audit.json"
  exit 1
fi
```

Pass criteria:

- unit tests pass;
- integration tests pass;
- `git diff --check` passes;
- MetaLoop verification is not blocking completion;
- hard secret/provider markers are absent from publishable artifacts;
- schema marker names appear only where explicitly allowed;
- `docs/reports/value_benchmark_20260531/final_report.md` has claims and
  non-claims sections;
- `docs/reports/value_benchmark_20260531/reproduction.md` has exact commands.

## Phase 9: Commit And Push

Before committing:

```bash
git status --short
git diff --stat
```

Expected committed paths:

- benchmark script fixes;
- benchmark tests;
- `docs/reports/value_benchmark_20260531/`;
- temporary stage report packs only if they are useful and sanitized;
- this plan document if not already committed.

Expected ignored or uncommitted paths:

- `benchmarks/runs/**`
- provider raw logs;
- node execution raw bodies;
- any local secret-bearing config.

Commit:

```bash
git add scripts/run_value_benchmark.py \
  scripts/build_value_benchmark_report.py \
  tests/test_value_benchmark_report_builder.py \
  docs/MISSIONFORGE_VALUE_BENCHMARK_NEXT_EXECUTION_PLAN.md \
  docs/MISSIONFORGE_VALUE_BENCHMARK_COMPLETION_RUNBOOK.md \
  docs/reports/value_benchmark_20260531

git commit -m "Complete MissionForge value benchmark report"

git push origin value-benchmark
```

If stage report packs are committed, add them explicitly only after they pass
the same publishable leakage checks.

## Completion Checklist

Do not mark the active goal complete until every item is checked:

- [ ] Phase 0 preflight passed.
- [ ] Publishable leakage audit repaired.
- [ ] Audit repair tests added.
- [ ] Unit tests passed after audit repair.
- [ ] SkillFoundry integration tests passed after audit repair.
- [ ] Stage 3 failed trial classified.
- [ ] Stage 3 report pack built and sanitized.
- [ ] Stage 4 live A/B completed.
- [ ] Stage 4 report pack built and sanitized.
- [ ] Stage 4 stop conditions did not block Stage 5.
- [ ] Stage 5 representative tasks selected from Stage 4 evidence.
- [ ] Stage 5 live stability run completed.
- [ ] Stage 5 report pack built and sanitized.
- [ ] Final builder exposes Stage 5 stability in committed report files.
- [ ] Blind review completed or explicitly waived with rationale.
- [ ] Final report pack exists under `docs/reports/value_benchmark_20260531/`.
- [ ] Final report has claims and non-claims sections.
- [ ] Every cost comparison uses an available cost source.
- [ ] Hidden checks were not worker-visible.
- [ ] Every non-comparable trial has a reason.
- [ ] Publishable leakage audit passed.
- [ ] Final unit tests passed.
- [ ] Final SkillFoundry integration tests passed.
- [ ] `git diff --check` passed.
- [ ] MetaLoop verification passed or any remaining review requirement was
  satisfied by an independent reviewer.
- [ ] Final commit created.
- [ ] Branch pushed to `origin/value-benchmark`.

## Expected Timeline

Assuming provider access remains stable:

| phase | expected elapsed time | notes |
| --- | ---: | --- |
| Phase 1 audit repair | 1 to 2 hours | mostly script and test work |
| Phase 2 Stage 3 report | 0.5 hour | after audit repair |
| Phase 3 Stage 4 run | 3 to 6 hours | live PiWorker matrix |
| Phase 4 Stage 5 run | 3 to 5 hours | selected tasks only |
| Phase 5 builder enhancement | 1 to 2 hours | stability summary and report text |
| Phase 6 review decision | 0.5 to 2 hours | depends on whether review is waived |
| Phase 7 to 9 final assembly | 1 to 2 hours | validation, commit, push |

Fast path:

```text
1 working day after audit repair
```

Conservative path:

```text
2 working days if live runs are slow or Stage 4 exposes a repairable harness bug
```

## Final Answer Shape

When the work is complete, the final user-facing answer should include:

- final report path;
- run ids used;
- total task/trial counts;
- accepted counts by mode;
- success, cost, and time winners;
- whether MissionForge beat direct chat anywhere;
- the strongest negative finding;
- leakage audit status;
- cost source caveat;
- validation commands run;
- commit hash and push status.

Do not bury a direct-chat win or a MissionForge failure. The value of the
benchmark is that it tells the truth clearly enough to improve the system.
