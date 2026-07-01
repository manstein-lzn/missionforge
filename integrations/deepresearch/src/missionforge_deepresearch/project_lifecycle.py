"""DeepResearch project lifecycle refs.

This module records product-level project state and opaque MissionForge
ContextPackage refs. It does not inspect, trim, summarize, or reinterpret
ContextPackage internals.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

import missionforge as mf

from .workspace import read_json_ref, ref_exists, write_json_ref


PROJECT_MANIFEST_REF = "project/project_manifest.json"
PROJECT_LIFECYCLE_STATE_REF = "project/lifecycle_state.json"
PROJECT_RUN_INDEX_REF = "project/run_index.json"


def write_project_manifest(
    run_root: str | Path,
    *,
    request_id: str,
) -> str:
    """Write the stable project manifest if it does not already exist."""

    if ref_exists(run_root, PROJECT_MANIFEST_REF):
        return PROJECT_MANIFEST_REF
    payload = {
        "schema_version": "missionforge_deepresearch.project_manifest.v1",
        "request_id": request_id,
        "product": "deepresearch",
        "lifecycle_state_ref": PROJECT_LIFECYCLE_STATE_REF,
        "run_index_ref": PROJECT_RUN_INDEX_REF,
        "created_at": _utc_now(),
    }
    mf.assert_refs_only_payload(payload, "deepresearch_project_manifest")
    return write_json_ref(run_root, PROJECT_MANIFEST_REF, payload)


def write_kernel_lifecycle_state(
    run_root: str | Path,
    *,
    request_id: str,
    product_status: str,
    flow_result: mf.FlowRunResult,
    result_ref: str,
    contract_ref: str,
    run_status_ref: str,
    research_state_ref: str,
    final_report_ref: str,
) -> str:
    """Write project lifecycle state for a completed Kernel v2 update."""

    step_record_refs = list(flow_result.flow_result.step_record_refs)
    package_refs = latest_context_package_refs(run_root, step_record_refs)
    phase = _phase_from_status(product_status)
    payload = {
        "schema_version": "missionforge_deepresearch.lifecycle_state.v1",
        "request_id": request_id,
        "phase": phase,
        "active_agent": _active_agent(step_record_refs, package_refs),
        "control_agent": "frontdesk",
        "latest_run_ref": result_ref,
        "latest_flow_result_ref": flow_result.flow_result_ref,
        "latest_run_status_ref": run_status_ref,
        "current_contract_ref": contract_ref,
        "current_revision_ref": "",
        "research_state_ref": research_state_ref if ref_exists(run_root, research_state_ref) else "",
        "final_report_ref": final_report_ref if ref_exists(run_root, final_report_ref) else "",
        "latest_source_mapper_context_package_ref": package_refs.get("source_mapper", ""),
        "latest_researcher_context_package_ref": package_refs.get("researcher", ""),
        "latest_reviewer_context_package_ref": package_refs.get("reviewer", ""),
        "latest_judge_context_package_ref": package_refs.get("judge", ""),
        "updated_at": _utc_now(),
    }
    mf.assert_refs_only_payload(payload, "deepresearch_lifecycle_state")
    write_json_ref(run_root, PROJECT_LIFECYCLE_STATE_REF, payload)
    _append_run_index(
        run_root,
        request_id=request_id,
        phase=phase,
        status=product_status,
        result_ref=result_ref,
        flow_result_ref=flow_result.flow_result_ref,
        context_package_refs=package_refs,
    )
    return PROJECT_LIFECYCLE_STATE_REF


def latest_context_package_refs(run_root: str | Path, step_record_refs: list[str]) -> dict[str, str]:
    """Return the latest opaque ContextPackage ref for each Kernel step id."""

    result: dict[str, str] = {}
    for step_record_ref in step_record_refs:
        if not ref_exists(run_root, step_record_ref):
            continue
        record = read_json_ref(run_root, step_record_ref, "deepresearch_step_record")
        step_id = record.get("step_id")
        if not isinstance(step_id, str) or not step_id:
            continue
        metadata = record.get("metadata", {})
        if not isinstance(metadata, Mapping):
            continue
        package_ref = metadata.get("context_package_ref")
        if isinstance(package_ref, str) and package_ref:
            result[step_id] = mf.validate_ref(package_ref, "deepresearch_lifecycle.context_package_ref")
    return result


def _append_run_index(
    run_root: str | Path,
    *,
    request_id: str,
    phase: str,
    status: str,
    result_ref: str,
    flow_result_ref: str,
    context_package_refs: Mapping[str, str],
) -> None:
    if ref_exists(run_root, PROJECT_RUN_INDEX_REF):
        payload = read_json_ref(run_root, PROJECT_RUN_INDEX_REF, "deepresearch_run_index")
        runs = payload.get("runs", [])
        if not isinstance(runs, list):
            runs = []
    else:
        runs = []
    entry = {
        "request_id": request_id,
        "phase": phase,
        "status": status,
        "result_ref": result_ref,
        "flow_result_ref": flow_result_ref,
        "context_packages": dict(context_package_refs),
        "updated_at": _utc_now(),
    }
    runs = [item for item in runs if not isinstance(item, Mapping) or item.get("result_ref") != result_ref]
    runs.append(entry)
    payload = {
        "schema_version": "missionforge_deepresearch.run_index.v1",
        "request_id": request_id,
        "runs": runs,
    }
    mf.assert_refs_only_payload(payload, "deepresearch_run_index")
    write_json_ref(run_root, PROJECT_RUN_INDEX_REF, payload)


def _phase_from_status(status: str) -> str:
    if status == "accepted":
        return "accepted"
    if status in {"failed", "rejected"}:
        return "rejected"
    if status == "revision_required":
        return "revision_required"
    if "blocked" in status or status in {"cancelled", "paused"}:
        return "blocked"
    return "running"


def _active_agent(step_record_refs: list[str], context_package_refs: Mapping[str, str]) -> str:
    for step_record_ref in reversed(step_record_refs):
        for step_id in context_package_refs:
            if f"/steps/{step_id}/" in step_record_ref or step_record_ref.endswith(f"/{step_id}/step_record.json"):
                return step_id
    if context_package_refs:
        return next(reversed(dict(context_package_refs)))
    return "frontdesk"


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
