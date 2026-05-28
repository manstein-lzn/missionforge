"""Work-unit contract objects."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .contracts import (
    ContractValidationError,
    require_int_at_least,
    require_mapping,
    require_non_empty_str,
    require_str_list,
    validate_ref,
)


@dataclass(frozen=True)
class WorkUnitContract:
    """Committed bounded work-unit contract."""

    work_unit_id: str
    mission_id: str
    iteration: int
    next_objective: str
    allowed_scope: list[str] = field(default_factory=list)
    visible_refs: list[str] = field(default_factory=list)
    expected_outputs: list[str] = field(default_factory=list)
    exit_criteria: list[str] = field(default_factory=list)
    stop_conditions: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "WorkUnitContract":
        data = require_mapping(payload, "work_unit")
        contract = cls(
            work_unit_id=require_non_empty_str(data.get("work_unit_id"), "work_unit.work_unit_id"),
            mission_id=require_non_empty_str(data.get("mission_id"), "work_unit.mission_id"),
            iteration=require_int_at_least(data.get("iteration"), "work_unit.iteration", 1),
            next_objective=require_non_empty_str(data.get("next_objective"), "work_unit.next_objective"),
            allowed_scope=require_str_list(data.get("allowed_scope", []), "work_unit.allowed_scope"),
            visible_refs=require_str_list(data.get("visible_refs", []), "work_unit.visible_refs"),
            expected_outputs=require_str_list(data.get("expected_outputs", []), "work_unit.expected_outputs"),
            exit_criteria=require_str_list(data.get("exit_criteria", []), "work_unit.exit_criteria"),
            stop_conditions=require_str_list(data.get("stop_conditions", []), "work_unit.stop_conditions"),
        )
        contract.validate()
        return contract

    def validate(self) -> None:
        require_non_empty_str(self.work_unit_id, "work_unit.work_unit_id")
        require_non_empty_str(self.mission_id, "work_unit.mission_id")
        require_int_at_least(self.iteration, "work_unit.iteration", 1)
        require_non_empty_str(self.next_objective, "work_unit.next_objective")
        for ref in self.allowed_scope:
            validate_ref(ref, "work_unit.allowed_scope[]")
        for ref in self.visible_refs:
            validate_ref(ref, "work_unit.visible_refs[]")
        for ref in self.expected_outputs:
            validate_ref(ref, "work_unit.expected_outputs[]")
        require_str_list(self.exit_criteria, "work_unit.exit_criteria")
        require_str_list(self.stop_conditions, "work_unit.stop_conditions")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "work_unit_id": self.work_unit_id,
            "mission_id": self.mission_id,
            "iteration": self.iteration,
            "next_objective": self.next_objective,
            "allowed_scope": list(self.allowed_scope),
            "visible_refs": list(self.visible_refs),
            "expected_outputs": list(self.expected_outputs),
            "exit_criteria": list(self.exit_criteria),
            "stop_conditions": list(self.stop_conditions),
        }


@dataclass(frozen=True)
class AttemptInputManifest:
    """Refs visible to one worker attempt."""

    attempt_id: str
    work_unit_id: str
    visible_refs: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "AttemptInputManifest":
        data = require_mapping(payload, "attempt_manifest")
        manifest = cls(
            attempt_id=require_non_empty_str(data.get("attempt_id"), "attempt_manifest.attempt_id"),
            work_unit_id=require_non_empty_str(data.get("work_unit_id"), "attempt_manifest.work_unit_id"),
            visible_refs=require_str_list(data.get("visible_refs", []), "attempt_manifest.visible_refs"),
        )
        manifest.validate()
        return manifest

    def validate(self) -> None:
        require_non_empty_str(self.attempt_id, "attempt_manifest.attempt_id")
        require_non_empty_str(self.work_unit_id, "attempt_manifest.work_unit_id")
        for ref in self.visible_refs:
            validate_ref(ref, "attempt_manifest.visible_refs[]")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "attempt_id": self.attempt_id,
            "work_unit_id": self.work_unit_id,
            "visible_refs": list(self.visible_refs),
        }


@dataclass(frozen=True)
class WorkerInvocation:
    """Deterministic worker invocation record."""

    invocation_id: str
    attempt_id: str
    work_unit_id: str
    manifest_ref: str

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "WorkerInvocation":
        data = require_mapping(payload, "worker_invocation")
        invocation = cls(
            invocation_id=require_non_empty_str(data.get("invocation_id"), "worker_invocation.invocation_id"),
            attempt_id=require_non_empty_str(data.get("attempt_id"), "worker_invocation.attempt_id"),
            work_unit_id=require_non_empty_str(data.get("work_unit_id"), "worker_invocation.work_unit_id"),
            manifest_ref=validate_ref(data.get("manifest_ref"), "worker_invocation.manifest_ref"),
        )
        invocation.validate()
        return invocation

    def validate(self) -> None:
        require_non_empty_str(self.invocation_id, "worker_invocation.invocation_id")
        require_non_empty_str(self.attempt_id, "worker_invocation.attempt_id")
        require_non_empty_str(self.work_unit_id, "worker_invocation.work_unit_id")
        validate_ref(self.manifest_ref, "worker_invocation.manifest_ref")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "invocation_id": self.invocation_id,
            "attempt_id": self.attempt_id,
            "work_unit_id": self.work_unit_id,
            "manifest_ref": self.manifest_ref,
        }


@dataclass(frozen=True)
class ExecutionReport:
    """Refs-only execution report for one worker attempt."""

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
