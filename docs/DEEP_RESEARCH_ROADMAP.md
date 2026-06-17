# Deep Research Roadmap

Last updated: 2026-06-17

Status: Phase 1 offline single-agent baseline, Phase 2 live extension-backed
source acquisition, Phase 3 quality comparison, Phase 4 independent judging,
Phase 5A evidence/citation hard checks, Phase 5B tool healthcheck diagnostics,
Phase 5C fixed reviewer-guided iteration, and the first Phase 6 reviewer
observation routing path are implemented under `integrations/deepresearch`.
The active Phase 6 work is prompt/manual polish, posterior state contract
hardening, and live validation. Implementation stays outside `src/missionforge`
until a primitive is proven to be product-neutral.

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

## Research Loop Principle

Deep Research is naturally a state-estimation loop, not a one-shot source
collection job. The initial request is a noisy prior. Sources, papers,
repositories, benchmarks, and reviewer observations are measurements. The
durable research state is the posterior that should become clearer as the run
learns more.

Use this mental model:

```text
topic / previous run refs = prior
source packet + fetched evidence = observations
research_state.json = posterior
reviewer report = expert measurement of the posterior
controller decision = simple bounded routing
judge report = final independent acceptance decision
```

Each research update should improve the posterior, not merely append more
sources. The researcher should record what it now believes about the field:
major schools of work, strong evidence, weak evidence, conflicting evidence,
unresolved gaps, and the most valuable next action. The reviewer should assess
that state like a serious academic reviewer: whether the current view of the
field is structurally right, what blockers remain, and whether another research
step is likely to add meaningful value.

Reviewer and Judge PiWorkers should give complete, high-quality feedback in one
pass. They should batch material blockers, missing evidence, stale claims,
failed taxonomy, and repair guidance instead of drip-feeding critique across
loops. Minor polish, nice-to-have expansion, and disclosed residual uncertainty
should not cause endless iteration.

The dynamic controller should remain extremely small and non-semantic. It may
route explicit decisions such as `continue`, `ready_for_judge`, `tool_blocked`,
`revision_required`, `rejected`, and `accepted`; it may enforce round budgets
and stop when no progress is visible. It must not infer domain concepts, add
keywords, rank papers, or judge whether the synthesis is true. Those judgments
belong to PiWorkers through artifacts.

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

Expose research depth as a user-facing product knob, not as hidden Python
semantics:

- `quick`: concise scan with lower source/query/model budgets;
- `standard`: balanced default;
- `intensive`: higher-recall investigation with broader budgets and stronger
  cross-check guidance.

The intensity knob may tune budgets, manuals, and judge rubrics. It must not
add domain-specific keyword branches, source ranking, or semantic acceptance in
Python.

Commercial research is a later profile after the academic path is useful.

## MVP Shape

Start with one researcher PiWorker.

