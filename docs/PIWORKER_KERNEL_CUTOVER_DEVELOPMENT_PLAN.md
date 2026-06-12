# PiWorker Kernel Cutover Development Plan

Last updated: 2026-06-12

Status: completed release-candidate cutover plan for the
`agentic-runtime-upgrade` branch.

## Goal

MissionForge should converge into a minimal delegation kernel around Pi:

```text
Product Integration
  -> TaskContract
  -> PiWorkerCall
  -> Pi Agent runtime
  -> executor artifacts
  -> independent judge
  -> accepted | repair | revision_required | rejected
  -> refs-first ledger/final package
```

The next work should be cutover, dogfood, and cleanup. It should not add a new
workflow framework, provider marketplace, or deterministic product-understanding
layer.

## Phase 1: Establish The Branch Baseline

Purpose: make the current branch state reproducible.

Work:

- Run full local validation with `./scripts/validate.sh`.
- Run SkillFoundry validation with `./scripts/validate_integrations.sh skillfoundry`.
- Record test counts, skips, and any known opt-in live checks.
- Check README, AGENTS, constitution, and implementation status docs for
  contradictions.
- Keep one concise engineering-state note for the current branch truth.

Acceptance:

- Working tree is clean.
- Local validation results are reproducible.
- The branch state document agrees with the README and constitution.

## Phase 2: Narrow The Public API And Concept Center

Purpose: make TaskContract/PiWorker the obvious default path for programmers.

Work:

- Audit `src/missionforge/__init__.py`.
- Separate public API guidance into:
  - primary kernel surface;
  - adapter-specific imports;
  - legacy compatibility surface.
- Keep MissionIR and older runtime symbols available only where compatibility
  requires them.
- Add or update public API boundary tests.
- Prevent product-specific semantics from entering `src/missionforge`.

Acceptance:

- README recommended APIs match the actual public surface.
- MissionIR and old runtime surfaces are clearly documented as compatibility.
- New development docs point to TaskContract/PiWorker first.

## Phase 3: Harden The Default PiWorker Runtime Loop

Purpose: make `create_default_task_contract_flow(...)` a reliable default
execution entrypoint.

Work:

- Keep `WorkUnitContract` as an adapter projection, not the conceptual center.
- Tighten the `PiWorkerCall -> PiAgentRuntimeInput -> workers/pi-agent-runtime`
  path.
- Fix and test the relationship among run root, `attempts/` refs, runtime
  evidence refs, and permission manifests.
- Ensure executor reports expose only refs that the outer AgenticFlow
  permission model can validate.
- Maintain a stable faux path for CI.
- Maintain an opt-in live smoke path for real Pi Agent execution.

Acceptance:

- Faux executor and judge can complete an accepted TaskContract flow.
- Opt-in live executor and judge can complete at least one small accepted flow.
- Secrets, raw provider payloads, raw transcripts, stdout/stderr bodies, and
  artifact bodies do not become durable task truth.
- Executor completion never grants acceptance.
- Judge uses the frozen contract, judge rubric, artifact refs, evidence refs,
  and hard-check refs.

## Phase 4: Unify Repair And Revision

Purpose: make repair and revision natural branches of the same PiWorkerCall
lifecycle.

Work:

- Repair path:
  - `JudgeReport(decision=repair)`;
  - `RepairBrief`;
  - `RepairTicket`;
  - `RepairExecutionDirective`;
  - `PiWorkerCall(role=repair_piworker)`.
- Revision path:
  - `JudgeReport(decision=revision_required)`;
  - `TaskRevisionRequest`;
  - `RevisionPendingRecord`;
  - `PiWorkerCall(role=revision_drafter_piworker)`;
  - revised `TaskContract`;
  - `RevisionAppliedRecord`.
- Ensure repair preserves the same contract hash.
- Ensure revision freezes explicit new task authority before continuing.

Acceptance:

- `accepted`, `repair`, `revision_required`, and `rejected` paths all have
  tests.
- Repair does not weaken or mutate the frozen contract.
- Revision produces explicit pending/applied records.
- Ledger replay can explain the path without reading Pi chat memory.

## Phase 5: Use SkillFoundry As The Product Dogfood

Purpose: prove the substrate through an external product integration.

Work:

- Keep all SkillFoundry semantics under `integrations/skillfoundry`.
- Compile SkillFoundry intent into:
  - `TaskContract`;
  - `WorkspacePolicy`;
  - `PermissionManifest`;
  - judge rubric refs or fragments;
  - product hard checks.
- Use faux runtime in default tests.
- Use live runtime only for explicit dogfood.
- Maintain a standalone product-shell example that programmers can build from
  docs without reading MissionForge source.

Acceptance:

- SkillFoundry integration tests pass.
- A standalone example can be written from docs and public primitives.
- Live dogfood reaches accepted, repair, revision_required, or rejected through
  the MissionForge boundary instead of failing on runtime plumbing.
- MissionForge core contains no SkillFoundry branches.

## Phase 6: Complete Programmer Documentation

Purpose: let programmers use MissionForge without reading source code.

Required docs:

- `GETTING_STARTED.md`: fastest runnable path.
- `USER_MANUAL.md`: full programmer manual.
- `PRIMITIVE_REFERENCE.md`: field-level primitive reference.
- `COOKBOOK.md`: common composition patterns.
- `MIGRATION_GUIDE.md`: MissionIR and legacy runtime to TaskContract path.
- `LIVE_RUNTIME_GUIDE.md`: faux/live provider setup, Codex current provider,
  secret redaction, and debugging.

Coverage:

- TaskContract compile result.
- Run-relative refs.
- Minimal executor and judge.
- Hard-check status rules.
- Repair and revision flows.
- Live Pi Agent configuration.
- SkillFoundry integration pattern.

Acceptance:

- Authoritative docs tests cover the core usage promises.
- A manual-only standalone experiment can reproduce a product shell.
- Docs clearly distinguish primary path from compatibility path.

## Phase 7: Legacy Cleanup And Boundary Freezing

Purpose: stop legacy surfaces from pulling the system back toward the old
architecture.

Work:

- Mark MissionIR, old runtime, steering, and metric dict surfaces as
  compatibility unless a change intentionally preserves them.
- Stop adding features to legacy paths.
- Remove or isolate stale benchmark/demo references from the active product
  lane.
- Update import-boundary and product-boundary tests.

Acceptance:

- New features land only in the TaskContract/PiWorker path.
- Legacy tests either pass as compatibility checks or have explicit migration
  records.
- README does not present legacy runtime as the default conceptual API.

## Phase 8: Release Candidate

Purpose: produce a version that external programmers can try.

Acceptance checklist:

- `./scripts/validate.sh` passes.
- `./scripts/validate_integrations.sh skillfoundry` passes.
- Faux TaskContract flow reaches accepted.
- Opt-in live smoke reaches accepted.
- SkillFoundry dogfood produces a refs-first report.
- Programmer docs support a standalone product shell.
- Public API boundary is stable.
- Product semantics stay outside `src/missionforge`.

## Immediate Priorities

Do these first:

1. Fix and test Pi Agent live runtime run-root, `attempts/`, evidence refs, and
   permission-manifest alignment.
2. Narrow the public API and documentation around the TaskContract/PiWorker
   default path.
3. Run SkillFoundry through faux and live dogfood, then convert any runtime
   boundary failures into tests.

## Current Engineering State

Recorded on 2026-06-12 for branch `agentic-runtime-upgrade`.

Baseline validation:

- `MISSIONFORGE_SKIP_NPM_CI=1 ./scripts/validate.sh` passed before this
  cutover work: 496 Python tests passed, 4 skipped; Node runtime tests passed;
  whitespace check passed.
- `./scripts/validate_integrations.sh skillfoundry` passed before this cutover
  work: 106 tests passed, 1 skipped.

Phase 3 progress:

- Fixed the default TaskContract flow run-root alignment for Pi-backed executor
  and judge nodes. When invoked by `AgenticFlowRunner`, Pi runtime artifacts are
  written under the active run workspace instead of the outer repository
  workspace.
- `attempts/<call_id>/...` remains the full Pi runtime audit plane.
- `AgentExecutionReport` no longer exposes runtime-owned `attempts/...` refs in
  `changed_refs`, `evidence_refs`, or `metric_refs`.
- Runtime-owned call-result and metrics projections are written under
  `reports/piworker_runtime/<call_id>/...` and are validated by the outer flow
  as existing runtime evidence, not as worker-written refs.
- Executors are denied direct writes to `reports/piworker_runtime`, so worker
  code cannot forge the runtime projection.
