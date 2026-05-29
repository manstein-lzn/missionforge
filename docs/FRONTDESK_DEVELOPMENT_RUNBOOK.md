# FrontDesk Development Runbook

Last updated: 2026-05-29

Status: `direct-start implementation runbook`

## Purpose

This runbook is the direct execution plan for completing MissionForge
FrontDesk from the current repository state.

Use this document when the goal is to start coding immediately without
re-deriving the architecture. The authoritative design remains
`docs/modules/frontdesk.md`; the phase-level plan remains
`docs/FRONTDESK_IMPLEMENTATION_GUIDE.md`. This runbook adds the concrete
current-state sequence, patch targets, acceptance commands, and failure
handling.

## Current Position

As of 2026-05-29, the repository already contains the main FrontDesk package
and tests for phases 1 through 5:

- `src/missionforge/frontdesk/schema.py`
- `src/missionforge/frontdesk/state.py`
- `src/missionforge/frontdesk/workspace.py`
- `src/missionforge/frontdesk/compiler.py`
- `src/missionforge/frontdesk/freeze_gate.py`
- `src/missionforge/frontdesk/service.py`
- `src/missionforge/frontdesk/elicitor.py`
- `src/missionforge/frontdesk/planner.py`
- `src/missionforge/frontdesk/auditor.py`
- `src/missionforge/frontdesk/cli.py`
- `tests/test_frontdesk_*.py`

The immediate open work is:

1. Finish Phase 5 CLI hardening.
2. Implement Phase 6 runtime feedback.
3. Implement Phase 7 SkillFoundry dogfood.
4. Run final integration gates.
5. Update documentation with verification evidence.

Do not restart from Phase 1 unless the current implementation is intentionally
discarded.

## Non-Negotiable Constraints

These constraints apply to every step in this runbook:

- FrontDesk is generic MissionIR authoring, not a SkillFoundry adapter.
- Product-specific code stays under `integrations/*`.
- No runtime branch may key on FrontDesk, SkillFoundry, Codexarium, product
  names, mission names, or benchmark names.
- LLM nodes may draft, recommend, and audit only.
- Deterministic code owns schema validation, profile validation, approval,
  freeze, MissionIR validation, and runtime handoff.
- Raw chat, prompts, provider payloads, transcripts, secrets, and credentials
  must not enter runtime-facing MissionIR or frozen contracts.
- Default tests must stay deterministic and offline.
- PiWorker remains the LLM worker direction. Do not add a second production
  worker abstraction.
- Frozen mission changes must go through revision authority, not silent
  FrontDesk mutation.

## Worktree Discipline

The working tree may contain unrelated changes. Before editing, inspect the
files you will touch and preserve unrelated user work.

Recommended status check:

```bash
git status --short
```

Use `apply_patch` for manual edits. Avoid broad formatting across unrelated
files.

## Phase 5 Closeout: CLI Hardening

### Goal

Make the FrontDesk CLI pass its contract tests and keep command results
operator-safe.

### Files To Edit

- `src/missionforge/frontdesk/service.py`
- `src/missionforge/frontdesk/cli.py` only if command refs need adjustment
- `tests/test_frontdesk_cli.py` only if assertions need to follow the intended
  public shape

### Known Failures

Run:

```bash
PYTHONPATH=src python3 -m unittest tests/test_frontdesk_cli.py
```

Expected current failures before this closeout:

- `freeze` before approval returns `missing_state`; it should return
  `invalid_input`.
- `inspect` places a dict under data key `refs`; the command envelope treats
  keys ending in `refs` as list-of-ref fields, so inspect fails validation.

### Required Patch

In `FrontDeskInspectResult.to_dict()`, do not emit a dict under the key
`refs`. Use a non-ref-suffixed map key:

```python
def to_dict(self) -> dict[str, Any]:
    return {
        "session_id": self.session_id,
        "status": self.status,
        "next_action": self.next_action,
        "artifact_ref_map": dict(self.refs),
        "warnings": list(self.warnings),
    }
```

Keep the internal `FrontDeskInspectResult.refs` property so CLI command refs can
still be returned as a list:

```python
return result.to_dict(), [result.refs["session_ref"]]
```

In `FrontDesk.freeze()`, explicitly reject missing approval before reading the
approval artifact:

```python
if not self.workspace.exists(AUTHORING_APPROVAL_REF):
    raise ContractValidationError("FrontDesk freeze requires authoring approval")
```

Import `ContractValidationError` from `missionforge.contracts` in
`service.py`.

### Acceptance

Run:

```bash
PYTHONPATH=src python3 -m unittest \
  tests/test_frontdesk_cli.py \
  tests/test_operator_cli_contracts.py \
  tests/test_operator_cli_run.py
```
If this fails because unrelated operator tests changed, isolate the failure and
record whether the regression is in FrontDesk or pre-existing operator surface.

## Phase 6: Runtime Feedback

### Goal

Let FrontDesk interpret runtime and verification failures and recommend the
next authoring action without bypassing runtime authority.

### Files To Add

- `src/missionforge/frontdesk/runtime_feedback.py`
- `tests/test_frontdesk_runtime_feedback.py`

### Files To Update

- `src/missionforge/frontdesk/__init__.py`
- `src/missionforge/__init__.py` only for stable generic exports
- `docs/FRONTDESK_IMPLEMENTATION_GUIDE.md` after verification

### Contracts To Implement

Add a refs-first feedback contract:

```python
@dataclass(frozen=True)
class RuntimeFeedbackRecommendation:
    session_id: str
    source_kind: RuntimeFeedbackSourceKind
    recommended_action: RuntimeFeedbackAction
    reason: str
    authority_required: AuthorityRequirement
    source_refs: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    proposal_refs: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)
    can_auto_approve_revision: bool = False
```

Suggested enums:

```text
RuntimeFeedbackSourceKind:
  mission_result
  verification_result
  verifier_failure
  contract_mismatch
  unsupported_validator
  revision_diagnosis

RuntimeFeedbackAction:
  repair
  resume
  mission_revision
  redesign
  profile_extension
  validator_extension
  human_review
  stop
```

Every contract must implement `from_dict()`, `to_dict()`, and `validate()`.

### Deterministic Routing Rules

Implement deterministic helpers before any LLM-assisted interpretation:

- A failed `VerificationResult` with failed validators routes to `repair`.
- A contract mismatch routes to `mission_revision`.
- An unsupported validator routes to `validator_extension` or
  `profile_extension`.
- A user-authority or human-review authority requirement routes to
  `human_review`.
- A completed/passed result routes to `stop` or `resume` only when there is a
  clear next-step signal.
- `can_auto_approve_revision` must always be `False`.

### Revision Boundary

FrontDesk may draft a `MissionRevisionRequest` only as a proposal artifact.
Existing revision authority must still decide acceptance through
`MissionRevisionWorkflow`.

Do not call revision `apply()` from FrontDesk feedback code.

### Tests

Add tests proving:

- verifier failure produces repair guidance;
- contract mismatch produces mission revision guidance;
- unsupported validator produces validator/profile extension guidance;
- feedback never auto-approves revision;
- user-reserved authority remains user-reserved;
- feedback output is refs-first and does not embed raw transcript or provider
  output.

### Acceptance

Run:

```bash
PYTHONPATH=src python3 -m unittest tests/test_frontdesk_runtime_feedback.py
```

Then run:

```bash
PYTHONPATH=src python3 -m unittest \
  tests/test_mission_revision_contracts.py \
  tests/test_mission_revision_workflow.py \
  tests/test_revision_authority_boundaries.py
```

## Phase 7: SkillFoundry Dogfood

### Goal

Prove FrontDesk can author a real downstream product mission while keeping
MissionForge core generic.

### Files To Add Or Update

- `integrations/skillfoundry/tests/test_skillfoundry_frontdesk_flow.py`
- `integrations/skillfoundry/docs/skillfoundry_integration.md`
- `docs/modules/frontdesk.md` with dogfood evidence

Do not add SkillFoundry-specific branches under `src/missionforge`.

### Scenario

Build one deterministic SkillFoundry authoring flow:

1. Create a FrontDesk session in a temp workspace.
2. Provide a SkillFoundry-style natural-language request.
3. Use SkillFoundry integration code or ProfilePack data outside core to supply
   product semantics.
4. Draft FrontDesk artifacts.
5. Approve and freeze through the normal MissionForge path.
6. Assert the generated MissionIR has the expected profiles, validators,
   outputs, and frozen contract refs.
