# DeepResearch Academic Literature Upgrade Plan

Status: `m5c_parsed_pdf_evidence_consumption`; next priority is `citation_support_against_parsed_evidence`

This document plans the DeepResearch upgrade needed to support an academic
literature-review product with multi-source paper discovery, seed-paper/PDF
ingestion, citation-audited Chinese Markdown output, and a default no-key
scholarly provider stack. OpenAlex is an optional enhancement when configured;
Google Scholar, paid APIs, and browser providers are non-core fallbacks.

DeepResearch remains a product integration and reference external application.
It must keep importing MissionForge through the package root only:

```python
import missionforge as mf
```

MissionForge core owns refs, contracts, permissions, ledgers, runtime evidence,
extension locks, progress, and PiWorker execution boundaries. Academic search,
paper ranking, citation policy, PDF parsing, report templates, and Google
Scholar handling belong in the DeepResearch package or in explicit extensions,
not in `src/missionforge`.

DeepResearch must also be the reference product for MissionForge's long-lived
agent context lifecycle. Resume is not chat-history replay. Resume means
restoring a role-specific compiled `ContextPackage` for the active PiWorker
role, subject to contract, permission, tool-schema, compiler-version, and ref
hash validation. Raw dialogue is only one source inside the package.

DeepResearch should have a visual product surface. CLI/TUI remain useful for
developers, automation, and source-tree testing, but the reference product
experience should be a project-oriented web console where users can see the
research lifecycle, talk to FrontDesk, inspect sources/citations, pause/resume
runs, and open final reports without reading workspace files.

## Provider Policy Decision

DeepResearch academic literature review should work by default without any
provider API key, paid account, browser profile, cookie, or manual login. The
default product promise is a no-key scholarly acquisition stack with explicit
coverage limits.

Default no-key providers should be prioritized in this order:

- Semantic Scholar public search/fetch where available.
- arXiv API for preprints.
- Crossref for DOI and metadata verification.
- DBLP for computer-science venue metadata.
- OpenCitations for citation/reference data where public access is available.
- PubMed/PMC E-utilities for biomedical topics.
- Legal public URLs and PDFs discovered through provider metadata.

If an OpenAlex key is supplied, DeepResearch may enable an OpenAlex-enhanced
mode for broader metadata coverage, open-access locator enrichment, citation
and open-access cross-checks, and additional deduplication identifiers. Missing
OpenAlex configuration is not a task failure.

Google Scholar, SerpAPI, Playwright/browser automation, CORE, and other
key/session/paid providers may exist as optional extension capabilities, but
they are not part of the default acceptance bar.

## ContextPackage Resume Decision

DeepResearch should behave like a persistent project, not a one-shot run. When
the user closes FrontDesk, pauses a research run, or restarts the application,
MissionForge should save the latest complete ContextPackage for each active
role and restore it on the next open when the package fingerprint is still
valid.

The product-level promise:

```text
open existing DeepResearch project
  -> restore latest FrontDesk ContextPackage
  -> show current lifecycle/research state
  -> continue conversation or route intervention/revision
```

For provider-facing equivalence, when all fingerprints are unchanged and the
next user input is identical, the restored provider context should be
equivalent to the context that would have been sent without closing the
application.

MissionForge core owns:

- ContextPackage schema, persistence, hashing, and validation;
- provider-turn and tool-turn safe-point capture;
- role-specific package isolation;
- permission filtering before restore;
- invalidation and fallback recompile from refs, working sets, and checkpoints;
- compaction/checkpoint lifecycle when packages grow too large.

DeepResearch owns only product declarations and semantic state refs:

- which roles exist: FrontDesk, source mapper/researcher, reviewer, judge;
- which role is currently active;
- which product refs describe project state, such as `state/research_state.json`,
  `sources/source_graph.json`, reviewer observations, judge report, and final
  report refs;
- what user-facing lifecycle states mean for the project.

DeepResearch must not build a separate memory database, product-specific
context engine, token-pruning policy, or retention policy. Its resume layer
should save and reference ContextEngine-owned raw context records through core
APIs and treat ContextPackages as opaque MissionForge data.

## Target Product Standard

Working title:

> 面向学术调研的多源文献检索与综述生成工具

Given a research topic and optional seed papers, DeepResearch should:

1. Use FrontDesk to pressure-test vague research intent before execution when
   the topic is underspecified.
2. Search across multiple scholarly sources.
3. Normalize, deduplicate, rank, and triage papers.
4. Fetch metadata and accessible abstracts/full text where permitted.
5. Generate a Chinese Markdown literature review with traceable citations.
6. Verify that every report citation maps to a real, accessible reference.
7. Record source gaps, provider failures, and confidence limits explicitly.

The target report structure should support the requested pattern:

```text
引言与背景
-> 分主题论述
-> 横向对比表格
-> 现存挑战与展望
-> 结论
-> 文末参考文献
```

Inline citations should use Markdown-compatible clickable anchors:

```markdown
...相关工作已经显示这种设计会影响 HLS 后端优化 [cite: 12](#ref-12)。

## 参考文献

<a id="ref-12"></a>[12] Paper title. Authors. Venue, Year. https://...
```

The acceptance bar is not "a report exists"; it is a source-audited literature
review where cited claims, reference entries, and source records agree.

## Current Baseline

The current DeepResearch implementation now provides the first hard product
backbone:

- A product package under `integrations/deepresearch`.
- A package-first API boundary using `import missionforge as mf`.
- Kernel v2 flow:
  `source_mapper -> researcher -> reviewer -> judge` by default, with a
  conditional `seed_normalizer -> source_mapper -> researcher -> reviewer ->
  judge` path when seed papers or seed PDFs are supplied.
