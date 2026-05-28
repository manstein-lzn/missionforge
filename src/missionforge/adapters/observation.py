"""Optional read-only observation and control-intent host adapter."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Mapping

from ..contracts import (
    ContractValidationError,
    ensure_json_value,
    require_int_at_least,
    require_mapping,
    require_non_empty_str,
    require_str_list,
    validate_ref,
)
from ..control import ControlRequest
from ..evidence_store import EvidenceSnapshot
from ..runner import MissionResult


@dataclass(frozen=True)
class MissionRunView:
    """Read-only host-facing summary of a mission run."""

    mission_id: str
    status: str
    evidence_refs: list[str] = field(default_factory=list)
    artifact_refs: list[str] = field(default_factory=list)
    failed_constraint_ids: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    evidence_record_count: int = 0

    @classmethod
    def from_result(
        cls,
        result: MissionResult,
        *,
        evidence_snapshot: EvidenceSnapshot | None = None,
    ) -> "MissionRunView":
        result.validate()
        view = cls(
            mission_id=result.mission_id,
            status=result.status,
            evidence_refs=list(result.evidence_refs),
            artifact_refs=list(result.artifact_refs),
            failed_constraint_ids=list(result.failed_constraint_ids),
            metrics=dict(result.metrics),
            evidence_record_count=len(evidence_snapshot.records) if evidence_snapshot is not None else 0,
        )
        view.validate()
        return view

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MissionRunView":
        data = require_mapping(payload, "mission_run_view")
        view = cls(
            mission_id=require_non_empty_str(data.get("mission_id"), "mission_run_view.mission_id"),
            status=require_non_empty_str(data.get("status"), "mission_run_view.status"),
            evidence_refs=require_str_list(data.get("evidence_refs", []), "mission_run_view.evidence_refs"),
            artifact_refs=require_str_list(data.get("artifact_refs", []), "mission_run_view.artifact_refs"),
            failed_constraint_ids=require_str_list(
                data.get("failed_constraint_ids", []),
                "mission_run_view.failed_constraint_ids",
            ),
            metrics=ensure_json_value(
                require_mapping(data.get("metrics", {}), "mission_run_view.metrics"),
                "mission_run_view.metrics",
            ),
            evidence_record_count=require_int_at_least(
                data.get("evidence_record_count", 0),
                "mission_run_view.evidence_record_count",
                0,
            ),
        )
        view.validate()
        return view

    def validate(self) -> None:
        require_non_empty_str(self.mission_id, "mission_run_view.mission_id")
        require_non_empty_str(self.status, "mission_run_view.status")
        for ref in self.evidence_refs:
            validate_ref(ref, "mission_run_view.evidence_refs[]")
        for ref in self.artifact_refs:
            validate_ref(ref, "mission_run_view.artifact_refs[]")
        require_str_list(self.failed_constraint_ids, "mission_run_view.failed_constraint_ids")
        ensure_json_value(require_mapping(self.metrics, "mission_run_view.metrics"), "mission_run_view.metrics")
        require_int_at_least(self.evidence_record_count, "mission_run_view.evidence_record_count", 0)

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "mission_id": self.mission_id,
            "status": self.status,
            "evidence_refs": list(self.evidence_refs),
            "artifact_refs": list(self.artifact_refs),
            "failed_constraint_ids": list(self.failed_constraint_ids),
            "metrics": ensure_json_value(self.metrics, "mission_run_view.metrics"),
            "evidence_record_count": self.evidence_record_count,
        }


@dataclass(frozen=True)
class ControlRequestWriteResult:
    """Refs-only summary of a written control intent."""

    control_id: str
    control_type: str
    control_ref: str
    active: bool = True
    evidence_refs: list[str] = field(default_factory=list)

    def validate(self) -> None:
        require_non_empty_str(self.control_id, "control_request_write_result.control_id")
        require_non_empty_str(self.control_type, "control_request_write_result.control_type")
        validate_ref(self.control_ref, "control_request_write_result.control_ref")
        if not isinstance(self.active, bool):
            raise ContractValidationError("control_request_write_result.active must be a boolean")
        for ref in self.evidence_refs:
            validate_ref(ref, "control_request_write_result.evidence_refs[]")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "control_id": self.control_id,
            "control_type": self.control_type,
            "control_ref": self.control_ref,
            "active": self.active,
            "evidence_refs": list(self.evidence_refs),
        }


class ControlRequestWriter:
    """Write explicit control intent without mutating runtime state."""

    def __init__(self, *, workspace: str | Path = ".") -> None:
        self.workspace = Path(workspace).resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)

    def write_halt(
        self,
        *,
        reason: str,
        control_id: str = "halt-001",
        control_ref: str | None = None,
        active: bool = True,
        evidence_refs: list[str] | None = None,
    ) -> ControlRequestWriteResult:
        request = ControlRequest(
            control_id=control_id,
            control_type="halt",
            reason=reason,
            active=active,
            evidence_refs=evidence_refs or [],
        )
        request.validate()
        output_ref = control_ref or f"control/{control_id}.json"
        _write_json_ref(self.workspace, output_ref, request.to_dict())
        result = ControlRequestWriteResult(
            control_id=request.control_id,
            control_type=request.control_type,
            control_ref=output_ref,
            active=request.active,
            evidence_refs=list(request.evidence_refs),
        )
        result.validate()
        return result


def read_control_request(*, workspace: str | Path = ".", control_ref: str) -> ControlRequest:
    """Read a previously written control intent."""

    root = Path(workspace).resolve()
    path = _resolve_workspace_ref(root, control_ref)
    return ControlRequest.from_dict(json.loads(path.read_text(encoding="utf-8")))


def _write_json_ref(root: Path, ref: str, payload: Mapping[str, Any]) -> None:
    data = ensure_json_value(require_mapping(payload, ref), ref)
    path = _resolve_workspace_ref(root, ref)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _resolve_workspace_ref(root: Path, ref: str) -> Path:
    safe_ref = validate_ref(ref, "workspace_ref")
    path = (root / safe_ref).resolve()
    if root not in path.parents and path != root:
        raise ContractValidationError("host adapter ref escapes workspace")
    return path
