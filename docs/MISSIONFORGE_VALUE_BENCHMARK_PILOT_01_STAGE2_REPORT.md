# MissionForge Value Benchmark Pilot 01 Stage 2 Report

Last updated: 2026-05-30

Status: Stage 2 live three-seed pilot executed. The benchmark pipeline ran to
completion, but the result should not be treated as a MissionForge value
verdict yet because it exposed two remaining benchmark/product-loop issues.

## Run Evidence

Run artifacts are local under `benchmarks/runs/` and intentionally ignored by
git.

```text
benchmarks/runs/vb-pilot-01-stage2-20260530T123922Z/
```

Primary packet:

```text
benchmarks/runs/vb-pilot-01-stage2-20260530T123922Z/pilot_result_packet.json
```

Required run-level artifacts were produced:

- `manifest.json`
- `aggregate.json`
- `report.md`
- `mode_comparisons.json`
- `table_data.json`
- `multiseed_result.json`
- `pilot_result_packet.json`
- 9 hidden acceptance result refs

## Matrix

Fixture:

- task: `benchmarks/tasks/complex-method-skill-001/task.json`
- modes:
  - `direct_piworker_chat`
  - `missionforge_runtime_only`
  - `missionforge_full_product_flow`
- seeds: `1`, `2`, `3`
- worker: live PiWorker through the same current Codex provider configuration
- hidden checks: joined only after worker execution

## Raw Current-Pack Result

These are the raw results under the current hidden acceptance pack.

| mode | comparable trials | accepted | success rate | avg accepted time ms | p95 accepted time ms | tokens | failures |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `direct_piworker_chat` | 3 | 1 | 0.333333 | 97390 | 97390 | 173015 | `hidden_acceptance_failed` x2 |
| `missionforge_runtime_only` | 3 | 3 | 1.000000 | 66568 | 83309 | 181101 | none |
| `missionforge_full_product_flow` | 3 | 1 | 0.333333 | 384873 | 384873 | 45118 | `frontdesk_missing_llm_artifact` x2, `product_compile_failed_closed` x2, `hidden_acceptance_failed` x2 |

Aggregate:

- total trials: `9`
- comparable trials: `9`
- total accepted under current pack: `5`
- non-comparable trials: `0`
- hidden acceptance results joined: `9`
- leak hits in scanned public refs: `[]`

Current comparison winners:

- success rate: `missionforge_runtime_only`
- cost per accepted deliverable: `direct_piworker_chat`
- average accepted-deliverable time: `missionforge_runtime_only`

The cost winner is not meaningful yet because provider-reported cost is still
zero in the current PiWorker metrics.

## Per-Trial Summary

| mode | seed | accepted after hidden | hidden passed | product compile | product gate | failure taxonomy |
| --- | ---: | ---: | ---: | --- | --- | --- |
| `direct_piworker_chat` | 1 | no | no | | | `hidden_acceptance_failed` |
| `direct_piworker_chat` | 2 | no | no | | | `hidden_acceptance_failed` |
| `direct_piworker_chat` | 3 | yes | yes | | | none |
| `missionforge_runtime_only` | 1 | yes | yes | | `not_applicable` | none |
| `missionforge_runtime_only` | 2 | yes | yes | | `not_applicable` | none |
| `missionforge_runtime_only` | 3 | yes | yes | | `not_applicable` | none |
| `missionforge_full_product_flow` | 1 | no | no | `failed_closed` | `unsupported` | `frontdesk_missing_llm_artifact`, `hidden_acceptance_failed`, `product_compile_failed_closed` |
| `missionforge_full_product_flow` | 2 | yes | yes | `compiled` | `product_grade` | none |
| `missionforge_full_product_flow` | 3 | no | no | `failed_closed` | `unsupported` | `frontdesk_missing_llm_artifact`, `hidden_acceptance_failed`, `product_compile_failed_closed` |

## Finding 1: Hidden Semantic Check Is Still Too Brittle

The current hidden semantic check is:

```json
{
  "check_id": "HIDDEN-SKILL-MENTIONS-WORKFLOW",
  "kind": "file_contains",
  "ref": "package/SKILL.md",
  "expected_text": "workflow",
  "blocking": true
}
```