- A frozen task contract that includes the sanitized request payload and stable
  request payload hash, so optional seeds/provider policy/target source count
  are task authority rather than loose UI state.
- Previous run refs are staged into current-run `inputs/previous_runs/` with an
  `inputs/previous_run_index.json`, preserving the run-root permission boundary.
- Workspace refs for:
  - `inputs/seed_papers.json`
  - `inputs/seed_pdf_index.json`
  - `sources/seed_source_packet.json`
  - `reports/seed_gaps.md`
  - `state/seed_control.json`
  - `sources/provider_capabilities.json`
  - `sources/search_plan.json`
  - `sources/provider_hits.jsonl`
  - `sources/source_packet.json`
  - `sources/coverage_report.json`
  - `sources/canonical_sources.json`
  - `sources/dedupe_map.json`
  - `sources/source_graph.json`
  - `citations/citation_registry.json`
  - `citations/report_citation_map.json`
  - `state/citation_projection_validation.json`
  - `reports/evidence_index.md`
  - `reports/source_gaps.md`
  - `analysis/insight_map.json`
  - `claims/claim_index.json`
  - `state/claim_index_validation.json`
  - `reports/final_report.md`
  - `reports/final_report.citation_projected.md`
  - `judge/judge_report.json`
- Live academic extension tools:
  - `academic_provider_capabilities`
  - `academic_search`, including single-query and batch `queries` mode
  - `academic_fetch`
  - `citation_lookup`
  - `repo_search`
- Live PDF extension tools:
  - `pdf_provider_capabilities`
  - `grobid_parse_pdf`
- Current provider adapters:
  - Semantic Scholar
  - arXiv
  - Crossref
  - DBLP
  - PubMed
  - OpenCitations citation lookup for DOI neighborhoods
  - OpenAlex only when `OPENALEX_API_KEY` enables the optional enhancement
  - GitHub repository search
- Provider capability, missing-key, optional-enhancement status, search plans,
  provider-hit logs, and coverage reports are persisted as source artifacts.
- Optional seed papers and seed PDFs are staged into explicit input artifacts.
  PDF parsing is GROBID-first through `pi-pdf-sources`; raw TEI and diagnostics
  plus metadata, sections, references, and provenance projections are extension
  outputs under `sources/seed_pdfs/`, not hand-written Python PDF parsing.
- Parsed seed PDF refs are carried through source records, canonical sources,
  evidence indexes, and claim indexes as explicit `parsed_pdf_refs`,
  `evidence_refs`, and `supporting_evidence_refs`.
- Standard academic runs now target a 50-source reference budget by default;
  intensive runs target 100, while `target_source_count` may override the
  budget and coverage sufficiency remains a PiWorker/Judge decision.
- Product-level reviewer/judge prompts for synthesis, citation integrity,
  source gaps, insight map, and report quality.
- Mechanical source graph projection, exact-id/title dedupe, citation
  projection, citation validation, and claim-index source-id validation. If the
  PiWorker/Judge flow returns `accepted` but these mechanical checks fail, the
  product result is downgraded to `failed`.
- FrontDesk assistant turns support candidate choices with a freeform option;
  choices are UX protocol, not frozen task truth.
- Persistent project lifecycle and ContextPackage resume foundation:
  - `project/project_manifest.json`
  - `project/lifecycle_state.json`
  - `project/run_index.json`
  - `project/resume_diagnostics.json`
  - role-local ContextPackage pointers under `context/{role}/`
  - FrontDesk runs through a single-step Kernel flow, so FrontDesk also gets
    ContextEngine-owned ContextPackages and StepRecords.
  - Kernel StepRecords preserve provider pre-turn ContextPackage metadata and
    also record post-turn ContextPackage refs for lifecycle/resume.
  - DeepResearch lifecycle records opaque ContextPackage refs and core-authored
    restore decisions; it does not trim, summarize, or inspect provider
    message internals.

These are necessary but not sufficient for the full requested product.

## Gap Analysis

### G1: Provider Strategy: No-Key Default With OpenAlex Enhancement

Current state:

- `pi-academic-sources` has useful public provider adapters, including Semantic
  Scholar, arXiv, Crossref, DBLP, PubMed, OpenCitations citation lookup,
  optional OpenAlex, and GitHub repository search.
- The product plan previously treated Google Scholar/browser support as a major
  gap.
- Provider capability, missing-key, and enhancement state are available through
  `academic_provider_capabilities`. Product-level provider capability,
  search-plan, provider-hit, and coverage-report artifacts are part of the
  Kernel v2 source-mapper contract.

Target:

- Default academic literature runs require no provider API key, paid account,
  browser cookies, or manual login.
- Default acquisition uses no-key/public providers first:
  - Semantic Scholar
  - arXiv
  - Crossref
  - DBLP
  - OpenCitations
  - PubMed/PMC E-utilities when topic-relevant
- OpenAlex runs only as an optional enhancement when a key/configuration is
  present.
- Absence of an OpenAlex key records an explicit optional-enhancement-disabled
  diagnostic and does not fail the task.
- Google Scholar, SerpAPI, Playwright/browser automation, CORE, and other
  key/session/paid providers remain optional fallback/enrichment extensions.
- Record provider status, throttling, rate-limit, captcha/manual-intervention
  needs, disabled optional enhancements, and unavailable results as evidence
  artifacts.

Design rule:

- Provider preflight writes `sources/provider_capabilities.json`.
- Default runs must not require any secret.
- Optional provider credentials must be supplied through environment/secret
  mounts and excluded from persisted artifacts.
- No Google Scholar logic in `src/missionforge`.
- No bypassing access controls or anti-abuse systems.
- Browser automation, when explicitly enabled, must run under workspace,
  permission manifest, extension lock, network policy, and sandbox boundary.

