# DeepResearch Roadmap

DeepResearch v2 should stay a thin product package over MissionForge Kernel.

## Current Baseline

- Active command: `academic kernel-v2-run`.
- Active flow: researcher -> reviewer -> judge.
- Active adapter: PiWorker through Codex current provider config or fixture
  mode for tests.
- Active output: markdown final report, evidence/source packet, judge report,
  result package, usage summary, and optional HTML export.

## Design Principles

- Do not split research into a fixed Python checklist.
- Do not make Python a semantic research expert.
- Use PiWorker-authored state, observations, reviews, and judge artifacts.
- Keep code responsible for refs, permissions, schemas, progress, resume,
  source tool boundaries, final paths, and token accounting.
- Make reviewer and judge feedback complete in one pass rather than
  drip-feeding tiny issues across loops.

## Near-Term Work

- Improve mature platform/source acquisition by letting the researcher inspect
  repository files and documentation metadata when authorized.
- Strengthen claim-to-source mapping without requiring code to judge semantic
  sufficiency.
- Improve report export: HTML first, PDF later through a separate renderer.
- Keep usage accounting visible: input, cached input, output, and total tokens.
- Keep resume artifact-based and explicit.

## Non-Goals

- No hidden product semantics in `src/missionforge`.
- No deterministic paper ranking expert in Python.
- No forced installation, execution, benchmarks, or experimental reproduction.
- No `experimental` intensity until `standard` and `intensive` are stable.
