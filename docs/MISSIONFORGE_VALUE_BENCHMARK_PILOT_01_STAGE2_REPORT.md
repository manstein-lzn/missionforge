# MissionForge Value Benchmark Pilot 01 Stage 2 Report

Last updated: 2026-05-30

Status: Stage 2 live three-seed pilot now has a clean fresh packet after
benchmark, FrontDesk, and SkillFoundry ProductGate repairs. The clean packet is
valid as a Pilot 01 harness result. It should still not be treated as a broad
MissionForge value verdict because it covers one fixture only and provider cost
metrics are still unavailable.

Update after repair pass: the hidden semantic check has been upgraded to a
case-insensitive token group and the run has been locally regraded without
overwriting the raw packet. That regrade made full-flow instability the primary
blocker for the next repair pass.

Second update after no-user-loop repair: a repaired live rerun moved full-flow
from FrontDesk fail-closed behavior to runtime/ProductGate quality validation.
One remaining failure was traced to the old compiled raw-context command
validator and was repaired in code; another fresh live rerun was required for a
fully clean packet.

Final update: two additional fresh packets exposed and then closed the remaining
contract gaps. `final2` proved FrontDesk no longer failed closed but exposed a
raw-context inspection-language false positive in SkillFoundry ProductGate.
`final3` compiled with the repaired validator and accepted all 9 comparable
trials.

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

These were the raw results under the hidden acceptance pack used during the
live run.

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

## Repaired-Evaluator Regrade

After the run, the hidden semantic check was repaired from exact lower-case
`workflow` matching to a case-insensitive token group:

```json
{
  "kind": "file_contains_any",
  "expected_terms": ["method", "workflow"]
}
```

Local regrade evidence:

```text
benchmarks/runs/vb-pilot-01-stage2-20260530T123922Z/regrade_repaired_evaluator.json
```

Regraded result:

| mode | accepted after regrade | hidden passed | success rate after regrade |
| --- | ---: | ---: | ---: |
| `direct_piworker_chat` | 3/3 | 3/3 | 1.000000 |
| `missionforge_runtime_only` | 3/3 | 3/3 | 1.000000 |
| `missionforge_full_product_flow` | 1/3 | 1/3 | 0.333333 |

Interpretation:

- direct and runtime-only both close this fixture under the repaired evaluator;
- runtime-only remains faster on accepted-deliverable time in this run;
- full-flow still fails two seeds before ProductIntegration because NeedGriller
  chooses blocking clarification instead of assumption-backed `core_need_ready`;
- the repaired evaluator changes the value interpretation materially, so the raw
  packet and repaired regrade must both be kept visible.

## Repair Rerun

After the evaluator repair and the first FrontDesk no-user-loop policy change,
a second live run was executed:

```text
benchmarks/runs/vb-pilot-01-stage2-repair-20260530T131257Z/
```

Primary packet:

```text
benchmarks/runs/vb-pilot-01-stage2-repair-20260530T131257Z/pilot_result_packet.json
```

Result:

| mode | comparable trials | accepted | success rate | avg accepted time ms | p95 accepted time ms | tokens | failures |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `direct_piworker_chat` | 3 | 3 | 1.000000 | 80419 | 87118 | 140321 | none |
| `missionforge_runtime_only` | 3 | 3 | 1.000000 | 94686 | 129582 | 213178 | none |
| `missionforge_full_product_flow` | 3 | 2 | 0.666667 | 409700 | 424045 | 193183 | `runtime_verifier_failed` x1, `product_gate_failed` x1 |

Aggregate:

- total trials: `9`
- comparable trials: `9`
- total accepted: `8`
- non-comparable trials: `0`
- hidden acceptance results joined: `9`
- leak hits in scanned public refs: `[]`

Current comparison winners in this repair rerun:

- success rate: `missionforge_runtime_only`
- cost per accepted deliverable: `direct_piworker_chat`
- average accepted-deliverable time: `direct_piworker_chat`

Cost remains unavailable because provider-reported cost is still zero.

### Repair Rerun Interpretation

The no-user-loop FrontDesk policy changed the full-flow failure shape:

- previous raw Stage 2: full-flow failed 2 seeds at `frontdesk_grill`;
- repair rerun: full-flow had no `frontdesk_missing_llm_artifact` failures;
- full-flow seed 1 and seed 3 reached `product_grade`;
- full-flow seed 2 reached ProductIntegration and runtime but failed verifier
  and ProductGate.

Seed 2 diagnostic:

- FrontDesk status: `draft_ready`;
- ProductIntegration status: `compiled`;
- package files existed;
- hidden acceptance passed;
- ProductGate failed because `SF-PROMPT-NO-RAW-CONTEXT` treated
  non-trigger/policy wording about `provider payloads` as raw-context exposure.

That failure exposed a second raw-context policy false positive. The generated
package text was policy language, for example non-trigger and operating-boundary
sentences such as "Do not activate this skill for requests to collect provider
payloads" and "Do not embed provider payloads".

Code repair after this rerun:

- widened raw-context policy detection around non-trigger and operating-boundary
  language;
- matched the same wider context window in compiled MissionIR command
  validators;
- added regression coverage for non-trigger policy wording.

Local post-repair re-evaluation of the repair rerun seed 2 workspace:

```json
{
  "bundle_failures": [],
  "bundle_passed": true,
  "product_grade": true,
  "findings": [],
  "outcome_category": "product_grade_registered"
}
```

The old `mission_ir` inside that run still contains the pre-repair command
validator, so the persisted live packet correctly remains `8/9`. At that point,
a fresh live run was required to get a packet compiled with the repaired
validator.

## Final Fresh Packet

After repairing FrontDesk no-user-loop schema support and the SkillFoundry
raw-context policy detector, a final fresh packet was executed:

```text
benchmarks/runs/vb-pilot-01-stage2-final3-20260530T145609Z/
```

Diagnostic fresh packets before the final clean packet:

- `vb-pilot-01-stage2-final-20260530T135212Z`: `7/9`; proved the original
  NeedGriller clarification issue had changed into a FrontDesk schema-width
  issue around non-blocking questions and assumptions.
- `vb-pilot-01-stage2-final2-20260530T142333Z`: `8/9`; proved FrontDesk could
  close all seeds but exposed a ProductGate false positive for
  raw-context inspection/check language.

Primary packet:

```text
benchmarks/runs/vb-pilot-01-stage2-final3-20260530T145609Z/pilot_result_packet.json
```

Result:

| mode | comparable trials | accepted | success rate | avg accepted time ms | p95 accepted time ms | tokens | failures |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `direct_piworker_chat` | 3 | 3 | 1.000000 | 83414 | 94196 | 146410 | none |
| `missionforge_runtime_only` | 3 | 3 | 1.000000 | 70088 | 72010 | 224512 | none |
| `missionforge_full_product_flow` | 3 | 3 | 1.000000 | 468323 | 483395 | 208300 | none |

Aggregate:

- total trials: `9`
- comparable trials: `9`
- total accepted: `9`
- non-comparable trials: `0`
- hidden acceptance results joined: `9`
- leak hits in scanned public refs: `[]`

Final packet comparison winners:

- success rate: tie at `1.000000`; the comparison helper reports
  `missionforge_runtime_only`;
- cost per accepted deliverable: `direct_piworker_chat`, but this remains not
  meaningful while provider-reported cost is zero;
- average accepted-deliverable time: `missionforge_runtime_only`.

Final full-flow per-seed checks:

| seed | accepted | hidden acceptance | product compile | generic verifier | ProductGate | product acceptance coverage |
| ---: | --- | --- | --- | --- | --- | --- |
| 1 | yes | passed | `compiled` | passed | `product_grade` | passed |
| 2 | yes | passed | `compiled` | passed | `product_grade` | passed |
| 3 | yes | passed | `compiled` | passed | `product_grade` | passed |

### Repairs Proven By Final Packet

The final packet proves the following repair chain under fresh live execution:

- `file_contains_any` removed brittle hidden exact-token false negatives without
  leaking expected terms into result payloads.
- FrontDesk no-user-loop mode now requires `core_need_brief`, marks the node
  execution policy explicitly, and supports assumption-backed core need briefs.
- `CoreNeedBrief` now has first-class non-blocking `assumptions` and
  `open_questions`, and `ranked_choices_or_free_text` is a supported question
  answer type.
