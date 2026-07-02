# DeepResearch Academic Literature Upgrade Plan

Status: `pdf_ocr_page_span_provenance`; next priority is citation evidence UX hardening

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
  - `reviews/claim_support_review.json`
  - `state/claim_support_review_validation.json`
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
- `pi-pdf-sources` provides `pdf_provider_capabilities`, `grobid_parse_pdf`,
  and `ocr_parse_pdf`. It delegates to configured GROBID/OCR providers and
  writes raw TEI when available plus diagnostics, metadata, sections,
  references, page spans, and provenance under `sources/seed_pdfs/`; it rejects
  absolute paths and unsafe refs.
- Web PDF upload, approved-project seed revision flow, and page-span refs are
  active. Source-mapper/researcher semantic use remains PiWorker-authored and
  evidence-ref driven.

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
  - page/span provenance refs
  - optional OCR fallback refs

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
- Claim validation also checks claim-level `supporting_evidence_refs` against
  known source evidence refs, including parsed PDF refs and fetched
  abstract/full-text refs carried in source records.
- Citation validation checks source-id citation projection and reference-anchor
  consistency.
- Accepted flows are downgraded to product `failed` when mechanical citation or
  claim-source validation fails.
- Reviewer PiWorker must write `reviews/claim_support_review.json`, a semantic
  claim-support audit over `claims/claim_index.json`, `sources/source_packet.json`,
  `reports/evidence_index.md`, parsed PDF refs, and fetched/full-text refs.
- Runtime writes `state/claim_support_review_validation.json` for schema/ref
  validation only. It does not decide whether evidence semantically supports a
  claim.
- Reviewer `revise_report` and Judge `repair` routes enter a dedicated
  repair PiWorker boundary. Reviewer repair reads reviewer claim-support
  feedback refs; Judge repair additionally reads `judge/judge_report.json`.
  The initial researcher step never reads stale review/judge artifacts.
- Accepted flows are downgraded to product `failed` if the reviewer-authored
  claim-support review is malformed, references unknown claims/sources/evidence
  refs, or still declares `repair_required`, `source_expansion_required`,
  `revision_required`, or `rejected`.
- URL accessibility and final semantic support remain Judge/PiWorker work backed
  by evidence refs.

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
- Add Reviewer PiWorker claim-support artifact:
  - `schema_version: missionforge_deepresearch.kernel_v2.claim_support_review.v1`
  - `claim_index_ref`, `source_packet_ref`, `evidence_index_ref`
  - `claim_reviews[]` with `claim_id`, `support_status`,
    `supporting_source_ids`, `supporting_evidence_refs`, `rationale`, and
    `required_repair`
  - `overall_status` and `repair_directive`
- Keep repair workers bounded to same-contract repairs; contract-changing fixes
  must become explicit revision-required work rather than silent contract
  weakening.

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

Status: `partial`

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

Implemented notes:

- M3B-A is complete for a read-only project web console.
- `missionforge-deepresearch academic web-console` serves a package-local
  standard-library HTTP view over existing project refs.
- The console reads project manifest, lifecycle state, resume diagnostics, run
  status, source packet, coverage report, citation registry, claim-support
  review, acceptance gate, judge report, usage summary, artifact refs, and the
  final Markdown preview.
- The web layer does not write product truth, mutate lifecycle state, or
  replace FrontDesk/runtime interaction APIs.
- M3B-B1 is complete for browser FrontDesk message submission through the same
  FrontDesk PiWorker turn boundary used by CLI/TUI.
- M3B-B2 foundation is complete for approving FrontDesk requirements from the
  browser without starting a long research run.
- M3B-B3 is complete for starting Kernel v2 from the browser as a server-owned
  background task after FrontDesk approval. The browser cannot choose provider
  config or adapter mode. Existing web tasks or already-written Kernel result
  refs are surfaced as current task state rather than silently rerunning and
  overwriting the same project run.
- M3B-C first slice is complete for browser runtime controls backed by the same
  MissionForge interaction plane as TUI. Web pause, resume, checkpoint,
  stop-after-current-turn, cancel, message, and revise actions append
  `interaction/user_events.jsonl` events through `FileControlPort`; the browser
  does not mutate lifecycle state or the frozen task contract directly.
