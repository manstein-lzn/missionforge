"""DeepResearch web background task state."""

from __future__ import annotations

from datetime import UTC, datetime
import json
import os
from pathlib import Path
import socket
import threading
from typing import Any, Callable, Iterable, Mapping

import missionforge as mf

from .workspace import read_json_ref, ref_exists, resolve_workspace_ref


WEB_TASK_STATE_REF = "web/tasks/current_task.json"
WEB_TASK_LOCK_REF = "web/locks/kernel_v2.lock"
WEB_TASK_LOCK_METADATA_FILE = "lock.json"
WEB_TASK_SCHEMA_VERSION = "missionforge_deepresearch.web_task_state.v1"
WEB_TASK_LOCK_SCHEMA_VERSION = "missionforge_deepresearch.web_task_lock.v1"
_TASK_STATUSES = {"idle", "running", "completed", "failed", "interrupted", "locked"}
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
    "lock_ref",
)

_TASK_LOCK = threading.Lock()
_RUNNING_THREADS: dict[str, threading.Thread] = {}


def read_web_task_state(run_root: str | Path) -> dict[str, Any]:
    root = Path(run_root).resolve()
    try:
        if not ref_exists(root, WEB_TASK_STATE_REF):
            if _lock_exists(root):
                return _locked_state_from_metadata(root)
            return _idle_state()
        payload = read_json_ref(root, WEB_TASK_STATE_REF, "deepresearch_web_task_state")
    except (json.JSONDecodeError, UnicodeDecodeError, OSError, mf.ContractValidationError):
        if _lock_exists(root):
            return _locked_state_from_metadata(root)
        return _idle_state()
    state = _sanitize_task_state(payload)
    if _lock_exists(root):
        if state.get("status") == "running" and _thread_alive(str(root)):
            return state
        return _locked_state_from_metadata(root, existing=state)
    if state.get("status") == "locked":
        return _idle_state()
    return state