- SkillFoundry TaskContract permissions no longer need to grant product worker
  write access to `attempts`; faux Pi runtime dogfood still records attempts on
  disk while passing the outer permission boundary.
- The PI Agent runtime sidecar now treats missing expected outputs as a bounded
  retry condition. After a model turn returns without producing required refs,
  the runtime issues a refs-only follow-up prompt inside the same turn budget
  and still lets the output writer decide success or failure from files on
  disk.
- Judge PiWorker calls now expose exact judge-authored writable refs for the
  judge report, optional rationale, repair brief, and revision request. They do
  not grant directory-level write access to runtime-owned reports, packets,
  contracts, hard checks, or evidence.
- Repair and revision-drafter helper calls now persist `PiWorkerCallResult`
  under `attempts/<call_id>/piworker_call_result.json`, keeping those Phase 4
  continuations inspectable through the same attempt audit plane.
- When supplied a decision ledger ref, those helpers append refs-only
  `repair_execution_recorded` and `revision_draft_recorded` entries with
  content hashes, so replay can explain repair/revision continuations without
  reading Pi chat memory.
- `build_repair_rejudge_packet(...)` now bridges a completed
  `repair_piworker` call result back into the independent judge lane. It writes
  the same-contract repair `AgentExecutionReport` at the directive's
  `execution_report_ref`, writes a fresh `JudgePacket` under
  `packets/repairs/{ticket_id}/judge_packet.json`, and deliberately stops
  before acceptance.
- `load_revision_draft_contract(...)` now validates a
  `revision_drafter_piworker` output as a revised `TaskContract` proposal
  bound to the `RevisionPendingRecord`. It proves the draft came from the
  revision-drafter role, completed, appears in `output_refs`, and changes the
  contract hash, while still requiring an explicit authority decision before
  `apply_task_contract_revision(...)`.
- `build_revision_execution_directive(...)` now bridges an applied
  `RevisionAppliedRecord` to the first revised-contract execution entry. It
  content-binds the applied record, pending record, revision decision, contract
  revision, revised `TaskContract`, `WorkspacePolicy`, and
  `PermissionManifest`; then writes a revised `WorkerBrief`,
  `AgentExecutionPacket`, and refs-only directive under
  `revisions/{request_id}/...` without mutating the previous frozen contract or
  granting acceptance.
- `build_revision_rejudge_packet(...)` now bridges a revised-contract executor
  `PiWorkerCallResult` back into the independent judge lane. It writes the
  revised `AgentExecutionReport`, projects a revised `JudgeRubric`, and writes
  a `JudgePacket` under `revisions/{request_id}/...`; acceptance still requires
  a separate judge result.
- `build_revision_judge_result(...)` now records the revised independent judge
  result under the revised contract hash. It validates the directive, applied
  revision, revised execution report, judge packet, and judge report; emits a
  revised final package only when the independent judge accepts; and appends a
  refs-only ledger sequence where `revision_applied` is the only allowed
  contract-hash transition.
- `docs/API_BOUNDARY.md` now names the primary TaskContract/PiWorker kernel
  surface first and demotes MissionIR, older runtime, work-unit, steering, and
  metric-dict surfaces to explicit legacy submodule compatibility guidance.
- The package root no longer re-exports MissionIR, MissionRuntime,
  RuntimeEngine, WorkUnitContract, old harness, old revision, or old steering
  runtime symbols. Legacy tests import those compatibility symbols from their
  owning submodules.
- `tests.test_public_api_boundary` now has an explicit primary kernel export
  test so public imports stay aligned with the documentation.

Phase 5 progress:

- SkillFoundry now exposes `run_skillfoundry_task_contract_bundle_build(...)`,
  a TaskContract-native product facade that compiles SkillFoundry intent into
  TaskContract refs, runs the MissionForge executor/judge boundary, validates
  package artifacts, evaluates the product-grade gate, registers the bundle,
  and writes refs-only product reports. The older
  `run_skillfoundry_bundle_build(...)` remains the MissionIR compatibility
  facade.
- `run_skillfoundry_live_dogfood(...)` now defaults to that TaskContract-native
  product facade when no custom build runner is supplied.
- The SkillFoundry live dogfood classifier now inspects TaskContract-native run
  workspaces under `runs/{bundle_id}/...`, preserves run-prefixed refs in its
  refs-only report, and classifies invalid judge artifacts as worker-execution
  boundary failures instead of generic product-contract failures.