```text
Research request
  -> SearchIntent
  -> bounded source collection tools
  -> optional advisory LongMemoryPacket
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

Long-memory support is an optional product integration layer. DeepResearch may
ask a provider such as Mem0 for a bounded MissionForge
`LongMemoryPacket`, but the packet is advisory retrieval context only. It must
carry source refs, stay under budget, and enter the PiWorker runtime through
the same provider-neutral packet boundary as any other product.

The single researcher should produce:

- `sources/source_packet.json`;
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
- a Pi academic source extension for arXiv, OpenAlex, Semantic Scholar,
  Crossref, and GitHub repository metadata;
- code repositories;
- benchmark and dataset sources;
- web fetch for allowed source URLs;
- previous-run artifact loading;
- exact deduplication and refs-safe diagnostics.

Provider-specific query syntax adaptation is allowed as mechanical glue.
Domain-specific fallback terms are not allowed. If a topic is hard to collect,
the agent should report source gaps and propose follow-up searches.

Current live academic runs declare `local:extensions/pi-academic-sources`
alongside the existing web/code-search Pi packages. That local extension
registers `academic_search`, `academic_fetch`, `citation_lookup`, and
`repo_search`; PiWorker decides which queries and follow-up fetches to run.

The structured evidence sink is `sources/source_packet.json`. The researcher
may freely explore with authorized tools, but must settle sources into
`source_records` and cite them with `[S1]` style identifiers. MissionForge only
checks schema and citation consistency; it does not decide which sources are
important.

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
- `academic minimal-run` is the prompt-first reference path. It keeps Python to
  boundary work only: write a small contract/manual/permission/output contract,
  call one PiWorker, and record boundary validation for file/source/citation
  shape.
- `academic minimal-run --live-extension-mode` declares Pi extension grants,
  compiles them into `compiled/extension_lock.json`, and passes that lock to the
  PiWorker runtime. Python does not precollect sources or choose search terms.
- `academic minimal-loop-run` adds the smallest research loop: researcher
  PiWorker writes/updates the evidence and report refs, reviewer PiWorker writes
  `reviews/review_round_N.json`, and Python only follows
  `accepted|continue|tool_blocked|rejected`.
- Minimal results separate `worker_status`, `boundary_status`, and the
  product-facing draft status. Boundary validation is not semantic acceptance;
  it should block only missing core artifacts, malformed source packets, or
  citations to unknown sources.
- The primary runtime modules stay directly under `missionforge_deepresearch`.
  Stage-specific diagnostics and larger workflows live under
  `missionforge_deepresearch.experimental` so the main path remains readable:
  quality evaluation, reviewer-guided iteration, and tool health checks.
- The default run produces `draft_ready`, never `accepted`.
- The default mode is fixture source collection and fixture researcher.
- `research_intensity` is part of the academic request contract and is exposed
  in the CLI as `--research-intensity quick|standard|intensive`.
- Structural checks now require a non-empty `sources/source_packet.json`,
  source ids in `[S1]` form, a `## References` section, and final-report
  citations that resolve to source packet records.
- The product output contract now includes a mechanical high-quality contract:
  required report sections, source-count/source-type/recentness thresholds, and
  source provenance fields. These checks reject overly thin report shapes
  without ranking source importance or performing semantic research judgment in
  Python.
- The high-quality contract uses stable section ids, localized report headings,
  and shared worker/judge quality dimensions. This keeps product output
  requirements explicit without turning MissionForge into a deterministic
  research expert.
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
- The live tool surface includes the local `pi-academic-sources` extension for
  normalized academic provider access, plus web and code-search Pi packages.
- `--search-intent-mode none` preserves the original topic as the only query.
- `--search-intent-mode external` executes user- or product-supplied queries.
- `--search-intent-mode piworker` asks a PiWorker authoring node to write the
  query plan before collection.
- The compiler does not add domain-specific fallback terms or rank semantic
  importance in Python.
- `--researcher-mode piworker` can hand the frozen contract, live source packet,
  and extension lock to the default MissionForge PiWorker runtime.
- In live extension mode, the initial source packet is an empty evidence sink;
  the researcher must overwrite it with structured records before structural
  checks can pass.

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

### Phase 5A: Evidence Sink And Citation Contract

Strengthen product-visible report quality without adding deterministic research
logic.

Exit criteria:

- `sources/source_packet.json` is a required worker output;
- `sources/source_packet.json` is written before report artifacts so reports
  cite an already recorded machine-readable evidence ledger;
- source records carry stable `S1`, `S2`, ... identifiers plus title, source
  type, and a locator;
- final reports cite material claims with `[S1]` style ids;
- final reports include a `## References` section;
- `reports/evidence_index.md` maps source ids from the packet;
- structural checks reject empty source packets, unknown citations, or
  references that do not align with the packet.

Current implementation:

- `missionforge_deepresearch.evidence` contains the mechanical source packet
  and citation audits.
- The compiled contract, manual, and output contract all state the
  evidence-first write order.
- The single researcher remains the only semantic executor.
- Python does not rank sources, expand domain terms, or judge whether a paper
  is important; it only enforces that cited source ids resolve to the evidence
  packet.

### Phase 5B: Tool Healthcheck

Make source-tool bottlenecks visible before blaming the research agent.

Exit criteria:

- probe public academic indexes separately;
- probe GitHub repository search separately;
- verify that declared Pi extension packages are reachable;
- record Google Scholar as unsupported unless a stable product-grade provider
  is configured;
