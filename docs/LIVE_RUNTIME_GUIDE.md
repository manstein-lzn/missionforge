# Live Runtime Guide

This guide covers the opt-in live PiAgent runtime path.

## Default

Default development uses faux execution:

```python
PiAgentRuntimeConfig(provider_mode="faux")
```

## Live Configuration

Set the provider env first:

```bash
export MISSIONFORGE_PI_AGENT_PROVIDER=live
export MISSIONFORGE_PI_AGENT_MODEL=gpt-5.5
export MISSIONFORGE_PI_AGENT_BASE_URL=https://example.test/v1
export MISSIONFORGE_PI_AGENT_API_KEY=...
```

Optional:

```bash
export MISSIONFORGE_PI_AGENT_REASONING=xhigh
export MISSIONFORGE_PI_AGENT_MAX_TURNS=12
export MISSIONFORGE_PI_AGENT_TOOL_TIMEOUT_SECONDS=60
```

## Codex Current Provider

If you set `provider_config_source="codex_current"`, MissionForge reads the
current Codex config/auth files and maps them into the child process
environment. The live path fails closed if the provider shape is wrong.

## What The Live Path Writes

- runtime input under `attempts/<call_id>/pi_agent_input.json`
- runtime output under `attempts/<call_id>/pi_agent_output.json`
- session, events, metrics, savepoints under `attempts/<call_id>/...`
- runtime evidence projection under `reports/piworker_runtime/<call_id>/...`

## Safety Rules

- secrets are redacted in workspace artifacts and evidence
- raw provider payloads do not become durable truth
- worker completion is not acceptance
- missing expected outputs trigger a small bounded follow-up inside the same
  live run before the runtime writes final status
- final status is still decided from expected refs on disk, not from the
  assistant's completion claim
- live smoke should be explicit, not default

## Validation

Run the live smoke only when you intend to use a live provider:

```bash
MISSIONFORGE_PI_AGENT_LIVE_SMOKE=1 PYTHONPATH=src python3 -m unittest tests.test_pi_agent_runtime_live_smoke
```

For the TaskContract-native accepted flow smoke, use the same live flag and
run `tests.test_agentic_flow.AgenticFlowTests.test_live_codex_current_default_task_contract_flow_accepts`.

Example:

```bash
MISSIONFORGE_PI_AGENT_LIVE_SMOKE=1 \
MISSIONFORGE_PI_AGENT_LIVE_TIMEOUT_SECONDS=420 \
PYTHONPATH=src:tests \
python3 -m unittest \
  tests.test_agentic_flow.AgenticFlowTests.test_live_codex_current_default_task_contract_flow_accepts
```

## SkillFoundry Live Dogfood

SkillFoundry live dogfood is a product integration gate, not a default test.
Run it only when you intend to spend live model calls:

```bash
MISSIONFORGE_SKILLFOUNDRY_LIVE_DOGFOOD=1 \
MISSIONFORGE_SKILLFOUNDRY_LIVE_TIMEOUT_SECONDS=420 \
PYTHONPATH=src:integrations/skillfoundry/src:integrations/skillfoundry/tests \
python3 - <<'PY'
from pathlib import Path
import tempfile

from missionforge_skillfoundry import run_skillfoundry_live_dogfood
from test_product_contract import sample_request

workspace = Path(tempfile.mkdtemp(prefix="mf-skillfoundry-live-", dir="/tmp"))
report = run_skillfoundry_live_dogfood(
    sample_request(),
    workspace=workspace,
    timeout_seconds=420,
)

print(f"workspace={workspace}")
print(f"outcome_category={report.outcome_category}")
print(f"run_status={report.run_status}")
print(f"issue_codes={report.issue_codes}")
print(f"package_refs={report.package_refs}")
print(f"evidence_refs={report.evidence_refs}")
PY
```

A completed dogfood run should produce a refs-first report at
`reports/skillfoundry_live_dogfood_report.json` with package refs under
`runs/{bundle_id}/package/`, product-grade refs under `runs/{bundle_id}/qa/`,
and MissionForge evidence refs for the judge report, decision ledger, and final
package.
