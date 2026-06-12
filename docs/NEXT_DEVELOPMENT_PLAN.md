# MissionForge Next Development Plan

Last updated: 2026-06-12

Status: proposed execution plan after the PiWorker kernel cutover.

## Purpose

MissionForge has crossed the main architectural cutover: the active direction is
now a product-neutral TaskContract/PiWorker kernel, with SkillFoundry proving
the external product-integration path.

The next development work should avoid adding new conceptual machinery. The
goal is to turn the current branch into a stable release-candidate surface that
programmers can use without reading MissionForge source code.

## Product Principle

MissionForge should feel like a small set of reliable programming primitives:

```text
ProductIntegration
  -> TaskContract
  -> WorkerBrief + JudgeRubric + WorkspacePolicy + PermissionManifest
  -> PiWorker executor
  -> artifact refs + execution report
  -> independent Judge PiWorker
  -> accepted | repair | revision_required | rejected
  -> refs-first ledger and final package
```

Core code owns deterministic boundaries:

- frozen contract authority
- workspace layout
- permission manifests
- run-relative refs
- role separation
- evidence hygiene
- repair and revision records
- replayable decision ledgers

PiWorker nodes own semantic work. Product meaning must stay in integrations,
contracts, rubrics, hard checks, fixtures, and product packages.

## Current Baseline

The current branch already has:

- TaskContract/PiWorker as the primary public direction.
- MissionIR, old runtime, steering, work-unit, and metric-dict APIs demoted to
  explicit legacy submodule surfaces rather than package-root public API.
- `create_default_task_contract_flow(...)` as the default product-neutral flow.
- Independent judge acceptance; executor completion does not self-accept.
- Same-contract repair and explicit revised-contract continuation.
- Refs-first final packages and decision-ledger replay.
- SkillFoundry as an external product dogfood under
  `integrations/skillfoundry`.
- A standalone product-shell example built from public primitives.
- Recent local validation and opt-in live dogfood evidence recorded in the
  active status documents.

The remaining work is mostly productization, documentation hardening, boundary
cleanup, and release-candidate audit.

## Phase 1: Commit The Current Stable Cut

Goal: preserve the current validated work before further changes.

Tasks:

- Commit the staged standalone product-shell example and related docs.
- Push the branch.
- Re-run `git status --branch --short`.
- Re-run `git diff --check`.
- If any staged or unstaged drift appears, classify it as either intentional
  release-candidate work or unrelated local work.

Exit condition:

- The branch has a clean, pushed checkpoint that includes the current
  standalone example and documentation updates.

## Phase 2: Release-Candidate Boundary Audit

Goal: prove that MissionForge core is still product-neutral and PiWorker-first.

Tasks:

- Search `src/missionforge` for product-specific names such as SkillFoundry,
  Codexarium, benchmark, finance, customer, or demo-only product branches.
- Confirm product-specific behavior remains under `integrations/`, examples,
  fixtures, tests, or docs.
- Re-check public exports in `src/missionforge/__init__.py`.
- Keep TaskContract/PiWorker primitives as the primary public surface.
- Keep MissionIR and old runtime APIs available only as explicit legacy
  submodule paths until they are deleted.
- Add or adjust boundary tests if any public surface moved.

Exit condition:

- A programmer looking at the package root sees the TaskContract/PiWorker path
  first.
- No product-specific semantic branch exists in MissionForge core.

## Phase 3: Documentation As Product Surface

Goal: make the programmer manual good enough that a developer can build a
standalone product integration from docs alone.

Tasks:

- Treat `docs/USER_MANUAL.md` as the authoritative manual.
- Keep `docs/PRIMITIVE_REFERENCE.md` field-level and precise.
- Keep `docs/COOKBOOK.md` focused on composition patterns, not product
  methodology.
- Keep `docs/GETTING_STARTED.md` short and runnable.
- Keep `docs/LIVE_RUNTIME_GUIDE.md` explicit about faux/live provider setup,
  `codex_current`, secret redaction, and debugging.
- Keep `docs/MIGRATION_GUIDE.md` clear that MissionIR is compatibility.
- Ensure the standalone product-shell example is discoverable from README,
  manual, and cookbook.
- Add doc tests or example tests for any manual promise that could drift.

Exit condition:

- A developer can create a product integration using only documented primitives,
  without copying SkillFoundry internals or reading `src/missionforge`.

## Phase 4: Standalone Product-Shell Experiment

Goal: keep pressure on the public API by testing it as an external programmer
would use it.

Tasks:

- Run the standalone product-shell example from a clean temp workspace.
- Verify it reaches `status=accepted` and `replay_status=accepted`.
- Confirm the example uses public imports and public docs vocabulary.
- Confirm it does not depend on SkillFoundry-specific code.
- Preserve a focused test for the example.
- If the example needs source archaeology, fix the docs or public primitive
  names instead of adding product-specific shortcuts.

Exit condition:

- The standalone example remains a living proof that MissionForge has enough
  general-purpose primitives for product authors.

## Phase 5: SkillFoundry Dogfood As External Product Proof

Goal: use SkillFoundry to prove the substrate, not to define core semantics.