- SkillFoundry raw-context validators now distinguish prohibited raw context
  exposure from policy, non-trigger, operating-boundary, and inspection/check
  language.

This does not prove that full-flow is faster or cheaper than direct chat. In
this fixture, full-flow is materially slower because it runs three FrontDesk AI
nodes plus runtime/ProductGate. The observed value is a stronger product
boundary and product-grade closure, not lower latency on this small fixture.

## Raw Initial Per-Trial Summary

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

## Finding 1: Hidden Semantic Check Was Too Brittle

The hidden semantic check used during the live run was:

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

Raw-run interpretation:

- direct raw accepted count is undercounted by the current hidden pack;
- the current raw comparison is useful as harness evidence but not a fair value
  comparison;
- hidden acceptance should support a case-insensitive semantic token group such
  as `method` or `workflow`, or a small structured semantic evaluator.

Do not silently rewrite the Stage 2 result as if the hidden pack had already
been repaired. Keep this run as raw evidence and run a repaired/regraded packet
explicitly if the evaluator is changed.

Repair status: addressed by `file_contains_any`, the local repaired-evaluator
regrade, and the repair rerun above.

## Finding 2: Full Flow Was Unstable At NeedGriller

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

Repair status: addressed. The first repair rerun had no NeedGriller
fail-closed samples and moved the remaining failure to runtime/ProductGate. The
later final packets exposed a narrower schema issue around non-blocking
assumptions/open questions and a ProductGate raw-context inspection-language
false positive. Both were repaired, and `final3` closed full-flow at `3/3`.

## What Worked

- The Stage 2 matrix executed all 9 live trials to completion.
- No trial was non-comparable.
- Hidden acceptance was joined after worker execution for all 9 trials.
- Public leak scan found no hard raw prompt/transcript/provider/API-key markers.
- Runtime-only was stable across all three seeds.
- Full-flow closed all three seeds end to end in the final fresh packet,
  including FrontDesk, ProductIntegration, runtime verification, ProductGate,
  and hidden acceptance.
- The repair process found real benchmark/product-boundary bugs rather than
  hiding them: hidden evaluator brittleness, FrontDesk no-user-loop contract
  width, and raw-context policy false positives.

## What Did Not Work

- The original hidden semantic check created false negatives before repair.
- Full-flow NeedGriller was too clarification-happy for a no-user-loop product
  benchmark before repair.
- FrontDesk initially lacked schema surface for no-user-loop assumptions and
  non-blocking open questions.
- SkillFoundry raw-context validation initially treated some safe policy,
  boundary, and inspection language as raw context exposure.
- Provider cost metrics remain zero, so cost-per-accepted-deliverable is not a
  meaningful comparison metric yet.
- Full-flow is much slower on this fixture than direct chat or runtime-only
  because it intentionally runs multiple AI/product gates.

## Decision

Pilot 01 Stage 2 passed as a harness exercise after the final fresh packet:

- all required artifacts were written;
- all 9 trials were comparable;
- all 9 trials were accepted in `final3`;
- hidden checks were evaluator-only and post-run;
- no hard public leak hits were found;
- the packet is readable and analyzable.

The Stage 2 result supports a narrow claim: the benchmark infrastructure can run
a comparable live three-mode matrix, and MissionForge full-flow can close this
SkillFoundry fixture through ProductGate when the product contracts are repaired.

It does not yet support a broad value claim that MissionForge is generally
faster, cheaper, or more reliable than pure chat. More fixtures, provider cost
projection, and repeated runs are required.

## Recommended Next Step

Before expanding to more fixtures or making value claims:

1. Keep raw, regraded, repair, `final2`, and `final3` packets visible next to
   each other as benchmark evolution evidence.
2. Add provider cost projection or explicitly mark cost metrics as unavailable
   in any user-facing comparison.
3. Add at least two more fixtures before making a value claim:
   one where FrontDesk should outperform direct chat by preventing ambiguity,
   and one where full-flow overhead is expected not to pay for itself.
4. Add a benchmark retry/repair lane for full-flow so a single ProductGate
   failure can exercise MissionForge repair rather than immediately ending the
   trial.
5. Treat `final3` as the baseline clean packet for future regressions.
