"""DeepResearch retry attempt lifecycle.

Attempt records consume explicit lifecycle requests and start a new Kernel
execution boundary. They preserve product-level refs and never mutate the
frozen contract directly.
"""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import shutil
from typing import Any, Callable, Mapping
from uuid import uuid4

import missionforge as mf

from .attempt_outputs import write_attempt_output_manifest
from .kernel_refs import (
    KERNEL_V2_ACCEPTANCE_GATE_REF,
    KERNEL_V2_CANONICAL_SOURCES_REF,
    KERNEL_V2_CITATION_PROJECTED_REPORT_REF,
    KERNEL_V2_CONTRACT_REF,
    KERNEL_V2_COVERAGE_REPORT_REF,
    KERNEL_V2_FINAL_REPORT_REF,
    KERNEL_V2_JUDGE_REPORT_REF,
    KERNEL_V2_RESULT_REF,
    KERNEL_V2_RUN_STATUS_REF,
    KERNEL_V2_SOURCE_PACKET_REF,
)
from .kernel_v2 import run_deepresearch_kernel_v2
from .research_requests import read_contract_revision_index, read_current_research_request
from .lifecycle_actions import (
    LATEST_RETRY_REQUEST_REF,
    LATEST_REVISE_REQUEST_REF,
    consume_latest_retry_request,
)
from .project_lifecycle import PROJECT_LIFECYCLE_STATE_REF
from .web_common import WebKernelConfig
from .web_tasks import WEB_TASK_LOCK_REF, WEB_TASK_STATE_REF, read_web_task_state, start_background_task
from .workspace import read_json_ref, ref_exists, resolve_workspace_ref, sha256_ref, write_json_ref


ATTEMPT_MANIFEST_SCHEMA_VERSION = "missionforge_deepresearch.attempt_manifest.v1"
ATTEMPT_INDEX_SCHEMA_VERSION = "missionforge_deepresearch.attempt_index.v1"
ATTEMPT_SNAPSHOT_SCHEMA_VERSION = "missionforge_deepresearch.attempt_snapshot.v1"
ATTEMPT_INDEX_REF = "project/attempt_index.json"

_RETRY_STARTABLE_TASK_STATUSES = {"failed", "interrupted"}
_SNAPSHOT_SOURCE_REFS = (
    PROJECT_LIFECYCLE_STATE_REF,
    WEB_TASK_STATE_REF,
    KERNEL_V2_RESULT_REF,
    KERNEL_V2_RUN_STATUS_REF,
    KERNEL_V2_FINAL_REPORT_REF,
    KERNEL_V2_CITATION_PROJECTED_REPORT_REF,
    KERNEL_V2_SOURCE_PACKET_REF,
    KERNEL_V2_CANONICAL_SOURCES_REF,
    KERNEL_V2_COVERAGE_REPORT_REF,
    KERNEL_V2_ACCEPTANCE_GATE_REF,
    KERNEL_V2_JUDGE_REPORT_REF,
)


