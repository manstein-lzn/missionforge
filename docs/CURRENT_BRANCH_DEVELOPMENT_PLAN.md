# MissionForge Current Branch Development Plan

Last updated: 2026-06-12

Status: release-candidate checkpoint for `agentic-runtime-upgrade`.

## Objective

Converge MissionForge into a small, product-neutral PiWorker kernel:

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

MissionForge should not become a deterministic Python system that tries to
understand arbitrary product needs with branching logic. Its job is to provide
hard deterministic boundaries around probabilistic workers:

- frozen task authority
- workspace layout
- permission manifests
- run-relative refs
- role separation
- evidence hygiene
- explicit repair and revision records
- replayable ledgers

PiWorker nodes do semantic work. Product-specific meaning stays in external
integrations, task contracts, rubrics, hard checks, fixtures, and product
packages.

## Non-Goals

This branch should not:

- add product semantics to `src/missionforge`
- create a provider marketplace or public multi-worker registry
- expand MissionIR or legacy runtime paths as the new conceptual center
- use metrics as semantic routing or acceptance authority
- treat executor completion as acceptance
- silently weaken a frozen contract during repair
- mutate a contract during revision without an explicit revision record
- persist raw prompts, transcripts, provider payload bodies, stdout/stderr
  bodies, artifact bodies, or secrets as operator-facing task truth

## Current Branch Truth

- `TaskContract` and PiWorker are the primary direction.
- `MissionIR` remains a high-detail compatibility data shape; the old runtime,
  harness, work-unit, runner, and fake-worker modules have been removed.
- Steering and metric modules remain product-neutral diagnostics/data surfaces,
  not a parallel execution path.
- `create_default_task_contract_flow(...)` is the default product-neutral flow.
- Runtime-owned `attempts/...` artifacts are the PiWorker audit plane.
- Runtime projections are exposed as refs, not as worker-owned artifacts.
- Executors cannot write directly to runtime-owned projection paths.
- Executor completion never grants semantic acceptance.
- Acceptance must come from an independent judge role using the frozen
  contract, judge rubric, artifact refs, hard-check refs, and recorded evidence.
- Repair remains under the same contract hash.
- Revision creates explicit new task authority before revised execution
  continues.
- SkillFoundry is an external product dogfood under
  `integrations/skillfoundry`, not a core branch.

## Recently Established Capabilities

### PiWorker Runtime Boundary

- Default TaskContract flow writes Pi runtime artifacts under the active run
  workspace.
- `attempts/<call_id>/...` records the full PiWorker call audit plane.
- `AgentExecutionReport` avoids exposing runtime-owned `attempts/...` refs as
  worker-written changed refs.
- Runtime-owned call-result and metrics projections are validated as runtime
  evidence, not executor authority.
- Judge PiWorker calls receive exact judge-authored writable refs instead of
  broad directory permissions.
- Faux runtime remains the default CI path.
- Live runtime remains opt-in.

### Repair Lifecycle

- Repair is represented as:

```text
JudgeReport(decision=repair)
  -> RepairBrief
  -> RepairTicket
  -> RepairExecutionDirective
  -> PiWorkerCall(role=repair_piworker)
  -> PiWorkerCallResult
  -> build_repair_rejudge_packet(...)
  -> independent JudgePacket
```

- `build_repair_rejudge_packet(...)` bridges a completed repair worker result
  back into the independent judge lane.
- Repair preserves the original contract hash.
- Repair does not accept work.
- A separate judge still decides `accepted`, `repair`,
  `revision_required`, or `rejected`.

### Revision Lifecycle

- Revision is represented as:

```text
JudgeReport(decision=revision_required)
  -> TaskRevisionRequest
  -> RevisionPendingRecord
  -> PiWorkerCall(role=revision_drafter_piworker)
  -> PiWorkerCallResult
  -> load_revision_draft_contract(...)
  -> TaskRevisionDecision(approved)
  -> apply_task_contract_revision(...)
  -> RevisionAppliedRecord + TaskContractRevision
  -> build_revision_execution_directive(...)
  -> revised-contract AgentExecutionPacket
  -> PiWorkerCallResult
  -> build_revision_rejudge_packet(...)
  -> independent revised-contract JudgePacket
  -> build_revision_judge_result(...)
  -> accepted | repair | revision_required | rejected
```

- `load_revision_draft_contract(...)` validates a revision drafter's proposed
  revised `TaskContract`.
- `build_revision_execution_directive(...)` creates the first execution entry
  under the revised contract authority.
- `build_revision_rejudge_packet(...)` records the revised execution report and
  prepares an independent revised judge packet.
- `build_revision_judge_result(...)` records the revised judge result and emits
  a revised final package when the independent judge accepts.
- Ledger replay allows a contract hash transition only through
  `revision_applied`.

### SkillFoundry Dogfood

- SkillFoundry exposes a TaskContract-native facade:
  `run_skillfoundry_task_contract_bundle_build(...)`.
- SkillFoundry compiles product intent into TaskContract refs, workspace policy,
  permission manifest, product hard checks, and product reports outside core.
