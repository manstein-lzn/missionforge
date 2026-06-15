# MissionForge DeepResearch Integration

Phase 1 is a single-agent academic research baseline. Live mode now uses an
extension-driven source acquisition path with an explicit search-intent layer.

This package intentionally starts small:

- compile an academic research request into MissionForge primitives;
- write a compact research manual, search intent, source packet, source
  collection report, and output contract as refs;
- call one researcher PiWorker;
- run structural checks over the expected draft files;
- return `draft_ready`, not `accepted`.
- run Phase 3 quality comparisons against a direct skill-like baseline when
  requested.

The default path remains offline fixture mode. Live mode declares extension
grants, compiles an extension lock, and lets the researcher use mounted Pi
tools to explore the topic. The system can preserve the original topic,
execute externally supplied queries, or ask a PiWorker to author
`sources/search_intent.json` before the live run. It does not contain
domain-specific fallback terms, multi-agent orchestration, or an independent
judge yet.

Live runs use a thin install step in the declared extension root. By default
the extension compiler verifies preinstalled packages; live DeepResearch passes
an npm-based installer into that compile step so the lock is produced from the
declared packages, not from a custom Python collector.

Offline quick start:

```bash
PYTHONPATH=src:integrations/deepresearch/src \
python3 -m missionforge_deepresearch.cli academic single-agent-run \
  --topic "compiler autotuning survey" \
  --request-id demo-research \
  --workspace /tmp/mf-dr-phase1
```

The run package is written under:

```text
runs/{request_id}/packages/deepresearch_run_result.json
```

Live source collection with the fixture researcher:

```bash
PYTHONPATH=src:integrations/deepresearch/src \
python3 -m missionforge_deepresearch.cli academic single-agent-run \
  --topic "compiler autotuning survey" \
  --request-id demo-live-sources \
  --workspace /tmp/mf-dr-live \
  --source-mode live \
  --live-extension-mode \
  --since-year 2023 \
  --max-sources 24
```

Live source collection with externally supplied search queries:

```bash
PYTHONPATH=src:integrations/deepresearch/src \
python3 -m missionforge_deepresearch.cli academic single-agent-run \
  --topic "编译自动调优领域近3年综述" \
  --request-id demo-live-external-intent \
  --workspace /tmp/mf-dr-live-external-intent \
  --source-mode live \
  --live-extension-mode \
  --search-intent-mode external \
  --search-query "compiler autotuning survey" \
  --search-query "auto tuning compilers recent survey" \
  --search-query "machine learning based compiler autotuning" \
  --since-year 2023 \
  --max-sources 24
```

Live source collection with a PiWorker-authored search intent:

```bash
PYTHONPATH=src:integrations/deepresearch/src \
python3 -m missionforge_deepresearch.cli academic single-agent-run \
  --topic "编译自动调优领域近3年综述" \
  --request-id demo-live-piworker-intent \
  --workspace /tmp/mf-dr-live-piworker-intent \
  --source-mode live \
  --live-extension-mode \
  --search-intent-mode piworker \
  --since-year 2023 \
  --max-sources 24 \
  --piworker-provider-config-source codex_current
```

Live source collection with a live PiWorker researcher:

```bash
PYTHONPATH=src:integrations/deepresearch/src \
python3 -m missionforge_deepresearch.cli academic single-agent-run \
  --topic "compiler autotuning survey" \
  --request-id demo-live-piworker \
  --workspace /tmp/mf-dr-live-piworker \
  --source-mode live \
  --live-extension-mode \
  --search-intent-mode piworker \
  --researcher-mode piworker \
  --piworker-provider-config-source codex_current \
  --piworker-max-turns 20 \
  --piworker-reasoning medium
```

The live search intent is written to `sources/search_intent.json`. The live
source packet is written to `sources/source_packet.json`, with an extension
lock at `compiled/extension_lock.json` and acquisition diagnostics at
`sources/source_collection_report.json`.

Phase 3 quality comparison:

```bash
PYTHONPATH=src:integrations/deepresearch/src \
python3 -m missionforge_deepresearch.cli academic quality-eval \
  --topic "compiler autotuning survey" \
  --request-id demo-quality-eval \
  --workspace /tmp/mf-dr-quality \
  --source-mode live \
  --live-extension-mode \
  --search-intent-mode piworker \
  --researcher-mode piworker \
  --direct-baseline-mode piworker \
  --evaluator-mode heuristic \
  --piworker-provider-config-source codex_current \
  --piworker-max-turns 20
```

The quality comparison writes:

```text
runs/{request_id}/packages/deepresearch_quality_evaluation_result.json
runs/{request_id}/evaluation/quality_comparison_report.md
runs/{request_id}/evaluation/quality_scorecard.json
```

The comparison is diagnostic. It compares visible output quality signals
against a direct skill-like baseline; it does not produce `accepted`.
The direct baseline and optional PiWorker evaluator inherit the compiled
workspace policy ref instead of creating a separate permission boundary.

Phase 4 judged run:

```bash
PYTHONPATH=src:integrations/deepresearch/src \
python3 -m missionforge_deepresearch.cli academic judged-run \
  --topic "compiler autotuning survey" \
  --request-id demo-judged \
  --workspace /tmp/mf-dr-judged \
  --source-mode live \
  --live-extension-mode \
  --search-intent-mode piworker \
  --researcher-mode piworker \
  --judge-mode piworker \
  --piworker-provider-config-source codex_current \
  --piworker-max-turns 20
```

The independent judge writes:

```text
runs/{request_id}/judge/judge_spec.json
runs/{request_id}/reports/judge_report.json
runs/{request_id}/reports/judge_rationale.md
runs/{request_id}/packages/deepresearch_judged_run_result.json
```

`packages/deepresearch_final_package.json` is written only when the separate
Judge PiWorker returns `accepted`. `repair`, `revision_required`, and
`rejected` are recorded without running a repair loop.

The judge report uses a strict refs-first JSON schema. The runtime may normalize
mechanical field aliases from live Judge PiWorker output, but it does not change
the judge's decision or infer semantic acceptance in Python.
