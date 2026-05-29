"""Run-local storage for mission revision artifacts."""

from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone

from .contracts import ContractValidationError, validate_ref
from .freeze import FrozenMissionContract
from .ir import MissionIR
from .json_store import JsonWorkspaceStore
from .review import ReviewerDecision
from .runtime_contract import load_active_contract
from .revision import MissionRevision, MissionRevisionDecision, MissionRevisionRequest, MissionRevisionWorkflow
from .state import MissionRun, load_mission_run
from .steering import ContractAdjustmentRequest


class MissionRevisionStore:
    """Store revision request, decision, frozen contract, and record refs."""

    def __init__(self, workspace: str | Path = ".") -> None:
        self.workspace = Path(workspace)
        self.store = JsonWorkspaceStore(self.workspace)

    def refs(self, mission_run_id: str, revision_id: str) -> dict[str, str]:
        run_id = validate_ref(mission_run_id, "revision_store.mission_run_id")
        safe_revision_id = validate_ref(revision_id, "revision_store.revision_id")
        root = f"runs/{run_id}/revisions/{safe_revision_id}"
        return {
            "revision_dir": root,
            "request": f"{root}/request.json",
            "decision": f"{root}/decision.json",
            "mission": f"{root}/mission_ir.json",
            "contract": f"{root}/frozen_contract.json",
            "revision": f"{root}/revision.json",
        }

    def write_request(self, request: MissionRevisionRequest) -> str:
        request.validate()
        ref = self.refs(request.mission_run_id, request.revision_id)["request"]
        self._write_json(ref, request.to_dict())
        return ref

    def write_decision(self, decision: MissionRevisionDecision) -> str:
        decision.validate()
        ref = self.refs(decision.mission_run_id, decision.revision_id)["decision"]
        self._write_json(ref, decision.to_dict())
        return ref

    def write_contract(self, mission_run_id: str, revision_id: str, contract: FrozenMissionContract) -> str:
        ref = self.refs(mission_run_id, revision_id)["contract"]
        self._write_json(ref, contract.to_dict())
        return ref

    def write_mission(self, mission_run_id: str, revision_id: str, mission: MissionIR) -> str:
        mission.validate()
        ref = self.refs(mission_run_id, revision_id)["mission"]
        self._write_json(ref, mission.to_dict())
        return ref

    def write_revision(self, revision: MissionRevision) -> str:
        revision.validate()
        ref = self.refs(revision.mission_run_id, revision.revision_id)["revision"]
        self._write_json(ref, revision.to_dict())
        return ref

    def load_revision(self, mission_run_id: str, revision_id: str) -> MissionRevision:
        ref = self.refs(mission_run_id, revision_id)["revision"]
        return MissionRevision.from_dict(self.store.read_json(ref))

    def load_revision_ref(self, revision_ref: str) -> MissionRevision:
        return MissionRevision.from_dict(self.store.read_json(revision_ref))

    def load_mission_ref(self, mission_ref: str) -> MissionIR:
        return MissionIR.from_dict(self.store.read_json(mission_ref))

    def record_on_mission_run(self, mission_run_id: str, revision: MissionRevision) -> None:
        revision.validate()
        run = self.store.load_mission_run(mission_run_id)
        refs = self.refs(mission_run_id, revision.revision_id)
        if not self.store.exists(revision.new_contract_ref):
            raise ContractValidationError("mission revision cannot activate missing contract ref")
        if revision.new_mission_ref and not self.store.exists(revision.new_mission_ref):
            raise ContractValidationError("mission revision cannot activate missing mission ref")
        if not self.store.exists(refs["revision"]):
            raise ContractValidationError("mission revision cannot activate missing revision ref")
        updated = MissionRun(
            mission_run_id=run.mission_run_id,
            mission_id=run.mission_id,
            status=run.status,
            current_attempt=run.current_attempt,
            latest_work_unit_id=run.latest_work_unit_id,
            latest_decision=run.latest_decision,
            next_action=run.next_action,
            updated_at=_now(),
            attempts_ref=run.attempts_ref,
            artifact_hygiene_ref=run.artifact_hygiene_ref,
            latest_safe_point=run.latest_safe_point,
            artifact_refs=list(run.artifact_refs),
            evidence_refs=list(run.evidence_refs),
            failed_constraint_ids=list(run.failed_constraint_ids),
            metrics=dict(run.metrics),
            current_contract_ref=revision.new_contract_ref,
            current_contract_hash=revision.new_contract_hash,
            revision_refs=_dedupe_refs([*run.revision_refs, refs["revision"]]),
        )
        self.store.write_mission_run(updated)

    def _write_json(self, ref: str, payload: dict) -> None:
        self.store.write_json(ref, payload)


