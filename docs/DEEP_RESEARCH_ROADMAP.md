# DeepResearch Roadmap

DeepResearch v2 should stay a thin product package over MissionForge Kernel.

## Current Baseline

- Active command: `academic kernel-v2-run`.
- Active flow: source_mapper -> researcher -> reviewer -> judge.
  Seeded runs insert `seed_normalizer` before source_mapper.
- Active adapter: PiWorker through Codex current provider config or fixture
  mode for tests.
- Active output: markdown final report, search plan, provider-hit JSONL,
  coverage report, evidence/source packet, judge report, result package, usage
  summary, and optional HTML export.
- Active source acquisition artifacts: `sources/provider_capabilities.json`,
  `sources/search_plan.json`, `sources/provider_hits.jsonl`,
  `sources/source_packet.json`, and `sources/coverage_report.json`.
- Active seed artifacts: `inputs/seed_papers.json`,
  `inputs/seed_pdf_index.json`, `sources/seed_source_packet.json`,
  `reports/seed_gaps.md`, and `state/seed_control.json`.
- Active PDF boundary: `pi-pdf-sources` delegates scholarly PDF parsing to
  GROBID when configured, writes raw TEI plus metadata/sections/references/
  provenance projections under `sources/seed_pdfs/`, and records diagnostics
  when unavailable.
- Active parsed-PDF evidence path: seed PDF `parse_refs` are preserved through
  source records, canonical sources, evidence indexes, and claim indexes as
  explicit evidence refs.
- Active claim-support review path: reviewer PiWorker writes
  `reviews/claim_support_review.json` as the semantic claim-to-evidence support
  audit, runtime validates only schema/ref boundaries in
  `state/claim_support_review_validation.json`, and Judge consumes the audit
  plus parsed/fetched evidence refs before acceptance.
- Active acceptance gate: runtime writes `state/acceptance_gate.json` after
  flow completion to enforce mechanical citation, claim-index, claim-support,
  reviewer-decision, and Judge-decision consistency before exposing product
  acceptance.
- Active revision request path: Judge `revision_required` preserves flow/product
  status as `revision_required` and writes `revisions/revision_request.json`
  without mutating the frozen contract.
- Active repair boundary: reviewer `revise_report` and Judge `repair` route to
  dedicated repair steps. Reviewer repair reads reviewer feedback refs; Judge
  repair additionally reads `judge/judge_report.json`; the initial researcher
  step does not read stale review or judge artifacts.
- Active academic acquisition scale: standard runs use a 50-source reference
  budget, intensive runs use 100, and request-level `target_source_count` can
  override either budget.
- Active analysis artifact: `analysis/insight_map.json`, authored by the
  researcher PiWorker and reviewed by reviewer/judge as the thesis, narrative
  arc, cross-source insight, audience relevance, and evidence-limit map.
- Active report shape: neutral literature-review/research-survey by default,
  with abstract/key findings, scope/method, background/problem definition,
  research lines, comparative analysis, limitations/counterevidence/open
  questions, trends/future directions, and references. Strategic memos are a
  user-requested genre, not the default.
- Active project lifecycle: DeepResearch writes a project manifest, lifecycle
  state, run index, resume diagnostics, and role-local ContextPackage pointers.
  FrontDesk, source mapper, researcher, reviewer, and judge keep isolated
  ContextPackage refs managed by MissionForge ContextEngine.
- Active web console slice: `academic web-console` serves a project dashboard,
  artifact browser, source/citation tables, Markdown report preview, and
  FrontDesk message submission through the existing FrontDesk PiWorker turn
  boundary. Browser requirements approval is wired through the existing
  FrontDesk approval boundary. Browser Start Research starts Kernel v2 as a
  server-owned background task, records `web/tasks/current_task.json`, and
  exposes `/api/task` for task state without letting the browser choose provider
  config or adapter mode. Browser runtime controls append pause, resume,
  checkpoint, stop-after-current-turn, cancel, message, and revise events
  through the same MissionForge interaction ledger used by TUI. Browser Start
  Research also uses a workspace-local `web/locks/kernel_v2.lock` guard so
  another web-console process surfaces a sanitized locked task state instead of
  starting a second Kernel run for the same project. Browser lifecycle actions
  record explicit retry, revision, and lock-recovery requests as refs-only
  project artifacts. Pending retry requests can now be explicitly consumed by
  `POST /api/research/attempt/start`, which writes attempt manifests, an
  attempt index, and before-run snapshots before launching a server-owned Kernel
  retry attempt. The dashboard also exposes a refs-first Progress Timeline
  projected from live sanitized progress markers, flow ledgers, step records,
  runtime interaction events, lifecycle actions, attempt index, and web task
  state. Pending revision requests can now be explicitly consumed by
  `POST /api/research/revision/start`, which writes contract revision records,
  a revision index, staged Kernel revision inputs, and a revision attempt before
  launching a server-owned Kernel run from the revised request. Retry attempts
  still cannot consume revision requests. Completed retry/revision attempts now
  copy stable Kernel outputs into attempt-scoped output refs, write an output
  manifest, and update `project/current_output_pointer.json` so the dashboard
  can prefer current attempt outputs while preserving stable refs as fallback
  for legacy/first-run projects. Once a current output pointer exists, missing
  attempt-scoped refs are surfaced as missing instead of silently falling back
  to stable Kernel refs.
  The progress timeline is now also grouped by project/attempt refs and
  highlights the attempt that owns the current output pointer. FrontDesk
  dialogue is projected by refs and turn metadata in the project snapshot; raw
  dialogue remains an explicit artifact read, not default dashboard state.