def start_retry_attempt(
    *,
    workspace: str | Path,
    request_id: str,
    config: WebKernelConfig,
    event_sink: Callable[[mf.FlowLedgerEvent], None] | None = None,
    runtime_progress_sink: mf.PiWorkerProgressSink | None = None,
) -> dict[str, Any]:
    """Consume the latest pending retry request and start a Kernel attempt."""

    root = Path(workspace).resolve()
    run_root = resolve_workspace_ref(root, _run_ref(request_id))
    request = read_current_research_request(workspace=root, request_id=request_id)
    _require_no_pending_revision(run_root)
    retry = _latest_retry_request(run_root)
    if retry.get("status") == "consumed" and _clean(retry.get("consumed_by_attempt_ref")):
        return _existing_attempt_result(run_root, retry)
    _require_pending_retry(retry)
    task_state = read_web_task_state(run_root)
    task_status = _clean(task_state.get("status"))
    if task_status not in _RETRY_STARTABLE_TASK_STATUSES:
        raise mf.ContractValidationError("retry attempt requires a failed or interrupted task")

    attempt_record: dict[str, str] = {}
    action_record: dict[str, Any] = {}

    def before_start(start_state: Mapping[str, Any]) -> None:
        _require_no_pending_revision(run_root)
        latest_retry = _latest_retry_request(run_root)
        _require_pending_retry(latest_retry)
        attempt_id = new_attempt_id()
        attempt_ref = attempt_manifest_ref(attempt_id)
        snapshot_ref = write_before_attempt_snapshot(run_root, attempt_id=attempt_id)
        generation = next_attempt_generation(run_root)
        manifest = _base_manifest(
            run_root=run_root,
            request_id=request_id,
            attempt_id=attempt_id,
            generation=generation,
            trigger_action=latest_retry,
            snapshot_ref=snapshot_ref,
            source_task_status=task_status,
        )
        write_json_ref(run_root, attempt_ref, manifest)
        write_attempt_index(run_root, manifest)
        try:
            consumed = consume_latest_retry_request(run_root, attempt_ref=attempt_ref)
        except Exception:
            update_attempt_manifest(
                run_root,
                attempt_ref=attempt_ref,
                status="blocked",
                error_summary="retry request consumption failed",
            )
            raise
        update_attempt_manifest(
            run_root,
            attempt_ref=attempt_ref,
            status="running",
            task_ref=WEB_TASK_STATE_REF,
            lock_ref=WEB_TASK_LOCK_REF if start_state.get("lock_ref") == WEB_TASK_LOCK_REF else "",
        )
        attempt_record["attempt_ref"] = attempt_ref
        action_record.update(consumed)

    def runner() -> Any:
        attempt_ref = _clean(attempt_record.get("attempt_ref"))
        if not attempt_ref:
            raise mf.ContractValidationError("retry attempt was not initialized")
        try:
            result = run_deepresearch_kernel_v2(
                request,
                workspace=root,
                adapter=config.adapter_factory(request.research_intensity),
                live_extension_mode=config.live_extension_mode,
                resume=False,
                event_sink=event_sink,
                runtime_progress_sink=_attempt_progress_sink(runtime_progress_sink, attempt_ref),
            )
        except Exception as exc:
            update_attempt_manifest(
                run_root,
                attempt_ref=attempt_ref,
                status="failed",
                error_summary=f"{type(exc).__name__}: attempt failed",
            )
            raise
        attempt = read_json_ref(run_root, attempt_ref, "deepresearch_attempt_manifest")
        output_manifest_ref = write_attempt_output_manifest(
            run_root,
            attempt_id=_clean(attempt.get("attempt_id")),
            attempt_ref=attempt_ref,
            attempt_kind="retry_attempt",
        )
        update_attempt_manifest(
            run_root,
            attempt_ref=attempt_ref,
            status="completed",
            result_ref=getattr(result, "result_ref", "") if result is not None else "",
            output_manifest_ref=output_manifest_ref,
        )
        _restore_current_revision_in_lifecycle(run_root)
        return result

    task_state = start_background_task(
        workspace=root,
        request_id=request_id,
        task_kind="kernel_v2_retry_attempt",
        runner=runner,
        restart_terminal_statuses=_RETRY_STARTABLE_TASK_STATUSES,
        before_start=before_start,
    )
    if not attempt_record:
        latest_retry = _latest_retry_request(run_root)
        if latest_retry.get("status") == "consumed" and _clean(latest_retry.get("consumed_by_attempt_ref")):
            return _existing_attempt_result(run_root, latest_retry)
        raise mf.ContractValidationError("retry attempt did not start")
    if task_state.get("status") != "running":
        raise mf.ContractValidationError("retry attempt did not start")
    attempt_ref = attempt_record["attempt_ref"]
    return {
        "schema_version": "missionforge_deepresearch.retry_attempt_start_result.v1",
        "status": "running",
        "attempt": read_json_ref(run_root, attempt_ref, "deepresearch_attempt_manifest"),
        "task": task_state,
        "action": _sanitized_action(action_record),
    }


def read_attempt_index(run_root: str | Path) -> dict[str, Any]:
    """Return the project attempt index or an empty index shape."""

    root = Path(run_root)
    if not ref_exists(root, ATTEMPT_INDEX_REF):
        return _empty_index()
    try:
        payload = read_json_ref(root, ATTEMPT_INDEX_REF, "deepresearch_attempt_index")
    except (json.JSONDecodeError, UnicodeDecodeError, OSError, mf.ContractValidationError):
        return _empty_index()
    if payload.get("schema_version") != ATTEMPT_INDEX_SCHEMA_VERSION:
        return _empty_index()
    attempts = payload.get("attempts", [])
    return {
        "schema_version": ATTEMPT_INDEX_SCHEMA_VERSION,
        "request_id": _clean(payload.get("request_id")),
        "latest_attempt_ref": _clean(payload.get("latest_attempt_ref")),
        "attempts": [item for item in attempts if isinstance(item, Mapping)],
        "updated_at": _clean(payload.get("updated_at")),
    }


def new_attempt_id() -> str:
    """Return a new product attempt id."""

    return _new_attempt_id()