### G2: Seed Papers And PDF Inputs

Current state:

- `AcademicResearchRequest` accepts optional `seed_papers`, `seed_pdf_refs`, and
  `sample_report_ref`; these fields are frozen into the task contract. Raw seed
  PDF refs are visible only to `seed_normalizer`; later steps consume seed
  packets and gaps instead of raw PDFs.
- `previous_run_refs` are staged into current-run input refs instead of exposing
  outer workspace paths directly.
- `inputs/seed_papers.json` and `inputs/seed_pdf_index.json` are written for
  each run. Available seed PDFs are staged under `inputs/seed_pdfs/` with hash,
  byte length, availability, diagnostics, and a parser output prefix under
  `sources/seed_pdfs/`.
- A conditional `seed_normalizer` PiWorker step writes
  `sources/seed_source_packet.json`, `reports/seed_gaps.md`, and
  `state/seed_control.json` before source mapping when seeds exist.
- `pi-pdf-sources` provides `pdf_provider_capabilities` and
  `grobid_parse_pdf`. It delegates to a configured GROBID service and writes
  raw TEI, diagnostics, metadata, sections, references, and provenance under
  `sources/seed_pdfs/`; it rejects absolute paths and unsafe refs.
- There is not yet a Web PDF upload UI, OCR fallback, or source-mapper authored
  semantic use of parsed PDF spans beyond the seed packet refs.

Target:

- Seed papers and seed PDFs are optional accelerators, not required inputs.
  The product must work from a natural-language topic alone.
- Add product contract fields:
  - `seed_papers`: title/arXiv/DOI/URL records.
  - `seed_pdf_refs`: uploaded PDF artifact refs.
  - `sample_report_ref`: optional user-provided sample report/template.
- Add seed normalization artifacts:
  - `inputs/seed_papers.json`
  - `inputs/seed_pdf_index.json`
  - `sources/seed_source_packet.json`
- Parse PDFs into refs through external providers, not custom PDF parsing:
  - raw PDF ref
  - GROBID TEI ref
  - metadata candidate ref
  - parse diagnostics ref
  - later page/span provenance refs

### G3: Source Graph, Deduplication, And Ranking

Current state:

- Kernel v2 source mapper now writes `sources/provider_hits.jsonl` as part of
  the source-acquisition artifact contract.
- Provider tools return normalized records, and Kernel v2 now projects
  `sources/source_packet.json` into `sources/canonical_sources.json`,
  `sources/dedupe_map.json`, and `sources/source_graph.json`.
- Deduplication for exact DOI, arXiv, Semantic Scholar, OpenAlex, and normalized
  title fallback is mechanical. Ranking and semantic inclusion remain later work
  owned by PiWorker-authored artifacts.

Target artifacts:

- `sources/provider_hits.jsonl`
- `sources/canonical_sources.json`
- `sources/dedupe_map.json`
- `sources/ranked_sources.json`
- `sources/inclusion_decisions.json`
- `sources/source_graph.json`

Canonical source records should include:

- canonical id
- title
- normalized title hash
- authors
- year
- venue
- DOI
- arXiv id
- Semantic Scholar paper id
- OpenAlex id
- URL/PDF URL
- abstract availability
- fulltext availability
- citation count where available
- provider provenance
- fetch status
- accessibility status
- inclusion/exclusion decision
- evidence strength

Hard code may normalize identifiers, deduplicate exact ids, validate schemas,
and compute mechanical scores. PiWorker owns semantic relevance, taxonomy, and
research-line assignment.

### G4: Search Strategy And Coverage Control

Current state:

- `source_mapper` is still the first-pass evidence handoff phase, but it now
  has an explicit search-acquisition artifact contract.
- `source_mapper` must write `sources/search_plan.json`,
  `sources/provider_hits.jsonl`, `sources/source_packet.json`,
  `sources/coverage_report.json`, source gaps, research state, and source
  control before synthesis handoff.
- `academic_search` supports batch `queries` so PiWorker can run independent
  query families across multiple providers concurrently.
- Standard mode targets a 50-source reference budget; intensive mode targets
  100. `target_source_count` may override either budget.
- The source count remains coverage guidance, not a hard acceptance rule. The
  report and coverage artifacts must explain why a run undershoots or expands
  beyond the reference target.

Target:

- Add a search-plan artifact authored by PiWorker:
  - `sources/search_plan.json`
  - query families
  - provider plan
  - seed expansion plan
  - inclusion criteria
  - stopping criteria
  - expected evidence classes
- Add a source-coverage artifact:
  - `sources/coverage_report.json`
  - provider coverage
  - year coverage
  - research-line coverage
  - seed-neighborhood coverage
  - inaccessible source counts
- Add an "academic_literature" intensity or mode with product-specific budgets:
  - 50 source records as a reference baseline for typical literature reviews
  - adaptive expansion beyond 50 when the research question requires more
    evidence, for example 100+ papers for broad or fragmented topics
  - max provider hits: larger than final included papers
  - max browser rounds
  - max PDF fetches
  - max citation-neighborhood expansions

The source count is a coverage budget and evidence-sufficiency decision, not a
hard cap or fixed acceptance rule. The final report must disclose when a topic,
provider failure, or access limitation prevents the reference baseline from
being useful, and the reviewer/judge may require more than 50 sources when the
topic is broad enough.

### G4A: FrontDesk Requirement Discovery And Choice UX

Current state:

- DeepResearch already has a FrontDesk PiWorker node and chat-style TUI.
- The assistant turn schema supports direct messages and focused questions.
- Candidate choices with labels/descriptions/recommended/freeform flags are now
  part of the assistant-turn protocol and rendered by CLI/TUI surfaces.

Target:

