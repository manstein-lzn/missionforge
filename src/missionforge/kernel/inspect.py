"""Refs-only Kernel run inspection helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Mapping

from ..contracts import ContractValidationError, assert_refs_only_payload, ensure_json_value, validate_ref
from ..observation import RunEvent, RunSnapshot, read_run_events, read_run_snapshot
from .contracts import FlowLedgerEvent, FlowResult, StepRecord
from .io import read_json_ref, ref_exists, resolve_workspace_ref


@dataclass(frozen=True)
class KernelStepInspection:
    """Refs-only summary for one recorded Kernel step."""

    step_id: str
    status: str
    step_record_ref: str
    output_refs: list[str] = field(default_factory=list)
    permission_manifest_ref: str = ""
    piworker_call_ref: str = ""
    piworker_call_result_ref: str = ""
    execution_report_ref: str = ""
    context_projection_ref: str = ""
    context_hash: str = ""
    metric_refs: list[str] = field(default_factory=list)
    failure_refs: list[str] = field(default_factory=list)

    @classmethod
    def from_record(cls, ref: str, record: StepRecord) -> "KernelStepInspection":
        """Build a step inspection from an already validated StepRecord."""

        return cls(
            step_id=record.step_id,
            status=record.status.value,
            step_record_ref=validate_ref(ref, "kernel_step_inspection.step_record_ref"),
            output_refs=list(record.output_refs),
            permission_manifest_ref=record.permission_manifest_ref,
            piworker_call_ref=record.piworker_call_ref or "",
            piworker_call_result_ref=record.piworker_call_result_ref or "",
            execution_report_ref=record.execution_report_ref or "",
            context_projection_ref=_metadata_ref(record.metadata, "context_projection_ref"),
            context_hash=_metadata_text(record.metadata, "context_hash"),
            metric_refs=list(record.metric_refs),
            failure_refs=list(record.failure_refs),
        )

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "step_id": self.step_id,
            "status": self.status,
            "step_record_ref": self.step_record_ref,
            "output_refs": list(self.output_refs),
            "permission_manifest_ref": self.permission_manifest_ref,
            "piworker_call_ref": self.piworker_call_ref,
            "piworker_call_result_ref": self.piworker_call_result_ref,
            "execution_report_ref": self.execution_report_ref,
            "context_projection_ref": self.context_projection_ref,
            "context_hash": self.context_hash,
            "metric_refs": list(self.metric_refs),
            "failure_refs": list(self.failure_refs),
        }
        return dict(assert_refs_only_payload(payload, "kernel_step_inspection"))


@dataclass(frozen=True)
class KernelRunInspection:
    """Refs-only summary for a Kernel Flow execution.

    This is intentionally a read-only view for host UIs and debuggers. It does
    not read artifact bodies, prompts, provider payloads, tool bodies, stdout,
    stderr, or user interaction text.
    """

    flow_result_ref: str
    flow_id: str
    run_id: str
    status: str
    contract_ref: str
    contract_hash: str
    flow_ledger_ref: str = ""
    run_events_ref: str = ""
    run_snapshot_ref: str = ""
    snapshot_status: str = ""
    current_step_id: str = ""
    current_role: str = ""
    latest_event_id: str = ""
    latest_event_kind: str = ""
    latest_event_status: str = ""
    last_safe_point_ref: str = ""
    pending_user_event_count: int = 0
    step_record_refs: list[str] = field(default_factory=list)
    missing_step_record_refs: list[str] = field(default_factory=list)
    decision_refs: list[str] = field(default_factory=list)
    final_artifact_refs: list[str] = field(default_factory=list)
    ledger_refs: list[str] = field(default_factory=list)
    context_projection_refs: list[str] = field(default_factory=list)
    artifact_refs: list[str] = field(default_factory=list)
    metric_refs: list[str] = field(default_factory=list)
    failure_refs: list[str] = field(default_factory=list)
    execution_report_refs: list[str] = field(default_factory=list)
    observation_refs: list[str] = field(default_factory=list)
    step_records: list[KernelStepInspection] = field(default_factory=list)
    run_event_count: int = 0
    ledger_event_count: int = 0
    stop_reason: str = ""
    flow_result_metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "flow_result_ref": self.flow_result_ref,
            "flow_id": self.flow_id,
            "run_id": self.run_id,
            "status": self.status,
            "contract_ref": self.contract_ref,
            "contract_hash": self.contract_hash,
            "flow_ledger_ref": self.flow_ledger_ref,
            "run_events_ref": self.run_events_ref,
            "run_snapshot_ref": self.run_snapshot_ref,
            "snapshot_status": self.snapshot_status,
            "current_step_id": self.current_step_id,
            "current_role": self.current_role,
            "latest_event_id": self.latest_event_id,
            "latest_event_kind": self.latest_event_kind,
            "latest_event_status": self.latest_event_status,
            "last_safe_point_ref": self.last_safe_point_ref,
            "pending_user_event_count": self.pending_user_event_count,
            "step_record_refs": list(self.step_record_refs),
            "missing_step_record_refs": list(self.missing_step_record_refs),
            "decision_refs": list(self.decision_refs),
            "final_artifact_refs": list(self.final_artifact_refs),
            "ledger_refs": list(self.ledger_refs),
            "context_projection_refs": list(self.context_projection_refs),
            "artifact_refs": list(self.artifact_refs),
            "metric_refs": list(self.metric_refs),
            "failure_refs": list(self.failure_refs),
            "execution_report_refs": list(self.execution_report_refs),
            "observation_refs": list(self.observation_refs),
            "step_records": [record.to_dict() for record in self.step_records],
            "run_event_count": self.run_event_count,
            "ledger_event_count": self.ledger_event_count,
            "stop_reason": self.stop_reason,
            "flow_result_metadata": dict(self.flow_result_metadata),
        }
        return dict(assert_refs_only_payload(ensure_json_value(payload, "kernel_run_inspection"), "kernel_run_inspection"))


def inspect_kernel_run(workspace: str | Path, flow_result_ref: str) -> KernelRunInspection:
    """Inspect one Kernel run through refs-only records.

    The flow result is the authority for run identity and final status. Snapshot
    and event refs are optional so older or partially written runs remain
    inspectable.
    """

    safe_flow_result_ref = validate_ref(flow_result_ref, "kernel_run_inspection.flow_result_ref")
    flow_result = FlowResult.from_dict(read_json_ref(workspace, safe_flow_result_ref))
    run_events_ref = _metadata_ref(flow_result.metadata, "run_events_ref")
    run_snapshot_ref = _metadata_ref(flow_result.metadata, "run_snapshot_ref")
    flow_ledger_ref = _flow_ledger_ref(flow_result.ledger_refs)

    run_events = _read_run_events_if_present(workspace, run_events_ref, flow_result.run_id)
    run_snapshot = _read_run_snapshot_if_present(workspace, run_snapshot_ref)
    flow_ledger_events = _read_flow_ledger_if_present(workspace, flow_ledger_ref)

    step_records: list[KernelStepInspection] = []
    missing_step_record_refs: list[str] = []
    for step_record_ref in flow_result.step_record_refs:
        if not ref_exists(workspace, step_record_ref):
            missing_step_record_refs.append(step_record_ref)
            continue
        step_record = StepRecord.from_dict(read_json_ref(workspace, step_record_ref))
        step_records.append(KernelStepInspection.from_record(step_record_ref, step_record))

    latest_event = run_events[-1] if run_events else None
    context_projection_refs = _dedupe_refs(
        [
            *_snapshot_refs(run_snapshot, "context_projection_refs"),
            *(record.context_projection_ref for record in step_records if record.context_projection_ref),
        ]
    )
    artifact_refs = _dedupe_refs(
        [
            *_snapshot_refs(run_snapshot, "artifact_refs"),
            *flow_result.final_artifact_refs,
            *(ref for record in step_records for ref in record.output_refs),
        ]
    )
    metric_refs = _dedupe_refs(
        [
            *_snapshot_refs(run_snapshot, "metric_refs"),
            *(ref for record in step_records for ref in record.metric_refs),
        ]
    )
    failure_refs = _dedupe_refs(ref for record in step_records for ref in record.failure_refs)
    execution_report_refs = _dedupe_refs(
        record.execution_report_ref for record in step_records if record.execution_report_ref
    )
    observation_refs = _dedupe_refs(
        ref
        for ref in [run_events_ref, run_snapshot_ref, _snapshot_text(run_snapshot, "last_safe_point_ref")]
        if ref
    )

    return KernelRunInspection(
        flow_result_ref=safe_flow_result_ref,
        flow_id=flow_result.flow_id,
        run_id=flow_result.run_id,
        status=flow_result.status,
        contract_ref=flow_result.contract_ref,
        contract_hash=flow_result.contract_hash,
        flow_ledger_ref=flow_ledger_ref,
        run_events_ref=run_events_ref,
        run_snapshot_ref=run_snapshot_ref,
        snapshot_status=_snapshot_status(run_snapshot),
        current_step_id=_snapshot_text(run_snapshot, "current_step_id"),
        current_role=_snapshot_text(run_snapshot, "current_role"),
        latest_event_id=latest_event.event_id if latest_event else "",
        latest_event_kind=latest_event.kind.value if latest_event else "",
        latest_event_status=latest_event.status if latest_event else "",
        last_safe_point_ref=_snapshot_text(run_snapshot, "last_safe_point_ref"),
        pending_user_event_count=run_snapshot.pending_user_event_count if run_snapshot else 0,
        step_record_refs=list(flow_result.step_record_refs),
        missing_step_record_refs=missing_step_record_refs,
        decision_refs=list(flow_result.decision_refs),
        final_artifact_refs=list(flow_result.final_artifact_refs),
        ledger_refs=list(flow_result.ledger_refs),
        context_projection_refs=context_projection_refs,
        artifact_refs=artifact_refs,
        metric_refs=metric_refs,
        failure_refs=failure_refs,
        execution_report_refs=execution_report_refs,
        observation_refs=observation_refs,
        step_records=step_records,
        run_event_count=len(run_events),
        ledger_event_count=len(flow_ledger_events),
        stop_reason=_metadata_text(flow_result.metadata, "stop_reason"),
        flow_result_metadata=_safe_flow_result_metadata(flow_result.metadata),
    )


def _read_run_events_if_present(workspace: str | Path, events_ref: str, run_id: str) -> list[RunEvent]:
    if not events_ref or not ref_exists(workspace, events_ref):
        return []
    return read_run_events(workspace, run_id=run_id, events_ref=events_ref)


def _read_run_snapshot_if_present(workspace: str | Path, snapshot_ref: str) -> RunSnapshot | None:
    if not snapshot_ref or not ref_exists(workspace, snapshot_ref):
        return None
    return read_run_snapshot(workspace, snapshot_ref=snapshot_ref)


def _read_flow_ledger_if_present(workspace: str | Path, ledger_ref: str) -> list[FlowLedgerEvent]:
    if not ledger_ref or not ref_exists(workspace, ledger_ref):
        return []
    events: list[FlowLedgerEvent] = []
    for line in resolve_workspace_ref(workspace, ledger_ref).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if not isinstance(payload, Mapping):
            raise ContractValidationError("kernel flow ledger record must be a JSON object")
        events.append(FlowLedgerEvent.from_dict(payload))
    return events


def _snapshot_refs(snapshot: RunSnapshot | None, field_name: str) -> list[str]:
    if snapshot is None:
        return []
    value = getattr(snapshot, field_name)
    return list(value) if isinstance(value, list) else []


def _snapshot_text(snapshot: RunSnapshot | None, field_name: str) -> str:
    if snapshot is None:
        return ""
    value = getattr(snapshot, field_name)
    return value if isinstance(value, str) else ""


def _snapshot_status(snapshot: RunSnapshot | None) -> str:
    if snapshot is None:
        return ""
    status = snapshot.status
    return status.value if hasattr(status, "value") else str(status)


def _metadata_ref(metadata: Mapping[str, Any], key: str) -> str:
    value = metadata.get(key)
    if value is None or value == "":
        return ""
    return validate_ref(value, f"kernel_run_inspection.{key}")


def _metadata_text(metadata: Mapping[str, Any], key: str) -> str:
    value = metadata.get(key)
    return value if isinstance(value, str) else ""


def _safe_flow_result_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in ("max_steps", "executed_steps", "projection_count"):
        value = metadata.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            result[key] = value
    for key in ("flow_execution_id", "stop_reason"):
        value = metadata.get(key)
        if isinstance(value, str) and value and _is_safe_token(value):
            result[key] = value
    for key in ("run_events_ref", "run_snapshot_ref"):
        value = metadata.get(key)
        if isinstance(value, str) and value:
            result[key] = validate_ref(value, f"kernel_run_inspection.{key}")
    return result


def _is_safe_token(value: str) -> bool:
    try:
        validate_ref(value, "kernel_run_inspection.metadata_token")
    except ContractValidationError:
        return False
    return "/" not in value and "\\" not in value and value not in {".", ".."}


def _flow_ledger_ref(refs: list[str]) -> str:
    for ref in refs:
        if ref.endswith(".jsonl"):
            return ref
    return ""


def _dedupe_refs(refs: Any) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for ref in refs:
        if not ref:
            continue
        safe_ref = validate_ref(ref, "kernel_run_inspection.ref")
        if safe_ref not in seen:
            result.append(safe_ref)
            seen.add(safe_ref)
    return result