This is case-sensitive and exact. Direct seeds 1 and 2 produced valid-looking
method skills but failed because they used `Method Overview` and lower-case
`method` rather than the exact lower-case token `workflow`.

Observed diagnostic:

| mode | seed | package exists | contains `method` or `workflow` case-insensitive | contains exact lower-case `workflow` |
| --- | ---: | ---: | ---: | ---: |
| `direct_piworker_chat` | 1 | yes | yes | no |
| `direct_piworker_chat` | 2 | yes | yes | no |
| `direct_piworker_chat` | 3 | yes | yes | yes |
| `missionforge_runtime_only` | 1 | yes | yes | yes |
| `missionforge_runtime_only` | 2 | yes | yes | yes |
| `missionforge_runtime_only` | 3 | yes | yes | yes |
| `missionforge_full_product_flow` | 1 | no | no | no |
| `missionforge_full_product_flow` | 2 | yes | yes | yes |
| `missionforge_full_product_flow` | 3 | no | no | no |

Interpretation:

- direct raw accepted count is undercounted by the current hidden pack;
- the current raw comparison is useful as harness evidence but not a fair value
  comparison;
- before the next value run, hidden acceptance should support a case-insensitive
  semantic token group such as `method` or `workflow`, or a small structured
  semantic evaluator.

Do not silently rewrite the Stage 2 result as if the hidden pack had already
been repaired. Keep this run as raw evidence and run a repaired/regraded packet
explicitly if the evaluator is changed.

## Finding 2: Full Flow Is Unstable At NeedGriller

`missionforge_full_product_flow` accepted seed 2 but failed seeds 1 and 3 at
`frontdesk_grill`.

The failed NeedGriller nodes produced valid `decision_tree.json` and
`need_grilling_report.json`, but selected:

```json
"readiness": "needs_clarification"
```

and did not produce:

```text
frontdesk/core_need_brief.json
```

That makes `FrontDesk.grill()` fail closed before SolutionArchitect,
IntentBundleAuthor, ProductIntegration, runtime, or ProductGate can run.

The failure is product-relevant rather than environment-non-comparable: the
FrontDesk AI chose to ask a blocking question in a no-user-loop benchmark even
though enough public task information existed to infer a default core need.

Interpretation:

- full-flow needs a clearer no-user-loop benchmark policy;
- NeedGriller should be instructed that when a benchmark/product profile
  supplies enough public constraints and a recommended default exists, it should
  produce `core_need_ready` with an explicitly marked assumption instead of
  blocking for clarification;
- alternatively, the benchmark harness should support a controlled synthetic
  clarification loop, but that would test a different product behavior.

## What Worked

- The Stage 2 matrix executed all 9 live trials to completion.
- No trial was non-comparable.
- Hidden acceptance was joined after worker execution for all 9 trials.
- Public leak scan found no hard raw prompt/transcript/provider/API-key markers.
- Runtime-only was stable across all three seeds.
- Full-flow proved that the AI FrontDesk path can close the task end to end in
  at least one live seed.

## What Did Not Work

- The current hidden semantic check still creates false negatives.
- Full-flow NeedGriller is too clarification-happy for a no-user-loop product
  benchmark.
- Provider cost metrics remain zero, so cost-per-accepted-deliverable is not a
  meaningful comparison metric yet.

## Decision

The Stage 2 pipeline run itself passed as a harness exercise:

- all required artifacts were written;
- all 9 trials were comparable;
- hidden checks were evaluator-only and post-run;
- no hard public leak hits were found;
- the packet is readable and analyzable.

The Stage 2 run does not yet support a clean MissionForge value claim.

## Recommended Next Step

Before expanding to more fixtures or making value claims:

1. Repair the hidden acceptance evaluator so simple semantic checks are not
   case-sensitive exact-token traps.
2. Add a FrontDesk no-user-loop benchmark policy so NeedGriller uses
   assumption-backed `core_need_ready` when enough public information exists.
3. Add provider cost projection or explicitly mark cost metrics as unavailable.
4. Re-run Pilot 01 Stage 2 after those repairs, or regrade this run with a
   clearly versioned repaired evaluator packet and keep both raw and repaired
   results.