- The TaskContract-native SkillFoundry facade has focused test coverage proving
  a supplied `PiAgentRuntimeConfig` reaches both the default PiWorker executor
  and default PiWorker judge calls.
- SkillFoundry TaskContract compilation now writes product-owned manifest
  template and manifest artifact-contract refs under `product_contract/`, and
  the frozen TaskContract exposes those refs to PiWorker through source,
  hard-constraint, and semantic-acceptance refs. This absorbs the existing
  MissionIR-path manifest contract into the TaskContract path without moving
  SkillFoundry semantics into `src/missionforge`.
- Opt-in SkillFoundry live dogfood reached the SkillFoundry product-grade gate
  through the TaskContract-native facade on 2026-06-12. The persistent run at
  `/tmp/mf-skillfoundry-live-s69u2v18` produced all required package refs and a
  refs-first dogfood report with `outcome_category=product_grade`,
  `run_status=classified_failure`, and issue codes:
  `bundle_validator:SF-PROMPT-MANIFEST-SCHEMA`,
  `bundle_validator:SF-PROMPT-ENTRYPOINT`, and
  `bundle_validator:SF-PROMPT-REFS-SAFE`. This is product artifact quality
  evidence, not runtime plumbing failure.
- After the manifest-template change, the persistent live workspace at
  `/tmp/mf-skillfoundry-live-template-3kb7srux` produced package refs whose
  manifest passes SkillFoundry bundle validation. Replaying the product facade
  tail from recorded refs produced `product_grade=true` and
  `registry=product_grade_registered`.
- A later fresh live dogfood run at
  `/tmp/mf-skillfoundry-live-template2-zfswgw1e` hit provider quota after
  writing package refs. The dogfood classifier now reports this as
  `outcome_category=worker_execution` with
  `piworker_runtime_status:failed`, citing attempt refs instead of misclassifying
  worker-written `reports/execution_report.json` as an authoritative
  MissionForge execution report.
- A fresh live dogfood run at `/tmp/mf-skillfoundry-live-xxxbuoj9` completed
  through the TaskContract-native facade with `outcome_category=completed`,
  `run_status=completed`, `product_grade_registered`, bundle validation
  passed, product grade true, registry status `product_grade_registered`, and
  refs-only evidence pointing to the judge report, decision ledger, and final
  package. Replaying `runs/demo-skill/ledgers/decision_ledger.jsonl` returned
  `status=accepted` and the three package refs accepted by the independent
  judge.

Focused validation after this progress:

- `PYTHONPATH=src:tests python3 -m unittest tests.test_agentic_flow` passed:
  16 tests, 1 skipped.
- `PYTHONPATH=src python3 -m unittest tests.test_pi_agent_runtime_adapter`
  passed: 17 tests, 1 skipped.
- `PYTHONPATH=src python3 -m unittest tests.test_piworker_runtime_boundary
  tests.test_piworker_call` passed: 17 tests.
- `PYTHONPATH=src python3 -m unittest tests.test_piworker_runtime_boundary`
  passed: 5 tests.
- `PYTHONPATH=src python3 -m unittest tests.test_agentic_ledger
  tests.test_piworker_runtime_boundary` passed: 10 tests.
- `PYTHONPATH=src python3 -m unittest tests.test_agentic_repair_controller`
  passed after the repair rejudge, revision draft, and revision execution
  directive/rejudge helpers: 27 tests.
- `PYTHONPATH=src python3 -m unittest tests.test_agentic_repair_controller
  tests.test_agentic_ledger` passed after revised judge result handling:
  36 tests.
- `PYTHONPATH=src:integrations/skillfoundry/src:integrations/skillfoundry/tests
  python3 -m unittest integrations/skillfoundry/tests/test_skillfoundry_live_dogfood.py
  integrations/skillfoundry/tests/test_task_contract_compiler.py
  integrations/skillfoundry/tests/test_skillfoundry_runtime_facade.py` passed
  after the TaskContract-native SkillFoundry facade, manifest-template, and
  dogfood classifier fixes: 24 tests, 1 skipped.
- `PYTHONPATH=src python3 -m unittest tests.test_piworker_call
  tests.test_piworker_runtime_boundary tests.test_agentic_ledger
  tests.test_public_api_boundary` passed after the repair rejudge bridge:
  25 tests.