def _dedupe_refs(refs: list[str]) -> list[str]:
    result: list[str] = []
    for ref in refs:
        safe_ref = validate_ref(ref, "revision_ref")
        if safe_ref not in result:
            result.append(safe_ref)
    return result


def apply_mission_revision(
    *,
    workspace: str | Path,
    mission: MissionIR,
    adjustment: ContractAdjustmentRequest,
    reviewer_decision: ReviewerDecision | None = None,
    reviewer_decision_ref: str = "",
) -> MissionRevision:
    """Apply one approved conservative revision as a durable state transition."""

    root = Path(workspace)
    mission.validate()
    adjustment.validate()
    run = load_mission_run(root, adjustment.mission_run_id)
    if run.mission_id != mission.mission_id:
        raise ContractValidationError("mission revision mission_id does not match MissionRun")
    store = MissionRevisionStore(root)
    active = load_active_contract(workspace=root, run=run)
    base_mission = _base_mission_for_active_contract(store=store, run=run, fallback=mission, active_hash=active.contract_hash)
    revision_id = f"revision-{adjustment.iteration:06d}"
    refs = store.refs(run.mission_run_id, revision_id)
    request = MissionRevisionRequest.from_adjustment(
        adjustment,
        base_contract_ref=active.contract_ref,
        base_contract_hash=active.contract_hash,
        request_ref=refs["request"],
        revision_id=revision_id,
    )
    workflow = MissionRevisionWorkflow()
    decision = workflow.decide(
        request,
        reviewer_decision=reviewer_decision,
        reviewer_decision_ref=reviewer_decision_ref,
    )
    request_ref = store.write_request(request)
    decision_ref = store.write_decision(decision)
    if decision.decision != "approved":
        raise ContractValidationError(f"mission revision was not approved: {decision.decision}")
    revised_mission, new_contract, revision = workflow.apply(
        base_mission,
        request,
        decision,
        old_contract=active.frozen_contract,
        new_contract_ref=refs["contract"],
        decision_ref=decision_ref,
        new_mission_ref=refs["mission"],
    )
    if request_ref != revision.revision_request_ref:
        raise ContractValidationError("mission revision request ref mismatch")
    store.write_mission(request.mission_run_id, request.revision_id, revised_mission)
    store.write_contract(request.mission_run_id, request.revision_id, new_contract)
    store.write_revision(revision)
    store.record_on_mission_run(run.mission_run_id, revision)
    return revision


def _base_mission_for_active_contract(
    *,
    store: MissionRevisionStore,
    run: MissionRun,
    fallback: MissionIR,
    active_hash: str,
) -> MissionIR:
    if run.revision_refs:
        latest_revision = store.load_revision_ref(run.revision_refs[-1])
        if latest_revision.new_mission_ref:
            mission = store.load_mission_ref(latest_revision.new_mission_ref)
            if _mission_hash(mission) != active_hash:
                raise ContractValidationError("stored revised MissionIR does not match active contract hash")
            return mission
    if _mission_hash(fallback) != active_hash:
        raise ContractValidationError("mission input does not match active contract hash")
    return fallback


def _mission_hash(mission: MissionIR) -> str:
    from .freeze import freeze_mission

    return freeze_mission(mission).contract_hash


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