def attempt_manifest_ref(attempt_id: str) -> str:
    """Return the manifest ref for an attempt id."""

    return _attempt_manifest_ref(attempt_id)


def next_attempt_generation(run_root: str | Path) -> int:
    """Return the next project attempt generation number."""

    return _next_generation(Path(run_root))


def write_before_attempt_snapshot(
    run_root: str | Path,
    *,
    attempt_id: str,
    snapshot_kind: str = "before_retry",
) -> str:
    """Snapshot stable Kernel refs before a new attempt overwrites them."""

    return _write_before_snapshot(Path(run_root), attempt_id=attempt_id, snapshot_kind=snapshot_kind)


def write_attempt_index(run_root: str | Path, manifest: Mapping[str, Any]) -> str:
    """Write the shared project attempt index."""

    return _write_attempt_index(Path(run_root), manifest)


def update_attempt_manifest(
    run_root: str | Path,
    *,
    attempt_ref: str,
    status: str,
    result_ref: str = "",
    error_summary: str = "",
    task_ref: str = "",
    lock_ref: str = "",
    output_manifest_ref: str = "",
) -> None:
    """Update a shared attempt manifest and refresh the attempt index."""

    _update_attempt_manifest(
        Path(run_root),
        attempt_ref=attempt_ref,
        status=status,
        result_ref=result_ref,
        error_summary=error_summary,
        task_ref=task_ref,
        lock_ref=lock_ref,
        output_manifest_ref=output_manifest_ref,
    )


def current_contract_hash(run_root: str | Path) -> str:
    """Return the current Kernel contract hash when available."""

    return _contract_hash(Path(run_root))


def _latest_retry_request(run_root: Path) -> dict[str, Any]:
    if not ref_exists(run_root, LATEST_RETRY_REQUEST_REF):
        raise mf.ContractValidationError("pending retry request is required")
    payload = read_json_ref(run_root, LATEST_RETRY_REQUEST_REF, "deepresearch_lifecycle_retry_request")
    if payload.get("kind") != "retry":
        raise mf.ContractValidationError("pending retry request is required")
    return dict(payload)


def _require_pending_retry(retry: Mapping[str, Any]) -> None:
    if retry.get("status") != "pending_retry":
        raise mf.ContractValidationError("pending retry request is required")
    if _clean(retry.get("next_required_boundary")) != "kernel_attempt":
        raise mf.ContractValidationError("pending retry request is not ready for a Kernel attempt")


def _require_no_pending_revision(run_root: Path) -> None:
    if not ref_exists(run_root, LATEST_REVISE_REQUEST_REF):
        return
    revise = read_json_ref(run_root, LATEST_REVISE_REQUEST_REF, "deepresearch_lifecycle_revise_request")
    if revise.get("kind") == "revise" and revise.get("status") == "pending_revision":
        raise mf.ContractValidationError("pending revision must be resolved before starting a retry attempt")


def _base_manifest(
    *,
    run_root: Path,
    request_id: str,
    attempt_id: str,
    generation: int,
    trigger_action: Mapping[str, Any],
    snapshot_ref: str,
    source_task_status: str,
) -> dict[str, Any]:
    lifecycle = _read_lifecycle(run_root)
    payload = {
        "schema_version": ATTEMPT_MANIFEST_SCHEMA_VERSION,
        "attempt_id": attempt_id,
        "generation": generation,
        "request_id": request_id,
        "kind": "retry_attempt",
        "status": "starting",
        "source_retry_request_ref": LATEST_RETRY_REQUEST_REF,
        "source_action_id": _clean(trigger_action.get("action_id")),
        "reason_ref": _clean(trigger_action.get("reason_ref")),
        "base_contract_ref": KERNEL_V2_CONTRACT_REF,
        "base_contract_hash": _contract_hash(run_root),
        "parent_result_ref": _clean(lifecycle.get("latest_run_ref")),
        "parent_flow_result_ref": _clean(lifecycle.get("latest_flow_result_ref")),
        "parent_run_status_ref": _clean(lifecycle.get("latest_run_status_ref")),
        "parent_web_task_ref": WEB_TASK_STATE_REF,
        "source_task_ref": WEB_TASK_STATE_REF,
        "source_task_status": source_task_status,
        "task_ref": WEB_TASK_STATE_REF,
        "lock_ref": "",
        "before_snapshot_ref": snapshot_ref,
        "result_ref": "",
        "flow_result_ref": "",
        "run_status_ref": "",
        "output_manifest_ref": "",
        "error_summary": "",
        "created_at": _utc_now(),
        "started_at": "",
        "finished_at": "",
    }
    mf.assert_refs_only_payload(payload, "deepresearch_attempt_manifest")
    return payload