- M3B-C2 is complete for a conservative workspace-local cross-process run lock.
  Browser Start Research acquires `web/locks/kernel_v2.lock` before spawning a
  background Kernel task, exposes a sanitized `locked` task state when another
  process holds the lock, and releases the lock after completion or failure.
  `POST /api/research/start` validates existing FrontDesk approval before it
  records or returns existing task state; read-only task polling remains
  `/api/task`.
- M3B-D first slice is complete for explicit retry/revise/recover lifecycle
  requests. The web surface writes refs-only lifecycle action records and
  user-authored reason text refs, and explicit lock recovery records an action
  before converting the web task to `interrupted`. It does not start a new
  Kernel attempt or mutate the frozen contract.
- M3B-E first slice is complete for consuming explicit pending retry requests
  and starting a new Kernel retry attempt from the browser. The attempt path
  writes `project/attempt_index.json`, per-attempt manifests under
  `project/attempts/{attempt_id}/attempt_manifest.json`, and before-run
  snapshots for stable result refs that may be overwritten by the current
  Kernel v2 output shape. Retry consumption is recorded back to
  `project/lifecycle/latest_retry_request.json`; revision requests remain
  pending and are not consumed by this slice.
- M3B-F first slice is complete for a refs-first progress timeline. The web
  console projects sanitized rows from `web/progress_timeline.jsonl`, flow
  ledgers, step records, runtime interaction events,
  `project/lifecycle_actions.jsonl`, `project/attempt_index.json`, and
  `web/tasks/current_task.json`. Live FrontDesk/Kernel web runs append
  sanitized progress markers without persisting raw user text, provider payloads,
  prompt bodies, or adapter progress messages.
- M3B-G first slice is complete for consuming explicit pending revision
  requests through a contract-revision boundary. The web console exposes
  `POST /api/research/revision/start`, writes revision records under
  `project/revisions/{revision_id}/`, updates `project/revision_index.json`,
  consumes `project/lifecycle/latest_revise_request.json`, stages revision
  artifacts through `inputs/contract_revision_index.json`, and starts a
  server-owned Kernel revision attempt using the revised request.
- M3B-H first slice is complete for attempt-scoped output projection. Completed
  retry/revision attempts copy Kernel v2 stable outputs into
  `project/attempts/{attempt_id}/outputs/`, write an output manifest, and update
  `project/current_output_pointer.json`. The web snapshot and artifact browser
  prefer current attempt-scoped refs while preserving stable refs as fallback.
- M3B-I is complete for attempt-grouped progress timeline projection. The web
  snapshot exposes `progress_timeline_groups`, groups sanitized timeline rows by
  project/attempt refs, highlights the current output pointer, and keeps the
  flat timeline as an operator fallback view.
- Reviewer hardening is complete for the M3B-E/F/G/H/I slice. Failed contract
  revision attempts keep the frozen revised request as current task authority;
  retry attempts preserve lifecycle `current_revision_ref`; current-output
  snapshots no longer mix attempt-scoped refs with stable refs after a current
  pointer exists; FrontDesk dialogue is projected by ref/turn metadata instead
  of raw dialogue text; and attempt runtime-progress rows carry attempt refs for
  grouping.
- M3B-J is complete for Web seed-paper/PDF input. The dashboard
  includes a Seed Inputs panel, `POST /api/seeds/papers`, and
  `POST /api/seeds/pdfs`. Seed inputs are staged as explicit project artifacts
  and merged into `frontdesk/research_request.json` before FrontDesk approval.
  Once a project is approved, seed additions do not mutate the approved
  FrontDesk request; they stage `project/seed_inputs.json`, record a refs-first
  pending revision request, and are frozen into
  `project/revisions/{revision_id}/revised_research_request.json` only when
  `POST /api/research/revision/start` consumes that revision request.
- M3B-K is complete for Web artifact access policy. The artifact browser still
  exposes refs and byte-size metadata, but sensitive raw user input, uploaded
  seed files, lifecycle action text, ContextPackage refs, and parsed seed-PDF
  outputs are `metadata_only` by default and do not return raw content through
  the web artifact preview/API.

### M3B-A: Read-Only Project Web Console

Status: `complete`

Deliverables:

- `missionforge_deepresearch.web_console` snapshot, renderer, artifact preview,
  and standard-library HTTP adapter.
- CLI command `academic web-console`.
- Dashboard cards for lifecycle, active agent, run status, resume diagnostics,
  source count, citation validation, claim-support status, acceptance gate,
  Judge decision, and token usage.
- Artifact table, source table, citation table, and Markdown report preview.
- Tests proving snapshot rendering, HTML escaping, artifact path safety, and
  pure request routing without live provider or socket dependency.

Exit criteria:

- Existing project refs can be opened from a browser without starting a new
  model/provider call.
- The dashboard is read-only and does not write product authority.
- Artifact reads are constrained to the selected project workspace.

### M3B-B1: Web FrontDesk Chat And Project Resume

Status: `complete`

Deliverables:

- FrontDesk chat panel in the web console.
- `POST /api/frontdesk/message` endpoint.
- Server-owned `WebFrontDeskConfig` with adapter factory, audience, language,
  intensity, and live-extension settings.
- Browser messages are submitted to `run_deepresearch_frontdesk_turn`; the
  browser cannot choose provider config or write project refs directly.
- Response returns the FrontDesk result plus the latest project snapshot.
- Tests for unconfigured FrontDesk rejection, fixture FrontDesk chat, resumed
  dialogue state, and CLI-owned adapter configuration.

Exit criteria:

- A browser user can open an existing or new project and continue FrontDesk
  requirements discovery through the same persisted refs and ContextPackage
  lifecycle as CLI/TUI.
- Web FrontDesk message submission updates project state only through the
  FrontDesk PiWorker/runtime path.
- Approval/start-run and runtime controls remain explicit follow-up work, not
  hidden browser-side mutations.

### M3B-Web Modularization

Status: `maintenance_refactor_slice_complete`

Deliverables:

- `web_common.py` for response/config shared types.
- `web_actions.py` for FrontDesk message and approval actions.
- `web_artifacts.py` for artifact preview, JSON pretty-printing, and sensitive
  ref access-policy projection.
- `kernel_refs.py` for stable Kernel v2 artifact refs so modules that only
  need ref names do not import the Kernel execution module.
- `web_console.py` remains the compatibility surface and owns dashboard
  snapshot/render/server wiring for now. Existing public imports such as
  `missionforge_deepresearch.web_console.read_project_artifact` remain
  compatible.

Exit criteria:

- Mutating web actions are isolated from snapshot/render code.
- Existing public imports keep working.
- Future start-run/runtime-control work has a dedicated action module instead
  of growing the dashboard renderer.

Remaining modularization:

- Split snapshot construction into `web_snapshot.py`.
- Split HTML/CSS/JS rendering into `web_render.py`.
- Split stdlib HTTP routing into `web_server.py` once start-run/background
  task routing is added.

### M3B-B2 Foundation: Web Requirements Approval

Status: `complete`

Deliverables:

- `POST /api/frontdesk/approve` endpoint.
- Browser approval calls `approve_frontdesk_requirements`.
- Response returns an approved research request plus the latest project
  snapshot.
- Approval does not start `run_deepresearch_kernel_v2`; long-running background
  execution remains a separate milestone.
- Tests for not-ready approval rejection and approval-ready success without
  creating a Kernel final report.

Exit criteria:

- Web approval uses the existing FrontDesk approval boundary.
- The browser cannot rewrite requirements or mutate task authority directly.
- Approval and start-run are separate, making the next long-running execution
  design explicit.

### M3B-B3: Web Start Run Background Execution

Status: `complete`

Deliverables:

- `WebKernelConfig` as server-owned Kernel execution configuration.
- `POST /api/research/start` endpoint.
- `GET /api/task` endpoint.
- `web/tasks/current_task.json` as a refs-first web task state artifact.
- Browser Start Research action that verifies an existing FrontDesk approval,
  then starts `run_deepresearch_kernel_v2` in a process-local background task.
- Snapshot/dashboard task status card and artifact entry for web task state.
- CLI wiring for web-console Kernel adapter mode without exposing provider
  selection to browser requests.
- Duplicate-start guard: live, completed, failed, or pre-existing Kernel result
  refs are returned as current task state instead of rerunning the same project.

Exit criteria:

- A browser user can approve requirements and start a long-running research run
  without blocking the HTTP request.
- The browser submits only the start command; adapter/provider choices remain
  process-owned CLI/server configuration.
- The start endpoint does not bypass FrontDesk approval for new runs.
- Existing project runs are not silently overwritten by clicking Start Research.
  Future retry/revise flows must use explicit runtime controls and revision
  records.
- Current duplicate-start protection combines process-local thread detection,
  existing-result-ref detection, and the workspace-local run lock delivered in
  M3B-C2.

### M3B-C: Web Runtime Controls Through Interaction Plane

Status: `m3b_retry_attempt_generation_first_slice`

Deliverables:

- `web_controls.py` maps browser runtime actions onto
  `mf.FileControlPort(mf.FileInteractionPort(run_root))`.
- `POST /api/runtime/control` endpoint for:
  - `pause`
  - `resume`
  - `checkpoint`
  - `stop_after_current_turn`
  - `cancel`
  - `message`
  - `revise`
- Runtime control panel in the web console.
- Project snapshot includes sanitized runtime event summaries from
  `interaction/user_events.jsonl`; it does not expose raw intervention text.
- Tests prove controls append product-neutral interaction events with the
  expected run id and that revision/message actions require explicit text.
- Workspace-local cross-process run lock:
  - `web/locks/kernel_v2.lock` is acquired through atomic directory creation.
  - lock metadata is written as `web/locks/kernel_v2.lock/lock.json`.
  - `/api/task` and `/api/research/start` surface only sanitized task fields,
    including `status: locked` and `lock_ref`, not process owner metadata.
  - `/api/research/start` requires existing FrontDesk approval before recording
    existing task refs or acquiring a lock.
  - background tasks release the lock after completion or failure.
- Explicit retry/revise/recover lifecycle actions:
  - `POST /api/lifecycle/action` for `retry`, `revise`, and `recover_lock`.
  - latest request refs:
    - `project/lifecycle/latest_retry_request.json`
    - `project/lifecycle/latest_revise_request.json`
    - `project/lifecycle/latest_lock_recovery_request.json`
  - append-only action ledger:
    `project/lifecycle_actions.jsonl`
  - user-entered reasons are written to
    `project/lifecycle/action_text/*.txt` and only referenced by action JSON.
  - retry requires an approved project plus a failed or interrupted web task;
    locked tasks must first use explicit lock recovery, which converts the web
    task to `interrupted`.
  - revision requires an approved/completed/revision-required project phase and
    records a pending revision request without mutating the frozen contract.
  - lock recovery requires an approved project plus a locked/stale-lock task
    state; it releases `web/locks/kernel_v2.lock`, marks the web task
    `interrupted`, and leaves retry as a separate explicit request.

Exit criteria:

- Web runtime controls use the same interaction ledger and safe-point semantics
  as TUI.
- Pause/cancel/revision requests do not interrupt an in-flight PiWorker call;
  Kernel consumes them at safe points.
- Revision requests are user interventions, not contract mutations. The frozen
  task remains unchanged until a later explicit revision flow.

Remaining runtime-control hardening:

- Timeline UX hardening, including per-attempt grouping and richer live polling.
- Richer stale-lock diagnostics, including age/owner display and optional
  process-local liveness hints, without automatic lock stealing.

### M3B-E: Retry Attempt Generation

Status: `retry_first_slice_complete`

Deliverables:

- `research_attempts.py` product-layer attempt boundary.
- `POST /api/research/attempt/start` endpoint. It is separate from
  `POST /api/research/start`; the original start endpoint remains first-run
  only and still refuses to silently rerun completed projects.
- Retry attempt manifests under
  `project/attempts/{attempt_id}/attempt_manifest.json` with request id,
  generation, source retry action ref/id, reason ref, base contract ref/hash,
  parent run refs, task/lock refs, before snapshot ref, status, and result refs.
- Project attempt index at `project/attempt_index.json`.
- Pending retry consumption updates
  `project/lifecycle/latest_retry_request.json` with `status: consumed`,
  `consumed_at`, and `consumed_by_attempt_ref`, and appends the consumed action
  to `project/lifecycle_actions.jsonl`.