Tasks:

- Keep SkillFoundry-specific rules under `integrations/skillfoundry`.
- Run default faux SkillFoundry validation.
- Run live SkillFoundry dogfood only when real provider usage is intentional.
- Require the dogfood classifier to report either:
  - completed product-grade registration; or
  - a correctly classified boundary failure with refs.
- Convert repeated runtime or permission failures into focused tests.

Exit condition:

- SkillFoundry proves the MissionForge boundary without pulling SkillFoundry
  concepts into core.

## Phase 6: Repair, Revision, And Ledger Hardening

Goal: make long-running task correction auditable from refs, not chat memory.

Tasks:

- Preserve tests for accepted, repair, revision-required, and rejected judge
  outcomes.
- Preserve tests proving repair keeps the same contract hash.
- Preserve tests proving revision requires pending, approved, applied, revised
  execution, rejudge, and revised result records.
- Confirm ledger replay explains contract-hash transitions only through
  `revision_applied`.
- Confirm executor output never grants acceptance.
- Confirm judge packets use frozen or explicitly revised contract authority.

Exit condition:

- A decision ledger plus refs can explain the full run path without reading Pi
  transcripts or provider payloads.

## Phase 7: Legacy Deletion Cut

Goal: remove the old conceptual surface instead of preserving compatibility
forever.

Tasks:

- Keep package-root exports limited to the TaskContract/PiWorker kernel and
  genuinely shared infrastructure.
- Replace FrontDesk generic MissionIR fallback with TaskContract-native
  ProductIntegration compilation.
- Move or delete CLI commands that require MissionIR as the run input.
- Change Pi Agent runtime projection so it can consume PiWorkerCall/agent
  packets directly instead of `WorkUnitContract`.
- Delete `MissionRuntime`, `RuntimeEngine`, `MissionIR`, `WorkUnitContract`,
  old harness, old faux worker, and old steering runtime tests only after their
  invariants are covered by TaskContract/PiWorker tests.

Exit condition:

- New programmers encounter one conceptual runtime path in code and docs:
  TaskContract/PiWorker.

## Phase 8: Store And Runtime Cleanup

Goal: reduce future maintenance risk without changing the conceptual model.

Tasks:

- Identify remaining direct file writes that bypass the store boundary.
- Keep layout-compatible reads where they are harmless.
- Avoid a broad store rewrite until it reduces real duplication or closes a
  concrete boundary risk.
- Ensure runtime-owned `attempts/` and projection refs remain distinct from
  worker-written artifact refs.
- Keep secret exclusion and raw-payload exclusion tests focused and current.

Exit condition:

- Runtime evidence remains refs-first, permission-bounded, and replayable, with
  no second hidden write path for important state.

## Phase 9: FrontDesk PiWorker Authoring Slice

Goal: improve requirement discovery without adding deterministic product
understanding to core.

Tasks:

- Keep FrontDesk as a high-intelligence requirements-discovery surface.
- Fail closed when required LLM/PiWorker-authored artifacts are unavailable.
- Add PiWorker-authored need grilling, solution architecture, or intent-bundle
  authoring only behind schemas, refs, and product-neutral boundaries.
- Keep product-specific inquiry profiles outside core.
- Do not add regex or if-else product-intent extraction to MissionForge core.

Exit condition:

- FrontDesk can improve semantic input quality while preserving the same hard
  contract and product-integration boundaries.

## Phase 10: Release Candidate Validation

Goal: produce a branch external programmers can try.

Required checks:

```bash
MISSIONFORGE_SKIP_NPM_CI=1 ./scripts/validate.sh
./scripts/validate_integrations.sh skillfoundry
PYTHONPATH=src:. python3 -m unittest tests.test_standalone_product_shell_example
PYTHONPATH=src python3 -m unittest tests.test_public_api_boundary tests.test_agentic_ledger tests.test_agentic_flow tests.test_piworker_call tests.test_piworker_runtime_boundary tests.test_standalone_product_shell_example
git diff --check
git status --branch --short
```

Opt-in live checks:

```bash
MISSIONFORGE_PI_AGENT_LIVE_SMOKE=1 \
MISSIONFORGE_PI_AGENT_LIVE_TIMEOUT_SECONDS=420 \
PYTHONPATH=src:tests \
python3 -m unittest \
  tests.test_agentic_flow.AgenticFlowTests.test_live_codex_current_default_task_contract_flow_accepts
```

SkillFoundry live dogfood should be run only when real provider usage is
intended and quota is available.

Exit condition:

- Local validation passes.
- Integration validation passes.
- Standalone product shell passes.
- Public API boundary tests pass.
- Live smoke has recent evidence or is clearly marked opt-in.
- Worktree is clean except for explicitly documented local artifacts.

## Definition Of Done

The next development cycle is complete when MissionForge can be handed to a
programmer as:

- a small set of documented primitives;
- a product-neutral PiWorker delegation kernel;
- a deterministic boundary around probabilistic workers;
- a system where execution, judgment, repair, revision, and replay are
  inspectable through refs and ledgers;
- a platform where product teams build integrations outside core instead of
  modifying MissionForge internals.
