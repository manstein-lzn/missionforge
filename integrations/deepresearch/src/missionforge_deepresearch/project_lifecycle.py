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
PROJECT_RESUME_DIAGNOSTICS_REF = "project/resume_diagnostics.json"

ROLE_CONTEXT_PACKAGE_POINTER_REFS = {
    "frontdesk": "context/frontdesk/latest_context_package.json",
    "source_mapper": "context/source_mapper/latest_context_package.json",
    "researcher": "context/researcher/latest_context_package.json",
    "reviewer": "context/reviewer/latest_context_package.json",
    "judge": "context/judge/latest_context_package.json",
}


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
    package_records = latest_context_package_records(run_root, step_record_refs)
    package_refs = {role: record["context_package_ref"] for role, record in package_records.items()}
    pointer_refs = write_context_package_pointers(run_root, package_records, source="kernel_step_record")
    resume_diagnostics_ref = write_project_resume_diagnostics(
        run_root,
        request_id=request_id,
        decisions=_evaluate_package_records(run_root, package_records),
    )
    existing = read_project_lifecycle_state(run_root)
    phase = _phase_from_status(product_status)
    payload = _base_lifecycle_state(existing, request_id=request_id)
    existing_pointers = payload.get("context_package_pointers", {})
    if not isinstance(existing_pointers, Mapping):
        existing_pointers = {}
    payload.update({
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
        "latest_context_packages": _merge_mapping(payload.get("latest_context_packages"), package_refs),
        "context_package_pointers": _merge_mapping(existing_pointers, pointer_refs),
        "resume_diagnostics_ref": resume_diagnostics_ref,
        "updated_at": _utc_now(),
    })
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


def write_frontdesk_lifecycle_state(
    run_root: str | Path,
    *,
    request_id: str,
    status: str,
    result_ref: str,
    flow_result: mf.FlowRunResult,
    contract_ref: str,
    requirements_ref: str,
    control_ref: str,
    assistant_turn_ref: str,
    session_state_ref: str,
    research_request_ref: str,
) -> str:
    """Write project lifecycle state for one FrontDesk turn."""

    step_record_refs = list(flow_result.flow_result.step_record_refs)
    package_records = latest_context_package_records(run_root, step_record_refs)
    pointer_refs = write_context_package_pointers(run_root, package_records, source="frontdesk_step_record")
    package_refs = {role: record["context_package_ref"] for role, record in package_records.items()}
    resume_diagnostics_ref = write_project_resume_diagnostics(
        run_root,
        request_id=request_id,
        decisions=_evaluate_package_records(run_root, package_records),
    )
    existing = read_project_lifecycle_state(run_root)
    payload = _base_lifecycle_state(existing, request_id=request_id)
    payload.update({
        "schema_version": "missionforge_deepresearch.lifecycle_state.v1",
        "request_id": request_id,
        "phase": _frontdesk_phase_from_status(status),
        "active_agent": "frontdesk",
        "control_agent": "frontdesk",
        "latest_frontdesk_result_ref": result_ref,
        "latest_frontdesk_flow_result_ref": flow_result.flow_result_ref,
        "frontdesk_contract_ref": contract_ref,
        "frontdesk_requirements_ref": requirements_ref,
        "frontdesk_control_ref": control_ref,
        "frontdesk_assistant_turn_ref": assistant_turn_ref,
        "frontdesk_session_state_ref": session_state_ref,
        "frontdesk_research_request_ref": research_request_ref,
        "latest_frontdesk_context_package_ref": package_refs.get("frontdesk", ""),
        "latest_context_packages": _merge_mapping(payload.get("latest_context_packages"), package_refs),
        "context_package_pointers": _merge_mapping(payload.get("context_package_pointers"), pointer_refs),
        "resume_diagnostics_ref": resume_diagnostics_ref,
        "updated_at": _utc_now(),
    })
    mf.assert_refs_only_payload(payload, "deepresearch_lifecycle_state")
    return write_json_ref(run_root, PROJECT_LIFECYCLE_STATE_REF, payload)


def read_project_lifecycle_state(run_root: str | Path) -> dict[str, Any]:
    """Read lifecycle state, returning an empty dict for a new project."""

    if not ref_exists(run_root, PROJECT_LIFECYCLE_STATE_REF):
        return {}
    payload = read_json_ref(run_root, PROJECT_LIFECYCLE_STATE_REF, "deepresearch_lifecycle_state")
    return dict(payload) if isinstance(payload, Mapping) else {}