- write refs-first healthcheck JSON and markdown artifacts.

Current implementation:

- `academic tool-healthcheck` probes Semantic Scholar, Crossref, OpenAlex,
  arXiv, GitHub public repository search, and the declared Pi extension
  packages.
- The command writes `health/tool_healthcheck.json` and
  `health/tool_healthcheck.md` under the run workspace.
- The command can execute explicit `--search-query` values so tool health can
  be separated from raw prompt-language/query-quality noise.
- The healthcheck measures reachability and structured source-record
  production. It does not rank sources, expand domain terms, or judge final
  research quality.

### Phase 5C: Reviewer-Guided Iteration

Turn one-shot research into paper-review-guided updates without building a
Python research engine.

Exit criteria:

- run an initial draft through one or more bounded peer-review rounds;
- give the reviewer a strict academic critique role, not final acceptance
  authority;
- require the reviewer to write `reviewer_report.md` and
  `next_research_directive.md`;
- require the researcher to update the evidence packet, report artifacts, and
  a per-round `research_state.json`;
- carry reviewer and research-state refs into the final run result so the
  independent judge can see the update trail.

Current implementation:

- `academic reviewed-run` runs the draft path, then reviewer-guided update
  rounds, and returns `draft_ready` or `failed`.
- `academic reviewed-judged-run` runs the same reviewer-guided path and then
  submits the revised draft to the independent Judge PiWorker.
- Reviewer and judge roles are instructed to provide complete one-pass feedback:
  batch material blockers, missing evidence, stale claims, and repair guidance
  instead of drip-feeding critique across repeated loops.
- Minor polish, nice-to-have expansion, and disclosed residual uncertainty
  should not force endless iteration.
- `research_intensity` now carries default and maximum review-round budgets:
  quick defaults to one round, standard to two, and intensive to three with a
  four-round cap.
- Each round writes:
  - `reviews/round_XX/review_spec.json`;
  - `reviews/round_XX/reviewer_report.md`;
  - `reviews/round_XX/next_research_directive.md`;
  - `reviews/round_XX/research_state.json`.
- The peer reviewer uses a `judge_piworker` role for critique discipline, but
  metadata and manuals make its authority guidance-only. Product acceptance
  still belongs only to Phase 4's independent judge.
- Python does not decide which critique is semantically correct. It enforces
  refs, role separation, budgets, required artifacts, citation checks, and
  final judge visibility.

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

### Phase 6: State-Driven Research Loop

Replace fixed review-round control with a compact state-driven loop.

Current implementation:

- `academic reviewed-run` requires the reviewer to write
  `reviews/round_XX/reviewer_observation.json`.
- The reviewed-run controller routes only on the observation `decision`.
- `continue` runs one researcher revision and records `research_state.json`.
- `ready_for_judge` stops the loop as `draft_ready` without a revision round.
- `tool_blocked` and `revision_required` stop as `blocked`.
- `rejected` stops as `failed`.
- `academic reviewed-judged-run` invokes the independent judge only after a
  reviewed result is `draft_ready`.

Exit criteria:

- define `research_state.json` as the durable posterior for the run;
- define reviewer observations with explicit decisions such as `continue`,
  `ready_for_judge`, `tool_blocked`, `revision_required`, and `rejected`;
- let the researcher update evidence, reports, and research state from reviewer
  observations;
- let a small controller route only on the structured decisions, progress
  evidence, and hard budgets;
- send the final candidate to the independent judge only when the reviewer says
  the state is ready or budgets force a final decision;
- allow judge `repair` to trigger at most a bounded same-contract repair and
  rejudge path, with complete repair briefs rather than drip-fed issues;
- stop as blocked or revision-required when tools, evidence, or the frozen
  contract prevent meaningful progress.

Target round artifacts:

```text
reviews/round_XX/review_spec.json
reviews/round_XX/reviewer_report.md
reviews/round_XX/next_research_directive.md
reviews/round_XX/reviewer_observation.json
reviews/round_XX/research_state.json   # only after a continue revision
```

`reviewer_observation.json` is the only artifact Python reads for loop
routing. It is intentionally refs-first and small:

```json
{
  "schema_version": "missionforge_deepresearch.reviewer_observation.v1",
  "request_id": "npu-compiler-survey",
  "round_index": 1,
  "decision": "continue",
  "contract_ref": "contract/task_contract.json",
  "contract_hash": "sha256:...",
  "reviewer_report_ref": "reviews/round_01/reviewer_report.md",
  "next_directive_ref": "reviews/round_01/next_research_directive.md",
  "artifact_refs": ["reports/final_report.md"],
  "evidence_refs": ["sources/source_packet.json"],
  "blocker_refs": [],
  "state_refs": [],
  "allowed_next_actions": ["researcher_revision"]
}
```

`research_state.json` is the researcher-authored posterior after a `continue`
revision. It is not a controller decision and must not replace the independent
judge. It should be durable enough for the next researcher, reviewer, or judge
to recover the current view of the field from refs:

```json
{
  "schema_version": "missionforge_deepresearch.research_state.v1",
  "request_id": "npu-compiler-survey",
  "round_index": 1,
  "posterior_kind": "review_guided_research_state",
  "contract_ref": "contract/task_contract.json",
  "contract_hash": "sha256:...",
  "source_packet_ref": "sources/source_packet.json",
  "prior_state_refs": [],
  "reviewer_observation_ref": "reviews/round_01/reviewer_observation.json",
  "reviewer_guidance_refs": [
    "reviews/round_01/reviewer_report.md",
    "reviews/round_01/next_research_directive.md",
    "reviews/round_01/reviewer_observation.json"
  ],
  "belief_updates": [
    {
      "update": "what changed in the researcher's view",
      "supporting_refs": ["sources/source_packet.json"],
      "risk_refs": ["reports/source_gaps.md"]
    }
  ],
  "current_hypotheses": [
    {
      "hypothesis": "current synthesis claim or taxonomy choice",
      "supporting_refs": ["reports/final_report.md", "sources/source_packet.json"]
    }
  ],
  "confidence_notes": [
    {
      "topic": "where the posterior is strong or weak",
      "evidence_refs": ["sources/source_packet.json"],
      "risk_refs": ["reports/source_gaps.md"]
    }
  ],
  "unresolved_gaps": [
    {
      "gap": "remaining uncertainty",
      "gap_refs": ["reports/source_gaps.md"],
      "next_action": "best next evidence action if another round is allowed"
    }
  ],
  "next_best_actions": [
    {
      "action": "judge, continue research, revise contract, or stop",
      "depends_on_refs": ["reports/final_report.md"]
    }
  ],
  "updated_artifact_refs": ["reports/final_report.md"],
  "evidence_refs": ["sources/source_packet.json", "reports/evidence_index.md"]
}
```

The shape is intentionally lightweight: Python may validate schema, refs, round,
and contract linkage, but it must not score the beliefs, rank sources, or infer
semantic sufficiency from the state body.

Decision semantics:

- `continue`: run one researcher revision round, then structural checks, then
  continue if the hard review-round budget allows it.
- `ready_for_judge`: stop the review loop and return `draft_ready` without a
  researcher revision in that round.
- `tool_blocked`: stop as `blocked`; the reviewer report/directive should cite
  the tool or evidence blockers.
- `revision_required`: stop as `blocked`; a frozen-contract revision record is
  required before execution can continue.
- `rejected`: stop as `failed`; product acceptance still belongs only to the
  independent judge and cannot be inferred by this controller.

Controller laws:

- route only on the structured observation decision and hard budgets;
- never inspect report prose to infer whether the research is good enough;
- never synthesize missing domain concepts, fallback queries, or source ranks;
- require refs and schema validation for observation, directives, research
  state, and call records;
- keep reviewer authority guidance-only unless the independent judge is called
  later.

Non-goals:

- no Python semantic research planner;
- no topic-specific fallback terms;
- no paper ranking in code;
- no unbounded loops;
- no replacement of the independent judge with controller heuristics.

## Next Step

Run live reviewed and reviewed-judged acceptance on a real topic, then decide
whether reviewer/revision calls need explicit role-scoped long-memory packets.
Keep the single researcher unless measured output quality shows a need for
another role, more tools, or a specialized repair role.
