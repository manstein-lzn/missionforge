"""Attempt-scoped DeepResearch output projection.

Kernel v2 still writes its established stable refs. This module copies the
completed attempt outputs into immutable attempt-scoped refs and records a
current pointer. It does not judge output quality or rewrite Kernel artifacts.
"""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import shutil
from typing import Any, Mapping

import missionforge as mf

from .kernel_refs import (
    KERNEL_V2_ACCEPTANCE_GATE_REF,
    KERNEL_V2_CANONICAL_SOURCES_REF,
    KERNEL_V2_CITATION_PROJECTION_VALIDATION_REF,
    KERNEL_V2_CITATION_PROJECTED_REPORT_REF,
    KERNEL_V2_CITATION_REGISTRY_REF,
    KERNEL_V2_CLAIM_INDEX_REF,
    KERNEL_V2_CLAIM_INDEX_VALIDATION_REF,
    KERNEL_V2_CLAIM_SUPPORT_REVIEW_REF,
    KERNEL_V2_CLAIM_SUPPORT_REVIEW_VALIDATION_REF,
    KERNEL_V2_COVERAGE_REPORT_REF,
    KERNEL_V2_EVIDENCE_INDEX_REF,
    KERNEL_V2_FINAL_REPORT_REF,
    KERNEL_V2_INSIGHT_MAP_REF,
    KERNEL_V2_JUDGE_REPORT_REF,
    KERNEL_V2_PROVIDER_HITS_REF,
    KERNEL_V2_REPORT_HTML_REF,
    KERNEL_V2_RESEARCH_STATE_REF,
    KERNEL_V2_RESULT_REF,
    KERNEL_V2_RUN_STATUS_REF,
    KERNEL_V2_SEARCH_PLAN_REF,
    KERNEL_V2_SOURCE_GAPS_REF,
    KERNEL_V2_SOURCE_GRAPH_REF,
    KERNEL_V2_SOURCE_PACKET_REF,
    KERNEL_V2_USAGE_SUMMARY_REF,
)
from .workspace import read_json_ref, ref_exists, resolve_workspace_ref, sha256_ref, write_json_ref


ATTEMPT_OUTPUT_MANIFEST_SCHEMA_VERSION = "missionforge_deepresearch.attempt_output_manifest.v1"
CURRENT_OUTPUT_POINTER_SCHEMA_VERSION = "missionforge_deepresearch.current_output_pointer.v1"
CURRENT_OUTPUT_POINTER_REF = "project/current_output_pointer.json"

_ATTEMPT_OUTPUT_SOURCE_REFS = (
    KERNEL_V2_RESULT_REF,
    KERNEL_V2_RUN_STATUS_REF,
    KERNEL_V2_SEARCH_PLAN_REF,
    KERNEL_V2_PROVIDER_HITS_REF,
    KERNEL_V2_SOURCE_PACKET_REF,
    KERNEL_V2_CANONICAL_SOURCES_REF,
    KERNEL_V2_SOURCE_GRAPH_REF,
    KERNEL_V2_COVERAGE_REPORT_REF,
    KERNEL_V2_FINAL_REPORT_REF,
    KERNEL_V2_CITATION_PROJECTED_REPORT_REF,
    KERNEL_V2_REPORT_HTML_REF,
    KERNEL_V2_CITATION_REGISTRY_REF,
    KERNEL_V2_CITATION_PROJECTION_VALIDATION_REF,
    KERNEL_V2_EVIDENCE_INDEX_REF,
    KERNEL_V2_SOURCE_GAPS_REF,
    KERNEL_V2_INSIGHT_MAP_REF,
    KERNEL_V2_CLAIM_INDEX_REF,
    KERNEL_V2_CLAIM_INDEX_VALIDATION_REF,
    KERNEL_V2_CLAIM_SUPPORT_REVIEW_REF,
    KERNEL_V2_CLAIM_SUPPORT_REVIEW_VALIDATION_REF,
    KERNEL_V2_ACCEPTANCE_GATE_REF,
    KERNEL_V2_JUDGE_REPORT_REF,
    KERNEL_V2_RESEARCH_STATE_REF,
    KERNEL_V2_USAGE_SUMMARY_REF,
)


def write_attempt_output_manifest(
    run_root: str | Path,
    *,
    attempt_id: str,
    attempt_ref: str,
    attempt_kind: str,
    set_current: bool = True,
) -> str:
    """Copy stable Kernel outputs to attempt-scoped refs and write a manifest."""

    root = Path(run_root).resolve()
    entries: list[dict[str, str]] = []
    safe_attempt_id = _safe_id(attempt_id, "deepresearch_attempt_output.attempt_id")
    for source_ref in _ATTEMPT_OUTPUT_SOURCE_REFS:
        source_path = resolve_workspace_ref(root, source_ref)
        if not source_path.is_file():
            continue
        output_ref = f"project/attempts/{safe_attempt_id}/outputs/{source_ref}"
        output_path = resolve_workspace_ref(root, output_ref)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, output_path)
        entries.append(
            {
                "source_ref": source_ref,
                "output_ref": output_ref,
                "sha256": sha256_ref(root, output_ref),
            }
        )
    manifest_ref = _attempt_output_manifest_ref(safe_attempt_id)
    payload = {
        "schema_version": ATTEMPT_OUTPUT_MANIFEST_SCHEMA_VERSION,
        "attempt_id": safe_attempt_id,
        "attempt_ref": mf.validate_ref(attempt_ref, "deepresearch_attempt_output.attempt_ref"),
        "attempt_kind": _clean(attempt_kind),
        "entries": entries,
        "created_at": _utc_now(),
    }
    mf.assert_refs_only_payload(payload, "deepresearch_attempt_output_manifest")
    write_json_ref(root, manifest_ref, payload)
    if set_current:
        write_current_output_pointer(root, manifest_ref=manifest_ref)
    return manifest_ref