- FrontDesk should actively pressure-test vague topics before execution.
- It should ask fewer, sharper questions rather than generic intake checklists.
- When useful, FrontDesk should offer 2-4 mutually exclusive candidate choices
  that the UI can render as a direction-key selection, following Codex/Claude
  Code style interaction:
  - recommended option first when there is a defensible recommendation
  - short labels
  - one-sentence tradeoff/rationale
  - last option reserved for the user's own custom idea
- Candidate choices are a UX protocol, not frozen task truth. The frozen
  authority remains the approved requirements document and derived
  `AcademicResearchRequest`.
- FrontDesk should explicitly capture whether seed papers, OpenAlex key, PDF
  uploads, and other optional inputs are available, but it must not block a run
  only because those optional accelerators are absent.

### G5: Citation Projection And Markdown Anchors

Current state:

- Researcher brief asks for citations like `[S1]`.
- A deterministic citation projector converts `[S1]` body citations into
  `[cite: N](#ref-N)`, writes citation registry/map artifacts, replaces the
  reference section, and validates unknown/unprojected source ids.
- HTML renderer is minimal but citation-aware for validated citation links and
  generated reference anchors.

Target artifacts:

- `citations/citation_registry.json`
- `citations/reference_entries.json`
- `citations/report_citation_map.json`
- `reports/final_report.citation_projected.md`
- `state/citation_projection_validation.json`

Citation projector responsibilities:

- Assign stable reference numbers.
- Convert source ids to `[cite: N](#ref-N)`.
- Generate reference anchors and entries.
- Reject references without source records or accessible locator.
- Preserve source refs and hashes.

The projector should not decide whether a claim is semantically supported by a
paper. It only enforces mechanical citation integrity.

### G6: Citation Truthfulness And Claim Support

Current state:

- Claim validation checks that `supporting_source_ids` exist.
- Citation validation checks source-id citation projection and reference-anchor
  consistency.
- Accepted flows are downgraded to product `failed` when mechanical citation or
  claim-source validation fails.
- URL accessibility and semantic support remain Judge/PiWorker work backed by
  evidence refs.

Target:

- Extend claim index:
  - claim text
  - report location
  - cited reference numbers
  - supporting canonical source ids
  - quoted/evidence snippets when available
  - evidence type: metadata, abstract, full text, PDF text, repo docs
  - support status
  - confidence note
- Add hard checks:
  - every `[cite: N]` maps to a reference entry
  - every reference entry maps to a canonical source
  - every canonical source has at least one accessible locator or explicit
    inaccessible status
  - no orphan references
  - no unknown source ids
  - no duplicate reference numbers
- Add Judge PiWorker rubric:
  - cited claim must be consistent with cited source record and fetched content
  - strong claims require stronger evidence than metadata-only records
  - unsupported or mismatched citations require repair

This preserves the architecture rule: code checks mechanical truth boundaries;
Judge PiWorker checks semantic support against evidence refs.

### G7: Report Template And Sample Matching

Current state:

- Report sections are a generic literature-review template.
- A user-provided target sample is not part of the contract.

Target:

- Add report-template contract:
  - required section ids
  - display headings
  - citation style
  - comparison table requirements
  - language
  - audience
  - style constraints
  - sample report ref/hash when provided
- Add product templates:
  - `academic_literature_review.zh`
  - future variants such as survey, annotated bibliography, technical memo
- The researcher may adapt subsection structure, but required top-level
  sections and citation policy remain contract authority.

### G8: Frontend And Long-Running UX

Current state:

- CLI and TUI exist.
- No web frontend, upload UI, source table, or citation audit page.

Target:

- Web console as a first-class DeepResearch product surface:
  - project list/open existing project
  - ContextPackage resume status
  - FrontDesk chat and lifecycle controls
  - topic input
  - seed paper input
  - PDF upload
  - provider capability status
  - live progress board
  - pause/resume/checkpoint/revise/cancel controls backed by the interaction
    plane
  - source table with dedupe/ranking/inclusion status
  - citation audit table
  - final Markdown preview/download
- The UI reads refs, lifecycle state, context-package status, and progress
  artifacts; it does not become the source of task truth.

The frontend must be a host over MissionForge/DeepResearch APIs, not a second
runtime. It may render and submit user actions, but the durable authority
remains frozen contracts, revision records, interaction events, role
ContextPackages, and artifact refs.

### G9: Deployment And Runtime Capabilities

Current state:

- Package install path exists.
- Browser dependencies, PDF parsers, and provider credentials are not modeled as
  product deployment capabilities.

Target:

- Docker compose for the DeepResearch example:
  - Python package
  - PiAgent runtime
  - Node extension runtime
  - optional Playwright browsers
  - workspace volume
  - provider credential/session volume
- Capability preflight:
  - network availability
  - Node/npm
  - browser availability
  - PDF parser availability
  - provider configuration
  - sandbox status

### G10: Persistent Project Lifecycle And ContextPackage Resume

Current state:

- MissionForge ContextEngine already has context sources, working sets,
  checkpoints, pressure diagnostics, and managed compaction records.
- Kernel steps already support `context_working_set_ref`.
- DeepResearch FrontDesk persists `frontdesk/dialogue.jsonl`,
  `frontdesk/session_state.json`, `frontdesk/assistant_turn.json`,
  `frontdesk/research_requirements.md`, and `frontdesk/frontdesk_control.json`.
- DeepResearch runtime interventions are persisted through the MissionForge
  interaction plane and projected into safe-point refs.
- DeepResearch has product state refs such as `state/research_state.json`,
  `sources/source_graph.json`, citation artifacts, reviewer observations, judge
  report, and final reports.

Gap:

- There is no formal project-level lifecycle manifest that records the active
  agent, current phase, run index, latest result refs, and latest role context
  packages.
