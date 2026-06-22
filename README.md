# MissionForge

MissionForge is a small PiWorker-centered runtime kernel.

PiWorker owns semantic work. MissionForge owns hard boundaries: frozen task
contracts, workspace refs, permission manifests, evidence records, runtime
progress, secret exclusion, and independent judge artifacts.

## Current Shape

```text
FrontDesk or ProductIntegration
  -> TaskContract + WorkerBrief + JudgeRubric + PermissionManifest
  -> PiWorkerCall
  -> run_piworker_call(...)
  -> PiWorkerCallResult
  -> product judge / package / resume logic
```

The root package intentionally exposes a small programmer API:

- `TaskContract`, `WorkspacePolicy`, `PermissionManifest`
- `WorkerBrief`, `JudgeRubric`
- `PiWorkerCall`, `PiWorkerCallResult`
- `create_default_piworker_adapter`, `run_piworker_call`
- refs, evidence, extension, sandbox, and progress primitives

Higher-level product meaning belongs in integrations such as
`integrations/deepresearch`, not in `src/missionforge`.

## Install

```bash
python3 -m pip install -e .
npm ci --ignore-scripts --prefix workers/pi-agent-runtime
npm run build --prefix workers/pi-agent-runtime
```

## Minimal Call

```python
from missionforge import PiWorkerCall, PiWorkerCallRole, run_piworker_call

call = PiWorkerCall(
    call_id="call-001",
    role=PiWorkerCallRole.EXECUTOR,
    contract_id="contract-001",
    contract_hash="sha256:" + "a" * 64,
    contract_ref="contract/task_contract.json",
    objective="Produce reports/final.md from the visible refs.",
    visible_refs=["contract/task_contract.json"],
    writable_refs=["reports"],
    expected_output_refs=["reports/final.md"],
    permission_manifest_ref="policy/permission_manifest.json",
)

result = run_piworker_call(call, workspace="/tmp/missionforge-run")
```

`PiWorkerCallResult` is boundary evidence, not semantic acceptance. Acceptance
must come from a separate judge role or product integration artifact.

## DeepResearch

The active DeepResearch path is the simplified kernel-v2 runner:

```bash
PYTHONPATH=src:integrations/deepresearch/src \
python3 -m missionforge_deepresearch.cli academic kernel-v2-run \
  --topic "你的调研主题" \
  --request-id research-001 \
  --workspace /tmp/mf-dr \
  --research-intensity standard \
  --live-extension-mode \
  --kernel-v2-adapter-mode piworker \
  --piworker-provider-config-source codex_current \
  --stream-progress
```

The CLI prints absolute output paths for `final_report`, `source_packet`,
`result_package`, `judge_report` when present, and `usage_summary`.

## Validate

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_public_api_boundary \
  tests.test_piworker_call \
  tests.test_pi_agent_runtime_adapter \
  tests.test_kernel_api

PYTHONPATH=src:integrations/deepresearch/src python3 -m unittest \
  integrations.deepresearch.tests.test_kernel_v2 \
  integrations.deepresearch.tests.test_cli \
  integrations.deepresearch.tests.test_deepresearch_import_boundaries

npm test --prefix workers/pi-agent-runtime
```

## Design Notes

- Raw chat is not operational truth.
- A frozen `TaskContract` or explicit revision is task truth.
- Code may reject malformed, unsafe, stale, unauthorized, or unreferenced
  output.
- Code should not pretend to perform product-level semantic judgment.
- Product semantics live in integrations, profiles, manuals, rubrics, and
  artifacts.
- MissionForge core stays product-neutral and PiWorker-centered.

Start with:

- [Kernel API Design](docs/KERNEL_API_DESIGN.md)
- [Deep Research Roadmap](docs/DEEP_RESEARCH_ROADMAP.md)
- [API Boundary](docs/API_BOUNDARY.md)