- Attempt manifest/index creation and retry consumption run inside the
  background-task start boundary after the workspace-local web run lock is
  acquired, so concurrent retry-start requests cannot publish separate pending
  attempts for the same retry request.
- Before snapshots preserve key stable refs, including lifecycle state, web
  task state, result package, run status, reports, source packet, canonical
  sources, coverage report, acceptance gate, and judge report.
- Dashboard shows attempt count, latest attempt status, latest attempt ref, and
  a dedicated Start Retry Attempt button.
- Tests cover missing retry rejection, retry consumption, before snapshot
  preservation, idempotent repeat click on a consumed retry, and pending
  revision rejection.

Exit criteria:

- A failed or interrupted web task with an explicit pending retry request can
  start a new Kernel retry attempt without overloading Start Research.
- The browser cannot choose adapter/provider settings, mutate the frozen
  contract, or convert revision requests into retry attempts.
- Retry reason text remains behind `reason_ref`; attempt/index/task snapshots
  do not embed raw user text.
- Repeating the same attempt-start command after retry consumption returns the
  existing consumed attempt rather than generating a second attempt.

Remaining:

- Move deeper Kernel internals to native output ref plans only if the projection
  boundary proves insufficient. The first slice keeps Kernel v2 stable refs and
  adds immutable attempt-scoped output copies plus a current pointer.

### M3B-F: Progress Timeline

Status: `first_slice_complete`

Deliverables:

- `web_timeline.py` product-layer timeline projection.
- `web/progress_timeline.jsonl` for sanitized live progress markers emitted
  during web FrontDesk, Kernel start, and retry attempt runs.
- Flow ledger and step record projection from persisted Kernel refs.
- Runtime control event projection from `interaction/user_events.jsonl`.
- Lifecycle action projection from `project/lifecycle_actions.jsonl`; reason
  text remains behind `reason_ref`.
- Attempt projection from `project/attempt_index.json`, including attempt ref
  and generation.
- Web task projection from `web/tasks/current_task.json`.
- Dashboard Progress Timeline panel and artifact entry.
- Tests cover completed flow-ledger projection, missing ledger/step-record
  degradation, runtime/lifecycle text redaction, and sanitized live progress
  markers.

Exit criteria:

- Timeline is read-only product projection, not task authority.
- Timeline rows carry source kind/ref, visible state, stage, optional attempt
  ref/generation, and refs; they do not embed FrontDesk dialogue, report
  markdown, runtime intervention text, provider payloads, stdout/stderr, or
  secrets.
- Browser UI reads and renders the projection only; it does not write product
  truth through timeline state.
- Missing flow ledger or step records degrade to visible missing/unknown rows
  instead of failing dashboard render.

Remaining:

- Per-attempt grouping using attempt output manifests.
- Live browser polling and compact filters for long timelines.

### M3B-G: Revision Contract Flow

Status: `first_slice_complete`

Deliverables:

- `research_requests.py` resolves the current DeepResearch request as the
  approved FrontDesk request superseded only by usable frozen revision records.
- `research_revisions.py` product-layer contract revision boundary.
- `POST /api/research/revision/start` endpoint. It is separate from retry
  attempts and from first-run Start Research.
- Pending revision consumption updates
  `project/lifecycle/latest_revise_request.json` with `status: consumed`,
  `consumed_at`, `consumed_by_revision_ref`, and `consumed_by_attempt_ref`, and
  appends the consumed action to `project/lifecycle_actions.jsonl`.
- Per-revision artifacts under `project/revisions/{revision_id}/`:
  `revision_directive.md`, `revision_proposal.json`,
  `revised_research_request.json`, and `revision_record.json`.
- Project revision index at `project/revision_index.json`.
- Revised `AcademicResearchRequest.contract_revision_refs` carries only refs to
  frozen revision artifacts. Kernel stages those refs through
  `inputs/contract_revision_index.json`, so PiWorker roles can read the
  directive as task authority without reaching into `project/lifecycle`.
- Revision attempt manifests share `project/attempt_index.json` with retry
  attempts and use `kind: revision_attempt`.
- Dashboard shows revision count, latest revision status/ref, and a dedicated
  Start Revision Attempt button. The Progress Timeline projects revision rows
  from the revision index.