- FrontDesk reopen/resume is not yet a first-class project operation.
- The current resume story is artifact-boundary oriented; it does not yet
  persist and restore a complete compiled ContextPackage for each role.
- Resume should be a thin persistence boundary over ContextEngine-owned raw
  records. DeepResearch should not inspect, trim, summarize, or reinterpret
  ContextPackage internals.

Target artifacts:

```text
project/project_manifest.json
project/lifecycle_state.json
project/run_index.json
context/frontdesk/latest_context_package.json
context/source_mapper/latest_context_package.json
context/researcher/latest_context_package.json
context/reviewer/latest_context_package.json
context/judge/latest_context_package.json
context/frontdesk/working_set.json
context/researcher/working_set.json
```

Target behavior:

- Starting `frontdesk-tui` for an existing `request_id` resumes the project by
  default.
- Resume restores the latest valid FrontDesk ContextPackage and project
  lifecycle state; it does not force the user to restate the topic.
- If package fingerprints match, resume reuses the package.
- If contract, permission, tool schema, compiler version, or visible ref hashes
  changed, resume falls back to ContextEngine recompile from refs, checkpoints,
  and working sets.
- DeepResearch records ContextPackage refs and lifecycle status only; size
  limits, pressure handling, compaction, and retention are MissionForge
  ContextEngine responsibilities.
- Role packages are isolated. FrontDesk, researcher, reviewer, and judge do not
  share a single unfiltered memory blob.
- Scope or acceptance changes after freeze still require explicit revision
  records. Resumed context cannot silently weaken a frozen contract.

## Target Architecture

```text
Existing project or user topic + seed papers/PDFs
  -> project lifecycle load/create
  -> ContextEngine restore/recompile FrontDesk ContextPackage
  -> DeepResearch FrontDesk/ProductIntegration
  -> AcademicLiteratureTaskContract
  -> WorkspacePolicy + PermissionManifest + ExtensionLock
  -> ContextEngine safe-point ContextPackage capture per role
  -> provider_capability_preflight
  -> seed_normalizer PiWorker/tool phase
  -> search_planner PiWorker
  -> source_acquirer PiWorker + academic/browser/PDF extensions
  -> source_graph_projector (mechanical)
  -> researcher PiWorker
  -> citation_projector (mechanical)
  -> citation_auditor hard checks
  -> reviewer PiWorker
  -> judge PiWorker
  -> accepted | repair | source_expansion | revision_required | rejected
  -> project lifecycle update + latest role ContextPackages
  -> final package
```

The controller may route based on structured decisions:

- `continue_search`
- `ready_for_synthesis`
- `ready_for_citation_projection`
- `repair_citations`
- `ready_for_review`
- `ready_for_judge`
- `accepted`
- `blocked`

The controller must not infer academic concepts, rank papers semantically, or
judge whether a source supports a claim. Those remain PiWorker responsibilities.

## Proposed Flow Upgrade

Current flow:

```text
source_mapper -> researcher -> reviewer -> judge
```

Target flow:

```text
seed_normalizer
  -> provider_capability_preflight
  -> search_planner
  -> source_acquirer
  -> source_graph_projector
  -> researcher
  -> citation_projector
  -> citation_auditor
  -> reviewer
  -> judge
```

Pragmatic intermediate flow:

```text
source_mapper
  -> provider_capability_preflight
  -> source_graph_projector
  -> researcher
  -> citation_projector
  -> reviewer
  -> judge
```

The intermediate flow is enough for the first production milestone if
`source_mapper` writes the new search/source graph artifacts.

## Extensions

### Upgrade `pi-academic-sources`

Current support:

- default no-key provider registry:
  - Semantic Scholar
  - arXiv
  - Crossref
  - DBLP
  - PubMed/PMC
- citation-neighborhood provider support:
  - Semantic Scholar
  - OpenCitations for DOI locators
  - OpenAlex when configured
- optional OpenAlex enhancement adapter enabled only when configured
- `academic_provider_capabilities` preflight tool
- query batch execution through `academic_search.queries`
- DOI/arXiv/S2/OpenAlex normalization helpers
- fetch status and provider diagnostics
- optional provider credentials

Remaining extension work:

- paginated provider search beyond current per-provider limits
- richer rate-limit/backoff reporting
- full provider-hit JSONL writer helpers if the extension later receives
  workspace-write authority; today DeepResearch source mapper writes the JSONL
  artifact from tool outputs

Keep:

- provider adapters only
- no semantic research planning
- no product acceptance logic
- no hard dependency on OpenAlex, Google Scholar, paid APIs, or browser sessions

### Add `pi-pdf-sources`

Tools:

- `pdf_provider_capabilities`
- `grobid_parse_pdf`

Outputs:

- raw PDF manifest
- raw GROBID TEI ref under `sources/seed_pdfs/`
- parse diagnostics ref under `sources/seed_pdfs/`
- TEI-derived metadata, sections, references, and provenance refs

Rules:

- Do not implement a custom PDF parser in DeepResearch or MissionForge core.
- Delegate scholarly PDF parsing to GROBID when configured.
- Missing GROBID is a recorded seed gap, not a task failure.
- Raw TEI is the authoritative parsed artifact; Markdown/text summaries are
  derived views only.
- Extension tools accept workspace refs, not absolute paths, and reject path
  traversal.

### Add Optional `pi-browser-scholar`

Tools:

- `browser_search`
- `browser_fetch_result`
- `browser_provider_status`
- optional `manual_intervention_request`

Rules:

- explicit permission grant
- explicit network/browser capability
- user-owned session support
- no stealth bypass claims
- provider failure/captcha/manual-intervention recorded as evidence

Google Scholar support should be declared as:

> Supported when the user enables and configures a compliant browser/provider
> extension. Not guaranteed as a default official API source.