def start_background_task(
    *,
    workspace: str | Path,
    request_id: str,
    task_kind: str,
    runner: Callable[[], Any],
    existing_result_refs: Iterable[str] = (),
    restart_terminal_statuses: Iterable[str] = (),
    before_start: Callable[[Mapping[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Start a background task if no live task is already running."""

    root = Path(workspace).resolve()
    run_root = root / _run_ref(request_id)
    run_root.mkdir(parents=True, exist_ok=True)
    task_key = str(run_root)
    restartable = set(restart_terminal_statuses)
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
            if _lock_exists(run_root):
                return _locked_state_from_metadata(run_root, existing=existing)
            interrupted = _interrupted_state(existing)
            _write_task_state(run_root, interrupted)
            return interrupted
        if existing.get("status") == "locked":
            return existing
        if existing.get("status") in {"completed", "failed", "interrupted"} and existing.get("status") not in restartable:
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
        lock_ref = _acquire_run_lock(
            run_root=run_root,
            request_id=request_id,
            task_kind=task_kind,
            task_id=task_id,
        )
        if not lock_ref:
            return _locked_state_from_metadata(run_root)
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
            "lock_ref": lock_ref,
        }
        try:
            if before_start is not None:
                before_start(state)
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
        except Exception:
            _RUNNING_THREADS.pop(task_key, None)
            _release_run_lock(run_root, state)
            raise
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
            if _lock_exists(run_root):
                return _locked_state_from_metadata(run_root, existing=existing)
            interrupted = _interrupted_state(existing)
            _write_task_state(run_root, interrupted)
            return interrupted
        if existing.get("status") == "locked":
            return existing
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


def release_web_task_lock_for_recovery(run_root: str | Path) -> str:
    """Explicitly release a workspace-local web task lock for lifecycle recovery."""

    root = Path(run_root).resolve()
    with _TASK_LOCK:
        state = _recoverable_lock_state(root)
        lock_dir = _recoverable_lock_dir(root, state)
        _release_lock_dir(lock_dir)
        recovered = dict(state)
        recovered.update({
            "status": "interrupted",
            "finished_at": _utc_now(),
            "error_summary": "background task lock was explicitly recovered",
            "lock_ref": "",
        })
        _write_task_state(root, recovered)
        return WEB_TASK_LOCK_REF


def require_web_task_lock_recoverable(run_root: str | Path) -> str:
    """Validate that explicit lock recovery would affect a stale/cross-process lock."""

    root = Path(run_root).resolve()
    with _TASK_LOCK:
        state = _recoverable_lock_state(root)
        _recoverable_lock_dir(root, state)
        return WEB_TASK_LOCK_REF


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
            _release_run_lock(run_root, state)


def _thread_alive(task_key: str) -> bool:
    thread = _RUNNING_THREADS.get(task_key)
    return thread is not None and thread.is_alive()


def _recoverable_lock_state(run_root: Path) -> dict[str, Any]:
    if _thread_alive(str(run_root)):
        raise mf.ContractValidationError("cannot recover a lock held by a live task in this process")
    state = read_web_task_state(run_root)
    if state.get("status") != "locked" and state.get("lock_ref") != WEB_TASK_LOCK_REF:
        raise mf.ContractValidationError("lock recovery requires a locked task")
    return state


def _recoverable_lock_dir(run_root: Path, state: Mapping[str, Any]) -> Path:
    lock_dir = resolve_workspace_ref(run_root, WEB_TASK_LOCK_REF)
    if not lock_dir.exists():
        raise mf.ContractValidationError("lock recovery requires an existing lock")
    return lock_dir


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
        "lock_ref": "",
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


def _acquire_run_lock(*, run_root: Path, request_id: str, task_kind: str, task_id: str) -> str:
    lock_dir = resolve_workspace_ref(run_root, WEB_TASK_LOCK_REF)
    try:
        lock_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        return ""
    except OSError as exc:
        raise mf.ContractValidationError(f"cannot create web task lock: {exc}") from exc
    metadata = {
        "schema_version": WEB_TASK_LOCK_SCHEMA_VERSION,
        "lock_ref": WEB_TASK_LOCK_REF,
        "task_id": task_id,
        "task_kind": task_kind,
        "request_id": request_id,
        "owner_pid": str(os.getpid()),
        "owner_thread": str(threading.get_ident()),
        "owner_host": socket.gethostname(),
        "acquired_at": _utc_now(),
    }
    try:
        _write_lock_metadata(lock_dir, metadata)
    except OSError as exc:
        _release_lock_dir(lock_dir)
        raise mf.ContractValidationError(f"cannot write web task lock metadata: {exc}") from exc
    return WEB_TASK_LOCK_REF


def _release_run_lock(run_root: Path, state: Mapping[str, Any]) -> None:
    if state.get("lock_ref") != WEB_TASK_LOCK_REF:
        return
    lock_dir = resolve_workspace_ref(run_root, WEB_TASK_LOCK_REF)
    metadata = _read_lock_metadata(run_root)
    if metadata.get("task_id") != state.get("task_id"):
        return
    _release_lock_dir(lock_dir)


def _release_lock_dir(lock_dir: Path) -> None:
    try:
        (lock_dir / WEB_TASK_LOCK_METADATA_FILE).unlink(missing_ok=True)
        lock_dir.rmdir()
    except FileNotFoundError:
        return
    except OSError:
        return


def _lock_exists(run_root: str | Path) -> bool:
    try:
        return resolve_workspace_ref(run_root, WEB_TASK_LOCK_REF).exists()
    except mf.ContractValidationError:
        return False


def _locked_state_from_metadata(run_root: str | Path, *, existing: Mapping[str, Any] | None = None) -> dict[str, Any]:
    metadata = _read_lock_metadata(run_root)
    return _locked_state(
        request_id=_string_field(metadata, "request_id") or _string_field(existing or {}, "request_id"),
        task_kind=_string_field(metadata, "task_kind") or _string_field(existing or {}, "task_kind"),
        task_id=_string_field(metadata, "task_id") or _string_field(existing or {}, "task_id"),
        started_at=_string_field(metadata, "acquired_at") or _string_field(existing or {}, "started_at"),
    )


def _locked_state(*, request_id: str, task_kind: str, task_id: str, started_at: str) -> dict[str, Any]:
    return {
        "schema_version": WEB_TASK_SCHEMA_VERSION,
        "task_id": task_id or f"{task_kind or 'kernel_v2_run'}-locked",
        "task_kind": task_kind,
        "request_id": request_id,
        "status": "locked",
        "started_at": started_at,
        "finished_at": "",
        "result_ref": "",
        "error_summary": "run lock is held by another process",
        "lock_ref": WEB_TASK_LOCK_REF,
    }


def _write_lock_metadata(lock_dir: Path, metadata: Mapping[str, Any]) -> None:
    path = lock_dir / WEB_TASK_LOCK_METADATA_FILE
    path.write_text(json.dumps(dict(metadata), sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _read_lock_metadata(run_root: str | Path) -> Mapping[str, Any]:
    try:
        path = resolve_workspace_ref(run_root, f"{WEB_TASK_LOCK_REF}/{WEB_TASK_LOCK_METADATA_FILE}")
        if not path.is_file():
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping):
            return {}
        if payload.get("schema_version") != WEB_TASK_LOCK_SCHEMA_VERSION:
            return {}
        if payload.get("lock_ref") != WEB_TASK_LOCK_REF:
            return {}
        return payload
    except (OSError, json.JSONDecodeError, UnicodeDecodeError, mf.ContractValidationError):
        return {}


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
        "lock_ref": "",
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
