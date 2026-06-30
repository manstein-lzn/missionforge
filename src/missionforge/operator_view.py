"""Refs-only operator views for MissionForge runs."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

from .contracts import assert_refs_only_payload, ensure_json_value, validate_ref
from .kernel import KernelRunInspection, inspect_kernel_run


@dataclass(frozen=True)
class MissionRunView:
    """Refs-only operator view over one Kernel run."""

    flow_id: str
    run_id: str
    status: str
    flow_result_ref: str
    contract_ref: str
    contract_hash: str
    snapshot_status: str = ""
    current_step_id: str = ""
    current_role: str = ""
    latest_event_kind: str = ""
    latest_event_status: str = ""
    latest_event_age_seconds: int = 0
    last_safe_point_ref: str = ""
    last_safe_point_step_id: str = ""
    last_safe_point_status: str = ""
    last_safe_point_age_seconds: int = 0
    last_safe_point_details: dict[str, Any] = field(default_factory=dict)
    pending_user_event_count: int = 0
    step_record_refs: list[str] = field(default_factory=list)
    artifact_refs: list[str] = field(default_factory=list)
    decision_refs: list[str] = field(default_factory=list)
    observation_refs: list[str] = field(default_factory=list)
    context_engine_refs: list[str] = field(default_factory=list)
    metric_refs: list[str] = field(default_factory=list)
    failure_refs: list[str] = field(default_factory=list)
    run_event_count: int = 0
    ledger_event_count: int = 0
    stop_reason: str = ""
    usage_totals: dict[str, Any] = field(default_factory=dict)
    context_pressure: dict[str, Any] = field(default_factory=dict)
    tool_activity_refs: list[str] = field(default_factory=list)
    tool_activity: dict[str, Any] = field(default_factory=dict)
    missing_step_record_refs: list[str] = field(default_factory=list)
    steps: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_inspection(cls, inspection: KernelRunInspection) -> "MissionRunView":
        return cls(
            flow_id=inspection.flow_id,
            run_id=inspection.run_id,
            status=inspection.status,
            flow_result_ref=inspection.flow_result_ref,
            contract_ref=inspection.contract_ref,
            contract_hash=inspection.contract_hash,
            snapshot_status=inspection.snapshot_status,
            current_step_id=inspection.current_step_id,
            current_role=inspection.current_role,
            latest_event_kind=inspection.latest_event_kind,
            latest_event_status=inspection.latest_event_status,
            latest_event_age_seconds=inspection.latest_event_age_seconds,
            last_safe_point_ref=inspection.last_safe_point_ref,
            last_safe_point_step_id=inspection.last_safe_point_step_id,
            last_safe_point_status=inspection.last_safe_point_status,
            last_safe_point_age_seconds=inspection.last_safe_point_age_seconds,
            last_safe_point_details=dict(inspection.last_safe_point_details),
            pending_user_event_count=inspection.pending_user_event_count,
            step_record_refs=list(inspection.step_record_refs),
            artifact_refs=list(inspection.artifact_refs),
            decision_refs=list(inspection.decision_refs),
            observation_refs=list(inspection.observation_refs),
            context_engine_refs=list(inspection.context_engine_refs),
            metric_refs=list(inspection.metric_refs),
            failure_refs=list(inspection.failure_refs),
            run_event_count=inspection.run_event_count,
            ledger_event_count=inspection.ledger_event_count,
            stop_reason=inspection.stop_reason,
            usage_totals=_usage_totals_from_inspection(inspection),
            context_pressure=_context_pressure_from_inspection(inspection),
            tool_activity_refs=list(inspection.tool_activity.tool_observation_refs),
            tool_activity=inspection.tool_activity.to_dict(),
            missing_step_record_refs=list(inspection.missing_step_record_refs),
            steps=[
                {
                    "step_id": step.step_id,
                    "status": step.status,
                    "step_record_ref": step.step_record_ref,
                    "output_refs": list(step.output_refs),
                    "context_projection_ref": step.context_projection_ref,
                    "context_engine_refs": list(step.context_engine_refs),
                    "permission_manifest_ref": step.permission_manifest_ref,
                    "execution_report_ref": step.execution_report_ref,
                    "metric_refs": list(step.metric_refs),
                    "failure_refs": list(step.failure_refs),
                }
                for step in inspection.step_records
            ],
        )

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "flow_id": self.flow_id,
            "run_id": self.run_id,
            "status": self.status,
            "flow_result_ref": self.flow_result_ref,
            "contract_ref": self.contract_ref,
            "contract_hash": self.contract_hash,
            "snapshot_status": self.snapshot_status,
            "current_step_id": self.current_step_id,
            "current_role": self.current_role,
            "latest_event_kind": self.latest_event_kind,
            "latest_event_status": self.latest_event_status,
            "latest_event_age_seconds": self.latest_event_age_seconds,
            "last_safe_point_ref": self.last_safe_point_ref,
            "last_safe_point_step_id": self.last_safe_point_step_id,
            "last_safe_point_status": self.last_safe_point_status,
            "last_safe_point_age_seconds": self.last_safe_point_age_seconds,
            "last_safe_point_details": dict(self.last_safe_point_details),
            "pending_user_event_count": self.pending_user_event_count,
            "step_record_refs": list(self.step_record_refs),
            "artifact_refs": list(self.artifact_refs),
            "decision_refs": list(self.decision_refs),
            "observation_refs": list(self.observation_refs),
            "context_engine_refs": list(self.context_engine_refs),
            "metric_refs": list(self.metric_refs),
            "failure_refs": list(self.failure_refs),
            "run_event_count": self.run_event_count,
            "ledger_event_count": self.ledger_event_count,
            "stop_reason": self.stop_reason,
            "usage_totals": dict(self.usage_totals),
            "context_pressure": dict(self.context_pressure),
            "tool_activity_refs": list(self.tool_activity_refs),
            "tool_activity": dict(self.tool_activity),
            "missing_step_record_refs": list(self.missing_step_record_refs),
            "steps": [dict(step) for step in self.steps],
        }
        return dict(assert_refs_only_payload(ensure_json_value(payload, "mission_run_view"), "mission_run_view"))


def build_mission_run_view(workspace: str | Path, *, flow_result_ref: str) -> MissionRunView:
    """Build a refs-only status view for one recorded Kernel run."""

    safe_ref = validate_ref(flow_result_ref, "mission_run_view.flow_result_ref")
    return MissionRunView.from_inspection(inspect_kernel_run(workspace, safe_ref))


def render_mission_run_view(view: MissionRunView) -> str:
    """Render a compact human-readable status view without artifact bodies."""

    current = view.current_step_id or "<none>"
    current_role = view.current_role or "<none>"
    latest = view.latest_event_kind or "<none>"
    latest_status = view.latest_event_status or "<none>"
    safe_point = view.last_safe_point_ref or "<none>"
    lines = [
        "MissionForge run",
        f"  flow: {view.flow_id}",
        f"  run: {view.run_id}",
        f"  status: {view.status}",
        f"  snapshot: {view.snapshot_status or '<none>'}",
        f"  current: {current} ({current_role})",
        f"  latest_event: {latest} status={latest_status}",
        f"  latest_event_age_seconds: {view.latest_event_age_seconds}",
        f"  stop_reason: {view.stop_reason or '<none>'}",
        f"  pending_user_events: {view.pending_user_event_count}",
        f"  last_safe_point_ref: {safe_point}",
        f"  last_safe_point_step_id: {view.last_safe_point_step_id or '<none>'}",
        f"  last_safe_point_status: {view.last_safe_point_status or '<none>'}",
        f"  last_safe_point_age_seconds: {view.last_safe_point_age_seconds}",
        f"  steps: {len(view.step_record_refs)} recorded",
        f"  events: {view.run_event_count} run, {view.ledger_event_count} ledger",
        "  refs:",
        f"    flow_result: {view.flow_result_ref}",
        f"    contract: {view.contract_ref}",
    ]
    if view.usage_totals:
        lines.append(
            "  usage: "
            f"input={view.usage_totals.get('input_tokens', 0)} "
            f"cached={view.usage_totals.get('cached_input_tokens', 0)} "
            f"output={view.usage_totals.get('output_tokens', 0)} "
            f"total={view.usage_totals.get('total_tokens', 0)}"
        )
    if view.context_pressure:
        lines.append(
            "  context_pressure: "
            f"ratio={view.context_pressure.get('ratio', '0')} "
            f"used_tokens={view.context_pressure.get('used_tokens', 0)} "
            f"limit_tokens={view.context_pressure.get('limit_tokens', 0)} "
            f"recommended_action={view.context_pressure.get('recommended_action', 'continue')}"
        )
    if view.tool_activity_refs:
        lines.append("  tool_activity_refs:")
        lines.extend(f"    - {ref}" for ref in view.tool_activity_refs)
    if view.tool_activity:
        lines.append(
            "  tool_activity: "
            f"count={view.tool_activity.get('observation_count', 0)} "
            f"errors={view.tool_activity.get('error_count', 0)} "
            f"repeated_reads={view.tool_activity.get('repeated_read_count', 0)} "
            f"latest={view.tool_activity.get('latest_tool_name', '<none>')} "
            f"status={view.tool_activity.get('latest_tool_status', '<none>')}"
        )
    thrash_refs = view.tool_activity.get("context_thrash_diagnostics_refs", []) if view.tool_activity else []
    if isinstance(thrash_refs, list) and thrash_refs:
        lines.append("  context_thrash_diagnostics:")
        lines.extend(f"    - {ref}" for ref in thrash_refs)
    if view.observation_refs:
        lines.append("    observations:")
        lines.extend(f"      - {ref}" for ref in view.observation_refs)
    if view.context_engine_refs:
        lines.append("    context_engine:")
        lines.extend(f"      - {ref}" for ref in view.context_engine_refs)
    if view.artifact_refs:
        lines.append("    artifacts:")
        lines.extend(f"      - {ref}" for ref in view.artifact_refs)
    if view.decision_refs:
        lines.append("    decisions:")
        lines.extend(f"      - {ref}" for ref in view.decision_refs)
    if view.missing_step_record_refs:
        lines.append("    missing_step_records:")
        lines.extend(f"      - {ref}" for ref in view.missing_step_record_refs)
    return "\n".join(lines) + "\n"


def _usage_totals_from_inspection(inspection: KernelRunInspection) -> dict[str, Any]:
    usage = inspection.usage
    has_usage = bool(usage.metric_refs) or any(
        value
        for value in (
            usage.total_tokens,
            usage.input_tokens,
            usage.output_tokens,
            usage.cache_read_tokens,
            usage.cache_write_tokens,
            usage.tool_call_count,
            usage.tool_error_count,
            usage.provider_reported_cost_usd,
        )
    )
    if not has_usage:
        return {}
    total_input = usage.input_tokens + usage.cache_read_tokens
    return {
        "input_tokens": usage.input_tokens,
        "cached_input_tokens": usage.cache_read_tokens,
        "cache_read_tokens": usage.cache_read_tokens,
        "cache_write_tokens": usage.cache_write_tokens,
        "total_input_tokens": total_input,
        "output_tokens": usage.output_tokens,
        "total_tokens": usage.total_tokens,
        "tool_call_count": usage.tool_call_count,
        "tool_error_count": usage.tool_error_count,
        "provider_reported_cost_usd": usage.provider_reported_cost_usd,
    }


def _context_pressure_from_inspection(inspection: KernelRunInspection) -> dict[str, Any]:
    context = inspection.context
    if context.token_budget <= 0 and context.estimated_input_tokens <= 0:
        return {}
    remaining = max(context.token_budget - context.estimated_input_tokens, 0) if context.token_budget else 0
    return {
        "ratio": f"{context.pressure_ratio:.2f}",
        "used_tokens": context.estimated_input_tokens,
        "limit_tokens": context.token_budget,
        "remaining_tokens": remaining,
        "recommended_action": context.recommended_action,
    }