- The live dogfood classifier inspects TaskContract-native workspaces and
  preserves run-prefixed refs in product-facing reports.
- The manifest-template change produced package refs that passed SkillFoundry
  bundle validation and product-grade registration when replayed from recorded
  refs.

## Verified Evidence

The following checks have passed during this branch line of work:

- `MISSIONFORGE_SKIP_NPM_CI=1 ./scripts/validate.sh`
  - 8 Node runtime tests passed.
  - 512 Python tests passed.
  - 5 Python tests skipped.
  - whitespace check passed.
- `./scripts/validate_integrations.sh skillfoundry`
  - 112 tests passed.
  - 1 test skipped.
- Focused repair/revision controller suite:
  - `tests.test_agentic_repair_controller`: 30 tests passed.
- Focused ledger suite:
  - `tests.test_agentic_ledger`: 6 tests passed.
- Focused combined repair/revision plus ledger suite:
  - 36 tests passed.
- Core PiWorker/flow/ledger/public API focused suite:
  - 44 tests passed.
  - 1 test skipped.
- Public API boundary now has an explicit primary TaskContract/PiWorker root
  export test.
- Product-neutral live TaskContract smoke passed with
  `provider_config_source="codex_current"`:

```bash
MISSIONFORGE_PI_AGENT_LIVE_SMOKE=1 \
MISSIONFORGE_PI_AGENT_LIVE_TIMEOUT_SECONDS=420 \
PYTHONPATH=src:tests \
python3 -m unittest \
  tests.test_agentic_flow.AgenticFlowTests.test_live_codex_current_default_task_contract_flow_accepts
```

  Result: 1 live test passed in 132.875 seconds.

- Fresh SkillFoundry live dogfood completed through the TaskContract-native
  facade with `provider_config_source="codex_current"`:

```text
Workspace: /tmp/mf-skillfoundry-live-xxxbuoj9
Outcome category: completed
Run status: completed
Issue codes:
  - product_grade_registered
Product report ref: reports/skillfoundry_product_report.json
Product grade report ref: runs/demo-skill/qa/product_grade_report.json
Bundle validation report ref: runs/demo-skill/qa/skill_bundle_validation_report.json
Registry decision ref: runs/demo-skill/registry/skillfoundry_registry.json
Package refs:
  - runs/demo-skill/package/SKILL.md
  - runs/demo-skill/package/skillfoundry.bundle.json
  - runs/demo-skill/package/README.md
Evidence refs:
  - runs/demo-skill/reports/judge_report.json
  - runs/demo-skill/ledgers/decision_ledger.jsonl
  - runs/demo-skill/packages/final_package.json
```

- Replay of `/tmp/mf-skillfoundry-live-xxxbuoj9/runs/demo-skill` returned
  `status=accepted` with the three package refs accepted by the independent
  judge.
- Manual-only standalone product shell evidence:

```bash
PYTHONPATH=src:. python3 -m unittest tests.test_standalone_product_shell_example
# Ran 1 test: OK

PYTHONPATH=src python3 examples/standalone_product_shell.py /tmp/mf-standalone-manual-demo
# status=accepted
# replay_status=accepted
```

## Known Gaps

- Programmer documentation exists, but it should be treated as a product
  surface and kept synchronized with every primitive or behavior change.
- Legacy compatibility surfaces still exist and must not pull new work back
  into the old MissionIR-centered architecture.

## Development Plan

### Phase 1: Refresh Baseline And Branch Truth

Status: completed for the current line of work.

Goal: make the current branch state reproducible.

Tasks:

- [x] Re-run focused repair/revision and ledger tests.
- [x] Re-run the core boundary suite.
- [x] Re-run `MISSIONFORGE_SKIP_NPM_CI=1 ./scripts/validate.sh`.
- [x] Re-run `./scripts/validate_integrations.sh skillfoundry`.
- [x] Record exact test counts and skips in this document.
- [x] Keep README, manuals, primitive reference, and module docs aligned with the
  current public API.

Exit condition:

- The branch has fresh validation evidence after the latest code and docs.
- This document matches the actual implementation state.

### Phase 2: Finish Revision Result Documentation And API Alignment

Status: completed for the current line of work.

Goal: make revised-contract result handling a documented primitive, not hidden
controller knowledge.

Tasks:

- [x] Ensure `build_revision_judge_result(...)` is exported from the public API
  only if it belongs in the programmer-facing primitive surface.
- [x] Document `build_revision_judge_result(...)` in:
  - `docs/USER_MANUAL.md`
  - `docs/PRIMITIVE_REFERENCE.md`
  - `docs/modules/agentic_repair.md`
- [x] Explain that revised acceptance emits a final package under the revised
  authority and that non-accepted decisions continue through the same
  judge-result vocabulary.
- [x] Document that the decision ledger changes contract hash only through
  `revision_applied`.

Exit condition:

- A programmer can understand the full repair and revision lifecycle without
  reading controller source code.

### Phase 3: Prove Repair And Revision Replay

Status: completed for the current line of work.

Goal: make repair and revision auditable from durable refs.

