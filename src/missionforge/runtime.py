"""Deterministic MissionForge runtime vertical slice."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

from .contracts import AdaptiveDecision, ContractValidationError, VerificationStatus, require_int_at_least, stable_json_hash
from .evidence_store import EvidenceLedger, InMemoryEvidenceStore
from .freeze import FrozenMissionContract
from .harness import ProposalValidator, WorkUnitCompiler, WorkUnitHarness
from .ir import MissionIR
from .review import ReviewPacket, ReviewerDecision
from .runtime_attempts import RuntimeAttemptRunner
from .runtime_contract import (
    ActiveMissionContract,
    RuntimeContractView,
    initialize_active_contract,
    load_active_contract,
    runtime_contract_view,
)
from .runtime_state_writer import RuntimeStateWriter
from .state import (
    SUPPORTED_RESUME_BOUNDARY,
    MissionRunState,
    RuntimeAttempt,
    inspect_runtime,
    load_mission_run,
    load_runtime_attempts,
    mission_run_id_for,
    mission_run_refs,
)
from .steering import ObservationSignal, StateCorrection, SteeringContext, SteeringProposal
from .steering_store import SteeringArtifactStore, steering_refs_for_iteration
from .verification import VerificationSpec, ValidatorSpec
from .verifier import Verifier


@dataclass
class RuntimeEngine:
    """Compose freeze, harness, fake worker, and verifier into one run."""

    workspace: str | Path = "."
    max_attempts: int = 1
    worker: Any | None = None
    evidence_store: EvidenceLedger = field(default_factory=InMemoryEvidenceStore)
    steering_provider: Any | None = None
    observation_interpreter: Any | None = None
    reviewer_provider: Any | None = None
    steering_mode: str = "deterministic"

    def inspect(self, mission_run_id: str | None = None) -> dict[str, Any]:
        return inspect_runtime(self.workspace, mission_run_id)

    def resume(self, mission: MissionIR, *, follow_up_prompt: str = "Resume from the latest completed turn."):
        run = load_mission_run(self.workspace, mission_run_id_for(mission.mission_id))
        if run.latest_safe_point is None:
            raise ContractValidationError("runtime resume requires a latest safe point")
        if run.latest_safe_point.kind != SUPPORTED_RESUME_BOUNDARY:
            raise ContractValidationError(f"unsupported resume boundary: {run.latest_safe_point.kind}")
        resume_worker = _resume_worker(
            self.worker,
            savepoint_ref=run.latest_safe_point.savepoint_ref,
            session_ref=run.latest_safe_point.session_ref,
            events_ref=run.latest_safe_point.events_ref,
            follow_up_prompt=follow_up_prompt,
        )
        if resume_worker is None:
            raise ContractValidationError("runtime worker does not support resume")
        return RuntimeEngine(
            workspace=self.workspace,
            max_attempts=self.max_attempts,
            worker=resume_worker,
            evidence_store=self.evidence_store,
            steering_provider=self.steering_provider,
            observation_interpreter=self.observation_interpreter,
            reviewer_provider=self.reviewer_provider,
            steering_mode=self.steering_mode,
        )._run(mission, initial_attempt_kind="resume", initial_decision="resume")

    def run(self, mission: MissionIR):
        return self._run(mission, initial_attempt_kind="initial", initial_decision="continue")

    def _run(self, mission: MissionIR, *, initial_attempt_kind: str, initial_decision: str):
        mission.validate()
        require_int_at_least(self.max_attempts, "runtime.max_attempts", 1)
        if self.steering_mode not in {"deterministic", "proposal"}:
            raise ContractValidationError("runtime.steering_mode must be deterministic or proposal")
        root = Path(self.workspace)
        root.mkdir(parents=True, exist_ok=True)
        attempt_runner = RuntimeAttemptRunner()
        state_writer = RuntimeStateWriter()
        mission_run_id = mission_run_id_for(mission.mission_id)
        refs = mission_run_refs(mission.mission_id)
        _resolve_workspace_ref(root, refs["run_dir"]).mkdir(parents=True, exist_ok=True)
        steering_store = SteeringArtifactStore(root)
        steering_artifact_refs: list[str] = []
        steering_metrics: dict[str, Any] = {
            "steering_mode": self.steering_mode,
            "proposal_count": 0,
            "accepted_proposal_count": 0,
            "rejected_proposal_count": 0,
            "observation_signal_count": 0,
            "review_packet_count": 0,
            "reviewer_decision_count": 0,
            "provider_failure_count": 0,
            "unsafe_proposal_rejection_count": 0,
        }
        previous_attempts = _previous_attempts(root, mission_run_id, initial_attempt_kind=initial_attempt_kind)

        active_contract = _active_contract_for_run(
            root=root,
            mission=mission,
            mission_run_id=mission_run_id,
            initial_attempt_kind=initial_attempt_kind,
        )
        frozen = active_contract.frozen_contract
        frozen_ref = active_contract.contract_ref
        contract_view = runtime_contract_view(frozen)
        required_artifacts = list(contract_view.required_artifacts)
        allowed_scopes = contract_view.allowed_write_scopes
        proposal = _initial_proposal(
            contract_view,
            iteration=len(previous_attempts) + 1,
            frozen_ref=frozen_ref,
            required_artifacts=required_artifacts,
            allowed_scopes=allowed_scopes,
        )
        context = _steering_context(
            mission_id=active_contract.mission_id,
            mission_run_id=mission_run_id,
            refs=refs,
            iteration=proposal.iteration,
            frozen=frozen,
            frozen_ref=frozen_ref,
            previous_attempts=previous_attempts,
            allowed_scopes=allowed_scopes,
            failed_constraint_ids=[],
            safe_summary="Initial mission dispatch.",
        )
        if self.steering_mode == "proposal":
            if self.steering_provider is None:
                raise ContractValidationError("runtime proposal mode requires a steering_provider")
            steering_artifact_refs.append(steering_store.write_context(context))
            try:
                proposal = _provider_next_proposal(self.steering_provider, context)
                proposal.validate()
                steering_metrics["proposal_count"] = 1
                steering_artifact_refs.append(steering_store.write_proposal(proposal))
            except Exception as exc:
                steering_metrics["provider_failure_count"] = 1
                raise ContractValidationError(f"steering provider failed: {exc}") from exc
        validator = ProposalValidator(available_refs={frozen_ref}, allowed_output_roots=allowed_scopes)
        harness = WorkUnitHarness(
            compiler=WorkUnitCompiler(mission_id=active_contract.mission_id, validator=validator),
            worker=self.worker,
            evidence_store=self.evidence_store,
        )
        dispatch = harness.dispatch(proposal, workspace=str(root))
        for entry in harness.decision_ledger:
            steering_artifact_refs.append(
                steering_store.append_decision(
                    mission_run_id=mission_run_id,
                    iteration=proposal.iteration,
                    decision=entry,
                )
            )
        if dispatch.validation.status.value == "accepted":
            steering_metrics["accepted_proposal_count"] = 1 if self.steering_mode == "proposal" else 0
        elif self.steering_mode == "proposal":
            steering_metrics["rejected_proposal_count"] = 1
            steering_metrics["unsafe_proposal_rejection_count"] = len(dispatch.validation.reasons)
        attempt_count = 1
        repair_attempted = False
        repair_exhausted = False
        retry_attempted = False
        retry_exhausted = False
        redesign_required = False
        resume_count = 1 if initial_attempt_kind == "resume" else 0
        if dispatch.validation.status.value != "accepted" or dispatch.work_unit is None or dispatch.execution_report is None:
            redesign_required = True
            state = MissionRunState(
                mission_id=active_contract.mission_id,
                status="failed",
                contract_hash=frozen.contract_hash,
                latest_decision="proposal_rejected",
            )
            result = _result(
                mission_id=active_contract.mission_id,
                status="failed",
                frozen=frozen,
                state=MissionRunState(
                    mission_id=active_contract.mission_id,
                    status="failed",
                    contract_hash=frozen.contract_hash,
                    latest_decision="proposal_rejected",
                ),
                evidence_refs=[],
                artifact_refs=[],
                failed_constraint_ids=[constraint.constraint_id for constraint in contract_view.constraints],
                metrics={
                    **steering_metrics,
                    "attempt_count": len(previous_attempts),
                    "repair_attempted": repair_attempted,
                    "repair_exhausted": repair_exhausted,
                    "retry_attempted": retry_attempted,
                    "retry_exhausted": retry_exhausted,
                    "redesign_required": redesign_required,
                    "resume_count": resume_count,
                    "latest_decision": "redesign",
                    "next_action": "redesign",
                    "verification_status": "proposal_rejected",
                    "validator_result_count": 0,
                    "failed_constraint_ids": [constraint.constraint_id for constraint in contract_view.constraints],
                    "proposal_status": dispatch.validation.status.value,
                    "proposal_rejection_count": len(dispatch.validation.reasons),
                    "steering_refs": _dedupe_refs(steering_artifact_refs),
                },
            )
            _write_runtime_state(
                state_writer=state_writer,
                root=root,
                mission_run_id=mission_run_id,
                mission_id=active_contract.mission_id,
                active_contract=active_contract,
                refs=refs,
                work_unit_id="WU-000001",
                attempt_records=[],
                status="failed",
                latest_decision="redesign",
                next_action="redesign",
                state=state,
                result=result,
                expected_artifacts=required_artifacts,
                report_refs=[],
                required_refs=_dedupe_refs([active_contract.contract_ref, *active_contract.revision_refs, *steering_artifact_refs]),
                metrics={
                    **steering_metrics,
                    "attempt_count": len(previous_attempts),
                    "repair_attempted": repair_attempted,
                    "repair_exhausted": repair_exhausted,
                    "retry_attempted": retry_attempted,
                    "retry_exhausted": retry_exhausted,
                    "redesign_required": redesign_required,
                    "resume_count": resume_count,
                    "latest_decision": "redesign",
                    "next_action": "redesign",
                    "verification_status": "proposal_rejected",
                    "validator_result_count": 0,
                    "failed_constraint_ids": [constraint.constraint_id for constraint in contract_view.constraints],
                    "steering_refs": _dedupe_refs(steering_artifact_refs),
                },
            )
            return result

        verification_spec = _verification_spec(contract_view, required_artifacts)
        verifier = Verifier(
            workspace=root,
            evidence_store=self.evidence_store,
            contract_hash=frozen.contract_hash,
        )
        verification = verifier.verify(verification_spec)
        reviewer_decision: ReviewerDecision | None = None
        review_packet_ref = ""
        if verification.status == VerificationStatus.REVIEW_REQUIRED and self.reviewer_provider is not None:
            review_packet = _review_packet(
                mission_run_id=mission_run_id,
                iteration=proposal.iteration,
                refs=refs,
                frozen_ref=frozen_ref,
                contract_hash=frozen.contract_hash,
                attempt_refs=[
                    dispatch.worker_result.execution_report_ref
                    if dispatch.worker_result is not None
                    else f"attempts/{dispatch.work_unit.work_unit_id}/pi_agent_execution_report.json"
                ],
                proposal_refs=[ref for ref in steering_artifact_refs if ref.endswith("/steering_proposal.json")],
                failed_constraint_ids=list(verification.failed_constraint_ids),
            )
            review_packet_ref = steering_store.write_review_packet(review_packet)
            steering_artifact_refs.append(review_packet_ref)
            steering_metrics["review_packet_count"] = 1
            reviewer_decision = _provider_review_decision(self.reviewer_provider, review_packet)
            reviewer_decision.validate_current(contract_hash=frozen.contract_hash)
            steering_artifact_refs.append(
                steering_store.write_reviewer_decision(
                    mission_run_id=mission_run_id,
                    iteration=proposal.iteration,
                    decision=reviewer_decision,
                )
            )
            steering_metrics["reviewer_decision_count"] = 1
            verification = verifier.verify(verification_spec, reviewer_decision=reviewer_decision)
        next_attempt_index = len(previous_attempts) + 1
        attempt_records = [
            _attempt_record(
                root=root,
                mission_run_id=mission_run_id,
                index=next_attempt_index,
                attempt_kind=initial_attempt_kind,
                decision=initial_decision,
                dispatch=dispatch,
                verification_status=verification.status.value,
                attempt_runner=attempt_runner,
            )
        ]
        if (
            verification.status == VerificationStatus.FAILED
            and self.max_attempts > attempt_count
            and dispatch.work_unit is not None
            and dispatch.execution_report is not None
        ):
            repair_worker = _repair_worker(
                self.worker,
                verification=verification,
                execution_report_ref=dispatch.worker_result.execution_report_ref if dispatch.worker_result else "",
            )
            if repair_worker is not None:
                repair_attempted = True
                attempt_count += 1
                next_attempt_index += 1
                repair_harness = WorkUnitHarness(
                    compiler=WorkUnitCompiler(mission_id=active_contract.mission_id, validator=validator),
                    worker=repair_worker,
                    evidence_store=self.evidence_store,
                )
                repair_dispatch = repair_harness.dispatch(_repair_proposal(proposal, verification), workspace=str(root))
                for entry in repair_harness.decision_ledger:
                    steering_artifact_refs.append(
                        steering_store.append_decision(
                            mission_run_id=mission_run_id,
                            iteration=entry.proposal_id.count("repair") + proposal.iteration,
                            decision=entry,
                        )
                    )
                if (
                    repair_dispatch.validation.status.value == "accepted"
                    and repair_dispatch.work_unit is not None
                    and repair_dispatch.execution_report is not None
                ):
                    dispatch = repair_dispatch
                    verification = verifier.verify(verification_spec)
                    attempt_records.append(
                        _attempt_record(
                            root=root,
                            mission_run_id=mission_run_id,
                            index=next_attempt_index,
                            attempt_kind="repair",
                            decision="repair",
                            dispatch=repair_dispatch,
                            verification_status=verification.status.value,
                            attempt_runner=attempt_runner,
                        )
                    )
                else:
                    repair_exhausted = True
            else:
                repair_exhausted = True
        elif verification.status == VerificationStatus.FAILED and self.max_attempts <= attempt_count:
            repair_exhausted = True
        if verification.status == VerificationStatus.UNSUPPORTED_VERIFICATION_SPEC:
            redesign_required = True

        artifact_refs = list(dispatch.execution_report.produced_artifacts)
        evidence_refs = _snapshot_evidence_ids(self.evidence_store)
        latest_decision = _latest_decision(verification.status.value, repair_attempted=repair_attempted, repair_exhausted=repair_exhausted, redesign_required=redesign_required)
        next_action = _next_action(verification.status.value, latest_decision=latest_decision, repair_exhausted=repair_exhausted)
        state = MissionRunState(
            mission_id=active_contract.mission_id,
            status=verification.status.value,
            contract_hash=frozen.contract_hash,
            work_unit_refs=[dispatch.validation.accepted_contract_ref] if dispatch.validation.accepted_contract_ref else [],
            evidence_refs=evidence_refs,
            artifact_refs=artifact_refs,
            failed_constraint_ids=list(verification.failed_constraint_ids),
            latest_decision=latest_decision,
        )
        result = _result(
            mission_id=active_contract.mission_id,
            status=verification.status.value,
            frozen=frozen,
            state=state,
            evidence_refs=evidence_refs,
            artifact_refs=artifact_refs,
            failed_constraint_ids=list(verification.failed_constraint_ids),
            metrics={
                **steering_metrics,
                "attempt_count": len(previous_attempts) + attempt_count,
                "repair_attempted": repair_attempted,
                "repair_exhausted": repair_exhausted,
                "retry_attempted": retry_attempted,
                "retry_exhausted": retry_exhausted,
                "redesign_required": redesign_required,
                "resume_count": resume_count,
                "latest_decision": latest_decision,
                "next_action": next_action,
                "contract_hash": frozen.contract_hash,
                "ledger_hash": self.evidence_store.snapshot().ledger_hash,
                "verification_status": verification.status.value,
                "validator_result_count": len(verification.validator_results),
                "failed_constraint_ids": list(verification.failed_constraint_ids),
                "steering_refs": _dedupe_refs(steering_artifact_refs),
                "review_packet_ref": review_packet_ref,
            },
        )
        observation_signal_ref = ""
        if self.observation_interpreter is not None:
            signal = _provider_observation_signal(
                self.observation_interpreter,
                _steering_context(
                    mission_id=active_contract.mission_id,
                    mission_run_id=mission_run_id,
                    refs=refs,
                    iteration=proposal.iteration,
                    frozen=frozen,
                    frozen_ref=frozen_ref,
                    previous_attempts=[*previous_attempts, *attempt_records],
                    allowed_scopes=allowed_scopes,
                    failed_constraint_ids=list(verification.failed_constraint_ids),
                    safe_summary=f"Latest verification status: {verification.status.value}.",
                ),
            )
            signal.validate()
            observation_signal_ref = steering_store.write_observation_signal(signal)
            steering_artifact_refs.append(observation_signal_ref)
            state_correction = StateCorrection(
                corrected_field="latest_observation_signal",
                source_ref=observation_signal_ref,
                trust_level=signal.trust_level,
                correction=signal.safe_summary,
            )
            state_correction_ref = steering_store.write_state_correction(
                mission_run_id=mission_run_id,
                iteration=proposal.iteration,
                correction=state_correction,
            )
            steering_artifact_refs.append(state_correction_ref)
            steering_metrics["observation_signal_count"] = 1
            result.metrics["observation_signal_count"] = 1
            result.metrics["observation_signal_ref"] = observation_signal_ref
            result.metrics["state_correction_ref"] = state_correction_ref
            result.metrics["steering_refs"] = _dedupe_refs(
                [*result.metrics.get("steering_refs", []), observation_signal_ref, state_correction_ref]
            )
        _write_runtime_state(
            state_writer=state_writer,
            root=root,
            mission_run_id=mission_run_id,
            mission_id=active_contract.mission_id,
            active_contract=active_contract,
            refs=refs,
            work_unit_id=dispatch.work_unit.work_unit_id,
            previous_attempts=previous_attempts,
            attempt_records=attempt_records,
            status=verification.status.value,
            latest_decision=latest_decision,
            next_action=next_action,
            state=state,
            result=result,
            expected_artifacts=required_artifacts,
            report_refs=[attempt.report_ref for attempt in attempt_records],
            required_refs=_dedupe_refs([
                active_contract.contract_ref,
                *active_contract.revision_refs,
                *[attempt.input_ref for attempt in attempt_records],
                *[attempt.output_ref for attempt in attempt_records],
                *[attempt.report_ref for attempt in attempt_records],
                *[attempt.savepoints_ref for attempt in attempt_records],
                *steering_artifact_refs,
            ]),
            metrics={**result.metrics, **steering_metrics, "observation_signal_ref": observation_signal_ref},
        )
        return result


def _previous_attempts(root: Path, mission_run_id: str, *, initial_attempt_kind: str) -> list[RuntimeAttempt]:
    if initial_attempt_kind != "resume":
        return []
    return load_runtime_attempts(root, mission_run_id)


def _active_contract_for_run(
    *,
    root: Path,
    mission: MissionIR,
    mission_run_id: str,
    initial_attempt_kind: str,
) -> ActiveMissionContract:
    if initial_attempt_kind == "resume":
        run = load_mission_run(root, mission_run_id)
        if run.mission_id != mission.mission_id:
            raise ContractValidationError("runtime resume mission_id does not match MissionRun")
        return load_active_contract(workspace=root, run=run)
    run_path = root / f"runs/{mission_run_id}/mission_run.json"
    if run_path.is_file():
        run = load_mission_run(root, mission_run_id)
        if run.mission_id != mission.mission_id:
            raise ContractValidationError("runtime run mission_id does not match MissionRun")
        return load_active_contract(workspace=root, run=run)
    return initialize_active_contract(workspace=root, mission=mission, mission_run_id=mission_run_id)


def _result(
    *,
    mission_id: str,
    status: str,
    frozen: FrozenMissionContract,
    state: MissionRunState,
    evidence_refs: list[str],
    artifact_refs: list[str],
    failed_constraint_ids: list[str],
    metrics: dict[str, Any],
):
    from .runner import MissionResult

    return MissionResult(
        mission_id=mission_id,
        status=status,
        evidence_refs=list(evidence_refs),
        artifact_refs=list(artifact_refs),
        failed_constraint_ids=list(failed_constraint_ids),
        metrics={
            **metrics,
            "contract_hash": frozen.contract_hash,
            "state_hash": stable_json_hash(state.to_dict()),
        },
    )


def _initial_proposal(
    contract_view: RuntimeContractView,
    *,
    iteration: int = 1,
    frozen_ref: str,
    required_artifacts: list[str],
    allowed_scopes: list[str],
) -> SteeringProposal:
    output_list = ", ".join(required_artifacts)
    artifact_contracts = _artifact_contract_instructions(contract_view.outputs)
    objective_parts = [
        contract_view.objective_summary,
        f"Write all required artifacts before stopping: {output_list}.",
    ]
    if artifact_contracts:
        objective_parts.append("Follow these artifact contracts: " + " ".join(artifact_contracts))
    return SteeringProposal(
        proposal_id="P-000001",
        mission_run_id=f"run-{contract_view.mission_id}",
        iteration=iteration,
        input_refs=[frozen_ref],
        recommended_route=AdaptiveDecision.CONTINUE,
        proposed_contract={
            "next_objective": " ".join(objective_parts),
            "allowed_scope": list(allowed_scopes),
            "visible_refs": [frozen_ref],
            "expected_outputs": list(required_artifacts),
            "exit_criteria": [
                f"All expected outputs exist: {output_list}.",
                *artifact_contracts,
                "MissionForge will run verification after worker output.",
            ],
            "stop_conditions": ["A halt control is active."],
        },
        rationale="Deterministic initial runtime proposal.",
        confidence=1.0,
    )


def _artifact_contract_instructions(outputs: dict[str, Any]) -> list[str]:
    contracts = outputs.get("artifact_contracts")
    if not isinstance(contracts, list):
        return []
    instructions: list[str] = []
    for index, item in enumerate(contracts, start=1):
        if not isinstance(item, dict):
            continue
        artifact_ref = item.get("artifact_ref")
        if not isinstance(artifact_ref, str) or not artifact_ref:
            continue
        parts = [f"Artifact {artifact_ref}:"]
        kind = item.get("kind")
        role = item.get("role")
        if isinstance(kind, str) and kind:
            parts.append(f"kind={kind}.")
        if isinstance(role, str) and role:
            parts.append(f"role={role}.")
        required_keys = item.get("required_keys")
        if isinstance(required_keys, list) and all(isinstance(key, str) and key for key in required_keys):
            parts.append(f"required JSON keys={', '.join(required_keys)}.")
        if item.get("forbidden_extra_keys") is True:
            parts.append("Do not add extra JSON keys.")
        field_contract = item.get("field_contract")
        if isinstance(field_contract, dict) and field_contract:
            parts.append(f"field contract={json.dumps(field_contract, sort_keys=True, separators=(',', ':'))}.")
        notes = item.get("notes")
        if isinstance(notes, list):
            safe_notes = [note for note in notes if isinstance(note, str) and note]
            if safe_notes:
                parts.append("Notes: " + " ".join(safe_notes))
        instructions.append(f"{index}. " + " ".join(parts))
    return instructions


def _repair_proposal(previous: SteeringProposal, verification) -> SteeringProposal:
    contract = dict(previous.proposed_contract)
    failures = _verification_failure_messages(verification)
    contract["next_objective"] = (
        f"Repair verifier failures for {previous.proposal_id}: "
        f"{'; '.join(failures) if failures else 'verifier failed'}"
    )
    contract["exit_criteria"] = _dedupe_refs([
        *list(contract.get("exit_criteria", [])),
        "Run verification after repair.",
    ])
    return SteeringProposal(
        proposal_id=f"{previous.proposal_id}-repair-001",
        mission_run_id=previous.mission_run_id,
        iteration=previous.iteration,
        input_refs=list(previous.input_refs),
        recommended_route=AdaptiveDecision.REPAIR,
        proposed_contract=contract,
        rationale="Verifier-driven bounded repair follow-up.",
        confidence=1.0,
    )


def _steering_context(
    *,
    mission_id: str,
    mission_run_id: str,
    refs: dict[str, str],
    iteration: int,
    frozen: FrozenMissionContract,
    frozen_ref: str,
    previous_attempts: list[RuntimeAttempt],
    allowed_scopes: list[str],
    failed_constraint_ids: list[str],
    safe_summary: str,
) -> SteeringContext:
    attempt_refs = [attempt.report_ref for attempt in previous_attempts]
    return SteeringContext(
        mission_run_id=mission_run_id,
        mission_id=mission_id,
        iteration=iteration,
        contract_ref=frozen_ref,
        contract_hash=frozen.contract_hash,
        mission_run_ref=refs["mission_run"],
        attempt_refs=attempt_refs,
        latest_attempt_ref=attempt_refs[-1] if attempt_refs else "",
        verification_refs=[],
        artifact_hygiene_ref=refs["artifact_hygiene"],
        failed_constraint_ids=list(failed_constraint_ids),
        allowed_output_roots=list(allowed_scopes),
        visible_refs=[frozen_ref],
        forbidden_actions=[
            "close_without_verifier",
            "expand_frozen_contract_authority",
            "write_outside_allowed_scope",
            "override_failed_executable_validator",
        ],
        authority_policy_ref="",
        safe_summary=safe_summary,
    )


def _provider_next_proposal(provider: Any, context: SteeringContext) -> SteeringProposal:
    try:
        proposal = provider.next_proposal(context)
    except TypeError:
        proposal = provider.next_proposal()
    if isinstance(proposal, SteeringProposal):
        return proposal
    if isinstance(proposal, dict):
        return SteeringProposal.from_dict(proposal)
    raise ContractValidationError("steering provider must return SteeringProposal or dict")


def _provider_observation_signal(provider: Any, context: SteeringContext) -> ObservationSignal:
    signal = provider.interpret_observation(context)
    if isinstance(signal, ObservationSignal):
        return signal
    if isinstance(signal, dict):
        return ObservationSignal.from_dict(signal)
    raise ContractValidationError("observation interpreter must return ObservationSignal or dict")


def _provider_review_decision(provider: Any, packet: ReviewPacket) -> ReviewerDecision:
    decision = provider.review(packet)
    if isinstance(decision, ReviewerDecision):
        return decision
    if isinstance(decision, dict):
        return ReviewerDecision.from_dict(decision)
    raise ContractValidationError("reviewer provider must return ReviewerDecision or dict")


def _review_packet(
    *,
    mission_run_id: str,
    iteration: int,
    refs: dict[str, str],
    frozen_ref: str,
    contract_hash: str,
    attempt_refs: list[str],
    proposal_refs: list[str],
    failed_constraint_ids: list[str],
) -> ReviewPacket:
    return ReviewPacket(
        review_packet_id=f"review-packet-{iteration:06d}",
        mission_run_id=mission_run_id,
        iteration=iteration,
        reason="Verifier routed to review_required.",
        contract_ref=frozen_ref,
        contract_hash=contract_hash,
        mission_run_ref=refs["mission_run"],
        attempt_refs=list(attempt_refs),
        verification_refs=[],
        proposal_refs=list(proposal_refs),
        failed_constraint_ids=list(failed_constraint_ids),
        questions=[
            "Can delegatable manual gates be approved for this run?",
            "Should the runtime continue, repair, redesign, stop, or escalate?",
        ],
        forbidden_decisions=[
            "override_failed_executable_validator",
            "close_without_verifier",
            "expand_frozen_contract_authority",
        ],
    )


def _repair_worker(worker: Any, *, verification, execution_report_ref: str):
    if not hasattr(worker, "with_repair"):
        return None
    failures = _verification_failure_messages(verification)
    failed_constraints = list(verification.failed_constraint_ids)
    if not failures and not failed_constraints:
        return None
    previous_output_ref = execution_report_ref or "attempts/WU-000001/pi_agent_execution_report.json"
    repair_prompt = _repair_prompt(failures=failures, failed_constraints=failed_constraints)
    return worker.with_repair(
        verifier_failures=failures,
        failed_constraints=failed_constraints,
        previous_output_ref=previous_output_ref,
        repair_prompt=repair_prompt,
    )


def _resume_worker(
    worker: Any,
    *,
    savepoint_ref: str,
    session_ref: str,
    events_ref: str,
    follow_up_prompt: str,
):
    if not hasattr(worker, "with_resume"):
        return None
    return worker.with_resume(
        savepoint_ref=savepoint_ref,
        session_ref=session_ref,
        events_ref=events_ref,
        follow_up_prompt=follow_up_prompt,
    )


def _verification_failure_messages(verification) -> list[str]:
    messages: list[str] = []
    for failure in verification.failed_constraints:
        if failure.message:
            messages.append(f"{failure.constraint_id}: {failure.message}")
        else:
            messages.append(f"{failure.constraint_id}: {failure.validator_id} failed")
    for result in verification.validator_results:
        if not result.passed and result.message:
            messages.append(f"{result.validator_id}: {result.message}")
    return _dedupe_refs(messages)


def _repair_prompt(*, failures: list[str], failed_constraints: list[str]) -> str:
    return "\n".join(
        [
            "Repair the expected outputs so the MissionForge verifier can pass.",
            f"Failed constraints: {', '.join(failed_constraints) if failed_constraints else '<none>'}",
            "Verifier failures:",
            *[f"- {failure}" for failure in failures],
            "Do not claim completion as acceptance; MissionForge will verify after repair.",
        ]
    )


def _verification_spec(contract_view: RuntimeContractView, required_artifacts: list[str]) -> VerificationSpec:
    manual_gates = list(contract_view.manual_gates)
    validators = list(contract_view.validators)
    if not validators:
        constraint_refs = [contract_view.constraints[0].constraint_id] if contract_view.constraints else []
        validators = [
            ValidatorSpec(
                validator_id=f"V-artifact-{index:03d}",
                constraint_refs=constraint_refs,
                type="file_exists",
                inputs={"path": artifact_ref},
            )
            for index, artifact_ref in enumerate(required_artifacts, start=1)
        ]
    return VerificationSpec(validators=validators, manual_gates=manual_gates)


def _write_json(root: Path, ref: str, payload: dict[str, Any]) -> str:
    path = _resolve_workspace_ref(root, ref)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return ref


def _append_jsonl(root: Path, ref: str, payloads: list[dict[str, Any]]) -> None:
    path = _resolve_workspace_ref(root, ref)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(payload, sort_keys=True) + "\n" for payload in payloads)
    path.write_text(text, encoding="utf-8")


def _snapshot_evidence_ids(evidence_store: EvidenceLedger) -> list[str]:
    return [record.evidence_id for record in evidence_store.snapshot().records]


def _dedupe_refs(refs: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for ref in refs:
        if not isinstance(ref, str) or not ref:
            continue
        if ref in seen:
            continue
        result.append(ref)
        seen.add(ref)
    return result


def _attempt_record(
    *,
    root: Path,
    mission_run_id: str,
    index: int,
    attempt_kind: str,
    decision: str,
    dispatch,
    verification_status: str,
    attempt_runner: RuntimeAttemptRunner,
) -> RuntimeAttempt:
    return attempt_runner.record_attempt(
        root=root,
        mission_run_id=mission_run_id,
        index=index,
        attempt_kind=attempt_kind,
        decision=decision,
        dispatch=dispatch,
        verification_status=verification_status,
    )


def _latest_decision(
    status: str,
    *,
    repair_attempted: bool,
    repair_exhausted: bool,
    redesign_required: bool,
) -> str:
    if status == VerificationStatus.COMPLETED_VERIFIED.value:
        return "complete"
    if redesign_required:
        return "redesign"
    if status == VerificationStatus.REVIEW_REQUIRED.value:
        return "review"
    if status == VerificationStatus.HUMAN_ACCEPTANCE_REQUIRED.value:
        return "escalate"
    if repair_attempted and repair_exhausted:
        return "stop"
    if repair_attempted:
        return "repair"
    if status == VerificationStatus.FAILED.value:
        return "repair"
    return "stop"


def _next_action(status: str, *, latest_decision: str, repair_exhausted: bool) -> str:
    if status == VerificationStatus.COMPLETED_VERIFIED.value:
        return "complete"
    if latest_decision == "review":
        return "await_review"
    if latest_decision == "redesign":
        return "redesign"
    if latest_decision == "repair" and not repair_exhausted:
        return "resume_repair"
    if latest_decision == "escalate":
        return "await_human_acceptance"
    return "inspect_failure"


def _write_runtime_state(
    *,
    state_writer: RuntimeStateWriter,
    root: Path,
    mission_run_id: str,
    mission_id: str,
    active_contract: ActiveMissionContract,
    refs: dict[str, str],
    work_unit_id: str,
    attempt_records: list[RuntimeAttempt],
    status: str,
    latest_decision: str,
    next_action: str,
    state: MissionRunState,
    result,
    expected_artifacts: list[str],
    report_refs: list[str],
    required_refs: list[str],
    metrics: dict[str, Any],
    previous_attempts: list[RuntimeAttempt] | None = None,
) -> None:
    state_writer.write(
        root=root,
        mission_run_id=mission_run_id,
        refs=refs,
        mission_id=mission_id,
        current_contract_ref=active_contract.contract_ref,
        current_contract_hash=active_contract.contract_hash,
        revision_refs=list(active_contract.revision_refs),
        work_unit_id=work_unit_id,
        attempt_records=attempt_records,
        status=status,
        latest_decision=latest_decision,
        next_action=next_action,
        state=state,
        result=result,
        expected_artifacts=expected_artifacts,
        report_refs=report_refs,
        required_refs=required_refs,
        metrics=metrics,
        previous_attempts=previous_attempts,
    )


def _resolve_workspace_ref(root: Path, ref: str) -> Path:
    from .contracts import validate_ref

    safe_ref = validate_ref(ref, "runtime.ref")
    path = (root / safe_ref).resolve()
    workspace = root.resolve()
    if workspace not in path.parents and path != workspace:
        raise ContractValidationError("runtime ref escapes workspace")
    return path
