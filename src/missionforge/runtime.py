"""Deterministic MissionForge runtime vertical slice."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

from .contracts import AdaptiveDecision, ContractValidationError, require_int_at_least, stable_json_hash
from .evidence_store import EvidenceLedger, InMemoryEvidenceStore
from .fake_worker import FakeWorker
from .freeze import FrozenMissionContract, freeze_mission
from .harness import ProposalValidator, WorkUnitCompiler, WorkUnitHarness
from .ir import MissionIR
from .state import MissionRunState
from .steering import SteeringProposal
from .verification import VerificationSpec, ValidatorSpec
from .verifier import Verifier


FROZEN_CONTRACT_REF = "mission/frozen_contract.json"


@dataclass
class RuntimeEngine:
    """Compose freeze, harness, fake worker, and verifier into one run."""

    workspace: str | Path = "."
    max_attempts: int = 1
    evidence_store: EvidenceLedger = field(default_factory=InMemoryEvidenceStore)

    def run(self, mission: MissionIR):
        mission.validate()
        require_int_at_least(self.max_attempts, "runtime.max_attempts", 1)
        root = Path(self.workspace)
        root.mkdir(parents=True, exist_ok=True)

        frozen = freeze_mission(mission)
        frozen_ref = _write_json(root, FROZEN_CONTRACT_REF, frozen.to_dict())
        required_artifacts = _required_artifacts(mission)
        allowed_scopes = _allowed_scopes(mission, required_artifacts)
        proposal = _initial_proposal(mission, frozen_ref=frozen_ref, required_artifacts=required_artifacts, allowed_scopes=allowed_scopes)
        validator = ProposalValidator(available_refs={frozen_ref}, allowed_output_roots=allowed_scopes)
        harness = WorkUnitHarness(
            compiler=WorkUnitCompiler(mission_id=mission.mission_id, validator=validator),
            worker=FakeWorker(),
            evidence_store=self.evidence_store,
        )
        dispatch = harness.dispatch(proposal, workspace=str(root))
        if dispatch.validation.status.value != "accepted" or dispatch.work_unit is None or dispatch.execution_report is None:
            return _result(
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

        verification_spec = _verification_spec(mission, required_artifacts)
        verification = Verifier(
            workspace=root,
            evidence_store=self.evidence_store,
            contract_hash=frozen.contract_hash,
        ).verify(verification_spec)
        artifact_refs = list(dispatch.execution_report.produced_artifacts)
        evidence_refs = _snapshot_evidence_ids(self.evidence_store)
        state = MissionRunState(
            mission_id=mission.mission_id,
            status=verification.status.value,
            contract_hash=frozen.contract_hash,
            work_unit_refs=[dispatch.validation.accepted_contract_ref] if dispatch.validation.accepted_contract_ref else [],
            evidence_refs=evidence_refs,
            artifact_refs=artifact_refs,
            failed_constraint_ids=list(verification.failed_constraint_ids),
            latest_decision=verification.status.value,
        )
        return _result(
            mission_id=mission.mission_id,
            status=verification.status.value,
            frozen=frozen,
            state=state,
            evidence_refs=evidence_refs,
            artifact_refs=artifact_refs,
            failed_constraint_ids=list(verification.failed_constraint_ids),
            metrics={
                "attempt_count": 1,
                "contract_hash": frozen.contract_hash,
                "ledger_hash": self.evidence_store.snapshot().ledger_hash,
                "verification_status": verification.status.value,
                "validator_result_count": len(verification.validator_results),
            },
        )


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
    frozen_ref: str,
    required_artifacts: list[str],
    allowed_scopes: list[str],
) -> SteeringProposal:
    return SteeringProposal(
        proposal_id="P-000001",
        mission_run_id=f"run-{mission.mission_id}",
        iteration=1,
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
    path = root / ref
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return ref


def _snapshot_evidence_ids(evidence_store: EvidenceLedger) -> list[str]:
    return [record.evidence_id for record in evidence_store.snapshot().records]