def write_current_output_pointer(run_root: str | Path, *, manifest_ref: str) -> str:
    """Set the current output pointer to an existing attempt output manifest."""

    root = Path(run_root).resolve()
    manifest = read_json_ref(root, manifest_ref, "deepresearch_attempt_output_manifest")
    if manifest.get("schema_version") != ATTEMPT_OUTPUT_MANIFEST_SCHEMA_VERSION:
        raise mf.ContractValidationError("attempt output manifest schema_version is unsupported")
    payload = {
        "schema_version": CURRENT_OUTPUT_POINTER_SCHEMA_VERSION,
        "status": "current",
        "attempt_id": _clean(manifest.get("attempt_id")),
        "attempt_ref": _clean(manifest.get("attempt_ref")),
        "attempt_kind": _clean(manifest.get("attempt_kind")),
        "output_manifest_ref": mf.validate_ref(manifest_ref, "deepresearch_current_output_pointer.manifest_ref"),
        "entries": _entry_list(manifest.get("entries", [])),
        "updated_at": _utc_now(),
    }
    mf.assert_refs_only_payload(payload, "deepresearch_current_output_pointer")
    return write_json_ref(root, CURRENT_OUTPUT_POINTER_REF, payload)


def read_current_output_pointer(run_root: str | Path) -> dict[str, Any]:
    """Return the current output pointer or an empty shape."""

    root = Path(run_root)
    if not ref_exists(root, CURRENT_OUTPUT_POINTER_REF):
        return _empty_pointer()
    try:
        payload = read_json_ref(root, CURRENT_OUTPUT_POINTER_REF, "deepresearch_current_output_pointer")
    except (json.JSONDecodeError, UnicodeDecodeError, OSError, mf.ContractValidationError):
        return _empty_pointer()
    if payload.get("schema_version") != CURRENT_OUTPUT_POINTER_SCHEMA_VERSION:
        return _empty_pointer()
    return {
        "schema_version": CURRENT_OUTPUT_POINTER_SCHEMA_VERSION,
        "status": _clean(payload.get("status")),
        "attempt_id": _clean(payload.get("attempt_id")),
        "attempt_ref": _clean(payload.get("attempt_ref")),
        "attempt_kind": _clean(payload.get("attempt_kind")),
        "output_manifest_ref": _clean(payload.get("output_manifest_ref")),
        "entries": _entry_list(payload.get("entries", [])),
        "updated_at": _clean(payload.get("updated_at")),
    }


def current_output_ref(run_root: str | Path, source_ref: str) -> str:
    """Return the current attempt-scoped output ref for a stable source ref."""

    safe_source_ref = mf.validate_ref(source_ref, "deepresearch_current_output.source_ref")
    pointer = read_current_output_pointer(run_root)
    for entry in pointer.get("entries", []):
        if isinstance(entry, Mapping) and entry.get("source_ref") == safe_source_ref:
            return _clean(entry.get("output_ref"))
    return ""


def _attempt_output_manifest_ref(attempt_id: str) -> str:
    return mf.validate_ref(
        f"project/attempts/{attempt_id}/outputs/output_manifest.json",
        "deepresearch_attempt_output.manifest_ref",
    )


def _entry_list(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    entries = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        source_ref = _optional_ref(item.get("source_ref"))
        output_ref = _optional_ref(item.get("output_ref"))
        sha256 = _optional_hash(item.get("sha256"))
        if source_ref and output_ref:
            entries.append({"source_ref": source_ref, "output_ref": output_ref, "sha256": sha256})
    return entries


def _empty_pointer() -> dict[str, Any]:
    return {
        "schema_version": CURRENT_OUTPUT_POINTER_SCHEMA_VERSION,
        "status": "",
        "attempt_id": "",
        "attempt_ref": "",
        "attempt_kind": "",
        "output_manifest_ref": "",
        "entries": [],
        "updated_at": "",
    }


def _safe_id(value: str, field_name: str) -> str:
    text = _clean(value)
    if not text or "/" in text or "\\" in text:
        raise mf.ContractValidationError(f"{field_name} must be one ref segment")
    return text


def _optional_ref(value: Any) -> str:
    if not isinstance(value, str) or not value:
        return ""
    try:
        return mf.validate_ref(value, "deepresearch_attempt_output.ref")
    except mf.ContractValidationError:
        return ""


def _optional_hash(value: Any) -> str:
    if not isinstance(value, str) or not value.startswith("sha256:"):
        return ""
    return value


def _clean(value: Any) -> str:
    return str(value).strip() if isinstance(value, str) else ""


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