def _update_attempt_manifest(
    run_root: Path,
    *,
    attempt_ref: str,
    status: str,
    result_ref: str = "",
    error_summary: str = "",
    task_ref: str = "",
    lock_ref: str = "",
    output_manifest_ref: str = "",
) -> None:
    manifest = read_json_ref(run_root, attempt_ref, "deepresearch_attempt_manifest")
    manifest["status"] = status
    if status == "running" and not manifest.get("started_at"):
        manifest["started_at"] = _utc_now()
    if status in {"completed", "failed", "blocked"}:
        manifest["finished_at"] = _utc_now()
    if result_ref:
        manifest["result_ref"] = mf.validate_ref(result_ref, "deepresearch_attempt_manifest.result_ref")
        manifest["run_status_ref"] = KERNEL_V2_RUN_STATUS_REF if ref_exists(run_root, KERNEL_V2_RUN_STATUS_REF) else ""
        lifecycle = _read_lifecycle(run_root)
        manifest["flow_result_ref"] = _clean(lifecycle.get("latest_flow_result_ref"))
    if task_ref:
        manifest["task_ref"] = mf.validate_ref(task_ref, "deepresearch_attempt_manifest.task_ref")
    if lock_ref:
        manifest["lock_ref"] = mf.validate_ref(lock_ref, "deepresearch_attempt_manifest.lock_ref")
    if output_manifest_ref:
        manifest["output_manifest_ref"] = mf.validate_ref(
            output_manifest_ref,
            "deepresearch_attempt_manifest.output_manifest_ref",
        )
    if error_summary:
        manifest["error_summary"] = _clean(error_summary)
    mf.assert_refs_only_payload(manifest, "deepresearch_attempt_manifest")
    write_json_ref(run_root, attempt_ref, manifest)
    _write_attempt_index(run_root, manifest)


def _write_before_snapshot(run_root: Path, *, attempt_id: str, snapshot_kind: str = "before_retry") -> str:
    entries: list[dict[str, str]] = []
    for source_ref in _SNAPSHOT_SOURCE_REFS:
        source_path = resolve_workspace_ref(run_root, source_ref)
        if not source_path.is_file():
            continue
        snapshot_ref = f"project/attempts/{attempt_id}/snapshots/before/{source_ref}"
        snapshot_path = resolve_workspace_ref(run_root, snapshot_ref)
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, snapshot_path)
        entries.append({
            "source_ref": source_ref,
            "snapshot_ref": snapshot_ref,
            "sha256": sha256_ref(run_root, snapshot_ref),
        })
    snapshot_ref = f"project/attempts/{attempt_id}/before_snapshot.json"
    payload = {
        "schema_version": ATTEMPT_SNAPSHOT_SCHEMA_VERSION,
        "attempt_id": attempt_id,
        "snapshot_kind": snapshot_kind,
        "entries": entries,
        "created_at": _utc_now(),
    }
    mf.assert_refs_only_payload(payload, "deepresearch_attempt_snapshot")
    return write_json_ref(run_root, snapshot_ref, payload)


def _write_attempt_index(run_root: Path, manifest: Mapping[str, Any]) -> str:
    index = read_attempt_index(run_root)
    records = [
        item
        for item in index.get("attempts", [])
        if isinstance(item, Mapping) and item.get("attempt_id") != manifest.get("attempt_id")
    ]
    record = _index_record(manifest)
    records.append(record)
    payload = {
        "schema_version": ATTEMPT_INDEX_SCHEMA_VERSION,
        "request_id": _clean(manifest.get("request_id")),
        "latest_attempt_ref": record["attempt_ref"],
        "attempts": records,
        "updated_at": _utc_now(),
    }
    mf.assert_refs_only_payload(payload, "deepresearch_attempt_index")
    return write_json_ref(run_root, ATTEMPT_INDEX_REF, payload)


def _index_record(manifest: Mapping[str, Any]) -> dict[str, Any]:
    attempt_id = _clean(manifest.get("attempt_id"))
    payload = {
        "attempt_id": attempt_id,
        "generation": int(manifest.get("generation") or 0),
        "kind": _clean(manifest.get("kind")),
        "status": _clean(manifest.get("status")),
        "attempt_ref": _attempt_manifest_ref(attempt_id),
        "source_retry_request_ref": _clean(manifest.get("source_retry_request_ref")),
        "source_revision_request_ref": _clean(manifest.get("source_revision_request_ref")),
        "revision_record_ref": _clean(manifest.get("revision_record_ref")),
        "output_manifest_ref": _clean(manifest.get("output_manifest_ref")),
        "created_at": _clean(manifest.get("created_at")),
        "started_at": _clean(manifest.get("started_at")),
        "finished_at": _clean(manifest.get("finished_at")),
    }
    mf.assert_refs_only_payload(payload, "deepresearch_attempt_index_record")
    return payload


