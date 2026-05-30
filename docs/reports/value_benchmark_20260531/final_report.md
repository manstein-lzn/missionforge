# MissionForge Value Benchmark Final Report

Report pack: `docs/reports/value_benchmark_20260531`
Primary run: `vb-stage4-ab-20260531T000000Z`

## Executive Summary

- task_count: 5
- trial_count: 45
- accepted_count: 44
- comparable_trial_count: 45
- success result: success tied between `direct_piworker_chat`, `missionforge_runtime_only` at 1.000000
- cost winner: `direct_piworker_chat`
- time winner: `direct_piworker_chat`
- leakage audit passed: True

## Experiment Design

- Worker: PiWorker only.
- Baseline: direct PiWorker chat using the same live provider/model and pricing table.
- MissionForge arms: runtime-only ablation and full FrontDesk + ProductIntegration + Runtime + ProductGate flow.
- Acceptance: deterministic hidden checks and ProductGate evidence; worker self-report is not acceptance.
- Cost method: provider-reported cost was unavailable in these runs, so cost comparisons use the committed pricing table projection.

## Compared Modes

- `direct_piworker_chat`: direct PiWorker chat baseline with the same task text and acceptance checks applied after execution
- `missionforge_runtime_only`: MissionForge runtime ablation without FrontDesk product discovery
- `missionforge_full_product_flow`: FrontDesk plus ProductIntegration compile plus MissionForge runtime plus ProductGate closure

## Fairness Controls

- provider_mode: `live`
- provider_config_source: `codex_current`
- model: `gpt-5.5`
- pricing_table_id: `pi-pricing-20260531`
- pricing_effective_date: `2026-05-31`
- seeds: `1,2,3`
- run_ids: `vb-stage4-ab-20260531T000000Z,vb-stage5-stability-20260531T000000Z`
- max_turns: `16`
- tool_timeout_seconds: `60`
- run_timeout_seconds: `900`
- hidden acceptance files were kept outside worker-visible prompts and workspaces; results are consumed only after worker execution.
- all modes used the same task manifest, seed list for the same stage, pricing table, provider model, and deterministic hidden acceptance authority.

## Task Inventory

| task_id | family | difficulty | budget | hypothesis |
| --- | --- | --- | --- | --- |
| sf-simple-skill-001 | skillfoundry | simple | 30m/120000tok/$5.00/4turns | direct_piworker_chat should be competitive on a simple prompt-only package |
| sf-ambiguous-skill-001 | skillfoundry | medium | 45m/180000tok/$8.00/6turns | missionforge_full_product_flow should benefit from FrontDesk grilling |
| sf-product-gate-001 | skillfoundry | medium | 45m/180000tok/$8.00/6turns | missionforge_full_product_flow should benefit from ProductGate constraints |
| codexarium-dogfood-001 | codexarium_like_skillfoundry | complex | 60m/260000tok/$12.00/6turns | missionforge_full_product_flow should help convert vague engineering pain into a reusable skill |
| codexarium-dogfood-002 | codexarium_like_skillfoundry | complex | 60m/260000tok/$12.00/6turns | missionforge_full_product_flow should keep product boundaries cleaner for a Rust/performance-oriented skill |

## Cost Method

- pricing_table_id: `pi-pricing-20260531`
- currency: `USD`
- effective_date: `2026-05-31`
- model_prices: `gpt-5.5,missionforge-faux`
- provider_reported_cost_usd was zero or unavailable in the live summaries, so the report uses pricing-table projection from input, output, and cache token counts.
- cost_per_accepted_deliverable_usd includes available attempt cost divided by accepted deliverables; failed attempts with available projected cost are not hidden.

## Included Runs

| run_id | stage | tasks | trials | accepted | comparable |
| --- | --- | ---: | ---: | ---: | ---: |
| vb-stage4-ab-20260531T000000Z | stage4_initial_ab | 5 | 45 | 44 | 45 |
| vb-stage5-stability-20260531T000000Z | stage5_stability | 3 | 30 | 28 | 30 |

## Stage 4 Multi-Task A/B Result

## Mode Summary

| mode | trials | comparable | accepted | success_rate | cost_source | cost_per_acceptance | avg_time_ms | p95_time_ms | tokens | repairs |
| --- | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: |
| direct_piworker_chat | 15 | 15 | 15 | 1.000000 | pricing_table | 0.052347 | 61435.80 | 75681.00 | 600207 | 0 |
| missionforge_full_product_flow | 15 | 15 | 14 | 0.933333 | pricing_table | 0.067362 | 432205.93 | 458185.00 | 849966 | 0 |
| missionforge_runtime_only | 15 | 15 | 15 | 1.000000 | pricing_table | 0.064053 | 73605.47 | 89760.00 | 820760 | 0 |

## Stage 4 Task/Mode Detail

