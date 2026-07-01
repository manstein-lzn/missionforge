"""Refs-only Kernel run inspection helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import json
from typing import Any, Mapping

from ..contracts import ContractValidationError, assert_refs_only_payload, ensure_json_value, validate_ref
from ..context import ContextView, ToolObservation
from ..context_engine import ContextThrashDiagnostics
from ..observation import RunEvent, RunSnapshot, read_run_events, read_run_snapshot
from .contracts import FlowLedgerEvent, FlowResult, StepRecord
from .io import RefStoreTarget, read_json_ref, read_jsonl_ref, ref_exists


_USAGE_KEYS = (
    "total_tokens",
    "input_tokens",
    "output_tokens",
    "cache_read_tokens",
    "cache_write_tokens",
    "tool_call_count",
    "tool_error_count",
    "provider_reported_cost_usd",
)

_CONTEXT_ENGINE_REF_KEYS = (
    "context_source_snapshot_ref",
    "context_epoch_ref",
    "context_cache_layout_ref",
    "context_pressure_ref",
    "context_checkpoint_ref",
    "context_turn_safe_point_ref",
    "context_turn_boundary_ref",
    "context_compile_result_ref",
    "context_package_ref",
    "post_turn_context_projection_ref",
    "post_turn_context_compile_result_ref",
    "post_turn_context_package_ref",
)


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
    context_engine_refs: list[str] = field(default_factory=list)
    context_thrash_diagnostics_refs: list[str] = field(default_factory=list)
    metric_refs: list[str] = field(default_factory=list)
    runtime_refs: list[str] = field(default_factory=list)
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
            context_engine_refs=_metadata_context_engine_refs(record.metadata),
            context_thrash_diagnostics_refs=_metadata_refs(record.metadata, "context_thrash_diagnostics_refs"),
            metric_refs=list(record.metric_refs),
            runtime_refs=_metadata_refs(record.metadata, "runtime_refs"),
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
            "context_engine_refs": list(self.context_engine_refs),
            "context_thrash_diagnostics_refs": list(self.context_thrash_diagnostics_refs),
            "metric_refs": list(self.metric_refs),
            "runtime_refs": list(self.runtime_refs),
            "failure_refs": list(self.failure_refs),
        }
        return dict(assert_refs_only_payload(payload, "kernel_step_inspection"))


@dataclass(frozen=True)
class KernelUsageInspection:
    """Refs-only token/tool-cost summary aggregated from metric refs."""

    metric_refs: list[str] = field(default_factory=list)
    total_tokens: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    tool_call_count: int = 0
    tool_error_count: int = 0
    provider_reported_cost_usd: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "metric_refs": list(self.metric_refs),
            "total_tokens": self.total_tokens,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_write_tokens": self.cache_write_tokens,
            "tool_call_count": self.tool_call_count,
            "tool_error_count": self.tool_error_count,
            "provider_reported_cost_usd": self.provider_reported_cost_usd,
        }
        return dict(assert_refs_only_payload(payload, "kernel_usage_inspection"))


@dataclass(frozen=True)
class KernelContextInspection:
    """Refs-only context projection summary."""

    context_projection_refs: list[str] = field(default_factory=list)
    context_engine_refs: list[str] = field(default_factory=list)
    stable_segment_count: int = 0
    semi_stable_segment_count: int = 0
    volatile_segment_count: int = 0
    omitted_segment_count: int = 0
    estimated_input_tokens: int = 0
    token_budget: int = 0
    pressure_ratio: float = 0.0
    recommended_action: str = "continue"

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "context_projection_refs": list(self.context_projection_refs),
            "context_engine_refs": list(self.context_engine_refs),
            "stable_segment_count": self.stable_segment_count,
            "semi_stable_segment_count": self.semi_stable_segment_count,
            "volatile_segment_count": self.volatile_segment_count,
            "omitted_segment_count": self.omitted_segment_count,
            "estimated_input_tokens": self.estimated_input_tokens,
            "token_budget": self.token_budget,
            "pressure_ratio": self.pressure_ratio,
            "recommended_action": self.recommended_action,
        }
        return dict(assert_refs_only_payload(payload, "kernel_context_inspection"))


@dataclass(frozen=True)
class KernelToolActivityInspection:
    """Refs-only tool activity summary from runtime refs and observations."""

    tool_observation_refs: list[str] = field(default_factory=list)
    context_thrash_diagnostics_refs: list[str] = field(default_factory=list)
    observed_tool_names: list[str] = field(default_factory=list)
    observation_count: int = 0
    error_count: int = 0
    read_observation_count: int = 0
    repeated_read_count: int = 0
    thrash_recommended_action: str = "continue"
    latest_tool_name: str = ""
    latest_tool_status: str = ""
    latest_source_ref: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "tool_observation_refs": list(self.tool_observation_refs),
            "context_thrash_diagnostics_refs": list(self.context_thrash_diagnostics_refs),
            "observed_tool_names": list(self.observed_tool_names),
            "observation_count": self.observation_count,
            "error_count": self.error_count,
            "read_observation_count": self.read_observation_count,
            "repeated_read_count": self.repeated_read_count,
            "thrash_recommended_action": self.thrash_recommended_action,
            "latest_tool_name": self.latest_tool_name,
            "latest_tool_status": self.latest_tool_status,
            "latest_source_ref": self.latest_source_ref,
        }
        return dict(assert_refs_only_payload(payload, "kernel_tool_activity_inspection"))


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
    latest_event_created_at: str = ""
    latest_event_age_seconds: int = 0
    last_safe_point_ref: str = ""
    last_safe_point_step_id: str = ""
    last_safe_point_status: str = ""
    last_safe_point_event_count: int = 0
    last_safe_point_age_seconds: int = 0
    last_safe_point_details: Mapping[str, Any] = field(default_factory=dict)
    pending_user_event_count: int = 0
    step_record_refs: list[str] = field(default_factory=list)
    missing_step_record_refs: list[str] = field(default_factory=list)
    decision_refs: list[str] = field(default_factory=list)
    final_artifact_refs: list[str] = field(default_factory=list)
    ledger_refs: list[str] = field(default_factory=list)
    context_projection_refs: list[str] = field(default_factory=list)
    context_engine_refs: list[str] = field(default_factory=list)
    artifact_refs: list[str] = field(default_factory=list)
    metric_refs: list[str] = field(default_factory=list)
    failure_refs: list[str] = field(default_factory=list)
    execution_report_refs: list[str] = field(default_factory=list)
    observation_refs: list[str] = field(default_factory=list)
    step_records: list[KernelStepInspection] = field(default_factory=list)
    usage: KernelUsageInspection = field(default_factory=KernelUsageInspection)
    context: KernelContextInspection = field(default_factory=KernelContextInspection)
    tool_activity: KernelToolActivityInspection = field(default_factory=KernelToolActivityInspection)
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
            "latest_event_created_at": self.latest_event_created_at,
            "latest_event_age_seconds": self.latest_event_age_seconds,
            "last_safe_point_ref": self.last_safe_point_ref,
            "last_safe_point_step_id": self.last_safe_point_step_id,
            "last_safe_point_status": self.last_safe_point_status,
            "last_safe_point_event_count": self.last_safe_point_event_count,
            "last_safe_point_age_seconds": self.last_safe_point_age_seconds,
            "last_safe_point_details": dict(self.last_safe_point_details),
            "pending_user_event_count": self.pending_user_event_count,
            "step_record_refs": list(self.step_record_refs),
            "missing_step_record_refs": list(self.missing_step_record_refs),
            "decision_refs": list(self.decision_refs),
            "final_artifact_refs": list(self.final_artifact_refs),
            "ledger_refs": list(self.ledger_refs),
            "context_projection_refs": list(self.context_projection_refs),
            "context_engine_refs": list(self.context_engine_refs),
            "artifact_refs": list(self.artifact_refs),
            "metric_refs": list(self.metric_refs),
            "failure_refs": list(self.failure_refs),
            "execution_report_refs": list(self.execution_report_refs),
            "observation_refs": list(self.observation_refs),
            "step_records": [record.to_dict() for record in self.step_records],
            "usage": self.usage.to_dict(),
            "context": self.context.to_dict(),
            "tool_activity": self.tool_activity.to_dict(),
            "run_event_count": self.run_event_count,
            "ledger_event_count": self.ledger_event_count,
            "stop_reason": self.stop_reason,
            "flow_result_metadata": dict(self.flow_result_metadata),
        }
        return dict(assert_refs_only_payload(ensure_json_value(payload, "kernel_run_inspection"), "kernel_run_inspection"))


def inspect_kernel_run(workspace: RefStoreTarget, flow_result_ref: str) -> KernelRunInspection:
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
    context_engine_refs = _dedupe_refs(ref for record in step_records for ref in record.context_engine_refs)
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
    runtime_refs = _dedupe_refs(ref for record in step_records for ref in record.runtime_refs)
    explicit_thrash_refs = _dedupe_refs(ref for record in step_records for ref in record.context_thrash_diagnostics_refs)
    tool_activity = _inspect_tool_activity(workspace, runtime_refs, explicit_thrash_refs)
    observation_refs = _dedupe_refs(
        ref
        for ref in [
            run_events_ref,
            run_snapshot_ref,
            _snapshot_text(run_snapshot, "last_safe_point_ref"),
            *tool_activity.tool_observation_refs,
            *tool_activity.context_thrash_diagnostics_refs,
        ]
        if ref
    )
    latest_safe_point = _latest_safe_point_event(run_events)
    last_safe_point_ref = _snapshot_text(run_snapshot, "last_safe_point_ref")

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
        latest_event_created_at=latest_event.created_at if latest_event else "",
        latest_event_age_seconds=_event_age_seconds(latest_event),
        last_safe_point_ref=last_safe_point_ref,
        last_safe_point_step_id=latest_safe_point.step_id if latest_safe_point else "",
        last_safe_point_status=latest_safe_point.status if latest_safe_point else "",
        last_safe_point_event_count=_event_metadata_int(latest_safe_point, "pending_user_event_count"),
        last_safe_point_age_seconds=_event_age_seconds(latest_safe_point),
        last_safe_point_details=_safe_point_details(latest_safe_point, last_safe_point_ref),
        pending_user_event_count=run_snapshot.pending_user_event_count if run_snapshot else 0,
        step_record_refs=list(flow_result.step_record_refs),
        missing_step_record_refs=missing_step_record_refs,
        decision_refs=list(flow_result.decision_refs),
        final_artifact_refs=list(flow_result.final_artifact_refs),
        ledger_refs=list(flow_result.ledger_refs),
        context_projection_refs=context_projection_refs,
        context_engine_refs=context_engine_refs,
        artifact_refs=artifact_refs,
        metric_refs=metric_refs,
        failure_refs=failure_refs,
        execution_report_refs=execution_report_refs,
        observation_refs=observation_refs,
        step_records=step_records,
        usage=_inspect_usage(workspace, metric_refs),
        context=_inspect_context(workspace, context_projection_refs, runtime_refs, context_engine_refs),
        tool_activity=tool_activity,
        run_event_count=len(run_events),
        ledger_event_count=len(flow_ledger_events),
        stop_reason=_metadata_text(flow_result.metadata, "stop_reason"),
        flow_result_metadata=_safe_flow_result_metadata(flow_result.metadata),
    )


def _read_run_events_if_present(workspace: RefStoreTarget, events_ref: str, run_id: str) -> list[RunEvent]:
    if not events_ref or not ref_exists(workspace, events_ref):
        return []
    return read_run_events(workspace, run_id=run_id, events_ref=events_ref)


def _read_run_snapshot_if_present(workspace: RefStoreTarget, snapshot_ref: str) -> RunSnapshot | None:
    if not snapshot_ref or not ref_exists(workspace, snapshot_ref):
        return None
    return read_run_snapshot(workspace, snapshot_ref=snapshot_ref)


def _read_flow_ledger_if_present(workspace: RefStoreTarget, ledger_ref: str) -> list[FlowLedgerEvent]:
    if not ledger_ref or not ref_exists(workspace, ledger_ref):
        return []
    events: list[FlowLedgerEvent] = []
    for payload in read_jsonl_ref(workspace, ledger_ref):
        if not isinstance(payload, Mapping):
            raise ContractValidationError("kernel flow ledger record must be a JSON object")
        events.append(FlowLedgerEvent.from_dict(payload))
    return events


def _inspect_usage(workspace: RefStoreTarget, metric_refs: list[str]) -> KernelUsageInspection:
    totals: dict[str, int | float] = {key: 0 for key in _USAGE_KEYS}
    safe_metric_refs: list[str] = []
    for metric_ref in metric_refs:
        if not ref_exists(workspace, metric_ref):
            continue
        safe_metric_refs.append(metric_ref)
        try:
            payload = read_json_ref(workspace, metric_ref)
        except (ContractValidationError, OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, Mapping):
            continue
        totals["total_tokens"] = int(totals["total_tokens"]) + _non_negative_int(
            payload.get("total_tokens", payload.get("token_count"))
        )
        totals["input_tokens"] = int(totals["input_tokens"]) + _non_negative_int(payload.get("input_tokens"))
        totals["output_tokens"] = int(totals["output_tokens"]) + _non_negative_int(payload.get("output_tokens"))
        totals["cache_read_tokens"] = int(totals["cache_read_tokens"]) + _non_negative_int(
            payload.get("cache_read_tokens")
        )
        totals["cache_write_tokens"] = int(totals["cache_write_tokens"]) + _non_negative_int(
            payload.get("cache_write_tokens")
        )
        totals["tool_call_count"] = int(totals["tool_call_count"]) + _non_negative_int(
            payload.get("tool_call_count", payload.get("tool_calls"))
        )
        totals["tool_error_count"] = int(totals["tool_error_count"]) + _non_negative_int(
            payload.get("tool_error_count")
        )
        totals["provider_reported_cost_usd"] = float(totals["provider_reported_cost_usd"]) + _non_negative_float(
            payload.get("provider_reported_cost_usd")
        )
    return KernelUsageInspection(
        metric_refs=_dedupe_refs(safe_metric_refs),
        total_tokens=int(totals["total_tokens"]),
        input_tokens=int(totals["input_tokens"]),
        output_tokens=int(totals["output_tokens"]),
        cache_read_tokens=int(totals["cache_read_tokens"]),
        cache_write_tokens=int(totals["cache_write_tokens"]),
        tool_call_count=int(totals["tool_call_count"]),
        tool_error_count=int(totals["tool_error_count"]),
        provider_reported_cost_usd=round(float(totals["provider_reported_cost_usd"]), 12),
    )


def _inspect_context(
    workspace: RefStoreTarget,
    context_projection_refs: list[str],
    runtime_refs: list[str],
    context_engine_refs: list[str],
) -> KernelContextInspection:
    stable = 0
    semi_stable = 0
    volatile = 0
    omitted = 0
    estimated = 0
    token_budget = 0
    pressure_ratio = 0.0
    recommended_action = "continue"
    engine_pressure = _context_engine_pressure(workspace, context_engine_refs)
    for ref in context_projection_refs:
        if not ref_exists(workspace, ref):
            continue
        try:
            payload = read_json_ref(workspace, ref)
        except (ContractValidationError, OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, Mapping):
            continue
        try:
            view = ContextView.from_dict(payload)
        except ContractValidationError:
            estimated += _non_negative_int(payload.get("estimated_input_tokens"))
            token_budget = max(token_budget, _context_budget(payload))
            ratio = _non_negative_float(payload.get("pressure_ratio"))
            if ratio >= pressure_ratio:
                pressure_ratio = ratio
                recommended_action = _safe_action(payload.get("recommended_action"))
            continue
        stable += len(view.stable_prefix)
        semi_stable += len(view.semi_stable_context)
        volatile += len(view.volatile_tail)
        omitted += len(view.omitted_segments)
        estimated += sum(segment.token_estimate for segment in view.all_segments)
        if view.token_budget is not None:
            token_budget = max(token_budget, view.token_budget)
    if engine_pressure is not None:
        estimated = engine_pressure["estimated_input_tokens"]
        token_budget = engine_pressure["token_budget"]
        pressure_ratio = engine_pressure["pressure_ratio"]
        recommended_action = engine_pressure["recommended_action"]
    else:
        for ref in runtime_refs:
            if not ref.endswith("/context/projection.json") and not ref.endswith("context/projection.json"):
                continue
            if not ref_exists(workspace, ref):
                continue
            try:
                payload = read_json_ref(workspace, ref)
            except (ContractValidationError, OSError, json.JSONDecodeError):
                continue
            if isinstance(payload, Mapping):
                estimated += _non_negative_int(payload.get("estimated_input_tokens"))
                token_budget = max(token_budget, _context_budget(payload))
                ratio = _non_negative_float(payload.get("pressure_ratio"))
                if ratio >= pressure_ratio:
                    pressure_ratio = ratio
                    recommended_action = _safe_action(payload.get("recommended_action"))
    if token_budget == 0 and estimated > 0:
        token_budget = estimated
    if pressure_ratio == 0.0 and token_budget > 0:
        pressure_ratio = min(1.0, estimated / token_budget)
    return KernelContextInspection(
        context_projection_refs=list(context_projection_refs),
        context_engine_refs=list(context_engine_refs),
        stable_segment_count=stable,
        semi_stable_segment_count=semi_stable,
        volatile_segment_count=volatile,
        omitted_segment_count=omitted,
        estimated_input_tokens=estimated,
        token_budget=token_budget,
        pressure_ratio=round(pressure_ratio, 6),
        recommended_action=recommended_action,
    )


def _context_engine_pressure(workspace: RefStoreTarget, context_engine_refs: list[str]) -> dict[str, Any] | None:
    selected: dict[str, Any] | None = None
    for ref in context_engine_refs:
        if not ref.endswith("/context/pressure.json") or not ref_exists(workspace, ref):
            continue
        try:
            payload = read_json_ref(workspace, ref)
        except (ContractValidationError, OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, Mapping):
            continue
        pressure = {
            "estimated_input_tokens": _non_negative_int(payload.get("estimated_input_tokens")),
            "token_budget": _context_budget(payload),
            "pressure_ratio": _non_negative_float(payload.get("pressure_ratio")),
            "recommended_action": _safe_action(payload.get("recommended_action")),
        }
        if selected is None or pressure["pressure_ratio"] >= selected["pressure_ratio"]:
            selected = pressure
    return selected


def _inspect_tool_activity(
    workspace: RefStoreTarget,
    runtime_refs: list[str],
    explicit_thrash_refs: list[str] | None = None,
) -> KernelToolActivityInspection:
    observation_refs = _dedupe_refs(ref for ref in runtime_refs if ref.endswith("tool_observations.jsonl"))
    thrash_refs = _dedupe_refs([
        *(explicit_thrash_refs or []),
        *(ref for ref in runtime_refs if ref.endswith("context/thrash_diagnostics.json")),
    ])
    observations: list[ToolObservation] = []
    for ref in observation_refs:
        if not ref_exists(workspace, ref):
            continue
        for payload in _read_jsonl_ref(workspace, ref):
            try:
                observations.append(ToolObservation.from_dict(payload))
            except ContractValidationError:
                continue
    thrash_diagnostics: list[ContextThrashDiagnostics] = []
    for ref in thrash_refs:
        if not ref_exists(workspace, ref):
            continue
        try:
            thrash_diagnostics.append(ContextThrashDiagnostics.from_dict(read_json_ref(workspace, ref)))
        except (ContractValidationError, OSError, json.JSONDecodeError):
            continue
    latest = observations[-1] if observations else None
    repeated_read_count = sum(len(diagnostics.repeated_observation_ids) for diagnostics in thrash_diagnostics)
    read_observation_count = sum(len(diagnostics.observations) for diagnostics in thrash_diagnostics)
    thrash_action = "prepare_checkpoint" if repeated_read_count else "continue"
    return KernelToolActivityInspection(
        tool_observation_refs=observation_refs,
        context_thrash_diagnostics_refs=thrash_refs,
        observed_tool_names=sorted({observation.tool_name for observation in observations}),
        observation_count=len(observations),
        error_count=sum(1 for observation in observations if observation.status.value == "error"),
        read_observation_count=read_observation_count,
        repeated_read_count=repeated_read_count,
        thrash_recommended_action=thrash_action,
        latest_tool_name=latest.tool_name if latest else "",
        latest_tool_status=latest.status.value if latest else "",
        latest_source_ref=latest.source_ref or latest.raw_ref or "" if latest else "",
    )


def _read_jsonl_ref(workspace: RefStoreTarget, ref: str) -> list[Mapping[str, Any]]:
    if not ref_exists(workspace, ref):
        return []
    result: list[Mapping[str, Any]] = []
    for payload in read_jsonl_ref(workspace, ref):
        if isinstance(payload, Mapping):
            result.append(payload)
    return result


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


def _metadata_refs(metadata: Mapping[str, Any], key: str) -> list[str]:
    value = metadata.get(key)
    if not isinstance(value, list):
        return []
    return _dedupe_refs(value)


def _metadata_context_engine_refs(metadata: Mapping[str, Any]) -> list[str]:
    return _dedupe_refs(_metadata_ref(metadata, key) for key in _CONTEXT_ENGINE_REF_KEYS)


def _latest_safe_point_event(events: list[RunEvent]) -> RunEvent | None:
    for event in reversed(events):
        if event.kind.value == "safe_point_reached":
            return event
    return None


def _safe_point_details(event: RunEvent | None, safe_point_ref: str) -> dict[str, Any]:
    if event is None and not safe_point_ref:
        return {}
    payload: dict[str, Any] = {}
    if safe_point_ref:
        payload["ref"] = safe_point_ref
    if event is not None:
        payload["step_id"] = event.step_id
        payload["status"] = event.status
        payload["event_count"] = _event_metadata_int(event, "pending_user_event_count")
        payload["event_id"] = event.event_id
    return payload


def _event_metadata_int(event: RunEvent | None, key: str) -> int:
    if event is None:
        return 0
    value = event.metadata.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def _event_age_seconds(event: RunEvent | None) -> int:
    if event is None:
        return 0
    try:
        created_at = datetime.fromisoformat(event.created_at.replace("Z", "+00:00"))
    except ValueError:
        return 0
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    return max(int((datetime.now(UTC) - created_at.astimezone(UTC)).total_seconds()), 0)


def _context_budget(payload: Mapping[str, Any]) -> int:
    value = payload.get("token_budget")
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    context_budget = payload.get("context_budget")
    if isinstance(context_budget, Mapping):
        for key in ("usable_input_budget", "model_context_window"):
            nested = context_budget.get(key)
            if isinstance(nested, int) and not isinstance(nested, bool) and nested > 0:
                return nested
    window = payload.get("model_context_window")
    return window if isinstance(window, int) and not isinstance(window, bool) and window > 0 else 0


def _safe_action(value: Any) -> str:
    if isinstance(value, str) and value in {
        "continue",
        "prepare_checkpoint",
        "checkpoint_before_next_turn",
    }:
        return value
    return "continue"


def _non_negative_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return max(value, 0)
    if isinstance(value, float):
        return max(int(value), 0)
    return 0


def _non_negative_float(value: Any) -> float:
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, (int, float)):
        return max(float(value), 0.0)
    return 0.0


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