This extension is outside the default product acceptance bar.

## Data Contracts

### `AcademicResearchRequest` Additions

```python
seed_papers: list[SeedPaper]
seed_pdf_refs: list[str]
sample_report_ref: str | None
target_source_count: int | None
provider_policy: Literal["default_no_key", "openalex_enhanced"]
requested_provider_families: list[str]
optional_provider_families: list[str]
citation_style: Literal["cite_anchor_v1"]
report_template_id: str
```

### `SeedPaper`

```json
{
  "kind": "title | doi | arxiv | url",
  "value": "...",
  "note": "... optional user note ..."
}
```

`seed_papers` and `seed_pdf_refs` default to empty lists.

### `FrontDeskAssistantTurn` Choice Extension

```json
{
  "schema_version": "missionforge_deepresearch.frontdesk_assistant_turn.v1",
  "message": "...",
  "questions": [
    {
      "question": "...",
      "why": "...",
      "answer_hint": "...",
      "choices": [
        {
          "label": "推荐方向",
          "description": "选择后的范围和取舍。",
          "recommended": true
        },
        {
          "label": "用户自定义",
          "description": "用户输入自己的方向、约束或混合方案。",
          "freeform": true
        }
      ]
    }
  ]
}
```

The TUI may render `choices` as a keyboard-selectable menu. Scripted clients may
ignore `choices` and answer in free text.

### `CanonicalSource`

```json
{
  "source_id": "S0001",
  "canonical_key": "doi:10....",
  "title": "...",
  "authors": ["..."],
  "year": 2025,
  "venue": "...",
  "identifiers": {
    "doi": "...",
    "arxiv": "...",
    "semantic_scholar": "...",
    "openalex": "..."
  },
  "locators": [
    {
      "kind": "doi | arxiv | openalex | semantic_scholar | url | pdf",
      "url": "...",
      "access_status": "accessible | inaccessible | unchecked"
    }
  ],
  "provider_provenance": ["semantic_scholar", "crossref"],
  "abstract_ref": "sources/abstracts/S0001.txt",
  "fulltext_ref": "sources/fulltext/S0001.txt",
  "evidence_strength": "metadata | abstract | full_text | pdf_text",
  "inclusion_status": "included | candidate | excluded",
  "inclusion_reason": "..."
}
```

### `CitationRegistry`

```json
{
  "schema_version": "missionforge_deepresearch.citation_registry.v1",
  "entries": [
    {
      "citation_number": 1,
      "anchor": "ref-1",
      "source_id": "S0001",
      "reference_markdown": "<a id=\"ref-1\"></a>[1] ...",
      "primary_url": "https://...",
      "access_status": "accessible"
    }
  ]
}
```

### DeepResearch Project Lifecycle State

DeepResearch should define product-level lifecycle records that point at
MissionForge-managed context packages instead of embedding prompt bodies:

```json
{
  "schema_version": "missionforge_deepresearch.lifecycle_state.v1",
  "request_id": "research-001",
  "phase": "requirements | running | paused | reviewing | accepted | revision_required | rejected | blocked",
  "active_agent": "frontdesk | source_mapper | researcher | reviewer | judge",
  "latest_run_ref": "runs/research-001/packages/deepresearch_kernel_v2_result.json",
  "latest_frontdesk_context_package_ref": "context/frontdesk/latest_context_package.json",
  "latest_researcher_context_package_ref": "context/researcher/latest_context_package.json",
  "latest_reviewer_context_package_ref": "context/reviewer/latest_context_package.json",
  "latest_judge_context_package_ref": "context/judge/latest_context_package.json",
  "current_contract_ref": "contracts/task_contract.json",
  "current_revision_ref": "",
  "research_state_ref": "state/research_state.json",
  "final_report_ref": "reports/final_report.citation_projected.md"
}
```

The `latest_*_context_package_ref` values identify complete ContextPackages
owned and validated by MissionForge core. DeepResearch may reference them and
display resume status, but it must not parse provider prompt bodies as product
truth. ContextPackage records are opaque ContextEngine data from the
DeepResearch integration's point of view.

## Permission Model

New capabilities should be explicit in the product permission manifest:

- `ExtensionCapability.WEB` for public API/fetch providers.
- `ExtensionCapability.BROWSER` for Playwright/browser providers.
- workspace write grants for:
  - `inputs`
  - `sources`
  - `citations`
  - `reports`
  - `analysis`
  - `claims`
  - `state`
  - `metrics`
- no secret refs in runtime state.
- default no-key mode requires no provider secret.
- OpenAlex keys and other optional provider credentials/session cookies must be
  supplied through environment or secret mounts and excluded from persisted
  artifacts.

## Milestones

### M0: Plan And Boundary Lock

Status: `complete`

Deliverables:

- This planning document.
- Existing roadmap links to this plan.
- Tests continue enforcing DeepResearch root-package imports only.

Exit criteria:

- No product-specific academic logic added to `src/missionforge`.

### M1: Contract And Artifact Schema Upgrade

Status: `mostly_complete`

Deliverables:

- Extend `AcademicResearchRequest`.
- Add provider policy and `sources/provider_capabilities.json` fixture schema.
- Add schemas/fixtures for seed papers, source graph, canonical sources,
  citation registry, and report template.
- Add tests for serialization, validation, refs-only result packages, and
  import boundary.

Exit criteria:

- Fixture run can accept seed papers and produce source graph, citation registry,
  projected Markdown, and validation artifacts.
- Remaining M1 work: formal provider capabilities artifact fixture and report
  template fixture beyond the current output contract fields.

### M2: Source Graph And Mechanical Deduplication

Status: `partial`

Deliverables:

- Upgrade `pi-academic-sources` provider outputs where needed.
- Add source graph projector.
- Add exact identifier dedupe:
  - DOI
  - arXiv
  - Semantic Scholar id
  - OpenAlex id when present
  - normalized title fallback
- Add ranking artifact with mechanical features and PiWorker-authored relevance
  rationale.

Exit criteria:

- Fixture and mocked-provider tests show duplicate provider hits collapsing into
  canonical sources.
- Remaining M2 work: ranked sources, inclusion decisions, and
  PiWorker-authored relevance rationale.

### M3: Search Planning And Multi-Wave Acquisition

Status: `complete`

Deliverables:

- Add `sources/search_plan.json`.
- Add `academic_search.queries` batch execution.
- Add `sources/provider_hits.jsonl`.
- Add `sources/coverage_report.json`.
- Add default no-key provider orchestration through source-mapper brief,
  provider capabilities, and extension provider policy.
- Keep optional OpenAlex-enhanced path configured-only and non-blocking.
- Keep `source_mapper.continue` route for bounded source-acquisition loops.
- Add literature-scale intensity budgets: standard 50, intensive 100, with
  `target_source_count` override.

Exit criteria:

- Fixture and mocked provider tests cover search plan, provider-hit JSONL,
  coverage report, no-key providers, and query-batch execution.
- Missing OpenAlex configuration is recorded but does not fail the run.
- Configured OpenAlex enhancement contributes extra identifiers/locators without
  changing the product contract shape.

Implemented notes:

- The source mapper is still the PiWorker role that authors search strategy;
  DeepResearch does not add a deterministic Python research planner.
- `coverage_report.json` is a coverage/evidence diagnostic. Its mechanical
  counts do not decide semantic sufficiency.
- Ranking artifacts and PiWorker-authored inclusion decisions remain M2/M6
  follow-up work rather than hidden Python semantics.

### M3A: Persistent Project Lifecycle And ContextPackage Resume

Status: `complete`

Deliverables:

- Add DeepResearch project manifest, lifecycle state, and run index artifacts.
- Wire FrontDesk TUI startup to load an existing project and resume by default.
- Use MissionForge ContextEngine to persist role-specific latest
  ContextPackages at safe points.
- Record latest FrontDesk, source mapper/researcher, reviewer, and judge
  ContextPackage refs in lifecycle state.
- Add fallback behavior when a package is stale: recompile from refs, working
  sets, and checkpoints instead of replaying an invalid package.
- Do not implement product-level ContextPackage trimming, summarization,
  retention, or token-budget logic in DeepResearch.
- Keep raw dialogue as provenance and context source, not as task authority.

Exit criteria:

- Closing and reopening FrontDesk for the same `request_id` restores the
  previous project conversation and current research state without requiring a
  new initial topic.
- When contract, permission manifest, tool schema, compiler version, and visible
  ref hashes are unchanged, resume reuses the latest ContextPackage.
- When any hard fingerprint changes, resume refuses direct reuse and records a
  recompile/invalidation diagnostic.
- Role isolation tests prove FrontDesk cannot restore researcher-only context
  unless the permission manifest allows it.
- Revision tests prove resumed conversation cannot modify frozen scope without
  an explicit revision record.

Implemented notes:

- MissionForge core exposes product-neutral ContextPackage restore evaluation:
  reusable, stale, or invalid.
- FrontDesk startup evaluates the latest FrontDesk ContextPackage and writes
  project resume diagnostics without starting a model call.
- DeepResearch lifecycle prefers post-turn ContextPackages for project resume
  while preserving provider pre-turn package refs in Kernel StepRecords.
- Role package pointers keep FrontDesk, source mapper, researcher, reviewer,
  and judge context packages isolated by role.
- Stale visible refs, role/step mismatch, missing packages, and changed hard
  fingerprints are recorded as explicit diagnostics and require recompile or
  denial before direct reuse.

### M3B: Web Console MVP

Status: `pending`

Deliverables:

- Add a minimal project-oriented web frontend for DeepResearch.
- Project open/resume screen backed by project manifest and lifecycle state.
- FrontDesk chat surface backed by the same FrontDesk/runtime interaction APIs
  as CLI/TUI.
- Current project board showing phase, active agent, latest run, resume status,
  source count, citation status, reviewer/judge status, and final report refs.
- Runtime controls for pause, resume, checkpoint, revise, cancel, and status.
- Markdown report preview and source/citation table views from existing refs.

Exit criteria:

- A non-CLI user can create or open a DeepResearch project, converse with
  FrontDesk, start a run, observe progress, pause/resume, and inspect the final
  Markdown from the browser.
- The frontend does not write product truth directly. It submits explicit
  FrontDesk messages, interaction events, approvals, and revision requests.
- Closing and reopening the browser resumes the same project through
  ContextPackage/lifecycle state rather than requiring a new topic.
- Web console tests or fixtures prove the UI can render lifecycle state and
  artifact refs without depending on live provider calls.

### M4: Citation Projection

Status: `mostly_complete`

Deliverables:

- Citation registry.
- Markdown citation projector.
- Reference anchor generator.
- Mechanical citation validation.

Exit criteria:

- Every `[cite: N]` in final Markdown maps to exactly one reference entry and
  source id.
- Orphan/missing/duplicate citations fail hard checks.
- Remaining M4 work: richer URL accessibility checks and repair routing before
  reviewer/judge rather than product-status downgrade after accepted flow.

### M5: PDF Seed Ingestion

Status: `partial`

Deliverables:

- `pi-pdf-sources` extension with GROBID provider capability and parse tool.
- PDF reference contract through `seed_pdf_refs`.
- `inputs/seed_papers.json` and `inputs/seed_pdf_index.json`.
- Conditional `seed_normalizer` step.
- `sources/seed_source_packet.json`, `reports/seed_gaps.md`, and
  `state/seed_control.json`.