| task_id | mode | trials | accepted | success_rate | hidden_pass | hidden_fail | gate_pass | gate_fail | gate_unsupported | failures |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| codexarium-dogfood-001 | direct_piworker_chat | 3 | 3 | 1.000000 | 3 | 0 | 0 | 0 | 0 | none |
| codexarium-dogfood-001 | missionforge_full_product_flow | 3 | 3 | 1.000000 | 3 | 0 | 3 | 0 | 0 | none |
| codexarium-dogfood-001 | missionforge_runtime_only | 3 | 3 | 1.000000 | 3 | 0 | 0 | 0 | 0 | none |
| codexarium-dogfood-002 | direct_piworker_chat | 3 | 3 | 1.000000 | 3 | 0 | 0 | 0 | 0 | none |
| codexarium-dogfood-002 | missionforge_full_product_flow | 3 | 3 | 1.000000 | 3 | 0 | 3 | 0 | 0 | none |
| codexarium-dogfood-002 | missionforge_runtime_only | 3 | 3 | 1.000000 | 3 | 0 | 0 | 0 | 0 | none |
| sf-ambiguous-skill-001 | direct_piworker_chat | 3 | 3 | 1.000000 | 3 | 0 | 0 | 0 | 0 | none |
| sf-ambiguous-skill-001 | missionforge_full_product_flow | 3 | 2 | 0.666667 | 2 | 1 | 2 | 0 | 1 | hidden_acceptance_failed:1, product_compile_failed_closed:1 |
| sf-ambiguous-skill-001 | missionforge_runtime_only | 3 | 3 | 1.000000 | 3 | 0 | 0 | 0 | 0 | none |
| sf-product-gate-001 | direct_piworker_chat | 3 | 3 | 1.000000 | 3 | 0 | 0 | 0 | 0 | none |
| sf-product-gate-001 | missionforge_full_product_flow | 3 | 3 | 1.000000 | 3 | 0 | 3 | 0 | 0 | none |
| sf-product-gate-001 | missionforge_runtime_only | 3 | 3 | 1.000000 | 3 | 0 | 0 | 0 | 0 | none |
| sf-simple-skill-001 | direct_piworker_chat | 3 | 3 | 1.000000 | 3 | 0 | 0 | 0 | 0 | none |
| sf-simple-skill-001 | missionforge_full_product_flow | 3 | 3 | 1.000000 | 3 | 0 | 3 | 0 | 0 | none |
| sf-simple-skill-001 | missionforge_runtime_only | 3 | 3 | 1.000000 | 3 | 0 | 0 | 0 | 0 | none |

The same counts are available in `stage4_task_mode_summary.json` with ProductGate status breakdowns.

## Stage 5 Stability Result

- stage5_run_id: `vb-stage5-stability-20260531T000000Z`
- interpretation: Stage 5 weakened the full-product-flow signal relative to direct chat.

| mode | trials | comparable | accepted | success_rate | cost_source | cost_per_acceptance | p50_cost | p95_cost | avg_time_ms | p50_time_ms | p95_time_ms |
| --- | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| direct_piworker_chat | 15 | 15 | 15 | 1.000000 | pricing_table | 0.048883 | 0.044589 | 0.068724 | 62395.53 | 60948.00 | 85282.00 |
| missionforge_full_product_flow | 15 | 15 | 13 | 0.866667 | pricing_table | 0.065265 | 0.049023 | 0.096935 | 425537.08 | 431397.00 | 485790.00 |

Task and mode rows are available in `stability_summary.json`.

## Claims We Can Make

- The benchmark produced refs-first comparable summaries for the primary run.
- Direct PiWorker and MissionForge modes were evaluated by the same aggregate/report contracts.
- In Stage 4, success tied between `direct_piworker_chat`, `missionforge_runtime_only` at 1.000000; cost winner was `direct_piworker_chat` and time winner was `direct_piworker_chat`.
- Stage 5 stability result: Stage 5 weakened the full-product-flow signal relative to direct chat.
- In Stage 5, direct PiWorker chat had higher accepted-deliverable rate, lower projected cost per accepted deliverable, and lower p95 time than MissionForge full product flow.
- The publishable report scan found no configured raw prompt/provider/secret leakage markers.
- Cost comparison uses available pricing-table or provider-reported cost sources.
- Blind review was explicitly waived; deterministic checks and ProductGate evidence are the authority.

## Claims We Cannot Make Yet

- Human or independent-agent quality preference beyond deterministic checks was not measured.
- This report does not support a claim that MissionForge full product flow is faster or cheaper than direct PiWorker chat on the measured tasks.

## Failure Taxonomy

- hidden_acceptance_failed: 2
- product_compile_failed_closed: 2
- product_gate_failed: 1
- runtime_verifier_failed: 1

## Leakage Audit

- scanned_file_count: 8
- passed: True
- hard_leak_hits: []
- internal_schema_marker_hit_count: 523

## Evidence Files

- `run_index.json`
- `aggregate.json`
- `mode_comparisons.json`
- `table_data.json`
- `stage4_task_mode_summary.json`
- `stability_summary.json`
- `failure_taxonomy.json`
- `leakage_audit.json`
- `blind_review_summary.md`
- `reproduction.md`

## Reproduction

Exact run and report-pack commands are recorded in `reproduction.md`.
