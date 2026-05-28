"""Deterministic faux PiWorker adapter."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from ..adapters.contracts import AdapterResult
from ..contracts import (
    ContractValidationError,
    EvidenceTrustLevel,
    ensure_json_value,
    require_int_at_least,
    require_mapping,
    require_non_empty_str,
    require_str_list,
    validate_ref,
)
from ..evidence_store import EvidenceLedger, InMemoryEvidenceStore
from ..work_unit import ExecutionReport, WorkUnitContract, WorkerResult
from ..workers import WorkerAdapterResult


PIWORKER_EVENT_TYPES = {
    "invocation_started",
    "artifact_written",
    "metrics_recorded",
    "contract_adjustment_requested",
    "invocation_completed",
}
PIWORKER_OUTPUT_STATUSES = {"completed", "failed", "blocked"}


@dataclass(frozen=True)
class PiWorkerMetrics:
    """Provider/tool/cache metrics recorded as evidence, not route logic."""

    tool_call_count: int = 0
    cache_hit_count: int = 0
    cache_miss_count: int = 0
    token_count: int = 0

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PiWorkerMetrics":
        data = require_mapping(payload, "piworker_metrics")
        metrics = cls(
            tool_call_count=require_int_at_least(data.get("tool_call_count", 0), "piworker_metrics.tool_call_count", 0),
            cache_hit_count=require_int_at_least(data.get("cache_hit_count", 0), "piworker_metrics.cache_hit_count", 0),
            cache_miss_count=require_int_at_least(data.get("cache_miss_count", 0), "piworker_metrics.cache_miss_count", 0),
            token_count=require_int_at_least(data.get("token_count", 0), "piworker_metrics.token_count", 0),
        )
        metrics.validate()
        return metrics

    def validate(self) -> None:
        require_int_at_least(self.tool_call_count, "piworker_metrics.tool_call_count", 0)
        require_int_at_least(self.cache_hit_count, "piworker_metrics.cache_hit_count", 0)
        require_int_at_least(self.cache_miss_count, "piworker_metrics.cache_miss_count", 0)
        require_int_at_least(self.token_count, "piworker_metrics.token_count", 0)

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "tool_call_count": self.tool_call_count,
            "cache_hit_count": self.cache_hit_count,
            "cache_miss_count": self.cache_miss_count,
            "token_count": self.token_count,
        }


@dataclass(frozen=True)
class PiWorkerInput:
    """Refs-only PiWorker input derived from a committed work unit."""

    input_id: str
    work_unit_id: str
    work_unit_ref: str
    attempt_manifest_ref: str
    allowed_scope: list[str] = field(default_factory=list)
    visible_refs: list[str] = field(default_factory=list)
    expected_outputs: list[str] = field(default_factory=list)

    @classmethod
    def from_work_unit(
        cls,
        work_unit: WorkUnitContract,
        *,
        work_unit_ref: str | None = None,
        attempt_manifest_ref: str | None = None,
    ) -> "PiWorkerInput":
        work_unit.validate()
        input_contract = cls(
            input_id=f"piworker-input-{work_unit.work_unit_id}",
            work_unit_id=work_unit.work_unit_id,
            work_unit_ref=work_unit_ref or f"work_units/{work_unit.work_unit_id}.json",
            attempt_manifest_ref=attempt_manifest_ref or f"attempts/{work_unit.work_unit_id}/input_manifest.json",
            allowed_scope=list(work_unit.allowed_scope),
            visible_refs=list(work_unit.visible_refs),
            expected_outputs=list(work_unit.expected_outputs),
        )
        input_contract.validate()
        return input_contract

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PiWorkerInput":
        data = require_mapping(payload, "piworker_input")
        input_contract = cls(
            input_id=require_non_empty_str(data.get("input_id"), "piworker_input.input_id"),
            work_unit_id=require_non_empty_str(data.get("work_unit_id"), "piworker_input.work_unit_id"),
            work_unit_ref=validate_ref(data.get("work_unit_ref"), "piworker_input.work_unit_ref"),
            attempt_manifest_ref=validate_ref(data.get("attempt_manifest_ref"), "piworker_input.attempt_manifest_ref"),
            allowed_scope=require_str_list(data.get("allowed_scope", []), "piworker_input.allowed_scope"),
            visible_refs=require_str_list(data.get("visible_refs", []), "piworker_input.visible_refs"),
            expected_outputs=require_str_list(data.get("expected_outputs", []), "piworker_input.expected_outputs"),
        )
        input_contract.validate()
        return input_contract

    def validate(self) -> None:
        require_non_empty_str(self.input_id, "piworker_input.input_id")
        require_non_empty_str(self.work_unit_id, "piworker_input.work_unit_id")
        validate_ref(self.work_unit_ref, "piworker_input.work_unit_ref")
        validate_ref(self.attempt_manifest_ref, "piworker_input.attempt_manifest_ref")
        for ref in self.allowed_scope:
            validate_ref(ref, "piworker_input.allowed_scope[]")
        for ref in self.visible_refs:
            validate_ref(ref, "piworker_input.visible_refs[]")
        for ref in self.expected_outputs:
            validate_ref(ref, "piworker_input.expected_outputs[]")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "input_id": self.input_id,
            "work_unit_id": self.work_unit_id,
            "work_unit_ref": self.work_unit_ref,
            "attempt_manifest_ref": self.attempt_manifest_ref,
            "allowed_scope": list(self.allowed_scope),
            "visible_refs": list(self.visible_refs),
            "expected_outputs": list(self.expected_outputs),
        }


@dataclass(frozen=True)
class ContractAdjustmentEvidence:
    """Worker-requested contract adjustment recorded as evidence only."""

    request_id: str
    work_unit_id: str
    requested_change: str
    reason: str
    evidence_refs: list[str] = field(default_factory=list)
    authority_required: str = "reviewer"

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ContractAdjustmentEvidence":
        data = require_mapping(payload, "contract_adjustment_evidence")
        evidence = cls(
            request_id=require_non_empty_str(data.get("request_id"), "contract_adjustment_evidence.request_id"),
            work_unit_id=require_non_empty_str(data.get("work_unit_id"), "contract_adjustment_evidence.work_unit_id"),
            requested_change=require_non_empty_str(
                data.get("requested_change"),
                "contract_adjustment_evidence.requested_change",
            ),
            reason=require_non_empty_str(data.get("reason"), "contract_adjustment_evidence.reason"),
            evidence_refs=require_str_list(
                data.get("evidence_refs", []),
                "contract_adjustment_evidence.evidence_refs",
            ),
            authority_required=require_non_empty_str(
                data.get("authority_required", "reviewer"),
                "contract_adjustment_evidence.authority_required",
            ),
        )
        evidence.validate()
        return evidence

    def validate(self) -> None:
        require_non_empty_str(self.request_id, "contract_adjustment_evidence.request_id")
        require_non_empty_str(self.work_unit_id, "contract_adjustment_evidence.work_unit_id")
        require_non_empty_str(self.requested_change, "contract_adjustment_evidence.requested_change")
        require_non_empty_str(self.reason, "contract_adjustment_evidence.reason")
        for ref in self.evidence_refs:
            validate_ref(ref, "contract_adjustment_evidence.evidence_refs[]")
        if self.authority_required not in {"reviewer", "user"}:
            raise ContractValidationError("contract_adjustment_evidence.authority_required must be reviewer or user")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "request_id": self.request_id,
            "work_unit_id": self.work_unit_id,
            "requested_change": self.requested_change,
            "reason": self.reason,
            "evidence_refs": list(self.evidence_refs),
            "authority_required": self.authority_required,
        }


@dataclass(frozen=True)
class PiWorkerEvent:
    """Refs-first faux PiWorker event."""

    event_id: str
    work_unit_id: str
    event_type: str
    artifact_refs: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    metrics: PiWorkerMetrics = field(default_factory=PiWorkerMetrics)
    contract_adjustment_ref: str | None = None

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PiWorkerEvent":
        data = require_mapping(payload, "piworker_event")
        contract_adjustment_ref = data.get("contract_adjustment_ref")
        event = cls(
            event_id=require_non_empty_str(data.get("event_id"), "piworker_event.event_id"),
            work_unit_id=require_non_empty_str(data.get("work_unit_id"), "piworker_event.work_unit_id"),
            event_type=require_non_empty_str(data.get("event_type"), "piworker_event.event_type"),
            artifact_refs=require_str_list(data.get("artifact_refs", []), "piworker_event.artifact_refs"),
            evidence_refs=require_str_list(data.get("evidence_refs", []), "piworker_event.evidence_refs"),
            metrics=PiWorkerMetrics.from_dict(require_mapping(data.get("metrics", {}), "piworker_event.metrics")),
            contract_adjustment_ref=(
                validate_ref(contract_adjustment_ref, "piworker_event.contract_adjustment_ref")
                if contract_adjustment_ref is not None
                else None
            ),
        )
        event.validate()
        return event

    def validate(self) -> None:
        require_non_empty_str(self.event_id, "piworker_event.event_id")
        require_non_empty_str(self.work_unit_id, "piworker_event.work_unit_id")
        if self.event_type not in PIWORKER_EVENT_TYPES:
            raise ContractValidationError(f"piworker_event.event_type must be one of {sorted(PIWORKER_EVENT_TYPES)}")
        for ref in self.artifact_refs:
            validate_ref(ref, "piworker_event.artifact_refs[]")
        for ref in self.evidence_refs:
            validate_ref(ref, "piworker_event.evidence_refs[]")
        self.metrics.validate()
        if self.contract_adjustment_ref is not None:
            validate_ref(self.contract_adjustment_ref, "piworker_event.contract_adjustment_ref")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        result = {
            "event_id": self.event_id,
            "work_unit_id": self.work_unit_id,
            "event_type": self.event_type,
            "artifact_refs": list(self.artifact_refs),
            "evidence_refs": list(self.evidence_refs),
            "metrics": self.metrics.to_dict(),
            "contract_adjustment_ref": self.contract_adjustment_ref,
        }
        return ensure_json_value(result, "piworker_event")


@dataclass(frozen=True)
class PiWorkerOutput:
    """Refs-only faux PiWorker output summary."""

    work_unit_id: str
    status: str
    produced_artifacts: list[str] = field(default_factory=list)
    event_evidence_refs: list[str] = field(default_factory=list)
    execution_report_ref: str = ""
    metrics: PiWorkerMetrics = field(default_factory=PiWorkerMetrics)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PiWorkerOutput":
        data = require_mapping(payload, "piworker_output")
        output = cls(
            work_unit_id=require_non_empty_str(data.get("work_unit_id"), "piworker_output.work_unit_id"),
            status=require_non_empty_str(data.get("status"), "piworker_output.status"),
            produced_artifacts=require_str_list(data.get("produced_artifacts", []), "piworker_output.produced_artifacts"),
            event_evidence_refs=require_str_list(
                data.get("event_evidence_refs", []),
                "piworker_output.event_evidence_refs",
            ),
            execution_report_ref=validate_ref(data.get("execution_report_ref"), "piworker_output.execution_report_ref"),
            metrics=PiWorkerMetrics.from_dict(require_mapping(data.get("metrics", {}), "piworker_output.metrics")),
        )
        output.validate()
        return output

    def validate(self) -> None:
        require_non_empty_str(self.work_unit_id, "piworker_output.work_unit_id")
        if self.status not in PIWORKER_OUTPUT_STATUSES:
            raise ContractValidationError(f"piworker_output.status must be one of {sorted(PIWORKER_OUTPUT_STATUSES)}")
        for ref in self.produced_artifacts:
            validate_ref(ref, "piworker_output.produced_artifacts[]")
        for ref in self.event_evidence_refs:
            validate_ref(ref, "piworker_output.event_evidence_refs[]")
        validate_ref(self.execution_report_ref, "piworker_output.execution_report_ref")
        self.metrics.validate()

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "work_unit_id": self.work_unit_id,
            "status": self.status,
            "produced_artifacts": list(self.produced_artifacts),
            "event_evidence_refs": list(self.event_evidence_refs),
            "execution_report_ref": self.execution_report_ref,
            "metrics": self.metrics.to_dict(),
        }


class FauxPiWorkerAdapter:
    """Deterministic harness-compatible faux PiWorker adapter."""

    adapter_id = "faux_piworker"

    def __init__(self, *, request_contract_adjustment: bool = False) -> None:
        self.request_contract_adjustment = request_contract_adjustment

    def run(
        self,
        work_unit: WorkUnitContract,
        *,
        workspace: str | Path = ".",
        evidence_store: EvidenceLedger | None = None,
    ) -> WorkerAdapterResult:
        if not isinstance(work_unit, WorkUnitContract):
            raise ContractValidationError("FauxPiWorkerAdapter consumes committed WorkUnitContract objects only")
        work_unit.validate()
        if not work_unit.expected_outputs:
            raise ContractValidationError("FauxPiWorkerAdapter requires at least one expected output")
        _reject_outputs_outside_scope(work_unit)

        store = evidence_store or InMemoryEvidenceStore()
        root = Path(workspace).resolve()
        root.mkdir(parents=True, exist_ok=True)
        piworker_input = PiWorkerInput.from_work_unit(work_unit)
        event_refs: list[str] = []
        produced_artifacts: list[str] = []

        event_refs.append(
            _record_event(
                store,
                PiWorkerEvent(
                    event_id=f"{work_unit.work_unit_id}-event-001",
                    work_unit_id=work_unit.work_unit_id,
                    event_type="invocation_started",
                    metrics=PiWorkerMetrics(cache_miss_count=1),
                ),
                source_refs=[piworker_input.work_unit_ref, piworker_input.attempt_manifest_ref],
            )
        )

        for index, output_ref in enumerate(work_unit.expected_outputs, start=1):
            artifact_ref = validate_ref(output_ref, "work_unit.expected_outputs[]")
            content = f"faux piworker artifact for {work_unit.work_unit_id} output {index}\n"
            artifact_path = _resolve_workspace_ref(root, artifact_ref)
            artifact_path.parent.mkdir(parents=True, exist_ok=True)
            artifact_path.write_text(content, encoding="utf-8")
            produced_artifacts.append(artifact_ref)
            artifact_hash = "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()
            event_refs.append(
                _record_event(
                    store,
                    PiWorkerEvent(
                        event_id=f"{work_unit.work_unit_id}-event-{index + 1:03d}",
                        work_unit_id=work_unit.work_unit_id,
                        event_type="artifact_written",
                        artifact_refs=[artifact_ref],
                        metrics=PiWorkerMetrics(tool_call_count=1, token_count=len(content)),
                    ),
                    extra_payload={"sha256": artifact_hash},
                )
            )

        contract_adjustment_ref: str | None = None
        if self.request_contract_adjustment:
            adjustment = ContractAdjustmentEvidence(
                request_id=f"adjust-{work_unit.work_unit_id}",
                work_unit_id=work_unit.work_unit_id,
                requested_change="review_required",
                reason="Faux PiWorker requests reviewer inspection of adapter output.",
                evidence_refs=list(event_refs),
            )
            contract_adjustment_ref = _record_contract_adjustment(store, adjustment)
            event_refs.append(
                _record_event(
                    store,
                    PiWorkerEvent(
                        event_id=f"{work_unit.work_unit_id}-event-adjustment",
                        work_unit_id=work_unit.work_unit_id,
                        event_type="contract_adjustment_requested",
                        evidence_refs=[contract_adjustment_ref],
                        contract_adjustment_ref=contract_adjustment_ref,
                    ),
                )
            )

        aggregate_metrics = PiWorkerMetrics(
            tool_call_count=len(produced_artifacts),
            cache_hit_count=0,
            cache_miss_count=1,
            token_count=sum(len(ref) for ref in produced_artifacts),
        )
        event_refs.append(
            _record_event(
                store,
                PiWorkerEvent(
                    event_id=f"{work_unit.work_unit_id}-event-metrics",
                    work_unit_id=work_unit.work_unit_id,
                    event_type="metrics_recorded",
                    metrics=aggregate_metrics,
                ),
            )
        )
        event_refs.append(
            _record_event(
                store,
                PiWorkerEvent(
                    event_id=f"{work_unit.work_unit_id}-event-completed",
                    work_unit_id=work_unit.work_unit_id,
                    event_type="invocation_completed",
                    artifact_refs=list(produced_artifacts),
                    evidence_refs=list(event_refs),
                    metrics=aggregate_metrics,
                ),
            )
        )

        report_ref = f"attempts/{work_unit.work_unit_id}/piworker_execution_report.json"
        report_evidence_refs = list(event_refs)
        if contract_adjustment_ref is not None:
            report_evidence_refs.append(contract_adjustment_ref)
        report = ExecutionReport(
            report_id=f"R-{work_unit.work_unit_id}",
            work_unit_id=work_unit.work_unit_id,
            status="completed",
            produced_artifacts=list(produced_artifacts),
            changed_refs=list(produced_artifacts),
            evidence_refs=_dedupe_refs(report_evidence_refs),
            worker_claims=[],
            metrics={
                **aggregate_metrics.to_dict(),
                "adapter_id": self.adapter_id,
                "contract_adjustment_ref": contract_adjustment_ref,
            },
        )
        report_path = _resolve_workspace_ref(root, report_ref)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report.to_dict(), sort_keys=True, indent=2) + "\n", encoding="utf-8")

        output = PiWorkerOutput(
            work_unit_id=work_unit.work_unit_id,
            status="completed",
            produced_artifacts=list(produced_artifacts),
            event_evidence_refs=list(event_refs),
            execution_report_ref=report_ref,
            metrics=aggregate_metrics,
        )
        adapter_result = AdapterResult(
            invocation_id=f"invoke-{work_unit.work_unit_id}",
            adapter_id=self.adapter_id,
            status="completed",
            output_refs=[report_ref, *output.produced_artifacts],
            evidence_refs=list(report.evidence_refs),
            metrics=output.metrics.to_dict(),
        )
        adapter_result.validate()

        return WorkerAdapterResult(
            execution_report=report,
            worker_result=WorkerResult(status="completed", execution_report_ref=report_ref),
            event_evidence_refs=list(event_refs),
            metrics={
                **aggregate_metrics.to_dict(),
                "adapter_result_status": adapter_result.status,
            },
        )


def _record_event(
    store: EvidenceLedger,
    event: PiWorkerEvent,
    *,
    source_refs: list[str] | None = None,
    extra_payload: Mapping[str, Any] | None = None,
) -> str:
    event.validate()
    payload = event.to_dict()
    if extra_payload:
        payload.update(ensure_json_value(require_mapping(extra_payload, "piworker_event.extra_payload"), "piworker_event.extra_payload"))
    evidence_ref = store.append(
        payload=payload,
        trust_level=EvidenceTrustLevel.ARTIFACT_REF,
        kind="piworker_event",
        source_refs=source_refs,
    )
    return evidence_ref.evidence_id


def _record_contract_adjustment(store: EvidenceLedger, adjustment: ContractAdjustmentEvidence) -> str:
    adjustment.validate()
    evidence_ref = store.append(
        payload=adjustment.to_dict(),
        trust_level=EvidenceTrustLevel.ARTIFACT_REF,
        kind="contract_adjustment_request",
        source_refs=list(adjustment.evidence_refs),
    )
    return evidence_ref.evidence_id


def _reject_outputs_outside_scope(work_unit: WorkUnitContract) -> None:
    for output_ref in work_unit.expected_outputs:
        if not any(_is_within(output_ref, scope) for scope in work_unit.allowed_scope):
            raise ContractValidationError(f"PiWorker output outside allowed scope: {output_ref}")


def _is_within(ref: str, scope: str) -> bool:
    safe_ref = validate_ref(ref, "ref")
    safe_scope = validate_ref(scope, "scope")
    return safe_ref == safe_scope or safe_ref.startswith(f"{safe_scope}/")


def _resolve_workspace_ref(root: Path, ref: str) -> Path:
    safe_ref = validate_ref(ref, "workspace_ref")
    path = (root / safe_ref).resolve()
    if root not in path.parents and path != root:
        raise ContractValidationError("PiWorker adapter ref escapes workspace")
    return path


def _dedupe_refs(refs: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for ref in refs:
        if ref not in seen:
            result.append(ref)
            seen.add(ref)
    return result