7. Assert MissionForge core imports no SkillFoundry or Codexarium modules.

### Product Boundary Check

Use existing import-boundary tests and add a focused assertion if needed:

```bash
PYTHONPATH=src python3 -m unittest tests/test_adapter_import_boundaries.py
```

The test must prove product logic lives under `integrations/skillfoundry`, not
under `src/missionforge`.

### Acceptance

Run:

```bash
./scripts/validate_integrations.sh skillfoundry
PYTHONPATH=src python3 -m unittest tests/test_adapter_import_boundaries.py
```

If live dogfood exists, it must be opt-in and skipped by default.

## Final Verification Gate

After phases 5 through 7 pass individually, run the FrontDesk-focused gate:

```bash
PYTHONPATH=src python3 -m unittest \
  tests/test_frontdesk_schema.py \
  tests/test_frontdesk_state.py \
  tests/test_frontdesk_workspace.py \
  tests/test_frontdesk_compiler.py \
  tests/test_frontdesk_freeze_gate.py \
  tests/test_frontdesk_profile_integration.py \
  tests/test_frontdesk_service.py \
  tests/test_frontdesk_elicitor.py \
  tests/test_frontdesk_planner.py \
  tests/test_frontdesk_auditor.py \
  tests/test_frontdesk_llm_boundaries.py \
  tests/test_frontdesk_cli.py \
  tests/test_frontdesk_runtime_feedback.py
```

Run shared contract gates:

```bash
PYTHONPATH=src python3 -m unittest \
  tests/test_adapter_import_boundaries.py \
  tests/test_profiles.py \
  tests/test_freeze.py \
  tests/test_public_api_boundary.py
```

Run integration and whitespace gates:

```bash
./scripts/validate_integrations.sh skillfoundry
git diff --check
```

If FrontDesk changes PiWorker-backed authoring or Node runtime code, also run:

```bash
cd workers/pi-agent-runtime && npm test
```

Before claiming completion, prefer the full test suite:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
```

## Documentation Closeout

After implementation and verification, update:

- `docs/FRONTDESK_IMPLEMENTATION_GUIDE.md`
- `docs/modules/frontdesk.md`
- `docs/API_BOUNDARY.md` if root exports changed
- `docs/IMPLEMENTATION_STATUS_AND_NEXT_PHASES.md` if it tracks the active
  roadmap

The docs must include:

- completed phases;
- verification commands and outcomes;
- remaining opt-in live dogfood, if any;
- known risks or deferred work;
- confirmation that no product-specific core branches were added.

## Completion Definition

FrontDesk can be called complete only when:

- CLI closeout passes;
- runtime feedback tests pass;
- SkillFoundry dogfood passes;
- FrontDesk-focused tests pass;
- shared contract/import/profile/freeze tests pass;
- `git diff --check` passes;
- docs record evidence;
- no runtime or core product branch violates the boundary rules.

## If A Gate Fails

Use this decision table:

```text
Schema or contract test fails:
  fix deterministic schema/state/compiler code first.

CLI envelope validation fails:
  inspect command result data keys and refs; avoid dict values under keys
  ending in "ref" or "refs" unless the command envelope expects them.

Profile validation fails:
  fix ProfileRegistry/ProfilePack wiring; do not hard-code product behavior in
  core runtime.

Runtime feedback tries to approve or apply revisions:
  remove the authority bypass and route through MissionRevisionWorkflow.

SkillFoundry dogfood requires core branches:
  move product semantics into integration code, ProfilePacks, validators, or
  evidence refs.

Full suite fails outside FrontDesk:
  isolate whether the failure is caused by this work. Do not revert unrelated
  user changes.
```

## First Patch To Apply Now

Start with this exact work unit:

```text
Finish FrontDesk Phase 5 CLI closeout.

Patch FrontDeskInspectResult.to_dict() so inspect data uses
"artifact_ref_map" instead of "refs". Patch FrontDesk.freeze() so missing
frontdesk/authoring_approval.json raises ContractValidationError before file
read. Run:

PYTHONPATH=src python3 -m unittest \
  tests/test_frontdesk_cli.py \
  tests/test_operator_cli_contracts.py \
  tests/test_operator_cli_run.py
```
