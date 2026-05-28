"""Runtime state snapshots."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .contracts import require_mapping, require_non_empty_str, require_str_list


@dataclass(frozen=True)
class MissionRunState:
    """Refs-only runtime state snapshot."""

    mission_id: str
    status: str
    contract_hash: str
    work_unit_refs: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    artifact_refs: list[str] = field(default_factory=list)
    failed_constraint_ids: list[str] = field(default_factory=list)
    latest_decision: str = ""

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MissionRunState":
        data = require_mapping(payload, "mission_run_state")
        state = cls(
            mission_id=require_non_empty_str(data.get("mission_id"), "mission_run_state.mission_id"),
            status=require_non_empty_str(data.get("status"), "mission_run_state.status"),
            contract_hash=require_non_empty_str(data.get("contract_hash"), "mission_run_state.contract_hash"),
            work_unit_refs=require_str_list(data.get("work_unit_refs", []), "mission_run_state.work_unit_refs"),
            evidence_refs=require_str_list(data.get("evidence_refs", []), "mission_run_state.evidence_refs"),
            artifact_refs=require_str_list(data.get("artifact_refs", []), "mission_run_state.artifact_refs"),
            failed_constraint_ids=require_str_list(
                data.get("failed_constraint_ids", []),
                "mission_run_state.failed_constraint_ids",
            ),
            latest_decision=data.get("latest_decision", ""),
        )
        state.validate()
        return state

    def validate(self) -> None:
        require_non_empty_str(self.mission_id, "mission_run_state.mission_id")
        require_non_empty_str(self.status, "mission_run_state.status")
        require_non_empty_str(self.contract_hash, "mission_run_state.contract_hash")
        require_str_list(self.work_unit_refs, "mission_run_state.work_unit_refs")
        require_str_list(self.evidence_refs, "mission_run_state.evidence_refs")
        require_str_list(self.artifact_refs, "mission_run_state.artifact_refs")
        require_str_list(self.failed_constraint_ids, "mission_run_state.failed_constraint_ids")
        if self.latest_decision:
            require_non_empty_str(self.latest_decision, "mission_run_state.latest_decision")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "mission_id": self.mission_id,
            "status": self.status,
            "contract_hash": self.contract_hash,
            "work_unit_refs": list(self.work_unit_refs),
            "evidence_refs": list(self.evidence_refs),
            "artifact_refs": list(self.artifact_refs),
            "failed_constraint_ids": list(self.failed_constraint_ids),
            "latest_decision": self.latest_decision,
        }