- Tests cover missing pending revision rejection, revision consumption,
  revised-contract freeze, FrontDesk approval preservation, staged revision
  inputs, lifecycle `current_revision_ref`, and secret/redaction boundaries in
  API responses, lifecycle snapshots, and timeline rows.

Exit criteria:

- A pending revision request cannot silently mutate the existing frozen
  contract; it must be consumed by an explicit revision boundary.
- The original FrontDesk approval remains intact. The revised request is a new
  contract authority ref, not a mutation of `frontdesk/research_request.json`.
- Revision directive text is available to Kernel as a staged input artifact but
  is not embedded in web task state, lifecycle action summaries, timeline rows,
  or API response payloads.
- Retry attempts cannot consume pending revision requests.

Remaining:

- Use a dedicated FrontDesk/revision PiWorker authoring node for richer
  semantic revision proposals when live adapters are available. The first slice
  freezes explicit user revision directives as revision artifacts without
  deterministic semantic interpretation.
- Move deeper Kernel internals to native output ref plans only if the projection
  boundary proves insufficient. The first slice preserves revised attempt outputs
  through immutable copies and `project/current_output_pointer.json`.

### M3B-H: Attempt-Scoped Kernel Outputs

Status: `first_slice_complete`

Deliverables:

- `attempt_outputs.py` product-layer output projection boundary.
- Completed retry and revision attempts copy stable Kernel output refs into
  `project/attempts/{attempt_id}/outputs/{source_ref}`.
- Per-attempt output manifest at
  `project/attempts/{attempt_id}/outputs/output_manifest.json`.
- Current output pointer at `project/current_output_pointer.json`.
- Attempt manifests and attempt index records include `output_manifest_ref`.
- Revision records and revision index records include `output_manifest_ref`.
- Web snapshot, report preview, source/citation/judge summaries, artifact list,
  and current-output summary prefer refs from the current output pointer and
  fall back to stable refs for first-run projects or legacy workspaces.
- Once a current output pointer exists, per-artifact dashboard reads do not
  silently fall back to stable Kernel refs for missing copied outputs. Missing
  attempt-scoped refs are surfaced as missing rather than mixed with later
  stable outputs.
- Progress timeline attempt rows include output manifest refs.
- Tests prove a completed retry attempt can serve the dashboard from
  attempt-scoped report refs even when the stable report ref is later changed.

Exit criteria:

- Completed retry/revision attempts leave immutable output refs that remain
  inspectable after later attempts overwrite Kernel stable refs.
- The browser reads current outputs through a refs-first pointer instead of
  inferring semantic truth from stable filenames.
- Failed process-level attempts do not update the current output pointer because
  output projection runs only after `run_deepresearch_kernel_v2` returns.
- The implementation does not require a broad Kernel v2 ref-plan rewrite.

Remaining:

- Consider native Kernel output ref plans only if output-copy projection is not
  enough for future live-run scale or storage constraints.

### M3B-I: Timeline Attempt Grouping

Status: `complete`

Deliverables:

- `web_timeline.build_timeline_attempt_groups()` groups sanitized progress rows
  by project-level events and attempt execution boundaries.
- Attempt groups are joined through refs only: attempt manifest refs,
  output-manifest refs, revision refs, flow result ledger refs, step-record
  refs, task refs, and copied attempt-output refs.
- Retry/revision runtime-progress markers carry the owning attempt ref so
  progress rows without provider/tool refs still group under their attempt.
- `build_project_snapshot()` exposes `progress_timeline_groups` alongside the
  flat `progress_timeline`.
- The dashboard renders grouped attempt timelines, highlights the group that
  owns `project/current_output_pointer.json`, and keeps the flat timeline in a
  collapsible fallback view.
- Runtime controls expose the current output manifest, owning attempt ref, and
  output-ref count without reading artifact bodies.

Exit criteria:

- Operators can distinguish base project events, retry attempts, and revision
  attempts from the browser without opening raw ledgers one by one.
- Grouping does not infer research semantics, acceptance quality, paper
  ranking, or citation correctness.
- Snapshot and HTML views remain sanitized: no raw runtime messages, lifecycle
  reason text, provider payloads, prompt bodies, or secret-like strings are
  projected into timeline groups.