def _next_generation(run_root: Path) -> int:
    index = read_attempt_index(run_root)
    generations = [
        int(item.get("generation") or 0)
        for item in index.get("attempts", [])
        if isinstance(item, Mapping)
    ]
    return max(generations or [0]) + 1


def _empty_index() -> dict[str, Any]:
    return {
        "schema_version": ATTEMPT_INDEX_SCHEMA_VERSION,
        "request_id": "",
        "latest_attempt_ref": "",
        "attempts": [],
        "updated_at": "",
    }


def _sanitized_action(action: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "action_id": _clean(action.get("action_id")),
        "kind": _clean(action.get("kind")),
        "status": _clean(action.get("status")),
        "consumed_by_attempt_ref": _clean(action.get("consumed_by_attempt_ref")),
    }


def _existing_attempt_result(run_root: Path, retry: Mapping[str, Any]) -> dict[str, Any]:
    attempt_ref = _clean(retry.get("consumed_by_attempt_ref"))
    attempt = read_json_ref(run_root, attempt_ref, "deepresearch_attempt_manifest")
    task_state = read_web_task_state(run_root)
    return {
        "schema_version": "missionforge_deepresearch.retry_attempt_start_result.v1",
        "status": _clean(attempt.get("status")) or _clean(task_state.get("status")) or "unknown",
        "attempt": attempt,
        "task": task_state,
        "action": _sanitized_action(retry),
    }


def _contract_hash(run_root: Path) -> str:
    if not ref_exists(run_root, KERNEL_V2_CONTRACT_REF):
        return ""
    contract = read_json_ref(run_root, KERNEL_V2_CONTRACT_REF, "deepresearch_attempt_contract")
    return mf.stable_json_hash(contract)


def _read_lifecycle(run_root: Path) -> dict[str, Any]:
    if not ref_exists(run_root, PROJECT_LIFECYCLE_STATE_REF):
        return {}
    try:
        return read_json_ref(run_root, PROJECT_LIFECYCLE_STATE_REF, "deepresearch_lifecycle_state")
    except (json.JSONDecodeError, UnicodeDecodeError, OSError, mf.ContractValidationError):
        return {}


def _restore_current_revision_in_lifecycle(run_root: Path) -> None:
    index = read_contract_revision_index(run_root)
    revision_ref = _clean(index.get("latest_revision_ref"))
    if not revision_ref or not ref_exists(run_root, PROJECT_LIFECYCLE_STATE_REF):
        return
    lifecycle = _read_lifecycle(run_root)
    if not lifecycle:
        return
    lifecycle["current_revision_ref"] = mf.validate_ref(revision_ref, "deepresearch_lifecycle.current_revision_ref")
    lifecycle["updated_at"] = _utc_now()
    mf.assert_refs_only_payload(lifecycle, "deepresearch_lifecycle_state")
    write_json_ref(run_root, PROJECT_LIFECYCLE_STATE_REF, lifecycle)


def _attempt_progress_sink(
    sink: mf.PiWorkerProgressSink | None,
    attempt_ref: str,
) -> mf.PiWorkerProgressSink | None:
    safe_attempt_ref = mf.validate_ref(attempt_ref, "deepresearch_attempt.progress_ref")
    if sink is None:
        return None

    def wrapped(payload: Mapping[str, Any] | Any) -> None:
        if isinstance(payload, Mapping):
            refs = payload.get("refs", [])
            ref_list = refs if isinstance(refs, list) else [refs]
            sink({**dict(payload), "refs": [safe_attempt_ref, *ref_list]})
            return
        sink({"refs": [safe_attempt_ref]})

    return wrapped


def _attempt_manifest_ref(attempt_id: str) -> str:
    return mf.validate_ref(f"project/attempts/{attempt_id}/attempt_manifest.json", "deepresearch_attempt.ref")


def _new_attempt_id() -> str:
    return f"ATT-{uuid4().hex}"


def _run_ref(request_id: str) -> str:
    if not isinstance(request_id, str) or not request_id.strip():
        raise mf.ContractValidationError("DeepResearch request_id is required")
    return mf.validate_ref(f"runs/{request_id.strip()}", "deepresearch_attempt.run_ref")


def _clean(value: Any) -> str:
    return str(value).strip() if isinstance(value, str) else ""


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
