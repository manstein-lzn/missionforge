"""Web-console actions that mutate DeepResearch projects through product APIs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Mapping

import missionforge as mf

from .frontdesk import (
    FRONTDESK_INITIAL_INPUT_REF,
    approve_frontdesk_requirements,
    run_deepresearch_frontdesk_turn,
)
from .kernel_v2 import KERNEL_V2_RESULT_REF, KERNEL_V2_RUN_STATUS_REF, run_deepresearch_kernel_v2
from .lifecycle_actions import record_lifecycle_action
from .research_attempts import start_retry_attempt
from .research_requests import read_current_research_request
from .research_revisions import start_revision_attempt
from .web_common import WEB_POST_MAX_BYTES, WebConsoleResponse, WebFrontDeskConfig, WebKernelConfig, json_response
from .web_tasks import read_or_record_existing_task, start_background_task
from .web_timeline import append_flow_ledger_event, runtime_progress_sink
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
            runtime_progress_sink=runtime_progress_sink(run_root, source="frontdesk", default_stage="frontdesk"),
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

    try:
        request = read_current_research_request(workspace=workspace, request_id=request_id)
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

        def runner() -> Any:
            return run_deepresearch_kernel_v2(
                request,
                workspace=workspace,
                adapter=config.adapter_factory(request.research_intensity),
                live_extension_mode=config.live_extension_mode,
                event_sink=lambda event: append_flow_ledger_event(
                    resolve_workspace_ref(workspace, _run_ref(request_id)),
                    event,
                ),
                runtime_progress_sink=runtime_progress_sink(
                    resolve_workspace_ref(workspace, _run_ref(request_id)),
                    source="kernel_v2",
                    default_stage="kernel_v2",
                ),
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


def lifecycle_action_response(
    *,
    workspace: Path,
    request_id: str,
    body: bytes | str,
) -> WebConsoleResponse:
    """Record an explicit retry/revise/recover lifecycle request."""

    try:
        payload = json_body(body)
        action = _clean(payload.get("action"))
        text = _clean(payload.get("text"))
        result = record_lifecycle_action(
            workspace=workspace,
            request_id=request_id,
            action=action,
            text=text,
        )
        return json_response(
            202,
            {
                "schema_version": "missionforge_deepresearch.web_console.lifecycle_action_result.v1",
                "status": result.get("status", "queued"),
                "action": {
                    "action_id": result.get("action_id", ""),
                    "kind": result.get("kind", ""),
                    "status": result.get("status", ""),
                    "reason_ref": result.get("reason_ref", ""),
                    "next_required_boundary": result.get("next_required_boundary", ""),
                },
            },
        )
    except (json.JSONDecodeError, UnicodeDecodeError):
        return json_response(400, {"status": "error", "message": "invalid_json_body"})
    except mf.ContractValidationError as exc:
        return json_response(409, {"status": "error", "message": str(exc)})


def research_attempt_start_response(
    *,
    workspace: Path,
    request_id: str,
    config: WebKernelConfig,
) -> WebConsoleResponse:
    """Start a retry attempt after an explicit pending retry request."""

    try:
        result = start_retry_attempt(
            workspace=workspace,
            request_id=request_id,
            config=config,
            event_sink=lambda event: append_flow_ledger_event(
                resolve_workspace_ref(workspace, _run_ref(request_id)),
                event,
            ),
            runtime_progress_sink=runtime_progress_sink(
                resolve_workspace_ref(workspace, _run_ref(request_id)),
                source="retry_attempt",
                default_stage="kernel_v2_retry_attempt",
            ),
        )
        response_status = 202 if result.get("status") == "running" else 200
        return json_response(
            response_status,
            {
                "schema_version": "missionforge_deepresearch.web_console.research_attempt_start_result.v1",
                "status": result.get("status", "unknown"),
                "attempt": result.get("attempt", {}),
                "task": result.get("task", {}),
                "action": result.get("action", {}),
            },
        )
    except mf.ContractValidationError as exc:
        return json_response(409, {"status": "error", "message": str(exc)})


def research_revision_start_response(
    *,
    workspace: Path,
    request_id: str,
    config: WebKernelConfig,
) -> WebConsoleResponse:
    """Start a revised-contract attempt after an explicit pending revision request."""

    try:
        result = start_revision_attempt(
            workspace=workspace,
            request_id=request_id,
            config=config,
            event_sink=lambda event: append_flow_ledger_event(
                resolve_workspace_ref(workspace, _run_ref(request_id)),
                event,
            ),
            runtime_progress_sink=runtime_progress_sink(
                resolve_workspace_ref(workspace, _run_ref(request_id)),
                source="revision_attempt",
                default_stage="kernel_v2_revision_attempt",
            ),
        )
        response_status = 202 if result.get("status") == "running" else 200
        return json_response(
            response_status,
            {
                "schema_version": "missionforge_deepresearch.web_console.research_revision_start_result.v1",
                "status": result.get("status", "unknown"),
                "revision": result.get("revision", {}),
                "attempt": result.get("attempt", {}),
                "task": result.get("task", {}),
                "action": result.get("action", {}),
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


def content_length(value: str | None, *, max_bytes: int = WEB_POST_MAX_BYTES) -> int:
    try:
        parsed = int(value or "0")
    except ValueError:
        return 0
    if parsed < 0:
        return 0
    return min(parsed, max_bytes)


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
