"""Explicit DeepResearch lifecycle action requests.

These refs record user/operator intent for retry, revision, and stale-lock
recovery. They do not mutate frozen contracts or start new Kernel attempts.
"""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

import missionforge as mf

from .frontdesk import read_approved_frontdesk_request
from .kernel_v2 import KERNEL_V2_REVISION_REQUEST_REF
from .web_tasks import (
    WEB_TASK_LOCK_REF,
    WEB_TASK_STATE_REF,
    read_web_task_state,
    release_web_task_lock_for_recovery,
    require_web_task_lock_recoverable,
)
from .workspace import read_json_ref, ref_exists, resolve_workspace_ref, write_json_ref, write_text_ref


LIFECYCLE_ACTION_SCHEMA_VERSION = "missionforge_deepresearch.lifecycle_action.v1"
LIFECYCLE_ACTION_INDEX_REF = "project/lifecycle_actions.jsonl"
LATEST_RETRY_REQUEST_REF = "project/lifecycle/latest_retry_request.json"
LATEST_REVISE_REQUEST_REF = "project/lifecycle/latest_revise_request.json"
LATEST_LOCK_RECOVERY_REQUEST_REF = "project/lifecycle/latest_lock_recovery_request.json"
_ACTION_KINDS = {"retry", "revise", "recover_lock"}
_RETRYABLE_TASK_STATUSES = {"failed", "interrupted"}
_REVISION_PHASES = {"revision_required", "rejected", "blocked", "accepted", "approved"}


def record_lifecycle_action(
    *,
    workspace: str | Path,
    request_id: str,
    action: str,
    text: str = "",
) -> dict[str, Any]:
    """Record one explicit lifecycle action request for a DeepResearch project."""

    action = _clean(action)
    if action not in _ACTION_KINDS:
        raise mf.ContractValidationError("unsupported lifecycle action")
    root = Path(workspace).resolve()
    run_root = resolve_workspace_ref(root, _run_ref(request_id))
    read_approved_frontdesk_request(request_id=request_id, workspace=root)
    if action == "retry":
        payload = _record_retry_request(run_root=run_root, request_id=request_id, text=text)
    elif action == "revise":
        payload = _record_revise_request(run_root=run_root, request_id=request_id, text=text)
    else:
        payload = _record_lock_recovery_request(run_root=run_root, request_id=request_id, text=text)
    _append_action_index(run_root, payload)
    return payload


def read_latest_lifecycle_actions(run_root: str | Path) -> dict[str, dict[str, Any]]:
    """Read sanitized latest lifecycle action refs for snapshots."""

    return {
        "retry": _read_action_if_exists(run_root, LATEST_RETRY_REQUEST_REF),
        "revise": _read_action_if_exists(run_root, LATEST_REVISE_REQUEST_REF),
        "recover_lock": _read_action_if_exists(run_root, LATEST_LOCK_RECOVERY_REQUEST_REF),
    }


def consume_latest_retry_request(run_root: str | Path, *, attempt_ref: str) -> dict[str, Any]:
    """Mark the latest pending retry request as consumed by a Kernel attempt."""

    root = Path(run_root).resolve()
    if not ref_exists(root, LATEST_RETRY_REQUEST_REF):
        raise mf.ContractValidationError("pending retry request is required")
    payload = read_json_ref(root, LATEST_RETRY_REQUEST_REF, "deepresearch_lifecycle_retry_request")
    if payload.get("kind") != "retry":
        raise mf.ContractValidationError("pending retry request is required")
    status = _clean(payload.get("status"))
    existing_attempt_ref = _clean(payload.get("consumed_by_attempt_ref"))
    if status == "consumed" and existing_attempt_ref:
        if existing_attempt_ref != mf.validate_ref(attempt_ref, "deepresearch_lifecycle_retry_request.attempt_ref"):
            raise mf.ContractValidationError("retry request was already consumed")
        return dict(payload)
    if status != "pending_retry":
        raise mf.ContractValidationError("pending retry request is required")
    payload.update({
        "status": "consumed",
        "consumed_at": _utc_now(),
        "consumed_by": "kernel_attempt",
        "consumed_by_attempt_ref": mf.validate_ref(attempt_ref, "deepresearch_lifecycle_retry_request.attempt_ref"),
        "next_required_boundary": "",
    })
    mf.assert_refs_only_payload(payload, "deepresearch_lifecycle_retry_request")
    write_json_ref(root, LATEST_RETRY_REQUEST_REF, payload)
    _append_action_index(root, payload)
    return dict(payload)


