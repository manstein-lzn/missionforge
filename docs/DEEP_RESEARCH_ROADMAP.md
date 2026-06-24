# DeepResearch Roadmap

DeepResearch v2 should stay a thin product package over MissionForge Kernel.

## Current Baseline

- Active command: `academic kernel-v2-run`.
- Active flow: researcher -> reviewer -> judge.
- Active adapter: PiWorker through Codex current provider config or fixture
  mode for tests.
- Active output: markdown final report, evidence/source packet, judge report,
  result package, usage summary, and optional HTML export.
- Active analysis artifact: `analysis/insight_map.json`, authored by the
  researcher PiWorker and reviewed by reviewer/judge as the thesis, narrative
  arc, cross-source insight, audience relevance, and evidence-limit map.
- Active report shape: neutral literature-review/research-survey by default,
  with abstract/key findings, scope/method, background/problem definition,
  research lines, comparative analysis, limitations/counterevidence/open
  questions, trends/future directions, and references. Strategic memos are a
  user-requested genre, not the default.

## Design Principles

- Do not split research into a fixed Python checklist.
- Do not make Python a semantic research expert.
- Use PiWorker-authored state, observations, reviews, and judge artifacts.
- Use PiWorker-authored insight artifacts for semantic depth; do not replace
  them with deterministic prose or insight scoring in Python.
- Keep code responsible for refs, permissions, schemas, progress, resume,
  source tool boundaries, final paths, and token accounting.
- Make reviewer and judge feedback complete in one pass rather than
  drip-feeding tiny issues across loops.

## Near-Term Work

- Improve mature platform/source acquisition by letting the researcher inspect
  repository files and documentation metadata when authorized.
- Strengthen claim-to-source mapping without requiring code to judge semantic
  sufficiency.
- Keep improving insight-map driven reports: thesis-first writing,
  evidence-conclusion calibration, cross-source tensions, and reader-value
  implications.
- Prefer synthesis-oriented organization over tool-by-tool catalogs. Match the
  user's requested genre: literature reviews should be objective, rigorous,
  comprehensive, and evidence-calibrated; strategic memos should only appear
  when explicitly requested.
- Improve report export: HTML first, PDF later through a separate renderer.
- Keep usage accounting visible: input, cached input, output, and total tokens.
- Keep resume artifact-based and explicit.

## Non-Goals

- No hidden product semantics in `src/missionforge`.
- No deterministic paper ranking expert in Python.
- No forced installation, execution, benchmarks, or experimental reproduction.
- No `experimental` intensity until `standard` and `intensive` are stable.