## Design Principles

- Do not split research into a fixed Python checklist.
- Do not make Python a semantic research expert.
- Use PiWorker-authored state, observations, reviews, and judge artifacts.
- Use PiWorker-authored insight artifacts for semantic depth; do not replace
  them with deterministic prose or insight scoring in Python.
- Keep code responsible for refs, permissions, schemas, progress, resume,
  source tool boundaries, final paths, and token accounting.
- Treat resume as ContextPackage restoration, not chat-history replay. Raw
  dialogue is only one source inside a role-specific compiled context package.
- Treat ContextPackages as opaque ContextEngine data in DeepResearch. Token
  pressure, compaction, retention, and stale-package recompile belong in
  MissionForge core.
- Treat the web console as the primary product surface for non-developer users.
  CLI/TUI remain developer and automation surfaces.
- Make reviewer and judge feedback complete in one pass rather than
  drip-feeding tiny issues across loops.

## Near-Term Work

- Upgrade DeepResearch toward the academic literature-review product standard
  in [DeepResearch Academic Literature Upgrade Plan](DEEP_RESEARCH_ACADEMIC_LITERATURE_UPGRADE_PLAN.md).
- Harden citation and claim support with richer URL accessibility checks,
  page/span-level parsed PDF provenance when available, and live fetched/full-text
  evidence coverage without making Python a semantic judge.
- Continue seed/PDF ingestion later with Web upload UI, OCR fallback, and
  richer page/span citation support.
- Keep hardening persistent project resume: reuse valid role ContextPackages,
  recompile stale packages from refs/checkpoints/working sets, and surface
  restore diagnostics in CLI/TUI/Web without moving token policy into
  DeepResearch.
- Continue the project-oriented web console. The project dashboard,
  source/citation inspection, artifact browser, Markdown preview, and FrontDesk
  chat plus requirements approval, background start-run, and first runtime
  controls are active; conservative cross-process run locking and first-slice
  retry/revise/recover lifecycle requests are active. Retry attempt generation
  from pending retry requests, the refs-first progress timeline, the first
  explicit contract revision flow, and attempt-scoped output projection are
  active. Attempt-grouped timeline projection is active. Upload controls remain
  next.
- Continue hardening the no-key provider stack. OpenAlex may enhance coverage
  when configured, but missing OpenAlex credentials must not block the default
  product path.
- Improve mature platform/source acquisition by letting the researcher inspect
  repository files and documentation metadata when authorized.
- Keep claim-to-source mapping PiWorker-authored while expanding the evidence
  plane that Reviewer/Judge can inspect.
- Keep improving insight-map driven reports: thesis-first writing,
  evidence-conclusion calibration, cross-source tensions, and reader-value
  implications.
- Prefer synthesis-oriented organization over tool-by-tool catalogs. Match the
  user's requested genre: literature reviews should be objective, rigorous,
  comprehensive, and evidence-calibrated; strategic memos should only appear
  when explicitly requested.
- Improve report export: HTML first, PDF later through a separate renderer.
- Keep CLI/TUI and web console on the same refs, lifecycle state, interaction
  events, approvals, and revision records. The frontend must not become a
  parallel source of truth.
- Keep usage accounting visible: input, cached input, output, and total tokens.
- Keep resume package-based, artifact-backed, and explicit: unchanged
  fingerprints may reuse the latest ContextPackage; stale packages must
  recompile from refs, checkpoints, and working sets.

## Non-Goals

- No hidden product semantics in `src/missionforge`.
- No deterministic paper ranking expert in Python.
- No forced installation, execution, benchmarks, or experimental reproduction.
- No `experimental` intensity until `standard` and `intensive` are stable.
