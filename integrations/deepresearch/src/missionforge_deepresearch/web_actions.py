"""Web-console actions that mutate DeepResearch projects through product APIs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Mapping

import missionforge as mf

from .frontdesk import (
    FRONTDESK_INITIAL_INPUT_REF,
    approve_frontdesk_requirements,
    read_approved_frontdesk_request,
    run_deepresearch_frontdesk_turn,
)
from .kernel_v2 import KERNEL_V2_RESULT_REF, KERNEL_V2_RUN_STATUS_REF, run_deepresearch_kernel_v2
from .web_common import WEB_POST_MAX_BYTES, WebConsoleResponse, WebFrontDeskConfig, WebKernelConfig, json_response
from .web_tasks import read_or_record_existing_task, start_background_task
from .workspace import resolve_workspace_ref


def frontdesk_message_response(
    *,
    workspace: Path,
    request_id: str,
    body: bytes | str,
    config: WebFrontDeskConfig,
    snapshot_factory: Callable[[Path, str], Mapping[str, Any]],
) -> WebConsoleResponse:
    """Submit a browser message through the FrontDesk PiWorker turn boundary."""

    try:
        payload = json_body(body)
        message = _clean(payload.get("message"))
        initial_input = _clean(payload.get("initial_input"))
        if not message and not initial_input:
            return json_response(400, {"status": "error", "message": "message_required"})
        run_root = resolve_workspace_ref(workspace, _run_ref(request_id))
        has_initial_input = _ref_is_file(run_root, FRONTDESK_INITIAL_INPUT_REF)
        result = run_deepresearch_frontdesk_turn(
            initial_input=initial_input or message if not has_initial_input else None,
            user_message=message or initial_input,
            request_id=request_id,
            workspace=workspace,
            adapter=config.adapter_factory(),
            audience=config.audience,
            language=config.language,
            research_intensity=config.research_intensity,
            live_extension_mode=config.live_extension_mode,
        )
        return json_response(
            200,
            {
                "schema_version": "missionforge_deepresearch.web_console.frontdesk_message_result.v1",
                "status": result.status,
                "result": result.to_dict(),
                "snapshot": snapshot_factory(workspace, request_id),
            },
        )
    except (json.JSONDecodeError, UnicodeDecodeError):
        return json_response(400, {"status": "error", "message": "invalid_json_body"})
    except mf.ContractValidationError as exc:
        return json_response(400, {"status": "error", "message": str(exc)})


def frontdesk_approve_response(
    *,
    workspace: Path,
    request_id: str,
    snapshot_factory: Callable[[Path, str], Mapping[str, Any]],
) -> WebConsoleResponse:
    """Approve FrontDesk requirements without starting a long research run."""

    try:
        request = approve_frontdesk_requirements(request_id=request_id, workspace=workspace)
        return json_response(
            200,
            {
                "schema_version": "missionforge_deepresearch.web_console.frontdesk_approval_result.v1",
                "status": "approved",
                "research_request": request.to_dict(),
                "snapshot": snapshot_factory(workspace, request_id),
            },
        )
    except mf.ContractValidationError as exc:
        return json_response(409, {"status": "error", "message": str(exc)})


def research_start_response(
    *,
    workspace: Path,
    request_id: str,
    config: WebKernelConfig,
) -> WebConsoleResponse:
    """Start Kernel v2 in a background task after FrontDesk approval."""

    existing_state = read_or_record_existing_task(
        workspace=workspace,
        request_id=request_id,
        task_kind="kernel_v2_run",
        existing_result_refs=[KERNEL_V2_RESULT_REF, KERNEL_V2_RUN_STATUS_REF],
    )
    if existing_state is not None:
        return json_response(
            200,
            {
                "schema_version": "missionforge_deepresearch.web_console.research_start_result.v1",
                "status": existing_state.get("status", "idle"),
                "task": existing_state,
            },
        )

    try:
        request = read_approved_frontdesk_request(request_id=request_id, workspace=workspace)

        def runner() -> Any:
            return run_deepresearch_kernel_v2(
                request,
                workspace=workspace,
                adapter=config.adapter_factory(request.research_intensity),
                live_extension_mode=config.live_extension_mode,
            )

        task_state = start_background_task(
            workspace=workspace,
            request_id=request_id,
            task_kind="kernel_v2_run",
            runner=runner,
            existing_result_refs=[KERNEL_V2_RESULT_REF, KERNEL_V2_RUN_STATUS_REF],
        )
        response_status = 202 if task_state.get("status") == "running" else 200
        return json_response(
            response_status,
            {
                "schema_version": "missionforge_deepresearch.web_console.research_start_result.v1",
                "status": task_state.get("status", "running"),
                "task": task_state,
            },
        )
    except mf.ContractValidationError as exc:
        return json_response(409, {"status": "error", "message": str(exc)})


def json_body(body: bytes | str) -> dict[str, Any]:
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


def content_length(value: str | None) -> int:
    try:
        parsed = int(value or "0")
    except ValueError:
        return 0
    if parsed < 0:
        return 0
    return min(parsed, WEB_POST_MAX_BYTES)


def _run_ref(request_id: str) -> str:
    if not isinstance(request_id, str) or not request_id.strip():
        raise mf.ContractValidationError("DeepResearch request_id is required")
    return mf.validate_ref(f"runs/{request_id.strip()}", "deepresearch_web.run_ref")


def _ref_is_file(run_root: Path, ref: str) -> bool:
    try:
        return resolve_workspace_ref(run_root, ref).is_file()
    except mf.ContractValidationError:
        return False


def _clean(value: Any) -> str:
    return str(value).strip() if isinstance(value, str) else ""