def latest_context_package_refs(run_root: str | Path, step_record_refs: list[str]) -> dict[str, str]:
    """Return the latest opaque ContextPackage ref for each Kernel step id."""

    return {
        step_id: record["context_package_ref"]
        for step_id, record in latest_context_package_records(run_root, step_record_refs).items()
    }


def latest_context_package_records(run_root: str | Path, step_record_refs: list[str]) -> dict[str, dict[str, str]]:
    """Return latest opaque ContextPackage refs and hashes for each role key."""

    result: dict[str, str] = {}
    records: dict[str, dict[str, str]] = {}
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
        package_ref = metadata.get("post_turn_context_package_ref") or metadata.get("context_package_ref")
        package_hash = metadata.get("post_turn_context_package_hash") or metadata.get("context_package_hash")
        if isinstance(package_ref, str) and package_ref:
            role_key = _role_key_for_step(step_id)
            result[role_key] = mf.validate_ref(package_ref, "deepresearch_lifecycle.context_package_ref")
            records[role_key] = {
                "role_key": role_key,
                "step_id": step_id,
                "step_record_ref": mf.validate_ref(step_record_ref, "deepresearch_lifecycle.step_record_ref"),
                "context_package_ref": result[role_key],
                "context_package_hash": _optional_hash(package_hash),
            }
    return records


def write_context_package_pointers(
    run_root: str | Path,
    package_records: Mapping[str, Mapping[str, str]],
    *,
    source: str,
) -> dict[str, str]:
    """Write role-local ContextPackage pointer refs."""

    pointer_refs: dict[str, str] = {}
    for role_key, record in package_records.items():
        pointer_ref = ROLE_CONTEXT_PACKAGE_POINTER_REFS.get(role_key)
        if not pointer_ref:
            continue
        package_ref = record.get("context_package_ref", "")
        if not isinstance(package_ref, str) or not package_ref:
            continue
        pointer_payload = {
            "schema_version": "missionforge_deepresearch.context_package_pointer.v1",
            "role": role_key,
            "source": source,
            "step_id": record.get("step_id", ""),
            "source_step_record_ref": record.get("step_record_ref", ""),
            "context_package_ref": mf.validate_ref(package_ref, "deepresearch_context_package_pointer.ref"),
            "context_package_hash": record.get("context_package_hash", ""),
            "updated_at": _utc_now(),
        }
        mf.assert_refs_only_payload(pointer_payload, "deepresearch_context_package_pointer")
        pointer_refs[role_key] = write_json_ref(run_root, pointer_ref, pointer_payload)
    return pointer_refs


def write_project_resume_diagnostics(
    run_root: str | Path,
    *,
    request_id: str,
    decisions: Mapping[str, mf.ContextPackageRestoreDecision] | None = None,
    missing_roles: list[str] | None = None,
) -> str:
    """Write project-level resume diagnostics from core ContextPackage decisions."""

    role_decisions = {
        role: decision.to_dict()
        for role, decision in (decisions or {}).items()
    }
    missing = sorted({role for role in missing_roles or [] if role})
    payload = {
        "schema_version": "missionforge_deepresearch.resume_diagnostics.v1",
        "request_id": request_id,
        "status": _resume_status(role_decisions, missing),
        "role_decisions": role_decisions,
        "missing_roles": missing,
        "updated_at": _utc_now(),
    }
    mf.assert_refs_only_payload(payload, "deepresearch_resume_diagnostics")
    return write_json_ref(run_root, PROJECT_RESUME_DIAGNOSTICS_REF, payload)


def evaluate_project_context_packages(
    run_root: str | Path,
    *,
    request_id: str,
    expectations: Mapping[str, mf.ContextPackageRestoreExpectation],
) -> str:
    """Evaluate latest role packages and write project resume diagnostics."""

    lifecycle = read_project_lifecycle_state(run_root)
    package_refs = lifecycle.get("latest_context_packages", {})
    if not isinstance(package_refs, Mapping):
        package_refs = {}
    decisions: dict[str, mf.ContextPackageRestoreDecision] = {}
    missing_roles: list[str] = []
    for role_key, expectation in expectations.items():
        package_ref = package_refs.get(role_key)
        if not isinstance(package_ref, str) or not package_ref:
            missing_roles.append(role_key)
            continue
        decisions[role_key] = mf.evaluate_context_package_ref(
            run_root,
            package_ref,
            expectation=expectation,
        )
    return write_project_resume_diagnostics(
        run_root,
        request_id=request_id,
        decisions=decisions,
        missing_roles=missing_roles,
    )


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


