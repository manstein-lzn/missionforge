# MissionForge Value Benchmark Pilot 01 Smoke Report

Last updated: 2026-05-30

Status: Stage 1 smoke repaired with clean split-run evidence. The 3-seed pilot
has not been run yet.

## Run Evidence

Run artifacts are local under `benchmarks/runs/` and intentionally ignored by
git.

| run id | scope | result |
| --- | --- | --- |
| `vb-pilot-01-smoke-repair-20260530T060000Z` | `direct_piworker_chat`, `missionforge_runtime_only`, and attempted full flow | direct and runtime-only accepted with hidden acceptance; full flow hit a transient provider error before final artifact write |
| `vb-pilot-01-fullflow-retry-20260530T070000Z` | full flow only | FrontDesk and compile completed; hidden acceptance passed; old raw-context validator still blocked ProductGradeGate |
| `vb-pilot-01-fullflow-retry-20260530T080000Z` | full flow only | generic verifier and hidden acceptance passed; ProductGradeGate failed because prompt-only target refs incorrectly included `package/check-local.sh` |
| `vb-pilot-01-fullflow-retry-20260530T090000Z` | full flow only | generic verifier passed, ProductGradeGate passed, package refs normalized to the prompt-only three-file contract; hidden acceptance passed after evaluator wording repair |

The final validated per-mode smoke evidence is:

| mode | evidence run | accepted under current checks | notes |
| --- | --- | ---: | --- |
| `direct_piworker_chat` | `vb-pilot-01-smoke-repair-20260530T060000Z` | yes | passed current hidden acceptance regrade |
| `missionforge_runtime_only` | `vb-pilot-01-smoke-repair-20260530T060000Z` | yes | passed current hidden acceptance regrade |
| `missionforge_full_product_flow` | `vb-pilot-01-fullflow-retry-20260530T090000Z` | yes | FrontDesk nodes, ProductIntegration compile, MissionForge verifier, ProductGradeGate, and hidden acceptance all passed |

## Current Hidden-Pack Regrade Trace

The split-run acceptance claim was rechecked against the current committed
hidden pack with the benchmark acceptance APIs:

```bash
env PYTHONPATH=src python3 - <<'PY'
import json
from pathlib import Path

from missionforge.benchmark import (
    BenchmarkSummary,
    apply_hidden_acceptance,
    evaluate_acceptance_pack,
    load_acceptance_pack,
)

root = Path(".")
pack = load_acceptance_pack(
    root,
    "benchmarks/tasks/complex-method-skill-001/acceptance/hidden_checks.json",
)
cases = [
    (
        "direct_T060",
        "benchmarks/runs/vb-pilot-01-smoke-repair-20260530T060000Z/"
        "trials/complex-method-skill-001/direct_piworker_chat/seed-1",
    ),
    (
        "runtime_T060",
        "benchmarks/runs/vb-pilot-01-smoke-repair-20260530T060000Z/"
        "trials/complex-method-skill-001/missionforge_runtime_only/seed-1",
    ),
    (
        "full_T090",
        "benchmarks/runs/vb-pilot-01-fullflow-retry-20260530T090000Z/"
        "trials/complex-method-skill-001/missionforge_full_product_flow/seed-1",
    ),
]
out = {}
for name, trial in cases:
    result = evaluate_acceptance_pack(
        workspace=root,
        trial_workspace_ref=f"{trial}/workspace",
        pack=pack,
    )
    summary = BenchmarkSummary.from_dict(
        json.loads((root / trial / "summary.json").read_text(encoding="utf-8"))
    )
    updated = apply_hidden_acceptance(summary, result)
    out[name] = {
        "hidden_acceptance_passed": result.passed,
        "accepted_after_current_hidden": updated.accepted,
        "failure_taxonomy": updated.failure_taxonomy,
    }
print(json.dumps(out, indent=2, sort_keys=True))
PY
```

Observed result:

```json
{
  "direct_T060": {
    "accepted_after_current_hidden": true,
    "failure_taxonomy": [],
    "hidden_acceptance_passed": true
  },
  "full_T090": {
    "accepted_after_current_hidden": true,
    "failure_taxonomy": [],
    "hidden_acceptance_passed": true
  },
  "runtime_T060": {
    "accepted_after_current_hidden": true,
    "failure_taxonomy": [],
    "hidden_acceptance_passed": true
  }
}
```

## Current T090 Full-Flow Packet

The strongest full-flow evidence is:

```text
benchmarks/runs/vb-pilot-01-fullflow-retry-20260530T090000Z/pilot_result_packet.json
```

After offline regrading with the repaired hidden acceptance pack:

- `smoke_passed`: `true`
- `accepted`: `true`
- `generic_verifier_passed`: `true`
- `product_compile_status`: `compiled`
- `product_gate_status`: `product_grade`
- `product_gate_blocking_finding_count`: `0`
- `hidden_acceptance_passed`: `true`
- `frontdesk_node_count`: `3`
- `frontdesk_worker_call_count`: `3`
- `artifact_refs`:
  - `package/SKILL.md`
  - `package/skillfoundry.bundle.json`
  - `package/README.md`

The T090 full-flow run used live PiWorker for all three FrontDesk nodes and the
runtime worker. The hidden evaluator was applied after the worker run and was
not worker-visible.

## Repairs Made

### Direct Baseline Fairness

The direct PiWorker baseline now receives a worker-safe public product contract
through `allowed_source_refs` instead of being judged only against hidden
SkillFoundry schema expectations.

Relevant fixture files:

- `benchmarks/tasks/complex-method-skill-001/public_contract.md`
- `benchmarks/tasks/complex-method-skill-001/task.json`

### Hidden Acceptance Robustness

The hidden leak checks now avoid failing harmless policy wording. The provider
payload check looks for the sentinel-style `raw_provider_payload` marker rather
than the ordinary phrase `provider payload`.

The semantic hidden check now looks for `workflow` instead of a brittle exact
`Method` heading. This still checks that the generated skill contains a reusable
working method/workflow, while avoiding false failures when the worker names the
section `Workflow`.

Relevant fixture file:

- `benchmarks/tasks/complex-method-skill-001/acceptance/hidden_checks.json`

### FrontDesk Live Node Contracts

FrontDesk PiWorker node specs now include compact schema and field-type
guidance for the high-AI nodes:

- `need_griller`
- `solution_architect`
- `intent_bundle_author`

The guidance keeps FrontDesk AI-heavy: it gives role, schema, and output
contracts to PiWorker, without coding domain semantic extraction with regex or
scenario-specific branches.

Relevant implementation:

- `src/missionforge/frontdesk/pi_node_runner.py`
- `tests/test_frontdesk_pi_node_runner.py`

### Runtime Artifact Projection

The PI Agent result writer now includes changed refs that are inside the
declared allowed scope. This preserves optional FrontDesk artifacts in the
execution report without broadening the worker contract.

Relevant implementation:

- `workers/pi-agent-runtime/src/result-writer.ts`
- `workers/pi-agent-runtime/tests/result-writer.test.mjs`

### Raw Context Validator Semantics

SkillFoundry raw-context checks now distinguish:

- field/sentinel markers such as `raw_prompt`, `raw_transcript`,
  `provider_payload`, and `conversation.jsonl`, which remain hard failures;
- policy sentences such as "do not store raw transcripts or provider payloads",
  which are allowed when they are clearly boundary guidance.

The same behavior is used by SkillFoundry ProductGradeGate validators and by
the MissionIR command validators compiled for runtime verification.

Relevant implementation:

- `integrations/skillfoundry/src/missionforge_skillfoundry/validators.py`
- `integrations/skillfoundry/src/missionforge_skillfoundry/compiler.py`
- `integrations/skillfoundry/tests/test_skill_bundle_validators.py`
- `integrations/skillfoundry/tests/test_prompt_only_compiler.py`

### Prompt-Only Output Normalization

SkillFoundry ProductIntegration now treats `prompt_only` as a fixed package
profile. Even if FrontDesk AI suggests an extra local checker such as
`package/check-local.sh`, the compiled prompt-only request and product contract
target only:

- `package/SKILL.md`
- `package/skillfoundry.bundle.json`
- `package/README.md`

Extra scripts and schemas remain valid only for `code_runtime`.

Relevant implementation:

- `integrations/skillfoundry/src/missionforge_skillfoundry/frontdesk_bridge.py`
- `integrations/skillfoundry/src/missionforge_skillfoundry/product_contract.py`
- `integrations/skillfoundry/tests/test_frontdesk_bridge.py`
- `integrations/skillfoundry/tests/test_product_contract.py`

## Remaining Risk

The clean evidence is split across runs rather than produced by one final
three-mode smoke matrix:

- direct/runtime evidence comes from T060;
- full-flow evidence comes from T090.

This is acceptable for repair validation because the later code changes affect
the full-flow ProductIntegration/ProductGate path and the hidden evaluator; the
T060 direct/runtime artifacts were rechecked against the current hidden pack and
passed.

If a single run packet is required for audit convenience, run one final Stage 1
three-mode smoke before Stage 2. If split-run evidence is acceptable, there is
no remaining smoke blocker to starting the three-seed pilot.

## Decision

Stage 1 no longer has a known blocking defect.

Recommended next action: start Pilot 01 Stage 2 with three seeds across all
three modes, using the current task fixture and the current hidden acceptance
pack. Do not interpret the next run as a final MissionForge value verdict; it
is the first statistically small pilot to prove that the comparison pipeline can
collect stable value metrics.
