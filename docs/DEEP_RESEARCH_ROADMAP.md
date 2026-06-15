# Deep Research Roadmap

Last updated: 2026-06-15

Status: Phase 1 offline single-agent baseline, Phase 2 live extension-backed
source acquisition, and a thin Phase 3 quality-comparison harness are
implemented under `integrations/deepresearch`. Implementation stays outside
`src/missionforge` until a primitive is proven to be product-neutral.

## Direction

MissionForge Deep Research should start as a thin academic research product
shell around a strong PiWorker researcher, not as a large deterministic research
engine.

The product exists to give the model a better playing field:

- a clear research manual;
- a frozen task contract;
- bounded source tools;
- explicit evidence refs;
- stable report outputs;
- delta comparison against previous runs;
- structural checks;
- independent judgment when the draft is ready for product use.

The model owns semantic research work: planning, source triage, coverage
judgment, synthesis, report writing, delta analysis, and repair proposals.
Python owns the hard boundaries: workspace layout, refs, permissions, tool
execution, schemas, package shape, ledgers, and role separation.

## Non-Goals

Do not build a domain expert in Python.

Avoid:

- product semantics in `src/missionforge`;
- hardcoded topic branches;
- deterministic intent inference for arbitrary research topics;
- Python source ranking that pretends to understand research importance;
- a large multi-node workflow before a single-agent baseline proves it is
  insufficient;
- accepting a worker's own output as final product quality.

The code budget is a design constraint. The first version should be hundreds of
lines of product shell and tests, not thousands of lines of research logic.

## First Product

The first product is academic research for R&D teams.

Initial target domains:

- NPU compilers;
- compiler autotuning;
- kernel auto-generation;
- large-model harness engineering.

The first user-visible value is not auditability by itself. The output should
feel better because it has:

- broader source coverage;
- fewer stale claims;
- stronger citations;
- clearer deltas against a previous result;
- explicit gaps when evidence is missing.

Commercial research is a later profile after the academic path is useful.

## MVP Shape

Start with one researcher PiWorker.

```text
Research request
  -> SearchIntent
  -> bounded source collection tools
  -> compact Deep Research manual
  -> TaskContract + WorkspacePolicy + PermissionManifest
  -> single researcher PiWorker
  -> draft report package
  -> structural checks
  -> draft_ready
```

The first version may let product code execute source tools on behalf of the
agent when direct tool calling is unavailable. That code must execute
LLM-authored search intent and record refs; it must not rescue quality with
topic-specific rules.

The single researcher should produce:

- `final_report.md`;
- `evidence_index.md`;
- `research_delta.md`;
- `reading_plan.md`;
- `source_gaps.md`;
- `run_result.json`.

The MVP status is `draft_ready`, not `accepted`, because the execution worker
must not self-accept.

## Source Tools

The source layer is the product's hands.

Prepare it as a bounded tool surface, not as hidden research intelligence:

- Pi extensions for web search, code search, fetch, and repository access;
- academic search APIs and paper indexes;
- code repositories;
- benchmark and dataset sources;
- web fetch for allowed source URLs;
- previous-run artifact loading;
- exact deduplication and refs-safe diagnostics.

Provider-specific query syntax adaptation is allowed as mechanical glue.
Domain-specific fallback terms are not allowed. If a topic is hard to collect,
the agent should report source gaps and propose follow-up searches.

## Roadmap

### Phase 0: Cleanup And Principle

Exit criteria:

- remove the previous experimental DeepResearch implementation;
- keep MissionForge core product-neutral;
- document the thin product shell principle;
- keep this roadmap as the planning anchor.

### Phase 1: Single-Agent Offline Baseline

Build the smallest integration that can run with fixtures.

Exit criteria:

- compile an academic research request into MissionForge primitives;
- write the manual, contract, source packet, and output contract as refs;
- call one researcher PiWorker;
- produce the expected draft package;
- run structural checks;
- prove the run result is refs-first and `draft_ready`.

Current implementation:

- `integrations/deepresearch` contains a compact academic request contract,
  compiler, fixture researcher adapter, structural checks, CLI, and tests.
- The default run produces `draft_ready`, never `accepted`.
- The default mode is fixture source collection and fixture researcher.
- Live source collection is available through `--source-mode live`, but remains
  a bounded source tool, not a Python research engine.
- There is no independent judge or multi-agent split in Phase 1.

### Phase 2: Live Source Acquisition

Replace fixture sources with extension-backed live acquisition.

Exit criteria:

- the agent can author search intent;
- extensions execute the authorized intent and write source refs;
- source gaps are visible in the package;
- a real topic can run end to end without topic-specific code.

Current implementation:

- `--source-mode live --live-extension-mode` compiles declared extension grants
  into `compiled/extension_lock.json`, writes `sources/source_packet.json`, and
  records acquisition diagnostics in `sources/source_collection_report.json`.
- `--search-intent-mode none` preserves the original topic as the only query.
- `--search-intent-mode external` executes user- or product-supplied queries.
- `--search-intent-mode piworker` asks a PiWorker authoring node to write the
  query plan before collection.
- The compiler does not add domain-specific fallback terms or rank semantic
  importance in Python.
- `--researcher-mode piworker` can hand the frozen contract, live source packet,
  and extension lock to the default MissionForge PiWorker runtime.

### Phase 3: Real Quality Evaluation

Compare the single-agent MissionForge path against a direct skill-like Codex
prompt.

Exit criteria:

- run the same topic through both paths;
- compare coverage, freshness, citation quality, deltas, and readability;
- keep only product shell features that improve visible output quality;
- delete or defer complexity that does not improve the report.

Current implementation:

- `academic quality-eval` runs the MissionForge single-agent path and a
  direct skill-like baseline against the same compiled workspace.
- The direct baseline writes its own draft artifacts under
  `direct_baseline/reports`.
- The direct baseline and optional PiWorker evaluator inherit the compiled
  workspace policy ref; they do not create a second permission boundary.
- The comparison writes `evaluation/quality_comparison_report.md`,
  `evaluation/quality_scorecard.json`, and a refs-first package result.
- The default evaluator is a mechanical triage scorecard; `--evaluator-mode
  piworker` can ask a separate PiWorker to compare the two drafts.
- Phase 3 still does not produce `accepted`; it identifies visible quality
  gaps before deciding whether Phase 4 judge work is worth adding.

### Phase 4: Independent Judge

Add a separate judge only after the draft path is useful.

Exit criteria:

- judge receives the frozen contract, rubric, artifact refs, and evidence refs;
- judge can return accepted, repair, revision_required, or rejected;
- repair does not weaken the contract silently;
- final package is accepted only by the judge role.

Current implementation:

- `academic judged-run` runs the single-agent DeepResearch path and then a
  separate Judge PiWorker.
- The judge receives `judge/judge_spec.json`, the frozen task contract,
  `projections/judge_rubric.json`, draft artifact refs, hard-check refs, and
  recorded evidence refs.
- The judge writes `reports/judge_report.json` and
  `reports/judge_rationale.md`.
- `judge/judge_spec.json` includes the required report shape, and the runtime
  only performs mechanical schema normalization for live Judge PiWorker output.
- `packages/deepresearch_final_package.json` is written only for `accepted`.
- `repair`, `revision_required`, and `rejected` are recorded as decisions; no
  repair loop is run in Phase 4.

### Phase 5: Decompose Only When Needed

Split the single researcher into multiple PiWorker nodes only when evidence
shows a bottleneck.

Allowed reasons:

- source acquisition needs a separate long-running agent;
- report writing and review exceed context limits;
- delta analysis becomes a reusable role;
- a judge finds recurring failures that a dedicated role can reduce.

Decomposition should preserve the same manual-first design. More nodes are not
a quality metric.

## Next Step

Run a real live `academic judged-run` after Phase 4 unit coverage. Keep the
single researcher unless measured output quality shows a need for another
role, more tools, or a repair loop.
