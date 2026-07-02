"""DeepResearch web background task state."""

from __future__ import annotations

from datetime import UTC, datetime
import json
import os
from pathlib import Path
import threading
from typing import Any, Callable, Iterable, Mapping

import missionforge as mf

from .workspace import read_json_ref, ref_exists, resolve_workspace_ref


WEB_TASK_STATE_REF = "web/tasks/current_task.json"
WEB_TASK_SCHEMA_VERSION = "missionforge_deepresearch.web_task_state.v1"
_TASK_STATUSES = {"idle", "running", "completed", "failed", "interrupted"}
_TASK_FIELDS = (
    "schema_version",
    "task_id",
    "task_kind",
    "request_id",
    "status",
    "started_at",
    "finished_at",
    "result_ref",
    "error_summary",
)

_TASK_LOCK = threading.Lock()
_RUNNING_THREADS: dict[str, threading.Thread] = {}


def read_web_task_state(run_root: str | Path) -> dict[str, Any]:
    try:
        if not ref_exists(run_root, WEB_TASK_STATE_REF):
            return _idle_state()
        payload = read_json_ref(run_root, WEB_TASK_STATE_REF, "deepresearch_web_task_state")
    except (json.JSONDecodeError, UnicodeDecodeError, OSError, mf.ContractValidationError):
        return _idle_state()
    return _sanitize_task_state(payload)


def start_background_task(
    *,
    workspace: str | Path,
    request_id: str,
    task_kind: str,
    runner: Callable[[], Any],
    existing_result_refs: Iterable[str] = (),
) -> dict[str, Any]:
    """Start a background task if no live task is already running."""

    root = Path(workspace).resolve()
    run_root = root / _run_ref(request_id)
    run_root.mkdir(parents=True, exist_ok=True)
    task_key = str(run_root)
    with _TASK_LOCK:
        existing = read_web_task_state(run_root)
        if existing.get("status") == "running":
            if _thread_alive(task_key):
                return existing
            existing_ref = _first_existing_ref(run_root, existing_result_refs)
            if existing_ref:
                state = _existing_run_state(
                    request_id=request_id,
                    task_kind=task_kind,
                    result_ref=existing_ref,
                )
                _write_task_state(run_root, state)
                return state
            interrupted = _interrupted_state(existing)
            _write_task_state(run_root, interrupted)
            return interrupted
        if existing.get("status") in {"completed", "failed", "interrupted"}:
            return existing
        existing_ref = _first_existing_ref(run_root, existing_result_refs)
        if existing_ref:
            state = _existing_run_state(
                request_id=request_id,
                task_kind=task_kind,
                result_ref=existing_ref,
            )
            _write_task_state(run_root, state)
            return state
        task_id = f"{task_kind}-{_utc_now().replace(':', '').replace('-', '')}"
        state = {
            "schema_version": WEB_TASK_SCHEMA_VERSION,
            "task_id": task_id,
            "task_kind": task_kind,
            "request_id": request_id,
            "status": "running",
            "started_at": _utc_now(),
            "finished_at": "",
            "result_ref": "",
            "error_summary": "",
        }
        _write_task_state(run_root, state)
        thread = threading.Thread(
            target=_run_task,
            kwargs={
                "run_root": run_root,
                "task_key": task_key,
                "state": state,
                "runner": runner,
            },
            daemon=True,
        )
        _RUNNING_THREADS[task_key] = thread
        thread.start()
        return state


def read_or_record_existing_task(
    *,
    workspace: str | Path,
    request_id: str,
    task_kind: str,
    existing_result_refs: Iterable[str] = (),
) -> dict[str, Any] | None:
    """Return a live/completed task state when the selected project already has one."""

    root = Path(workspace).resolve()
    run_root = root / _run_ref(request_id)
    if not run_root.exists():
        return None
    task_key = str(run_root)
    with _TASK_LOCK:
        existing = read_web_task_state(run_root)
        if existing.get("status") == "running":
            if _thread_alive(task_key):
                return existing
            existing_ref = _first_existing_ref(run_root, existing_result_refs)
            if existing_ref:
                state = _existing_run_state(
                    request_id=request_id,
                    task_kind=task_kind,
                    result_ref=existing_ref,
                )
                _write_task_state(run_root, state)
                return state
            interrupted = _interrupted_state(existing)
            _write_task_state(run_root, interrupted)
            return interrupted
        if existing.get("status") in {"completed", "failed", "interrupted"}:
            return existing
        existing_ref = _first_existing_ref(run_root, existing_result_refs)
        if not existing_ref:
            return None
        state = _existing_run_state(
            request_id=request_id,
            task_kind=task_kind,
            result_ref=existing_ref,
        )
        _write_task_state(run_root, state)
        return state