def _frontdesk_phase_from_status(status: str) -> str:
    if status == "ready_for_approval":
        return "awaiting_approval"
    if status == "approved":
        return "approved"
    return "frontdesk"


def _active_agent(step_record_refs: list[str], context_package_refs: Mapping[str, str]) -> str:
    for step_record_ref in reversed(step_record_refs):
        for step_id in context_package_refs:
            if f"/steps/{step_id}/" in step_record_ref or step_record_ref.endswith(f"/{step_id}/step_record.json"):
                return step_id
    if context_package_refs:
        return next(reversed(dict(context_package_refs)))
    return "frontdesk"


def _base_lifecycle_state(existing: Mapping[str, Any], *, request_id: str) -> dict[str, Any]:
    payload = dict(existing)
    payload.setdefault("schema_version", "missionforge_deepresearch.lifecycle_state.v1")
    payload.setdefault("request_id", request_id)
    payload.setdefault("phase", "frontdesk")
    payload.setdefault("active_agent", "frontdesk")
    payload.setdefault("control_agent", "frontdesk")
    payload.setdefault("latest_run_ref", "")
    payload.setdefault("latest_flow_result_ref", "")
    payload.setdefault("latest_run_status_ref", "")
    payload.setdefault("current_contract_ref", "")
    payload.setdefault("current_revision_ref", "")
    payload.setdefault("research_state_ref", "")
    payload.setdefault("final_report_ref", "")
    payload.setdefault("latest_frontdesk_result_ref", "")
    payload.setdefault("latest_frontdesk_flow_result_ref", "")
    payload.setdefault("frontdesk_contract_ref", "")
    payload.setdefault("frontdesk_requirements_ref", "")
    payload.setdefault("frontdesk_control_ref", "")
    payload.setdefault("frontdesk_assistant_turn_ref", "")
    payload.setdefault("frontdesk_session_state_ref", "")
    payload.setdefault("frontdesk_research_request_ref", "")
    payload.setdefault("latest_frontdesk_context_package_ref", "")
    payload.setdefault("latest_source_mapper_context_package_ref", "")
    payload.setdefault("latest_researcher_context_package_ref", "")
    payload.setdefault("latest_reviewer_context_package_ref", "")
    payload.setdefault("latest_judge_context_package_ref", "")
    payload.setdefault("latest_context_packages", {})
    payload.setdefault("context_package_pointers", {})
    payload.setdefault("resume_diagnostics_ref", PROJECT_RESUME_DIAGNOSTICS_REF)
    return payload


def _role_key_for_step(step_id: str) -> str:
    if step_id in ROLE_CONTEXT_PACKAGE_POINTER_REFS:
        return step_id
    return step_id


def _evaluate_package_records(
    run_root: str | Path,
    package_records: Mapping[str, Mapping[str, str]],
) -> dict[str, mf.ContextPackageRestoreDecision]:
    decisions: dict[str, mf.ContextPackageRestoreDecision] = {}
    for role_key, record in package_records.items():
        package_ref = record.get("context_package_ref", "")
        if not isinstance(package_ref, str) or not package_ref:
            continue
        decisions[role_key] = mf.evaluate_context_package_ref(run_root, package_ref)
    return decisions


def _merge_mapping(existing: Any, updates: Mapping[str, str]) -> dict[str, str]:
    result = dict(existing) if isinstance(existing, Mapping) else {}
    for key, value in updates.items():
        if isinstance(value, str):
            result[str(key)] = value
    return result


def _resume_status(role_decisions: Mapping[str, Any], missing_roles: list[str]) -> str:
    if missing_roles and not role_decisions:
        return "missing_context"
    statuses = [
        decision.get("status")
        for decision in role_decisions.values()
        if isinstance(decision, Mapping)
    ]
    if any(status == mf.ContextPackageRestoreStatus.INVALID.value for status in statuses):
        return "invalid"
    if missing_roles or any(status == mf.ContextPackageRestoreStatus.STALE.value for status in statuses):
        return "recompile_required"
    if statuses and all(status == mf.ContextPackageRestoreStatus.REUSABLE.value for status in statuses):
        return "reusable"
    return "missing_context"


def _optional_hash(value: Any) -> str:
    if not isinstance(value, str) or not value:
        return ""
    if not value.startswith("sha256:") or len(value) != len("sha256:") + 64:
        return ""
    return value


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
