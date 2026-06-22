# MissionForge DeepResearch v2

DeepResearch is a product integration built on MissionForge Kernel v2. It is
not part of core.

The active public command is:

```bash
PYTHONPATH=src:integrations/deepresearch/src \
python3 -m missionforge_deepresearch.cli academic kernel-v2-run \
  --topic "调研主题" \
  --request-id research-001 \
  --workspace /tmp/mf-dr \
  --research-intensity standard \
  --live-extension-mode \
  --kernel-v2-adapter-mode piworker \
  --piworker-provider-config-source codex_current \
  --stream-progress
```

## Product Shape

```text
academic request
  -> frozen contract, role briefs, rubrics, permissions, extension lock
  -> researcher PiWorker
  -> reviewer PiWorker
  -> judge PiWorker
  -> accepted | repair/research continuation | blocked | failed
```

Python owns hard boundaries: refs, schemas, permission manifests, extension
locks, route decisions, flow ledgers, progress projection, final path printing,
and token usage summaries.

PiWorker owns semantic research: search planning, source triage, repository and
documentation inspection, synthesis, gap tracking, reviewer critique response,
and final judgment.

## Intensities

- `standard`: web, paper, documentation, and repository-metadata survey.
- `intensive`: deeper repository/code-audit-backed survey when the topic
  involves software systems. The researcher may inspect README, docs, examples,
  tests, configs, source layout, entrypoints, and workflow/tool definitions. It
  must not require installing projects, executing repository code, running
  benchmarks, or experimental reproduction.

There is no active `experimental` intensity.

## Outputs

The CLI prints absolute paths for files that exist:

- `final_report`
- `source_packet`
- `result_package`
- `judge_report`
- `usage_summary`

If an expected file is missing, it is printed under `缺失输出`.

The main package lives at:

```text
runs/{request_id}/packages/deepresearch_kernel_v2_result.json
```

The final markdown report normally lives at:

```text
runs/{request_id}/reports/final_report.md
```

The product-level token summary lives at:

```text
runs/{request_id}/metrics/usage_summary.json
```

## Fixture Smoke

Use fixture mode only to test wiring without a live PiWorker:

```bash
PYTHONPATH=src:integrations/deepresearch/src \
python3 -m missionforge_deepresearch.cli academic kernel-v2-run \
  --topic "compiler autotuning survey" \
  --request-id demo-kernel-v2-fixture \
  --workspace /tmp/mf-dr-kernel-v2-fixture \
  --kernel-v2-adapter-mode fixture
```

## Validate

```bash
PYTHONPATH=src:integrations/deepresearch/src python3 -m unittest \
  integrations.deepresearch.tests.test_kernel_v2 \
  integrations.deepresearch.tests.test_cli \
  integrations.deepresearch.tests.test_deepresearch_import_boundaries
```
