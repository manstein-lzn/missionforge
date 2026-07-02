"""DeepResearch web runtime controls backed by MissionForge interaction ports."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import missionforge as mf

from .kernel_v2 import deepresearch_kernel_v2_flow_run_id
from .web_common import WEB_POST_MAX_BYTES, WebConsoleResponse, json_response
from .workspace import resolve_workspace_ref


WEB_CONTROL_SCHEMA_VERSION = "missionforge_deepresearch.web_runtime_control_result.v1"
WEB_CONTROL_ALLOWED_ACTIONS = {
    "message",
    "pause",
    "resume",
    "checkpoint",
    "stop_after_current_turn",
    "revise",
    "cancel",
}


def runtime_control_response(
    *,
    workspace: Path,
    request_id: str,
    body: bytes | str,
) -> WebConsoleResponse:
    """Append one runtime control event through the product-neutral ControlPort."""

    try:
        payload = _json_body(body)
        action = _clean(payload.get("action"))
        text = _clean(payload.get("text"))
        event = submit_runtime_control(workspace=workspace, request_id=request_id, action=action, text=text)
        return json_response(
            202,
            {
                "schema_version": WEB_CONTROL_SCHEMA_VERSION,
                "status": "queued",
                "event": _event_summary(event),
                "events_ref": mf.USER_EVENTS_REF,
            },
        )
    except (json.JSONDecodeError, UnicodeDecodeError):
        return json_response(400, {"status": "error", "message": "invalid_json_body"})
    except mf.ContractValidationError as exc:
        return json_response(409, {"status": "error", "message": str(exc)})


def submit_runtime_control(*, workspace: Path, request_id: str, action: str, text: str = "") -> mf.UserEvent:
    """Submit a web runtime control event for a DeepResearch Kernel run."""

    if action not in WEB_CONTROL_ALLOWED_ACTIONS:
        raise mf.ContractValidationError("unsupported runtime control action")
    run_root = resolve_workspace_ref(workspace, _run_ref(request_id))
    control = mf.FileControlPort(mf.FileInteractionPort(run_root))
    run_id = deepresearch_kernel_v2_flow_run_id(request_id)
    if action == "pause":
        return control.pause(run_id=run_id)
    if action == "resume":
        return control.resume(run_id=run_id)
    if action == "checkpoint":
        return control.force_checkpoint(run_id=run_id)
    if action == "stop_after_current_turn":
        return control.stop_after_current_turn(run_id=run_id)
    if action == "cancel":
        return control.cancel(run_id=run_id)
    if action == "revise":
        if not text:
            raise mf.ContractValidationError("revision text is required")
        return control.request_revision(run_id=run_id, text=text)
    if not text:
        raise mf.ContractValidationError("message text is required")
    return control.inject_message(run_id=run_id, text=text)


def _event_summary(event: mf.UserEvent) -> dict[str, str]:
    return {
        "event_id": event.event_id,
        "run_id": event.run_id,
        "target": event.target,
        "kind": event.kind.value,
        "delivery": event.delivery.value,
        "actor": event.actor,
    }


def _json_body(body: bytes | str) -> dict[str, Any]:
    if isinstance(body, bytes):
        if len(body) > WEB_POST_MAX_BYTES:
            raise mf.ContractValidationError("web console request body is too large")
        text = body.decode("utf-8")
    else:
        if len(body.encode("utf-8")) > WEB_POST_MAX_BYTES:
            raise mf.ContractValidationError("web console request body is too large")
        text = body
    payload = json.loads(text or "{}")
    return dict(payload) if isinstance(payload, Mapping) else {}


def _run_ref(request_id: str) -> str:
    if not isinstance(request_id, str) or not request_id.strip():
        raise mf.ContractValidationError("DeepResearch request_id is required")
    return mf.validate_ref(f"runs/{request_id.strip()}", "deepresearch_web_control.run_ref")


def _clean(value: Any) -> str:
    return str(value).strip() if isinstance(value, str) else ""