def consume_latest_revise_request(
    run_root: str | Path,
    *,
    revision_ref: str,
    attempt_ref: str,
) -> dict[str, Any]:
    """Mark the latest pending revision request as consumed by a revision boundary."""

    root = Path(run_root).resolve()
    if not ref_exists(root, LATEST_REVISE_REQUEST_REF):
        raise mf.ContractValidationError("pending revision request is required")
    payload = read_json_ref(root, LATEST_REVISE_REQUEST_REF, "deepresearch_lifecycle_revise_request")
    if payload.get("kind") != "revise":
        raise mf.ContractValidationError("pending revision request is required")
    safe_revision_ref = mf.validate_ref(revision_ref, "deepresearch_lifecycle_revise_request.revision_ref")
    safe_attempt_ref = mf.validate_ref(attempt_ref, "deepresearch_lifecycle_revise_request.attempt_ref")
    status = _clean(payload.get("status"))
    existing_revision_ref = _clean(payload.get("consumed_by_revision_ref"))
    existing_attempt_ref = _clean(payload.get("consumed_by_attempt_ref"))
    if status == "consumed" and existing_revision_ref and existing_attempt_ref:
        if existing_revision_ref != safe_revision_ref or existing_attempt_ref != safe_attempt_ref:
            raise mf.ContractValidationError("revision request was already consumed")
        return dict(payload)
    if status != "pending_revision":
        raise mf.ContractValidationError("pending revision request is required")
    payload.update({
        "status": "consumed",
        "consumed_at": _utc_now(),
        "consumed_by": "contract_revision",
        "consumed_by_revision_ref": safe_revision_ref,
        "consumed_by_attempt_ref": safe_attempt_ref,
        "next_required_boundary": "",
    })
    mf.assert_refs_only_payload(payload, "deepresearch_lifecycle_revise_request")
    write_json_ref(root, LATEST_REVISE_REQUEST_REF, payload)
    _append_action_index(root, payload)
    return dict(payload)


def _record_retry_request(*, run_root: Path, request_id: str, text: str) -> dict[str, Any]:
    task_state = read_web_task_state(run_root)
    status = _clean(task_state.get("status"))
    if status not in _RETRYABLE_TASK_STATUSES:
        raise mf.ContractValidationError("retry requires a failed or interrupted task")
    text_ref = _write_action_text(run_root, kind="retry", text=text)
    payload = _base_action_payload(
        request_id=request_id,
        kind="retry",
        status="pending_retry",
        reason_ref=text_ref,
    )
    payload.update({
        "source_task_ref": WEB_TASK_STATE_REF if ref_exists(run_root, WEB_TASK_STATE_REF) else "",
        "source_task_status": status,
        "source_lock_ref": WEB_TASK_LOCK_REF if status == "locked" else "",
        "next_required_boundary": "kernel_attempt",
    })
    mf.assert_refs_only_payload(payload, "deepresearch_lifecycle_retry_request")
    write_json_ref(run_root, LATEST_RETRY_REQUEST_REF, payload)
    return payload


def _record_revise_request(*, run_root: Path, request_id: str, text: str) -> dict[str, Any]:
    if not _clean(text):
        raise mf.ContractValidationError("revision text is required")
    _require_no_active_web_task(run_root, action="revise")
    lifecycle = _read_project_lifecycle(run_root)
    phase = _clean(lifecycle.get("phase"))
    if phase not in _REVISION_PHASES:
        raise mf.ContractValidationError("revise requires an approved or completed project state")
    text_ref = _write_action_text(run_root, kind="revise", text=text)
    payload = _base_action_payload(
        request_id=request_id,
        kind="revise",
        status="pending_revision",
        reason_ref=text_ref,
    )
    payload.update({
        "source_lifecycle_ref": "project/lifecycle_state.json",
        "source_phase": phase,
        "source_revision_ref": KERNEL_V2_REVISION_REQUEST_REF if ref_exists(run_root, KERNEL_V2_REVISION_REQUEST_REF) else "",
        "next_required_boundary": "frontdesk_contract_revision",
    })
    mf.assert_refs_only_payload(payload, "deepresearch_lifecycle_revise_request")
    write_json_ref(run_root, LATEST_REVISE_REQUEST_REF, payload)
    return payload


def _require_no_active_web_task(run_root: Path, *, action: str) -> None:
    task_state = read_web_task_state(run_root)
    if _clean(task_state.get("status")) in {"running", "locked"}:
        raise mf.ContractValidationError(f"{action} requires no active web task")