- `PYTHONPATH=src python3 -m unittest tests.test_pi_agent_runtime_adapter
  tests.test_agentic_flow tests.test_piworker_runtime_boundary
  tests.test_piworker_call tests.test_public_api_boundary` passed: 52 tests,
  1 skipped.
- `PYTHONPATH=src python3 -m unittest tests.test_public_api_boundary
  tests.test_agentic_ledger tests.test_agentic_flow tests.test_piworker_call
  tests.test_piworker_runtime_boundary
  tests.test_standalone_product_shell_example` passed after revised judge
  result handling, public API boundary tightening, and standalone shell
  evidence:
  44 tests, 1 skipped.
- `MISSIONFORGE_SKIP_NPM_CI=1 ./scripts/validate.sh` passed after the repair
  rejudge, revision draft, revision execution directive/rejudge, and revised
  judge result bridges:
  8 Node runtime tests; 512 Python tests, 5 skipped; whitespace check passed.
- `./scripts/validate_integrations.sh skillfoundry` passed after the repair
  rejudge, revision draft, revision execution directive/rejudge, revised judge
  result, and SkillFoundry TaskContract facade work:
  112 tests, 1 skipped.
- Opt-in live TaskContract smoke is now defined in
  `tests.test_agentic_flow.AgenticFlowTests.test_live_codex_current_default_task_contract_flow_accepts`
  and passed again with `MISSIONFORGE_PI_AGENT_LIVE_SMOKE=1`,
  `MISSIONFORGE_PI_AGENT_LIVE_TIMEOUT_SECONDS=420`, and
  `provider_config_source="codex_current"` on 2026-06-12:
  1 test passed in 132.875 seconds.
- Opt-in SkillFoundry live dogfood passed the unittest harness with
  `MISSIONFORGE_SKILLFOUNDRY_LIVE_DOGFOOD=1`,
  `MISSIONFORGE_SKILLFOUNDRY_LIVE_TIMEOUT_SECONDS=420`, and
  `provider_config_source="codex_current"` on 2026-06-12.
- A direct persistent SkillFoundry live dogfood run produced a refs-first
  classified report at `/tmp/mf-skillfoundry-live-s69u2v18`.
- A direct persistent SkillFoundry live package after the manifest-template
  change passed product validation when replayed from refs at
  `/tmp/mf-skillfoundry-live-template-3kb7srux`.
- The latest fresh live dogfood run completed at
  `/tmp/mf-skillfoundry-live-xxxbuoj9` with:
  - `outcome_category=completed`
  - `run_status=completed`
  - `issue_codes=["product_grade_registered"]`
  - `product_grade=true`
  - `registry status=product_grade_registered`
  - MissionForge ledger replay status `accepted`
- Manual-only standalone product shell evidence now exists:
  `examples/standalone_product_shell.py` runs from public primitives and
  reaches `status=accepted` plus `replay_status=accepted`; its focused test is
  `tests.test_standalone_product_shell_example`.

Release-candidate audit completed on 2026-06-12:

- The standalone product-shell example and documentation checkpoint was
  committed and pushed to `origin/agentic-runtime-upgrade`.
- Local validation passed after the checkpoint:
  - `MISSIONFORGE_SKIP_NPM_CI=1 ./scripts/validate.sh`
  - Node runtime: 8 tests passed.
  - Python: 512 tests passed, 5 skipped.
  - whitespace check passed.
- SkillFoundry integration validation passed:
  - `./scripts/validate_integrations.sh skillfoundry`
  - 112 tests passed, 1 skipped.
- Core PiWorker/flow/ledger/public API focused suite passed:
  - 44 tests passed, 1 skipped.
- Manual standalone product-shell run passed:
  - `PYTHONPATH=src python3 examples/standalone_product_shell.py /tmp/mf-standalone-rc-audit`
  - `status=accepted`
  - `replay_status=accepted`
- `git diff --check` passed.
- `git status --branch --short` showed `agentic-runtime-upgrade` aligned with
  `origin/agentic-runtime-upgrade`.
- Product-boundary source search found no SkillFoundry, Codexarium, benchmark,
  finance, customer, or demo-specific branches in `src/missionforge`; the only
  product-related core match was the generic `product_gate.py` status
  vocabulary.
