"""Active runtime contract loading and projection helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .contracts import ContractValidationError, validate_ref
from .freeze import FrozenMissionContract, freeze_mission
from .ir import MissionConstraint, MissionIR
from .json_store import JsonWorkspaceStore
from .state import MissionRun
from .verification import ValidatorSpec


LEGACY_FROZEN_CONTRACT_REF = "mission/frozen_contract.json"


@dataclass(frozen=True)
class ActiveMissionContract:
    """The frozen contract currently authoritative for runtime work."""

    mission_run_id: str
    mission_id: str
    contract_ref: str
    contract_hash: str
    frozen_contract: FrozenMissionContract
    revision_refs: list[str]


@dataclass(frozen=True)
class RuntimeContractView:
    """Internal runtime view derived from a frozen contract."""

    mission_id: str
    objective_summary: str
    outputs: dict[str, Any]
    constraints: list[MissionConstraint]
    validators: list[ValidatorSpec]
    manual_gates: list[dict[str, Any]]
    required_artifacts: list[str]

    @property
    def allowed_write_scopes(self) -> list[str]:
        scopes = self.outputs.get("allowed_write_scopes")
        if isinstance(scopes, list) and all(isinstance(item, str) and item for item in scopes):
            return list(scopes)
        return sorted({artifact.rsplit("/", 1)[0] for artifact in self.required_artifacts if "/" in artifact})


def base_contract_ref(mission_run_id: str) -> str:
    run_id = validate_ref(mission_run_id, "mission_run_id")
    return f"runs/{run_id}/contracts/base/frozen_contract.json"


def initialize_active_contract(
    *,
    workspace: str | Path,
    mission: MissionIR,
    mission_run_id: str,
) -> ActiveMissionContract:
    """Freeze and write the initial run-local active contract."""

    mission.validate()
    frozen = freeze_mission(mission)
    contract_ref = base_contract_ref(mission_run_id)
    store = JsonWorkspaceStore(workspace)
    store.write_json(contract_ref, frozen.to_dict())
    store.write_json(LEGACY_FROZEN_CONTRACT_REF, frozen.to_dict())
    return ActiveMissionContract(
        mission_run_id=mission_run_id,
        mission_id=mission.mission_id,
        contract_ref=contract_ref,
        contract_hash=frozen.contract_hash,
        frozen_contract=frozen,
        revision_refs=[],
    )


def load_active_contract(
    *,
    workspace: str | Path,
    run: MissionRun,
) -> ActiveMissionContract:
    """Load and validate the current contract recorded on MissionRun."""

    run.validate()
    contract_ref = run.current_contract_ref or LEGACY_FROZEN_CONTRACT_REF
    contract_hash = run.current_contract_hash
    frozen = load_frozen_contract(workspace=workspace, contract_ref=contract_ref)
    if frozen.mission_id != run.mission_id:
        raise ContractValidationError("active contract mission_id does not match MissionRun")
    if contract_hash and frozen.contract_hash != contract_hash:
        raise ContractValidationError("active contract hash does not match MissionRun.current_contract_hash")
    return ActiveMissionContract(
        mission_run_id=run.mission_run_id,
        mission_id=run.mission_id,
        contract_ref=contract_ref,
        contract_hash=frozen.contract_hash,
        frozen_contract=frozen,
        revision_refs=_dedupe_refs(list(run.revision_refs)),
    )


def load_frozen_contract(*, workspace: str | Path, contract_ref: str) -> FrozenMissionContract:
    ref = validate_ref(contract_ref, "active_contract.contract_ref")
    store = JsonWorkspaceStore(workspace)
    if not store.exists(ref):
        raise ContractValidationError(f"active contract ref is missing: {ref}")
    return FrozenMissionContract.from_dict(store.read_json(ref))


def runtime_contract_view(frozen: FrozenMissionContract) -> RuntimeContractView:
    frozen.validate()
    expanded = frozen.expanded_mission
    objective = expanded.objective
    summary = objective.get("summary")
    if not isinstance(summary, str) or not summary:
        raise ContractValidationError("active contract objective.summary is missing")
    required_artifacts = list(expanded.required_artifacts)
    if not required_artifacts:
        artifacts = expanded.outputs.get("required_artifacts", [])
        if isinstance(artifacts, list) and all(isinstance(item, str) and item for item in artifacts):
            required_artifacts = list(artifacts)
    if not required_artifacts:
        raise ContractValidationError("runtime requires outputs.required_artifacts as a list of refs")
    return RuntimeContractView(
        mission_id=expanded.mission_id,
        objective_summary=summary,
        outputs=dict(expanded.outputs),
        constraints=list(expanded.constraints),
        validators=list(expanded.validators),
        manual_gates=[dict(gate) for gate in expanded.manual_gates],
        required_artifacts=required_artifacts,
    )


def _dedupe_refs(refs: list[str]) -> list[str]:
    result: list[str] = []
    for ref in refs:
        safe_ref = validate_ref(ref, "active_contract.revision_refs[]")
        if safe_ref not in result:
            result.append(safe_ref)
    return result
