"""Project-level optional seed inputs for DeepResearch.

Seed inputs are explicit user-provided artifacts. They are not inferred from
chat and they only become task authority when compiled into an
AcademicResearchRequest before approval or through a later contract revision.
"""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any, Mapping

import missionforge as mf

from .product_contract import AcademicResearchRequest, SeedPaper
from .workspace import read_json_ref, ref_exists, write_json_ref


PROJECT_SEED_INPUTS_SCHEMA_VERSION = "missionforge_deepresearch.project_seed_inputs.v1"
PROJECT_SEED_INPUTS_REF = "project/seed_inputs.json"


def read_project_seed_inputs(run_root: str | Path) -> dict[str, Any]:
    """Return persisted project seed inputs or an empty shape."""

    root = Path(run_root)
    if not ref_exists(root, PROJECT_SEED_INPUTS_REF):
        return _empty_seed_inputs()
    try:
        payload = read_json_ref(root, PROJECT_SEED_INPUTS_REF, "deepresearch_project_seed_inputs")
    except (json.JSONDecodeError, UnicodeDecodeError, OSError, mf.ContractValidationError):
        return _empty_seed_inputs()
    if payload.get("schema_version") != PROJECT_SEED_INPUTS_SCHEMA_VERSION:
        return _empty_seed_inputs()
    return _normalized_seed_inputs(payload)


def write_project_seed_inputs(
    run_root: str | Path,
    *,
    request_id: str,
    seed_papers: list[SeedPaper | Mapping[str, Any]],
    seed_pdf_refs: list[str],
) -> str:
    """Write the project seed-input artifact."""

    papers = [_coerce_seed_paper(item) for item in seed_papers]
    refs = _dedupe_refs(seed_pdf_refs)
    payload = {
        "schema_version": PROJECT_SEED_INPUTS_SCHEMA_VERSION,
        "request_id": str(request_id).strip(),
        "seed_papers": [item.to_dict() for item in _dedupe_seed_papers(papers)],
        "seed_pdf_refs": refs,
        "updated_at": _utc_now(),
    }
    return write_json_ref(run_root, PROJECT_SEED_INPUTS_REF, payload)


def add_project_seed_paper(
    run_root: str | Path,
    *,
    request_id: str,
    seed_paper: SeedPaper | Mapping[str, Any],
) -> dict[str, Any]:
    """Append a seed paper if it is not already present."""

    current = read_project_seed_inputs(run_root)
    papers = [_coerce_seed_paper(item) for item in current.get("seed_papers", [])]
    papers.append(_coerce_seed_paper(seed_paper))
    write_project_seed_inputs(
        run_root,
        request_id=request_id,
        seed_papers=papers,
        seed_pdf_refs=[str(ref) for ref in current.get("seed_pdf_refs", [])],
    )
    return read_project_seed_inputs(run_root)


def add_project_seed_pdf_ref(
    run_root: str | Path,
    *,
    request_id: str,
    seed_pdf_ref: str,
) -> dict[str, Any]:
    """Append a seed PDF ref if it is not already present."""

    current = read_project_seed_inputs(run_root)
    refs = [str(ref) for ref in current.get("seed_pdf_refs", [])]
    refs.append(mf.validate_ref(seed_pdf_ref, "deepresearch_project_seed_inputs.seed_pdf_ref"))
    write_project_seed_inputs(
        run_root,
        request_id=request_id,
        seed_papers=[item for item in current.get("seed_papers", []) if isinstance(item, Mapping)],
        seed_pdf_refs=refs,
    )
    return read_project_seed_inputs(run_root)


def apply_project_seed_inputs(
    run_root: str | Path,
    request: AcademicResearchRequest,
) -> AcademicResearchRequest:
    """Return a request with the current project seed inputs merged in."""

    seed_inputs = read_project_seed_inputs(run_root)
    papers = _dedupe_seed_papers(
        [
            *list(request.seed_papers),
            *[_coerce_seed_paper(item) for item in seed_inputs.get("seed_papers", [])],
        ]
    )
    pdf_refs = _dedupe_refs([*list(request.seed_pdf_refs), *list(seed_inputs.get("seed_pdf_refs", []))])
    payload = request.to_dict()
    payload["seed_papers"] = [item.to_dict() for item in papers]
    payload["seed_pdf_refs"] = pdf_refs
    return AcademicResearchRequest.from_dict(payload)


def project_seed_summary(run_root: str | Path) -> dict[str, Any]:
    """Return a refs-first seed summary for web/operator projections."""

    seed_inputs = read_project_seed_inputs(run_root)
    return {
        "schema_version": "missionforge_deepresearch.project_seed_summary.v1",
        "seed_inputs_ref": PROJECT_SEED_INPUTS_REF if ref_exists(run_root, PROJECT_SEED_INPUTS_REF) else "",
        "seed_paper_count": len(seed_inputs.get("seed_papers", [])),
        "seed_pdf_count": len(seed_inputs.get("seed_pdf_refs", [])),
        "seed_pdf_refs": _dedupe_refs([str(ref) for ref in seed_inputs.get("seed_pdf_refs", [])]),
        "updated_at": str(seed_inputs.get("updated_at") or ""),
    }


def project_seed_inputs_hash(run_root: str | Path) -> str:
    """Return a stable hash for the current seed inputs."""

    return mf.stable_json_hash(read_project_seed_inputs(run_root))


def _normalized_seed_inputs(payload: Mapping[str, Any]) -> dict[str, Any]:
    papers = [_coerce_seed_paper(item) for item in _list(payload.get("seed_papers"))]
    refs = _dedupe_refs([str(ref) for ref in _list(payload.get("seed_pdf_refs"))])
    return {
        "schema_version": PROJECT_SEED_INPUTS_SCHEMA_VERSION,
        "request_id": str(payload.get("request_id") or "").strip(),
        "seed_papers": [item.to_dict() for item in _dedupe_seed_papers(papers)],
        "seed_pdf_refs": refs,
        "updated_at": str(payload.get("updated_at") or "").strip(),
    }


def _empty_seed_inputs() -> dict[str, Any]:
    return {
        "schema_version": PROJECT_SEED_INPUTS_SCHEMA_VERSION,
        "request_id": "",
        "seed_papers": [],
        "seed_pdf_refs": [],
        "updated_at": "",
    }


def _coerce_seed_paper(value: SeedPaper | Mapping[str, Any]) -> SeedPaper:
    if isinstance(value, SeedPaper):
        value.validate()
        return value
    if isinstance(value, Mapping):
        return SeedPaper.from_dict(value)
    raise mf.ContractValidationError("seed_paper must be an object")


def _dedupe_seed_papers(values: list[SeedPaper]) -> list[SeedPaper]:
    result = []
    seen: set[tuple[str, str]] = set()
    for item in values:
        item.validate()
        key = (item.kind, item.value.lower())
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _dedupe_refs(values: list[str]) -> list[str]:
    result = []
    for ref in values:
        safe_ref = mf.validate_ref(ref, "deepresearch_project_seed_inputs.seed_pdf_refs[]")
        if safe_ref not in result:
            result.append(safe_ref)
    return result


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
