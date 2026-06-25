"""Structured Kernel route decision helpers."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping

from ..contracts import ContractValidationError, assert_refs_only_payload, validate_ref
from .contracts import Flow, FlowStop, KernelValidationError, Step
from .io import read_json_ref


@dataclass(frozen=True)
class KernelRouteDecision:
    """Refs-only route decision derived from one structured decision artifact."""

    step_id: str
    decision_ref: str
    route_value: str
    target_kind: str
    route_target: str = ""
    target_step_id: str = ""
    terminal_status: str = ""
    route_key: str = ""
    error_type: str = ""

    @property
    def is_terminal(self) -> bool:
        return self.target_kind == "stop"

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "step_id": self.step_id,
            "decision_ref": self.decision_ref,
            "route_value": self.route_value,
            "target_kind": self.target_kind,
            "route_target": self.route_target,
            "target_step_id": self.target_step_id,
            "terminal_status": self.terminal_status,
            "route_key": self.route_key,
            "error_type": self.error_type,
            "is_terminal": self.is_terminal,
        }
        return dict(assert_refs_only_payload(payload, "kernel_route_decision"))


def resolve_step_route(flow: Flow, step: Step, workspace: str | Path) -> KernelRouteDecision:
    """Resolve the next route from a step's structured decision artifact."""

    flow.validate()
    step.validate()
    if step.route_on is None:
        return KernelRouteDecision(
            step_id=step.id,
            decision_ref="",
            route_value="",
            target_kind="invalid",
            route_target="blocked",
            error_type="missing_route_on",
        )
    try:
        route_value = route_value_for_step(workspace, step)
    except (OSError, json.JSONDecodeError, ContractValidationError, KernelValidationError) as exc:
        return KernelRouteDecision(
            step_id=step.id,
            decision_ref=step.route_on,
            route_value="invalid",
            target_kind="invalid",
            route_target="blocked",
            route_key=f"{step.id}.invalid",
            error_type=_safe_error_type(type(exc).__name__),
        )
    route_key = f"{step.id}.{route_value}"
    target = flow.routes.get(route_key)
    if target is None:
        return KernelRouteDecision(
            step_id=step.id,
            decision_ref=step.route_on,
            route_value=route_value,
            target_kind="unrouted",
            route_target="unrouted",
            route_key=route_key,
        )
    if isinstance(target, FlowStop):
        return KernelRouteDecision(
            step_id=step.id,
            decision_ref=step.route_on,
            route_value=route_value,
            target_kind="stop",
            route_target=target.status,
            terminal_status=target.status,
            route_key=route_key,
        )
    target_step_id = _safe_route_segment(target, "kernel_route_decision.target_step_id")
    return KernelRouteDecision(
        step_id=step.id,
        decision_ref=step.route_on,
        route_value=route_value,
        target_kind="step",
        route_target=target_step_id,
        target_step_id=target_step_id,
        route_key=route_key,
    )


def route_value_for_step(workspace: str | Path, step: Step) -> str:
    """Read and validate a step route value from its decision artifact."""

    if step.route_on is None:
        raise KernelValidationError("kernel_flow route step must declare route_on")
    payload = read_json_ref(workspace, step.route_on)
    if not isinstance(payload, Mapping):
        raise KernelValidationError("kernel_flow decision artifact must be a JSON object")
    values: list[str] = []
    for field in step.route_fields:
        value = payload.get(field)
        if value is None:
            raise KernelValidationError(f"kernel_flow decision artifact missing route field: {field}")
        if not isinstance(value, str) or not value.strip():
            raise KernelValidationError(f"kernel_flow decision artifact route field must be a string: {field}")
        values.append(_safe_route_segment(value.strip(), f"kernel_flow decision artifact route field: {field}"))
    return "+".join(values)


def _safe_route_segment(value: str, field_name: str) -> str:
    route_value = validate_ref(value, field_name)
    if "/" in route_value or "\\" in route_value or route_value in {".", ".."}:
        raise KernelValidationError(f"{field_name} must be a single safe route segment")
    return route_value


def _safe_error_type(value: str) -> str:
    try:
        return _safe_route_segment(value, "kernel_route_decision.error_type")
    except (ContractValidationError, KernelValidationError):
        return "RouteError"
