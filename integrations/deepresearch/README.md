# MissionForge DeepResearch Integration

Phase 1 is a single-agent academic research baseline. Live mode now uses an
extension-driven source acquisition path with an explicit search-intent layer.

This package intentionally starts small:

- compile an academic research request into MissionForge primitives;
- write a compact research manual, search intent, source packet, source
  collection report, and output contract as refs;
- call one researcher PiWorker;
- run structural checks over the expected draft files, structured source
  packet, and citation refs;
- return `draft_ready`, not `accepted`.
- optionally run paper-review-style update rounds before final judging;
- run Phase 3 quality comparisons against a direct skill-like baseline when
  requested.

The default path remains offline fixture mode. Live mode declares extension
grants, compiles an extension lock, and lets the researcher use mounted Pi
tools to explore the topic. The system can preserve the original topic,
execute externally supplied queries, or ask a PiWorker to author
`sources/search_intent.json` before the live run. It does not contain
domain-specific fallback terms or multi-agent orchestration.

Research intensity:

- `--research-intensity quick` runs a concise scan with smaller source/query
  and PiWorker budgets, with one review round by default.
- `--research-intensity standard` is the default balanced deep research mode.
- `--research-intensity intensive` raises source/query and PiWorker budgets
  and asks the researcher to cross-check more aggressively, with more review
  rounds available.

Intensity changes budget and rubric guidance only. It does not add
domain-specific source ranking, query terms, or Python research logic. Advanced
flags such as `--max-sources`, `--max-search-queries`,
`--piworker-max-turns`, and `--piworker-timeout-seconds` can still override
the preset when needed.

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

Reviewer-guided research updates:

```bash
PYTHONPATH=src:integrations/deepresearch/src \
python3 -m missionforge_deepresearch.cli academic reviewed-run \
  --topic "compiler autotuning survey" \
  --request-id demo-reviewed \
  --workspace /tmp/mf-dr-reviewed \
  --reviewer-mode piworker \
  --review-rounds 2 \
  --researcher-mode piworker \
  --piworker-provider-config-source codex_current
```

`reviewed-run` adds a process-internal paper reviewer before final judging. In
each round the reviewer writes:

```text
reviews/round_XX/reviewer_report.md
reviews/round_XX/next_research_directive.md
```

The researcher then updates the evidence packet and report artifacts, and
records the belief update at:

```text
reviews/round_XX/research_state.json
```

The reviewer is a strict academic critique role. It may guide the next research
step, but it cannot accept the product. The command returns
`packages/deepresearch_reviewed_run_result.json` with `draft_ready` or
`failed`.

Reviewer-guided updates followed by the independent judge:

```bash
PYTHONPATH=src:integrations/deepresearch/src \
python3 -m missionforge_deepresearch.cli academic reviewed-judged-run \
  --topic "compiler autotuning survey" \
  --request-id demo-reviewed-judged \
  --workspace /tmp/mf-dr-reviewed-judged \
  --reviewer-mode piworker \
  --review-rounds 2 \
  --source-mode live \
  --live-extension-mode \
  --search-intent-mode piworker \
  --researcher-mode piworker \
  --judge-mode piworker \
  --piworker-provider-config-source codex_current
```

Only `reviewed-judged-run` can produce the final package, and only when the
separate Judge PiWorker returns `accepted`.

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
  --research-intensity standard \
  --source-mode live \
  --live-extension-mode \
  --search-intent-mode piworker \
  --researcher-mode piworker \
  --piworker-provider-config-source codex_current \
  --piworker-max-turns 20 \
  --piworker-reasoning medium
```

The live search intent is written to `sources/search_intent.json`. The
structured evidence sink is `sources/source_packet.json`, with an extension
lock at `compiled/extension_lock.json` and acquisition diagnostics at
`sources/source_collection_report.json`. In live extension mode the researcher
must overwrite `sources/source_packet.json` with non-empty `source_records`.

Evidence and citation contract:

- source ids use `S1`, `S2`, ... style identifiers;
- `sources/source_packet.json` is the machine-readable evidence ledger;
- `reports/final_report.md` cites material claims with `[S1]` or `[S1, S2]`;
- `reports/final_report.md` includes `## References`;
- `reports/evidence_index.md` maps every source id from the source packet;
- structural checks reject unknown citations or empty source records, but do
  not rank source importance.

Tool healthcheck:

```bash
PYTHONPATH=src:integrations/deepresearch/src \
python3 -m missionforge_deepresearch.cli academic tool-healthcheck \
  --topic "compiler autotuning survey" \
  --request-id demo-tool-health \
  --workspace /tmp/mf-dr-tool-health \
  --search-query "compiler autotuning survey" \
  --search-query "automatic compiler tuning recent survey" \
  --since-year 2023 \
  --max-sources 5
```

The healthcheck writes:

```text
runs/{request_id}/health/tool_healthcheck.json
runs/{request_id}/health/tool_healthcheck.md
```

It probes public academic indexes, GitHub repository search, and the declared
npm Pi extension packages. Google Scholar is recorded as unsupported instead
of scraped because it has no stable official API. This command checks whether
the product's source-acquisition hands can produce structured records; it does
not judge final research quality. If `--search-query` is omitted, the original
topic is used as the only query; passing explicit queries is the recommended
way to test whether the tools are usable independent of prompt-language noise.

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