Tasks:

- [x] Preserve tests for accepted, repair, revision-required, and rejected judge
  outcomes.
- [x] Preserve tests for stale or mismatched contract hashes.
- [x] Preserve tests rejecting executor self-acceptance.
- [x] Preserve tests showing repair does not weaken or mutate the frozen contract.
- [x] Preserve tests showing revision requires pending, approved, applied, and
  revised-contract records.
- [x] Preserve ledger replay tests that explain the full revision path without Pi
  chat memory.

Exit condition:

- A ledger plus refs can explain how the run moved from original contract to
  revised contract and final result.

### Phase 4: Lock The Programmer Surface

Status: completed for the current release-candidate checkpoint.

Goal: let programmers build with MissionForge primitives without reading
`src/missionforge`.

Tasks:

- [x] Keep `README.md` pointing to the primary docs.
- [x] Keep `GETTING_STARTED.md` short and runnable.
- [x] Keep `USER_MANUAL.md` complete enough for standalone product integration
  work.
- [x] Keep `PRIMITIVE_REFERENCE.md` field-level and precise.
- [x] Keep `COOKBOOK.md` focused on composition patterns, not product methodology.
- [x] Keep `LIVE_RUNTIME_GUIDE.md` explicit about faux/live provider setup,
  `codex_current`, secret redaction, and debugging.
- [x] Keep `MIGRATION_GUIDE.md` clear that MissionIR is compatibility.
- [x] Keep `API_BOUNDARY.md` centered on the primary TaskContract/PiWorker
  kernel surface, with MissionIR and older runtime APIs marked as
  compatibility.
- [x] Keep SkillFoundry documentation as an external integration example, not a
  required product methodology.
- [x] Maintain a standalone product-shell example that can be run from public
  docs without reading MissionForge source.

Exit condition:

- A programmer can build a standalone product integration using only public
  docs and primitives.

### Phase 5: Re-Dogfood SkillFoundry

Status: completed for the current line of work.

Goal: prove the product-neutral substrate through an external product
integration.

Tasks:

- [x] Run default faux SkillFoundry integration validation in CI mode.
- [x] Re-run live SkillFoundry dogfood when provider quota is available.
- [x] Require either:
  - a completed TaskContract-native product-grade result; or
  - a correctly classified MissionForge boundary failure with refs.
- [x] Keep every SkillFoundry-specific rule under `integrations/skillfoundry`.
- [x] Convert any repeated runtime or boundary failure into focused tests.

Exit condition:

- SkillFoundry proves the MissionForge boundary without adding SkillFoundry
  branches to core.

### Phase 6: Clean Legacy Drift

Status: completed for the current release-candidate checkpoint.

Goal: prevent compatibility code from becoming the active architecture again.

Tasks:

- [x] Move MissionIR, old runtime, steering, and work-unit surfaces out of the
  package-root public API and leave them as explicit legacy submodule imports.
- [x] Stop adding features to legacy paths unless they preserve compatibility.
- [x] Remove or isolate stale benchmark/demo references from the active lane.
- [x] Keep product-specific branches out of `src/missionforge`.
- [x] Update public API boundary tests when imports move.

Exit condition:

- New feature work naturally lands in the TaskContract/PiWorker path.
- Compatibility surfaces remain available but do not read as the recommended
  conceptual API.

### Phase 7: Release Candidate Audit

Status: completed for the current release-candidate checkpoint.

Goal: produce a branch that external programmers can try.

Acceptance checklist:

- [x] `MISSIONFORGE_SKIP_NPM_CI=1 ./scripts/validate.sh` passes.
- [x] `./scripts/validate_integrations.sh skillfoundry` passes.
- [x] Faux TaskContract flow reaches independent accepted judgment.
- [x] Product-neutral opt-in live smoke reaches an independent judge decision.
- [x] SkillFoundry dogfood reaches a product-grade result or correctly classified
  boundary failure.
- [x] Programmer docs support a standalone product shell.
- [x] Public API boundary tests pass.
- [x] Product semantics remain outside `src/missionforge`.
- [x] Decision ledgers remain refs-first and replayable.
- [x] No executor path can self-accept.

## Completed Work Order

Completed for the current release-candidate checkpoint:

1. Updated primitive and module docs for `build_revision_judge_result(...)`.
2. Re-ran focused repair/revision and ledger tests.
3. Re-ran the core boundary suite.
4. Re-ran full validation and SkillFoundry integration validation.
5. Refreshed the verified evidence section with exact counts.
6. Audited README and public exports for TaskContract/PiWorker-first guidance.
7. Completed the release-candidate cleanup, commit, push, and clean-worktree
   audit.

## Definition Of Done

This branch is done only when MissionForge can be explained and used as a
minimal deterministic kernel around PiWorker:

- product integrations compile intent into contracts
- MissionForge freezes contracts and enforces boundaries
- PiWorker executes semantic work inside those boundaries
- an independent judge decides acceptance
- repair preserves contract authority
- revision creates explicit new authority
- ledgers and refs explain the run without chat memory
- docs let programmers use the system without source archaeology