def _record_lock_recovery_request(*, run_root: Path, request_id: str, text: str) -> dict[str, Any]:
    task_state = read_web_task_state(run_root)
    if task_state.get("status") != "locked" and not _has_lock_ref(task_state):
        raise mf.ContractValidationError("lock recovery requires a locked task")
    require_web_task_lock_recoverable(run_root)
    text_ref = _write_action_text(run_root, kind="recover_lock", text=text)
    payload = _base_action_payload(
        request_id=request_id,
        kind="recover_lock",
        status="pending_recovery",
        reason_ref=text_ref,
    )
    payload.update({
        "source_task_ref": WEB_TASK_STATE_REF if ref_exists(run_root, WEB_TASK_STATE_REF) else "",
        "source_lock_ref": WEB_TASK_LOCK_REF,
        "released_lock_ref": "",
        "next_required_boundary": "retry_request",
    })
    mf.assert_refs_only_payload(payload, "deepresearch_lifecycle_lock_recovery_request")
    write_json_ref(run_root, LATEST_LOCK_RECOVERY_REQUEST_REF, payload)
    released_lock_ref = release_web_task_lock_for_recovery(run_root)
    payload.update({
        "status": "completed",
        "released_lock_ref": released_lock_ref,
        "completed_at": _utc_now(),
    })
    mf.assert_refs_only_payload(payload, "deepresearch_lifecycle_lock_recovery_request")
    write_json_ref(run_root, LATEST_LOCK_RECOVERY_REQUEST_REF, payload)
    return payload


def _base_action_payload(*, request_id: str, kind: str, status: str, reason_ref: str) -> dict[str, Any]:
    return {
        "schema_version": LIFECYCLE_ACTION_SCHEMA_VERSION,
        "action_id": f"LA-{uuid4().hex}",
        "request_id": request_id,
        "kind": kind,
        "status": status,
        "reason_ref": reason_ref,
        "created_at": _utc_now(),
    }


def _has_lock_ref(task_state: Mapping[str, Any]) -> bool:
    return _clean(task_state.get("lock_ref")) == WEB_TASK_LOCK_REF


def _append_action_index(run_root: Path, payload: Mapping[str, Any]) -> None:
    path = resolve_workspace_ref(run_root, LIFECYCLE_ACTION_INDEX_REF)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8") if not path.exists() else None
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(payload), sort_keys=True) + "\n")


def _write_action_text(run_root: Path, *, kind: str, text: str) -> str:
    if not _clean(text):
        return ""
    ref = f"project/lifecycle/action_text/{kind}-{uuid4().hex}.txt"
    return write_text_ref(run_root, ref, _clean(text) + "\n")


def _read_action_if_exists(run_root: str | Path, ref: str) -> dict[str, Any]:
    try:
        if not ref_exists(run_root, ref):
            return {}
        payload = read_json_ref(run_root, ref, "deepresearch_lifecycle_action")
        if payload.get("schema_version") != LIFECYCLE_ACTION_SCHEMA_VERSION:
            return {}
        return {
            "action_id": _clean(payload.get("action_id")),
            "kind": _clean(payload.get("kind")),
            "status": _clean(payload.get("status")),
            "reason_ref": _clean(payload.get("reason_ref")),
            "created_at": _clean(payload.get("created_at")),
            "consumed_at": _clean(payload.get("consumed_at")),
            "consumed_by_revision_ref": _clean(payload.get("consumed_by_revision_ref")),
            "consumed_by_attempt_ref": _clean(payload.get("consumed_by_attempt_ref")),
            "next_required_boundary": _clean(payload.get("next_required_boundary")),
        }
    except (OSError, json.JSONDecodeError, mf.ContractValidationError):
        return {}


def _read_project_lifecycle(run_root: Path) -> dict[str, Any]:
    try:
        return read_json_ref(run_root, "project/lifecycle_state.json", "deepresearch_lifecycle_state")
    except mf.ContractValidationError:
        return {}


def _run_ref(request_id: str) -> str:
    if not isinstance(request_id, str) or not request_id.strip():
        raise mf.ContractValidationError("DeepResearch request_id is required")
    return mf.validate_ref(f"runs/{request_id.strip()}", "deepresearch_lifecycle_action.run_ref")


def _clean(value: Any) -> str:
    return str(value).strip() if isinstance(value, str) else ""


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