- FrontDesk dialogue projection in the project snapshot is refs-first: it shows
  role, turn index, timestamp, and `frontdesk/dialogue.jsonl` refs, while raw
  dialogue text is only available through explicit artifact reads.

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
- M5B is complete for deterministic TEI metadata/sections/references/
  provenance projection refs and seed packet `parse_refs`.
- M5C is complete for carrying parsed PDF evidence refs into source packets,
  canonical sources, evidence indexes, and claim indexes.
- M5D is complete for Web seed upload. Browser seed-paper input and
  PDF upload write `project/seed_inputs.json` and `inputs/seeds/*.pdf` before
  approval. The approved request carries `seed_papers` and `seed_pdf_refs` into
  Kernel v2, where existing `inputs/seed_papers.json`,
  `inputs/seed_pdf_index.json`, and seed-normalizer flow handle parsing and
  source-packet projection. The project snapshot shows seed counts and refs,
  not raw seed-paper values or PDF bytes. After approval, new seed inputs are
  accepted only through the explicit revision lifecycle; active tasks still
  reject seed additions until a safe revision boundary is available.
- M5E is complete for page-span evidence provenance and optional OCR fallback.
  `pi-pdf-sources` now projects GROBID coordinates into
  `sources/seed_pdfs/{id}/page_spans.json`, carries `page_spans_ref` through
  `inputs/seed_pdf_index.json`, seed source packets, canonical sources,
  evidence indexes, and claim-support refs, and exposes `ocr_parse_pdf` as an
  external-provider fallback gated by `PDF_OCR_BASE_URL`. Missing OCR
  configuration records diagnostics and is not a task failure.
- DeepResearch does not hand-parse PDF binaries or dump extracted full text
  into context.
- Remaining M5 work: mature citation evidence UX over parsed/fetched evidence
  refs.

### M6: Citation Support Judge

Status: `complete_for_current_architecture`

Deliverables:

- Extended claim index.
- Reviewer-authored `reviews/claim_support_review.json` semantic support audit.
- Runtime-owned `state/claim_support_review_validation.json` for schema/ref
  boundaries only.
- Judge rubric for claim-source support that consumes reviewer claim-support
  audit plus parsed/fetched evidence refs.
- Dedicated repair loop for unsupported/mismatched citations and bounded
  same-contract repairs, split between reviewer-feedback repair and
  judge-feedback repair to preserve minimal readable refs.
- Product status downgrade when an accepted flow has malformed claim-support
  review refs or a reviewer-authored non-passing claim-support status.
- Runtime-owned `state/acceptance_gate.json` that aggregates mechanical
  citation, claim-index, claim-support, reviewer decision, and Judge decision
  consistency before exposing product acceptance.
- Explicit `revisions/revision_request.json` when Judge returns
  `revision_required`; the flow and product status remain `revision_required`
  instead of collapsing into generic blocked state.

Exit criteria:

- Fixture tests simulate unsupported claims and require repair/rejection.
- Judge cannot accept reports with mechanically invalid citations.
- Reviewer claim-support reviews cannot reference unknown claim ids, source ids,
  or known evidence refs.
- Initial researcher execution does not read stale reviewer/judge refs; only
  repair workers consume reviewer/judge feedback, and Judge feedback is only
  readable in the Judge repair path.
- Acceptance gate fails reviewer/Judge decision inconsistencies such as
  `ready_for_judge` with non-passing claim support or Judge acceptance with a
  non-passing claim-support audit.
- Judge `revision_required` writes a refs-only pending revision request while
  preserving the frozen contract.
- Remaining post-M6 hardening: richer URL accessibility checks, citation
  evidence UX over parsed page spans, and broader live fetched/full-text
  evidence coverage.

### M6.1: Acceptance Gate And Revision Request Hardening

Status: `complete`

Deliverables:

- `state/acceptance_gate.json`
- `revisions/revision_request.json`
- Product status preservation for `revision_required`
- Run-status fields for acceptance-gate status and failure codes

Exit criteria:

- Accepted flows with reviewer/Judge claim-support inconsistency downgrade to
  product `failed` through the acceptance gate.
- Judge `revision_required` produces a pending revision request and lifecycle
  phase `revision_required`.
- The revision request cites refs only and does not mutate the frozen task
  contract.

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