- PDF parse diagnostics and TEI projection refs through extension outputs.

Exit criteria:

- User-provided seed papers/PDFs become seed source packet entries or explicit
  parse/missing-provider diagnostics.
- Missing PDFs are recorded in `reports/seed_gaps.md` and must not become source
  evidence.

Implemented notes:

- M5A is complete for artifact lifecycle, CLI seed refs, fixture flow, and
  GROBID-first extension boundary.
- M5B is complete for deterministic TEI metadata/sections/references/provenance
  projection refs and seed packet `parse_refs`.
- M5C is complete for carrying parsed PDF evidence refs into source packets,
  canonical sources, evidence indexes, and claim indexes.
- DeepResearch does not hand-parse PDF binaries or dump extracted full text
  into context.
- Remaining M5 work: Web upload UI, OCR fallback, and richer page/span
  provenance when GROBID coordinates are available.

### M6: Citation Support Judge

Status: `partial`

Deliverables:

- Extended claim index.
- Judge rubric for claim-source support.
- Repair loop for unsupported/mismatched citations.

Exit criteria:

- Fixture tests simulate unsupported claims and require repair/rejection.
- Judge cannot accept reports with mechanically invalid citations.
- Remaining M6 work: semantic claim-source support judgment and repair loop
  against fetched/full-text evidence, including parsed PDF spans.

### M7: Optional Scholar/Commercial Browser Fallback

Status: `pending`

Deliverables:

- `pi-browser-scholar` extension prototype.
- Playwright preflight.
- Provider status artifact.
- Manual-intervention/captcha blocked state.
- Documentation for user-owned session and compliance constraints.

Exit criteria:

- Browser provider can be enabled explicitly.
- Provider failure never blocks the whole run when other sources suffice, but
  the gap is recorded.
- Default no-key acceptance tests do not depend on this milestone.

### M8: Full Web UI And Docker Compose

Status: `pending`

Deliverables:

- Production-ready web frontend beyond the M3B MVP.
- Docker compose example.
- PDF upload.
- Source table.
- Citation audit table.
- Markdown preview/download.

Exit criteria:

- A user can run the end-to-end example on Linux/WSL/server with a workspace
  volume and inspect progress without reading raw workspace files.

## Acceptance Tests

### Contract Tests

- Seed papers accept title, DOI, arXiv id, and URL.
- Seed papers are optional; empty seed lists are valid.
- Invalid seed ids are rejected.
- PDF refs must be valid refs.
- Report template and citation style are frozen into the task contract.

### Provider Tests

- Mock no-key arXiv/Semantic Scholar/Crossref/DBLP/OpenCitations/PubMed hits
  normalize to a common source shape.
- Missing OpenAlex key records optional-enhancement-disabled status and does not
  fail the run.
- Mock OpenAlex-enhanced hits add identifiers, locators, and provenance without
  changing citation or contract invariants.
- Duplicate DOI/arXiv/provider ids collapse into one canonical source.
- Provider failures are recorded as source gaps, not hidden.

### Citation Tests

- Missing reference entry fails.
- Unknown source id fails.
- Duplicate citation number fails.
- Reference URL missing or inaccessible fails unless explicitly marked as
  inaccessible and uncited for factual claims.
- `[cite: N](#ref-N)` anchors match reference anchors.

### Flow Tests

- Fixture flow produces source graph, citation registry, projected Markdown,
  claim index validation, reviewer observation, and judge report.
- Reviewer can route `continue_search`.
- Judge cannot self-accept execution worker output.
- Repair does not weaken frozen contract.

### Package Boundary Tests

- DeepResearch source imports MissionForge only through `import missionforge`.
- Core does not import DeepResearch.
- Product-specific academic/browser/PDF code remains outside `src/missionforge`.

## Non-Goals

- Do not guarantee Google Scholar access without user-enabled provider support.
- Do not require any provider API key for default academic literature-review
  operation.
- Do not bypass anti-abuse systems.
- Do not make Python a semantic literature-review expert.
- Do not add academic product branches to MissionForge core.
- Do not require running untrusted code or benchmarks.
- Do not treat a fixed source count as more authoritative than explicit
  coverage and source-gap artifacts.

## Resolved Decisions

1. Default academic source acquisition is no-key.
2. OpenAlex is an optional enhancement when a key/configuration is provided.
3. Google Scholar, SerpAPI, Playwright/browser automation, CORE, and other
   key/session/paid providers are optional extension capabilities, not default
   acceptance requirements.
4. Citation numbering is assigned after draft by the product citation projector.
   Unknown source ids fail mechanical validation; accepted flows are downgraded
   to product `failed` until a repair loop is added.

## Open Decisions

1. Whether PDF upload belongs in CLI first or web UI first. Recommended: CLI
   ref support first, UI upload later.
2. Whether source ranking should include embeddings. Recommended: start with
   mechanical features plus PiWorker rationale; add embeddings only after
   source graph schema stabilizes.

## First Implementation Slice

Status: `complete`

The first development goal was M1-M2 plus the M4 citation projector interface,
not browser automation.

Concrete first slice:

1. Extend request contract for seed papers and citation style.
2. Add provider policy and provider capability preflight artifact.
3. Add source graph/canonical source/citation registry dataclasses.
4. Add fixture outputs and tests for no-key default and OpenAlex-enhanced mode.
5. Add source graph projector with exact identifier dedupe.
6. Add citation projector that rewrites fixture report citations into
   `[cite: N](#ref-N)` and writes references.

This created the hard product backbone. OpenAlex enhancement, browser/Google
Scholar fallback, CORE, and PDF parsing can then attach as extensions without
forcing another architecture rewrite.