def _run_task(
    *,
    run_root: Path,
    task_key: str,
    state: Mapping[str, Any],
    runner: Callable[[], Any],
) -> None:
    try:
        result = runner()
        result_ref = getattr(result, "result_ref", "")
        payload = dict(state)
        payload.update({
            "status": "completed",
            "finished_at": _utc_now(),
            "result_ref": result_ref if isinstance(result_ref, str) else "",
            "error_summary": "",
        })
        _write_task_state(run_root, payload)
    except Exception as exc:  # pragma: no cover - defensive task boundary.
        payload = dict(state)
        payload.update({
            "status": "failed",
            "finished_at": _utc_now(),
            "result_ref": "",
            "error_summary": f"{type(exc).__name__}: task failed",
        })
        _write_task_state(run_root, payload)
    finally:
        with _TASK_LOCK:
            _RUNNING_THREADS.pop(task_key, None)


def _thread_alive(task_key: str) -> bool:
    thread = _RUNNING_THREADS.get(task_key)
    return thread is not None and thread.is_alive()


def _idle_state() -> dict[str, Any]:
    return {
        "schema_version": WEB_TASK_SCHEMA_VERSION,
        "task_id": "",
        "task_kind": "",
        "request_id": "",
        "status": "idle",
        "started_at": "",
        "finished_at": "",
        "result_ref": "",
        "error_summary": "",
    }


def _sanitize_task_state(payload: Mapping[str, Any]) -> dict[str, Any]:
    state = _idle_state()
    if payload.get("schema_version") != WEB_TASK_SCHEMA_VERSION:
        return state
    status = _string_field(payload, "status")
    if status not in _TASK_STATUSES:
        return state
    for field_name in _TASK_FIELDS:
        state[field_name] = _string_field(payload, field_name)
    state["schema_version"] = WEB_TASK_SCHEMA_VERSION
    state["status"] = status
    return state


def _string_field(payload: Mapping[str, Any], field_name: str) -> str:
    value = payload.get(field_name)
    return value if isinstance(value, str) else ""


def _write_task_state(run_root: str | Path, payload: Mapping[str, Any]) -> str:
    state = _sanitize_task_state(payload)
    path = resolve_workspace_ref(run_root, WEB_TASK_STATE_REF)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    temp_path.write_text(json.dumps(state, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    temp_path.replace(path)
    return WEB_TASK_STATE_REF


def _existing_run_state(*, request_id: str, task_kind: str, result_ref: str) -> dict[str, Any]:
    return {
        "schema_version": WEB_TASK_SCHEMA_VERSION,
        "task_id": f"{task_kind}-existing",
        "task_kind": task_kind,
        "request_id": request_id,
        "status": "completed",
        "started_at": "",
        "finished_at": "",
        "result_ref": result_ref,
        "error_summary": "",
    }


def _interrupted_state(existing: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(existing)
    payload.update({
        "status": "interrupted",
        "finished_at": _utc_now(),
        "error_summary": "background task is not active in this process",
    })
    return payload


def _first_existing_ref(run_root: Path, refs: Iterable[str]) -> str:
    for ref in refs:
        if isinstance(ref, str) and ref and ref_exists(run_root, ref):
            return ref
    return ""


def _run_ref(request_id: str) -> str:
    if not isinstance(request_id, str) or not request_id.strip():
        raise mf.ContractValidationError("DeepResearch request_id is required")
    return mf.validate_ref(f"runs/{request_id.strip()}", "deepresearch_web_task.run_ref")


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
