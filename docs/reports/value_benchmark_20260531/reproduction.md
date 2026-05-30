# Reproduction

Run artifacts under `benchmarks/runs/` are intentionally ignored by git.
The sanitized report pack records refs, commands, and aggregate outputs.

## Runs

### vb-stage4-ab-20260531T000000Z

```bash
env PYTHONPATH=src:integrations/skillfoundry/src:integrations/skillfoundry/tests \
python3 scripts/run_value_benchmark.py \
  --run-id vb-stage4-ab-20260531T000000Z \
  --stage stage4_initial_ab \
  --task-manifest benchmarks/tasks/value_benchmark_manifest.json \
  --task-ids sf-simple-skill-001,sf-ambiguous-skill-001,sf-product-gate-001,codexarium-dogfood-001,codexarium-dogfood-002 \
  --pricing-table benchmarks/pricing/pi-pricing-20260531.json \
  --modes direct_piworker_chat,missionforge_runtime_only,missionforge_full_product_flow \
  --seeds 1,2,3 \
  --provider-mode live \
  --provider-config-source codex_current \
  --timeout-seconds 900 \
  --max-turns 16 \
  --tool-timeout-seconds 60
```

### vb-stage5-stability-20260531T000000Z

```bash
env PYTHONPATH=src:integrations/skillfoundry/src:integrations/skillfoundry/tests \
python3 scripts/run_value_benchmark.py \
  --run-id vb-stage5-stability-20260531T000000Z \
  --stage stage5_stability \
  --task-manifest benchmarks/tasks/value_benchmark_manifest.json \
  --task-ids sf-simple-skill-001,sf-ambiguous-skill-001,codexarium-dogfood-001 \
  --pricing-table benchmarks/pricing/pi-pricing-20260531.json \
  --modes direct_piworker_chat,missionforge_full_product_flow \
  --seeds 1,2,3,4,5 \
  --provider-mode live \
  --provider-config-source codex_current \
  --timeout-seconds 900 \
  --max-turns 16 \
  --tool-timeout-seconds 60
```

## Report Pack

```bash
env PYTHONPATH=src:integrations/skillfoundry/src:integrations/skillfoundry/tests \
python3 scripts/build_value_benchmark_report.py \
  --report-dir docs/reports/value_benchmark_20260531 \
  --run-ids vb-stage4-ab-20260531T000000Z,vb-stage5-stability-20260531T000000Z \
  --primary-run-id vb-stage4-ab-20260531T000000Z \
  --task-manifest benchmarks/tasks/value_benchmark_manifest.json \
  --pricing-table benchmarks/pricing/pi-pricing-20260531.json \
  --waive-blind-review \
  --blind-review-rationale 'Blind review is waived because this report claims only deterministic acceptance, ProductGate closure, cost projection, time, stability, and leakage outcomes.' \
  --force
```

## Validation

```bash
env PYTHONPATH=src:integrations/skillfoundry/src:integrations/skillfoundry/tests python3 -m unittest discover -s tests -p 'test*.py'
env PYTHONPATH=src:integrations/skillfoundry/src:integrations/skillfoundry/tests python3 -m unittest discover -s integrations/skillfoundry/tests -p 'test*.py'
git diff --check
```
