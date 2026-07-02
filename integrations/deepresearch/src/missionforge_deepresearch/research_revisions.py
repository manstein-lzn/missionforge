"""DeepResearch explicit contract revision lifecycle."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Mapping
from uuid import uuid4

import missionforge as mf

from .attempt_outputs import write_attempt_output_manifest
from .frontdesk import FRONTDESK_RESEARCH_REQUEST_REF
from .kernel_v2 import (
    KERNEL_V2_CITATION_PROJECTED_REPORT_REF,
    KERNEL_V2_CONTRACT_REF,
    KERNEL_V2_FINAL_REPORT_REF,
    KERNEL_V2_RESULT_REF,
    KERNEL_V2_RUN_STATUS_REF,
    run_deepresearch_kernel_v2,
)
from .lifecycle_actions import (
    LATEST_RETRY_REQUEST_REF,
    LATEST_REVISE_REQUEST_REF,
    consume_latest_revise_request,
)
from .product_contract import AcademicResearchRequest
from .project_lifecycle import PROJECT_LIFECYCLE_STATE_REF
from .project_seeds import apply_project_seed_inputs
from .research_attempts import (
    attempt_manifest_ref,
    current_contract_hash,
    new_attempt_id,
    next_attempt_generation,
    read_attempt_index,
    update_attempt_manifest,
    write_attempt_index,
    write_before_attempt_snapshot,
)
from .research_requests import CONTRACT_REVISION_INDEX_REF, read_contract_revision_index, read_current_research_request
from .web_common import WebKernelConfig
from .web_tasks import WEB_TASK_LOCK_REF, WEB_TASK_STATE_REF, read_web_task_state, start_background_task
from .workspace import (
    read_json_ref,
    read_text_ref,
    ref_exists,
    resolve_workspace_ref,
    write_json_ref,
    write_text_ref,
)


CONTRACT_REVISION_RECORD_SCHEMA_VERSION = "missionforge_deepresearch.contract_revision_record.v1"
CONTRACT_REVISION_PROPOSAL_SCHEMA_VERSION = "missionforge_deepresearch.contract_revision_proposal.v1"
_REVISION_STARTABLE_TASK_STATUSES = {"completed", "failed", "interrupted"}


def start_revision_attempt(
    *,
    workspace: str | Path,
    request_id: str,
    config: WebKernelConfig,
    event_sink: Callable[[mf.FlowLedgerEvent], None] | None = None,
    runtime_progress_sink: mf.PiWorkerProgressSink | None = None,
) -> dict[str, Any]:
    """Consume a pending revision request, freeze a revised contract, and run Kernel."""

    root = Path(workspace).resolve()
    run_root = resolve_workspace_ref(root, _run_ref(request_id))
    base_request = read_current_research_request(workspace=root, request_id=request_id)
    _require_no_pending_retry(run_root)
    revise = _latest_revise_request(run_root)
    if revise.get("status") == "consumed" and _clean(revise.get("consumed_by_attempt_ref")):
        return _existing_revision_result(run_root, revise)
    _require_pending_revision(revise)

    revision_record: dict[str, str] = {}
    action_record: dict[str, Any] = {}
    request_record: dict[str, AcademicResearchRequest] = {}

    def before_start(start_state: Mapping[str, Any]) -> None:
        _require_no_pending_retry(run_root)
        latest_revise = _latest_revise_request(run_root)
        _require_pending_revision(latest_revise)
        attempt_id = new_attempt_id()
        revision_id = _new_revision_id()
        attempt_ref = attempt_manifest_ref(attempt_id)
        revision_ref = _revision_record_ref(revision_id)
        proposal_ref = _revision_proposal_ref(revision_id)
        directive_ref = _revision_directive_ref(revision_id)
        revised_request_ref = _revised_request_ref(revision_id)
        snapshot_ref = write_before_attempt_snapshot(
            run_root,
            attempt_id=attempt_id,
            snapshot_kind="before_revision",
        )
        directive_text = _read_revision_directive(run_root, latest_revise)
        write_text_ref(run_root, directive_ref, directive_text)
        revised_request = _revised_request(
            base_request,
            request_id=request_id,
            run_root=run_root,
            revision_ref=revision_ref,
            proposal_ref=proposal_ref,
            directive_ref=directive_ref,
        )
        write_json_ref(run_root, revised_request_ref, revised_request.to_dict())
        proposal = _revision_proposal(
            run_root=run_root,
            request_id=request_id,
            revision_id=revision_id,
            revise_action=latest_revise,
            base_request=base_request,
            proposal_ref=proposal_ref,
            directive_ref=directive_ref,
            revised_request_ref=revised_request_ref,
        )
        write_json_ref(run_root, proposal_ref, proposal)
        record = _revision_record(
            run_root=run_root,
            request_id=request_id,
            revision_id=revision_id,
            revise_action=latest_revise,
            base_request=base_request,
            proposal_ref=proposal_ref,
            directive_ref=directive_ref,
            revised_request_ref=revised_request_ref,
            attempt_ref=attempt_ref,
            snapshot_ref=snapshot_ref,
        )
        write_json_ref(run_root, revision_ref, record)
        manifest = _revision_attempt_manifest(
            run_root=run_root,
            request_id=request_id,
            attempt_id=attempt_id,
            revision_id=revision_id,
            generation=next_attempt_generation(run_root),
            revise_action=latest_revise,
            revision_ref=revision_ref,
            proposal_ref=proposal_ref,
            revised_request_ref=revised_request_ref,
            snapshot_ref=snapshot_ref,
        )
        write_json_ref(run_root, attempt_ref, manifest)
        write_attempt_index(run_root, manifest)
        _write_revision_index(run_root, record)
        try:
            consumed = consume_latest_revise_request(
                run_root,
                revision_ref=revision_ref,
                attempt_ref=attempt_ref,
            )
        except Exception:
            update_attempt_manifest(
                run_root,
                attempt_ref=attempt_ref,
                status="blocked",
                error_summary="revision request consumption failed",
            )
            _update_revision_record(run_root, revision_ref=revision_ref, status="blocked")
            raise
        update_attempt_manifest(
            run_root,
            attempt_ref=attempt_ref,
            status="running",
            task_ref=WEB_TASK_STATE_REF,
            lock_ref=WEB_TASK_LOCK_REF if start_state.get("lock_ref") == WEB_TASK_LOCK_REF else "",
        )
        _update_revision_record(run_root, revision_ref=revision_ref, status="running")
        _record_current_revision_in_lifecycle(run_root, revision_ref=revision_ref)
        revision_record.update({"revision_ref": revision_ref, "attempt_ref": attempt_ref})
        request_record["request"] = revised_request
        action_record.update(consumed)

    def runner() -> Any:
        attempt_ref = _clean(revision_record.get("attempt_ref"))
        revision_ref = _clean(revision_record.get("revision_ref"))
        revised_request = request_record.get("request")
        if not attempt_ref or not revision_ref or revised_request is None:
            raise mf.ContractValidationError("revision attempt was not initialized")
        try:
            result = run_deepresearch_kernel_v2(
                revised_request,
                workspace=root,
                adapter=config.adapter_factory(revised_request.research_intensity),
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
                error_summary=f"{type(exc).__name__}: revision attempt failed",
            )
            _update_revision_record(run_root, revision_ref=revision_ref, status="failed")
            raise
        attempt = read_json_ref(run_root, attempt_ref, "deepresearch_attempt_manifest")
        output_manifest_ref = write_attempt_output_manifest(
            run_root,
            attempt_id=_clean(attempt.get("attempt_id")),
            attempt_ref=attempt_ref,
            attempt_kind="revision_attempt",
        )
        update_attempt_manifest(
            run_root,
            attempt_ref=attempt_ref,
            status="completed",
            result_ref=getattr(result, "result_ref", "") if result is not None else "",
            output_manifest_ref=output_manifest_ref,
        )
        _update_revision_record(
            run_root,
            revision_ref=revision_ref,
            status="completed",
            result_ref=getattr(result, "result_ref", "") if result is not None else "",
            output_manifest_ref=output_manifest_ref,
        )
        _record_current_revision_in_lifecycle(run_root, revision_ref=revision_ref)
        return result

    task_state = start_background_task(
        workspace=root,
        request_id=request_id,
        task_kind="kernel_v2_revision_attempt",
        runner=runner,
        restart_terminal_statuses=_REVISION_STARTABLE_TASK_STATUSES,
        before_start=before_start,
    )
    if not revision_record:
        latest_revise = _latest_revise_request(run_root)
        if latest_revise.get("status") == "consumed" and _clean(latest_revise.get("consumed_by_attempt_ref")):
            return _existing_revision_result(run_root, latest_revise)
        raise mf.ContractValidationError("revision attempt did not start")
    if task_state.get("status") != "running":
        raise mf.ContractValidationError("revision attempt did not start")
    revision_ref = revision_record["revision_ref"]
    attempt_ref = revision_record["attempt_ref"]
    return {
        "schema_version": "missionforge_deepresearch.revision_attempt_start_result.v1",
        "status": "running",
        "revision": _sanitized_revision(read_json_ref(run_root, revision_ref, "deepresearch_contract_revision")),
        "attempt": read_json_ref(run_root, attempt_ref, "deepresearch_attempt_manifest"),
        "task": task_state,
        "action": _sanitized_action(action_record),
    }


def _latest_revise_request(run_root: Path) -> dict[str, Any]:
    if not ref_exists(run_root, LATEST_REVISE_REQUEST_REF):
        raise mf.ContractValidationError("pending revision request is required")
    payload = read_json_ref(run_root, LATEST_REVISE_REQUEST_REF, "deepresearch_lifecycle_revise_request")
    if payload.get("kind") != "revise":
        raise mf.ContractValidationError("pending revision request is required")
    return dict(payload)


def _require_pending_revision(revise: Mapping[str, Any]) -> None:
    if revise.get("status") != "pending_revision":
        raise mf.ContractValidationError("pending revision request is required")
    if _clean(revise.get("next_required_boundary")) != "frontdesk_contract_revision":
        raise mf.ContractValidationError("pending revision request is not ready for contract revision")


def _require_no_pending_retry(run_root: Path) -> None:
    if not ref_exists(run_root, LATEST_RETRY_REQUEST_REF):
        return
    retry = read_json_ref(run_root, LATEST_RETRY_REQUEST_REF, "deepresearch_lifecycle_retry_request")
    if retry.get("kind") == "retry" and retry.get("status") == "pending_retry":
        raise mf.ContractValidationError("pending retry must be resolved before starting a revision attempt")


def _read_revision_directive(run_root: Path, revise_action: Mapping[str, Any]) -> str:
    reason_ref = _clean(revise_action.get("reason_ref"))
    if not reason_ref:
        raise mf.ContractValidationError("revision reason ref is required")
    text = read_text_ref(run_root, reason_ref).strip()
    if not text:
        raise mf.ContractValidationError("revision directive text is required")
    return text + "\n"


def _revised_request(
    base_request: AcademicResearchRequest,
    *,
    request_id: str,
    run_root: Path,
    revision_ref: str,
    proposal_ref: str,
    directive_ref: str,
) -> AcademicResearchRequest:
    payload = base_request.to_dict()
    revision_refs = _dedupe(
        [
            *list(payload.get("contract_revision_refs") or []),
            _outer_ref(request_id, revision_ref),
            _outer_ref(request_id, proposal_ref),
            _outer_ref(request_id, directive_ref),
        ]
    )
    previous_run_refs = _dedupe([*list(payload.get("previous_run_refs") or []), *_prior_output_refs(run_root, request_id)])
    constraints = _dedupe(
        [
            *list(payload.get("constraints") or []),
            f"Apply explicit contract revision artifacts staged from {_outer_ref(request_id, revision_ref)}.",
        ]
    )
    payload.update(
        {
            "contract_revision_refs": revision_refs,
            "previous_run_refs": previous_run_refs,
            "constraints": constraints,
        }
    )
    return apply_project_seed_inputs(run_root, AcademicResearchRequest.from_dict(payload))


def _revision_proposal(
    *,
    run_root: Path,
    request_id: str,
    revision_id: str,
    revise_action: Mapping[str, Any],
    base_request: AcademicResearchRequest,
    proposal_ref: str,
    directive_ref: str,
    revised_request_ref: str,
) -> dict[str, Any]:
    payload = {
        "schema_version": CONTRACT_REVISION_PROPOSAL_SCHEMA_VERSION,
        "revision_id": revision_id,
        "request_id": request_id,
        "status": "frozen",
        "source_revise_request_ref": LATEST_REVISE_REQUEST_REF,
        "source_action_id": _clean(revise_action.get("action_id")),
        "reason_ref": _clean(revise_action.get("reason_ref")),
        "directive_ref": directive_ref,
        "base_request_ref": _current_request_source_ref(run_root),
        "base_request_hash": mf.stable_json_hash(base_request.to_dict()),
        "base_contract_ref": KERNEL_V2_CONTRACT_REF if ref_exists(run_root, KERNEL_V2_CONTRACT_REF) else "",
        "base_contract_hash": current_contract_hash(run_root),
        "proposal_ref": proposal_ref,
        "revised_request_ref": revised_request_ref,
        "created_at": _utc_now(),
    }
    mf.assert_refs_only_payload(payload, "deepresearch_contract_revision_proposal")
    return payload


def _revision_record(
    *,
    run_root: Path,
    request_id: str,
    revision_id: str,
    revise_action: Mapping[str, Any],
    base_request: AcademicResearchRequest,
    proposal_ref: str,
    directive_ref: str,
    revised_request_ref: str,
    attempt_ref: str,
    snapshot_ref: str,
) -> dict[str, Any]:
    revised_payload = read_json_ref(run_root, revised_request_ref, "deepresearch_revised_request")
    payload = {
        "schema_version": CONTRACT_REVISION_RECORD_SCHEMA_VERSION,
        "revision_id": revision_id,
        "request_id": request_id,
        "status": "starting",
        "source_revise_request_ref": LATEST_REVISE_REQUEST_REF,
        "source_action_id": _clean(revise_action.get("action_id")),
        "reason_ref": _clean(revise_action.get("reason_ref")),
        "directive_ref": directive_ref,
        "proposal_ref": proposal_ref,
        "base_request_ref": _current_request_source_ref(run_root),
        "base_request_hash": mf.stable_json_hash(base_request.to_dict()),
        "base_contract_ref": KERNEL_V2_CONTRACT_REF if ref_exists(run_root, KERNEL_V2_CONTRACT_REF) else "",
        "base_contract_hash": current_contract_hash(run_root),
        "revised_request_ref": revised_request_ref,
        "revised_request_hash": mf.stable_json_hash(revised_payload),
        "attempt_ref": attempt_ref,
        "before_snapshot_ref": snapshot_ref,
        "result_ref": "",
        "run_status_ref": "",
        "output_manifest_ref": "",
        "created_at": _utc_now(),
        "started_at": "",
        "finished_at": "",
    }
    mf.assert_refs_only_payload(payload, "deepresearch_contract_revision_record")
    return payload


def _revision_attempt_manifest(
    *,
    run_root: Path,
    request_id: str,
    attempt_id: str,
    revision_id: str,
    generation: int,
    revise_action: Mapping[str, Any],
    revision_ref: str,
    proposal_ref: str,
    revised_request_ref: str,
    snapshot_ref: str,
) -> dict[str, Any]:
    lifecycle = _read_lifecycle(run_root)
    payload = {
        "schema_version": "missionforge_deepresearch.attempt_manifest.v1",
        "attempt_id": attempt_id,
        "generation": generation,
        "request_id": request_id,
        "kind": "revision_attempt",
        "status": "starting",
        "revision_id": revision_id,
        "source_revision_request_ref": LATEST_REVISE_REQUEST_REF,
        "source_action_id": _clean(revise_action.get("action_id")),
        "reason_ref": _clean(revise_action.get("reason_ref")),
        "revision_record_ref": revision_ref,
        "revision_proposal_ref": proposal_ref,
        "revised_request_ref": revised_request_ref,
        "base_contract_ref": KERNEL_V2_CONTRACT_REF,
        "base_contract_hash": current_contract_hash(run_root),
        "parent_result_ref": _clean(lifecycle.get("latest_run_ref")),
        "parent_flow_result_ref": _clean(lifecycle.get("latest_flow_result_ref")),
        "parent_run_status_ref": _clean(lifecycle.get("latest_run_status_ref")),
        "parent_web_task_ref": WEB_TASK_STATE_REF,
        "source_task_ref": WEB_TASK_STATE_REF,
        "source_task_status": _clean(read_web_task_state(run_root).get("status")),
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
    mf.assert_refs_only_payload(payload, "deepresearch_revision_attempt_manifest")
    return payload


def _write_revision_index(run_root: Path, record: Mapping[str, Any]) -> str:
    index = read_contract_revision_index(run_root)
    records = [
        item
        for item in index.get("revisions", [])
        if isinstance(item, Mapping) and item.get("revision_id") != record.get("revision_id")
    ]
    index_record = _revision_index_record(record)
    records.append(index_record)
    payload = {
        "schema_version": "missionforge_deepresearch.contract_revision_index.v1",
        "request_id": _clean(record.get("request_id")),
        "latest_revision_ref": index_record["revision_ref"],
        "latest_revised_request_ref": index_record["revised_request_ref"],
        "revisions": records,
        "updated_at": _utc_now(),
    }
    mf.assert_refs_only_payload(payload, "deepresearch_contract_revision_index")
    return write_json_ref(run_root, CONTRACT_REVISION_INDEX_REF, payload)


def _revision_index_record(record: Mapping[str, Any]) -> dict[str, Any]:
    payload = {
        "revision_id": _clean(record.get("revision_id")),
        "status": _clean(record.get("status")),
        "revision_ref": _revision_record_ref(_clean(record.get("revision_id"))),
        "proposal_ref": _clean(record.get("proposal_ref")),
        "revised_request_ref": _clean(record.get("revised_request_ref")),
        "attempt_ref": _clean(record.get("attempt_ref")),
        "output_manifest_ref": _clean(record.get("output_manifest_ref")),
        "created_at": _clean(record.get("created_at")),
        "started_at": _clean(record.get("started_at")),
        "finished_at": _clean(record.get("finished_at")),
    }
    mf.assert_refs_only_payload(payload, "deepresearch_contract_revision_index_record")
    return payload


def _update_revision_record(
    run_root: Path,
    *,
    revision_ref: str,
    status: str,
    result_ref: str = "",
    output_manifest_ref: str = "",
) -> None:
    record = read_json_ref(run_root, revision_ref, "deepresearch_contract_revision_record")
    record["status"] = status
    if status == "running" and not record.get("started_at"):
        record["started_at"] = _utc_now()
    if status in {"completed", "failed", "blocked"}:
        record["finished_at"] = _utc_now()
    if result_ref:
        record["result_ref"] = mf.validate_ref(result_ref, "deepresearch_contract_revision_record.result_ref")
        record["run_status_ref"] = KERNEL_V2_RUN_STATUS_REF if ref_exists(run_root, KERNEL_V2_RUN_STATUS_REF) else ""
    if output_manifest_ref:
        record["output_manifest_ref"] = mf.validate_ref(
            output_manifest_ref,
            "deepresearch_contract_revision_record.output_manifest_ref",
        )
    mf.assert_refs_only_payload(record, "deepresearch_contract_revision_record")
    write_json_ref(run_root, revision_ref, record)
    _write_revision_index(run_root, record)


def _record_current_revision_in_lifecycle(run_root: Path, *, revision_ref: str) -> None:
    if not ref_exists(run_root, PROJECT_LIFECYCLE_STATE_REF):
        return
    lifecycle = read_json_ref(run_root, PROJECT_LIFECYCLE_STATE_REF, "deepresearch_lifecycle_state")
    lifecycle["current_revision_ref"] = mf.validate_ref(revision_ref, "deepresearch_lifecycle.current_revision_ref")
    lifecycle["updated_at"] = _utc_now()
    mf.assert_refs_only_payload(lifecycle, "deepresearch_lifecycle_state")
    write_json_ref(run_root, PROJECT_LIFECYCLE_STATE_REF, lifecycle)


def _attempt_progress_sink(
    sink: mf.PiWorkerProgressSink | None,
    attempt_ref: str,
) -> mf.PiWorkerProgressSink | None:
    safe_attempt_ref = mf.validate_ref(attempt_ref, "deepresearch_revision.progress_ref")
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


def _current_request_source_ref(run_root: Path) -> str:
    index = read_contract_revision_index(run_root)
    latest_ref = _clean(index.get("latest_revised_request_ref"))
    if latest_ref:
        return latest_ref
    return FRONTDESK_RESEARCH_REQUEST_REF


def _prior_output_refs(run_root: Path, request_id: str) -> list[str]:
    refs = []
    for ref in (
        KERNEL_V2_RESULT_REF,
        KERNEL_V2_RUN_STATUS_REF,
        KERNEL_V2_CITATION_PROJECTED_REPORT_REF,
        KERNEL_V2_FINAL_REPORT_REF,
    ):
        if ref_exists(run_root, ref):
            refs.append(_outer_ref(request_id, ref))
    return refs


def _existing_revision_result(run_root: Path, revise: Mapping[str, Any]) -> dict[str, Any]:
    revision_ref = _clean(revise.get("consumed_by_revision_ref"))
    attempt_ref = _clean(revise.get("consumed_by_attempt_ref"))
    revision = read_json_ref(run_root, revision_ref, "deepresearch_contract_revision_record")
    attempt = read_json_ref(run_root, attempt_ref, "deepresearch_attempt_manifest")
    task_state = read_web_task_state(run_root)
    return {
        "schema_version": "missionforge_deepresearch.revision_attempt_start_result.v1",
        "status": _clean(attempt.get("status")) or _clean(task_state.get("status")) or "unknown",
        "revision": _sanitized_revision(revision),
        "attempt": attempt,
        "task": task_state,
        "action": _sanitized_action(revise),
    }


def _sanitized_revision(revision: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "revision_id": _clean(revision.get("revision_id")),
        "status": _clean(revision.get("status")),
        "revision_ref": _revision_record_ref(_clean(revision.get("revision_id"))),
        "proposal_ref": _clean(revision.get("proposal_ref")),
        "revised_request_ref": _clean(revision.get("revised_request_ref")),
        "attempt_ref": _clean(revision.get("attempt_ref")),
    }


def _sanitized_action(action: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "action_id": _clean(action.get("action_id")),
        "kind": _clean(action.get("kind")),
        "status": _clean(action.get("status")),
        "consumed_by_revision_ref": _clean(action.get("consumed_by_revision_ref")),
        "consumed_by_attempt_ref": _clean(action.get("consumed_by_attempt_ref")),
    }


def _read_lifecycle(run_root: Path) -> dict[str, Any]:
    if not ref_exists(run_root, PROJECT_LIFECYCLE_STATE_REF):
        return {}
    try:
        return read_json_ref(run_root, PROJECT_LIFECYCLE_STATE_REF, "deepresearch_lifecycle_state")
    except mf.ContractValidationError:
        return {}


def _revision_record_ref(revision_id: str) -> str:
    return mf.validate_ref(f"project/revisions/{revision_id}/revision_record.json", "deepresearch_revision.record_ref")


def _revision_proposal_ref(revision_id: str) -> str:
    return mf.validate_ref(f"project/revisions/{revision_id}/revision_proposal.json", "deepresearch_revision.proposal_ref")


def _revision_directive_ref(revision_id: str) -> str:
    return mf.validate_ref(f"project/revisions/{revision_id}/revision_directive.md", "deepresearch_revision.directive_ref")


def _revised_request_ref(revision_id: str) -> str:
    return mf.validate_ref(f"project/revisions/{revision_id}/revised_research_request.json", "deepresearch_revision.request_ref")


def _new_revision_id() -> str:
    return f"REV-{uuid4().hex}"


def _run_ref(request_id: str) -> str:
    if not isinstance(request_id, str) or not request_id.strip():
        raise mf.ContractValidationError("DeepResearch request_id is required")
    return mf.validate_ref(f"runs/{request_id.strip()}", "deepresearch_revision.run_ref")


def _outer_ref(request_id: str, inner_ref: str) -> str:
    return mf.validate_ref(f"runs/{request_id}/{inner_ref}", "deepresearch_revision.outer_ref")


def _dedupe(values: list[str]) -> list[str]:
    result = []
    seen = set()
    for value in values:
        text = _clean(value)
        if text and text not in seen:
            result.append(text)
            seen.add(text)
    return result


def _clean(value: Any) -> str:
    return str(value).strip() if isinstance(value, str) else ""


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
