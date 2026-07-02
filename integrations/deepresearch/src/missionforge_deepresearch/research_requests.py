"""Current DeepResearch request resolution.

FrontDesk approval remains the initial task authority. Explicit contract
revisions may supersede it only through revision records and revised request
refs written under the project lifecycle boundary.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import missionforge as mf

from .frontdesk import read_approved_frontdesk_request
from .product_contract import AcademicResearchRequest
from .workspace import read_json_ref, ref_exists, resolve_workspace_ref


CONTRACT_REVISION_INDEX_SCHEMA_VERSION = "missionforge_deepresearch.contract_revision_index.v1"
CONTRACT_REVISION_INDEX_REF = "project/revision_index.json"


def read_current_research_request(*, workspace: str | Path, request_id: str) -> AcademicResearchRequest:
    """Return the approved request, superseded by the latest frozen revision."""

    base_request = read_approved_frontdesk_request(request_id=request_id, workspace=workspace)
    root = Path(workspace).resolve()
    run_root = resolve_workspace_ref(root, _run_ref(request_id))
    index = read_contract_revision_index(run_root)
    latest_ref = _latest_usable_revised_request_ref(index)
    if not latest_ref:
        return base_request
    payload = read_json_ref(run_root, latest_ref, "deepresearch_current_research_request")
    return AcademicResearchRequest.from_dict(payload)


def read_contract_revision_index(run_root: str | Path) -> dict[str, Any]:
    """Return the contract revision index or an empty index shape."""

    root = Path(run_root)
    if not ref_exists(root, CONTRACT_REVISION_INDEX_REF):
        return _empty_revision_index()
    try:
        payload = read_json_ref(root, CONTRACT_REVISION_INDEX_REF, "deepresearch_contract_revision_index")
    except (json.JSONDecodeError, UnicodeDecodeError, OSError, mf.ContractValidationError):
        return _empty_revision_index()
    if payload.get("schema_version") != CONTRACT_REVISION_INDEX_SCHEMA_VERSION:
        return _empty_revision_index()
    revisions = payload.get("revisions", [])
    return {
        "schema_version": CONTRACT_REVISION_INDEX_SCHEMA_VERSION,
        "request_id": _clean(payload.get("request_id")),
        "latest_revision_ref": _clean(payload.get("latest_revision_ref")),
        "latest_revised_request_ref": _clean(payload.get("latest_revised_request_ref")),
        "revisions": [item for item in revisions if isinstance(item, Mapping)],
        "updated_at": _clean(payload.get("updated_at")),
    }


def _empty_revision_index() -> dict[str, Any]:
    return {
        "schema_version": CONTRACT_REVISION_INDEX_SCHEMA_VERSION,
        "request_id": "",
        "latest_revision_ref": "",
        "latest_revised_request_ref": "",
        "revisions": [],
        "updated_at": "",
    }


def _latest_usable_revised_request_ref(index: Mapping[str, Any]) -> str:
    revisions = index.get("revisions", [])
    if not isinstance(revisions, list):
        return ""
    for item in reversed(revisions):
        if not isinstance(item, Mapping):
            continue
        if _clean(item.get("status")) in {"starting", "running", "completed", "failed"}:
            return _clean(item.get("revised_request_ref"))
    return ""


def _run_ref(request_id: str) -> str:
    if not isinstance(request_id, str) or not request_id.strip():
        raise mf.ContractValidationError("DeepResearch request_id is required")
    return mf.validate_ref(f"runs/{request_id.strip()}", "deepresearch_research_request.run_ref")


def _clean(value: Any) -> str:
    return str(value).strip() if isinstance(value, str) else ""
