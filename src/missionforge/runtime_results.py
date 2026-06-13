"""Refs-first runtime result envelopes."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping

from .contracts import (
    ensure_json_value,
    require_mapping,
    require_non_empty_str,
    require_str_list,
    validate_ref,
)


@dataclass(frozen=True)
class MissionResult:
    """Refs-only product/run result envelope."""

    mission_id: str
    status: str
    evidence_refs: list[str] = field(default_factory=list)
    artifact_refs: list[str] = field(default_factory=list)
    failed_constraint_ids: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MissionResult":
        data = require_mapping(payload, "mission_result")
        return cls(
            mission_id=require_non_empty_str(data.get("mission_id"), "mission_result.mission_id"),
            status=require_non_empty_str(data.get("status"), "mission_result.status"),
            evidence_refs=require_str_list(data.get("evidence_refs", []), "mission_result.evidence_refs"),
            artifact_refs=require_str_list(data.get("artifact_refs", []), "mission_result.artifact_refs"),
            failed_constraint_ids=require_str_list(
                data.get("failed_constraint_ids", []),
                "mission_result.failed_constraint_ids",
            ),
            metrics=require_mapping(data.get("metrics", {}), "mission_result.metrics"),
        )

    def validate(self) -> None:
        require_non_empty_str(self.mission_id, "mission_result.mission_id")
        require_non_empty_str(self.status, "mission_result.status")
        require_str_list(self.evidence_refs, "mission_result.evidence_refs")
        require_str_list(self.artifact_refs, "mission_result.artifact_refs")
        require_str_list(self.failed_constraint_ids, "mission_result.failed_constraint_ids")
        require_mapping(self.metrics, "mission_result.metrics")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)


@dataclass(frozen=True)
class ExecutionReport:
    """Refs-only execution report for one PiWorker call."""

    report_id: str
    work_unit_id: str
    status: str
    produced_artifacts: list[str] = field(default_factory=list)
    changed_refs: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    worker_claims: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ExecutionReport":
        data = require_mapping(payload, "execution_report")
        report = cls(
            report_id=require_non_empty_str(data.get("report_id"), "execution_report.report_id"),
            work_unit_id=require_non_empty_str(data.get("work_unit_id"), "execution_report.work_unit_id"),
            status=require_non_empty_str(data.get("status"), "execution_report.status"),
            produced_artifacts=require_str_list(data.get("produced_artifacts", []), "execution_report.produced_artifacts"),
            changed_refs=require_str_list(data.get("changed_refs", []), "execution_report.changed_refs"),
            evidence_refs=require_str_list(data.get("evidence_refs", []), "execution_report.evidence_refs"),
            worker_claims=require_str_list(data.get("worker_claims", []), "execution_report.worker_claims"),
            metrics=require_mapping(data.get("metrics", {}), "execution_report.metrics"),
        )
        report.validate()
        return report

    def validate(self) -> None:
        require_non_empty_str(self.report_id, "execution_report.report_id")
        require_non_empty_str(self.work_unit_id, "execution_report.work_unit_id")
        require_non_empty_str(self.status, "execution_report.status")
        for ref in self.produced_artifacts:
            validate_ref(ref, "execution_report.produced_artifacts[]")
        for ref in self.changed_refs:
            validate_ref(ref, "execution_report.changed_refs[]")
        for ref in self.evidence_refs:
            validate_ref(ref, "execution_report.evidence_refs[]")
        require_str_list(self.worker_claims, "execution_report.worker_claims")
        require_mapping(self.metrics, "execution_report.metrics")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "report_id": self.report_id,
            "work_unit_id": self.work_unit_id,
            "status": self.status,
            "produced_artifacts": list(self.produced_artifacts),
            "changed_refs": list(self.changed_refs),
            "evidence_refs": list(self.evidence_refs),
            "worker_claims": list(self.worker_claims),
            "metrics": dict(self.metrics),
        }


@dataclass(frozen=True)
class WorkerResult:
    """Minimal worker result envelope."""

    status: str
    execution_report_ref: str

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "WorkerResult":
        data = require_mapping(payload, "worker_result")
        result = cls(
            status=require_non_empty_str(data.get("status"), "worker_result.status"),
            execution_report_ref=validate_ref(data.get("execution_report_ref"), "worker_result.execution_report_ref"),
        )
        result.validate()
        return result

    def validate(self) -> None:
        require_non_empty_str(self.status, "worker_result.status")
        validate_ref(self.execution_report_ref, "worker_result.execution_report_ref")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "status": self.status,
            "execution_report_ref": self.execution_report_ref,
        }


@dataclass(frozen=True)
class WorkerAdapterResult:
    """Refs-first result returned by a PiWorker adapter call."""

    execution_report: ExecutionReport
    worker_result: WorkerResult
    event_evidence_refs: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        self.execution_report.validate()
        self.worker_result.validate()
        require_str_list(self.event_evidence_refs, "worker_adapter_result.event_evidence_refs")
        ensure_json_value(
            require_mapping(self.metrics, "worker_adapter_result.metrics"),
            "worker_adapter_result.metrics",
        )

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "execution_report": self.execution_report.to_dict(),
            "worker_result": self.worker_result.to_dict(),
            "event_evidence_refs": list(self.event_evidence_refs),
            "metrics": ensure_json_value(self.metrics, "worker_adapter_result.metrics"),
        }
