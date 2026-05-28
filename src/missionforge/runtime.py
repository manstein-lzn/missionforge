"""Deterministic MissionForge runtime vertical slice."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from .contracts import AdaptiveDecision, ContractValidationError, VerificationStatus, require_int_at_least, stable_json_hash
from .evidence_store import EvidenceLedger, InMemoryEvidenceStore
from .freeze import FrozenMissionContract, freeze_mission
from .harness import ProposalValidator, WorkUnitCompiler, WorkUnitHarness
from .ir import MissionIR
from .state import (
    MISSION_RUN_SCHEMA_VERSION,
    SUPPORTED_RESUME_BOUNDARY,
    MissionRun,
    MissionRunState,
    RuntimeAttempt,
    RuntimeSafePoint,
    inspect_runtime,
    load_mission_run,
    load_runtime_attempts,
    mission_run_id_for,
    mission_run_refs,
    scan_artifact_hygiene,
)
from .steering import SteeringProposal
from .verification import VerificationSpec, ValidatorSpec
from .verifier import Verifier


FROZEN_CONTRACT_REF = "mission/frozen_contract.json"


@dataclass
class RuntimeEngine:
    """Compose freeze, harness, fake worker, and verifier into one run."""

    workspace: str | Path = "."
    max_attempts: int = 1
    worker: Any | None = None
    evidence_store: EvidenceLedger = field(default_factory=InMemoryEvidenceStore)

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
        )._run(mission, initial_attempt_kind="resume", initial_decision="resume")

    def run(self, mission: MissionIR):
        return self._run(mission, initial_attempt_kind="initial", initial_decision="continue")

    def _run(self, mission: MissionIR, *, initial_attempt_kind: str, initial_decision: str):
        mission.validate()
        require_int_at_least(self.max_attempts, "runtime.max_attempts", 1)
        root = Path(self.workspace)
        root.mkdir(parents=True, exist_ok=True)
        mission_run_id = mission_run_id_for(mission.mission_id)
        refs = mission_run_refs(mission.mission_id)
        _resolve_workspace_ref(root, refs["run_dir"]).mkdir(parents=True, exist_ok=True)
        previous_attempts = _previous_attempts(root, mission_run_id, initial_attempt_kind=initial_attempt_kind)

        frozen = freeze_mission(mission)
        frozen_ref = _write_json(root, FROZEN_CONTRACT_REF, frozen.to_dict())
        required_artifacts = _required_artifacts(mission)
        allowed_scopes = _allowed_scopes(mission, required_artifacts)
        proposal = _initial_proposal(
            mission,
            iteration=len(previous_attempts) + 1,
            frozen_ref=frozen_ref,
            required_artifacts=required_artifacts,
            allowed_scopes=allowed_scopes,
        )
        validator = ProposalValidator(available_refs={frozen_ref}, allowed_output_roots=allowed_scopes)
        harness = WorkUnitHarness(
            compiler=WorkUnitCompiler(mission_id=mission.mission_id, validator=validator),
            worker=self.worker,
            evidence_store=self.evidence_store,
        )
        dispatch = harness.dispatch(proposal, workspace=str(root))
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
                mission_id=mission.mission_id,
                status="failed",
                contract_hash=frozen.contract_hash,
                latest_decision="proposal_rejected",
            )
            result = _result(
                mission_id=mission.mission_id,
                status="failed",
                frozen=frozen,
                state=MissionRunState(
                    mission_id=mission.mission_id,
                    status="failed",
                    contract_hash=frozen.contract_hash,
                    latest_decision="proposal_rejected",
                ),
                evidence_refs=[],
                artifact_refs=[],
                failed_constraint_ids=[constraint.constraint_id for constraint in mission.constraints],
                metrics={
                    "proposal_status": dispatch.validation.status.value,
                    "proposal_rejection_count": len(dispatch.validation.reasons),
                },
            )
            _write_runtime_state(
                root=root,
                mission_run_id=mission_run_id,
                mission_id=mission.mission_id,
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
                required_refs=[],
                metrics={"redesign_required": redesign_required},
            )
            return result

        verification_spec = _verification_spec(mission, required_artifacts)
        verifier = Verifier(
            workspace=root,
            evidence_store=self.evidence_store,
            contract_hash=frozen.contract_hash,
        )
        verification = verifier.verify(verification_spec)
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
                    compiler=WorkUnitCompiler(mission_id=mission.mission_id, validator=validator),
                    worker=repair_worker,
                    evidence_store=self.evidence_store,
                )
                repair_dispatch = repair_harness.dispatch(_repair_proposal(proposal, verification), workspace=str(root))
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
            mission_id=mission.mission_id,
            status=verification.status.value,
            contract_hash=frozen.contract_hash,
            work_unit_refs=[dispatch.validation.accepted_contract_ref] if dispatch.validation.accepted_contract_ref else [],
            evidence_refs=evidence_refs,
            artifact_refs=artifact_refs,
            failed_constraint_ids=list(verification.failed_constraint_ids),
            latest_decision=latest_decision,
        )
        result = _result(
            mission_id=mission.mission_id,
            status=verification.status.value,
            frozen=frozen,
            state=state,
            evidence_refs=evidence_refs,
            artifact_refs=artifact_refs,
            failed_constraint_ids=list(verification.failed_constraint_ids),
            metrics={
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
            },
        )
        _write_runtime_state(
            root=root,
            mission_run_id=mission_run_id,
            mission_id=mission.mission_id,
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
                *[attempt.input_ref for attempt in attempt_records],
                *[attempt.output_ref for attempt in attempt_records],
                *[attempt.report_ref for attempt in attempt_records],
                *[attempt.savepoints_ref for attempt in attempt_records],
            ]),
            metrics=result.metrics,
        )
        return result


def _previous_attempts(root: Path, mission_run_id: str, *, initial_attempt_kind: str) -> list[RuntimeAttempt]:
    if initial_attempt_kind != "resume":
        return []
    return load_runtime_attempts(root, mission_run_id)


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
    mission: MissionIR,
    *,
    iteration: int = 1,
    frozen_ref: str,
    required_artifacts: list[str],
    allowed_scopes: list[str],
) -> SteeringProposal:
    return SteeringProposal(
        proposal_id="P-000001",
        mission_run_id=f"run-{mission.mission_id}",
        iteration=iteration,
        input_refs=[frozen_ref],
        recommended_route=AdaptiveDecision.CONTINUE,
        proposed_contract={
            "next_objective": mission.objective.summary,
            "allowed_scope": list(allowed_scopes),
            "visible_refs": [frozen_ref],
            "expected_outputs": list(required_artifacts),
            "exit_criteria": ["Run verification after fake worker output."],
            "stop_conditions": ["A halt control is active."],
        },
        rationale="Deterministic initial runtime proposal.",
        confidence=1.0,
    )


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


def _verification_spec(mission: MissionIR, required_artifacts: list[str]) -> VerificationSpec:
    manual_gates = list(mission.verification.get("manual_gates", []))
    validators = [
        ValidatorSpec.from_dict(item)
        for item in mission.verification.get("validators", [])
    ]
    if not validators:
        constraint_refs = [mission.constraints[0].constraint_id] if mission.constraints else []
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


def _required_artifacts(mission: MissionIR) -> list[str]:
    artifacts = mission.outputs.get("required_artifacts", [])
    if isinstance(artifacts, list) and all(isinstance(item, str) and item for item in artifacts):
        return list(artifacts)
    raise ContractValidationError("runtime requires outputs.required_artifacts as a list of refs")


def _allowed_scopes(mission: MissionIR, required_artifacts: list[str]) -> list[str]:
    scopes = mission.outputs.get("allowed_write_scopes")
    if isinstance(scopes, list) and all(isinstance(item, str) and item for item in scopes):
        return list(scopes)
    return sorted({artifact.rsplit("/", 1)[0] for artifact in required_artifacts if "/" in artifact})


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
) -> RuntimeAttempt:
    work_unit = dispatch.work_unit
    report = dispatch.execution_report
    worker_result = dispatch.worker_result
    work_unit_id = work_unit.work_unit_id if work_unit is not None else f"WU-{index:06d}"
    report_ref = worker_result.execution_report_ref if worker_result is not None else f"attempts/{work_unit_id}/pi_agent_execution_report.json"
    output_ref = _report_metric_or_default(report, "output_ref", f"attempts/{work_unit_id}/pi_agent_output.json")
    input_ref = _report_metric_or_default(report, "input_ref", f"attempts/{work_unit_id}/pi_agent_input.json")
    savepoints_ref = _report_metric_or_default(report, "savepoints_ref", f"attempts/{work_unit_id}/pi_agent_savepoints.jsonl")
    return RuntimeAttempt(
        attempt_id=f"attempt-{index:06d}",
        work_unit_id=work_unit_id,
        attempt_kind=attempt_kind,
        worker="missionforge.pi_agent_runtime",
        input_ref=input_ref,
        output_ref=output_ref,
        report_ref=report_ref,
        savepoints_ref=savepoints_ref,
        status=report.status if report is not None else "failed",
        verification_status=verification_status,
        decision=decision,
        created_at=_now(),
        evidence_refs=list(report.evidence_refs) if report is not None else [],
        artifact_refs=list(report.produced_artifacts) if report is not None else [],
        failure_category=_failure_category(report, verification_status),
        metrics=dict(report.metrics) if report is not None else {},
    )


def _report_metric_or_default(report, key: str, default: str) -> str:
    if report is not None and isinstance(report.metrics, dict):
        value = report.metrics.get(key)
        if isinstance(value, str) and value:
            return value
    return default


def _failure_category(report, verification_status: str) -> str:
    if verification_status == VerificationStatus.COMPLETED_VERIFIED.value:
        return ""
    if report is not None:
        if report.status != "completed":
            return "worker_failure"
        if not report.produced_artifacts:
            return "missing_artifact"
    if verification_status == VerificationStatus.UNSUPPORTED_VERIFICATION_SPEC.value:
        return "redesign_required"
    if verification_status == VerificationStatus.FAILED.value:
        return "verifier_failure"
    return verification_status


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
    root: Path,
    mission_run_id: str,
    mission_id: str,
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
    all_attempts = [*(previous_attempts or []), *attempt_records]
    all_report_refs = _dedupe_refs([*[attempt.report_ref for attempt in all_attempts], *report_refs])
    all_required_refs = _dedupe_refs([
        *[attempt.input_ref for attempt in all_attempts],
        *[attempt.output_ref for attempt in all_attempts],
        *[attempt.report_ref for attempt in all_attempts],
        *[attempt.savepoints_ref for attempt in all_attempts],
        *required_refs,
    ])
    hygiene = scan_artifact_hygiene(
        root,
        mission_run_id=mission_run_id,
        expected_artifacts=expected_artifacts,
        report_refs=all_report_refs,
        required_refs=all_required_refs,
    )
    _write_json(root, refs["artifact_hygiene"], hygiene.to_dict())
    if attempt_records:
        _append_jsonl(root, refs["attempts"], [attempt.to_dict() for attempt in all_attempts])
    else:
        _append_jsonl(root, refs["attempts"], [])
    latest_attempt = all_attempts[-1] if all_attempts else None
    safe_point = _latest_safe_point(root, latest_attempt)
    mission_run = MissionRun(
        mission_run_id=mission_run_id,
        mission_id=mission_id,
        status=status,
        current_attempt=latest_attempt.attempt_id if latest_attempt else "attempt-000000",
        latest_work_unit_id=work_unit_id,
        latest_safe_point=safe_point,
        latest_decision=latest_decision,
        next_action=next_action,
        artifact_refs=list(result.artifact_refs),
        evidence_refs=list(result.evidence_refs),
        failed_constraint_ids=list(result.failed_constraint_ids),
        attempts_ref=refs["attempts"],
        artifact_hygiene_ref=refs["artifact_hygiene"],
        metrics={
            **metrics,
            "artifact_hygiene_passed": hygiene.passed,
            "state_hash": stable_json_hash(state.to_dict()),
        },
        updated_at=_now(),
    )
    _write_json(root, refs["mission_run"], mission_run.to_dict())


def _latest_safe_point(root: Path, attempt: RuntimeAttempt | None) -> RuntimeSafePoint | None:
    if attempt is None:
        return None
    savepoints_path = _resolve_workspace_ref(root, attempt.savepoints_ref)
    if not savepoints_path.is_file():
        return None
    turn_ref = attempt.savepoints_ref
    for line in savepoints_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        resume_hint = payload.get("resume_hint") if isinstance(payload, dict) else None
        if isinstance(resume_hint, dict) and resume_hint.get("boundary") == SUPPORTED_RESUME_BOUNDARY:
            turn_index = payload.get("turn_index")
            if isinstance(turn_index, int):
                turn_ref = f"{attempt.savepoints_ref}#turn={turn_index}"
    return RuntimeSafePoint(
        kind=SUPPORTED_RESUME_BOUNDARY,
        savepoint_ref=turn_ref,
        session_ref=f"attempts/{attempt.work_unit_id}/pi_agent_session.jsonl",
        events_ref=f"attempts/{attempt.work_unit_id}/pi_agent_events.jsonl",
    )


def _resolve_workspace_ref(root: Path, ref: str) -> Path:
    from .contracts import validate_ref

    safe_ref = validate_ref(ref, "runtime.ref")
    path = (root / safe_ref).resolve()
    workspace = root.resolve()
    if workspace not in path.parents and path != workspace:
        raise ContractValidationError("runtime ref escapes workspace")
    return path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
