"""Web seed-input actions for DeepResearch projects."""

from __future__ import annotations

import base64
from binascii import Error as Base64Error
import json
from pathlib import Path
import re
from typing import Any, Mapping

import missionforge as mf

from .frontdesk import (
    FRONTDESK_APPROVAL_REF,
    FRONTDESK_CONTROL_REF,
    FRONTDESK_RESEARCH_PROJECTION_REF,
    FRONTDESK_RESEARCH_REQUEST_REF,
    FRONTDESK_REQUIREMENTS_REF,
)
from .lifecycle_actions import (
    record_lifecycle_action,
    require_revise_lifecycle_action_allowed,
)
from .product_contract import AcademicResearchRequest, SeedPaper
from .project_seeds import (
    PROJECT_SEED_INPUTS_REF,
    add_project_seed_paper,
    add_project_seed_pdf_ref,
    apply_project_seed_inputs,
    project_seed_inputs_hash,
    project_seed_summary,
    read_project_seed_inputs,
)
from .web_common import WEB_POST_MAX_BYTES, WebConsoleResponse, json_response
from .workspace import read_json_ref, read_text_ref, ref_exists, resolve_workspace_ref, write_json_ref


WEB_SEED_PDF_MAX_BYTES = 8 * 1024 * 1024
WEB_SEED_PDF_POST_MAX_BYTES = 12 * 1024 * 1024


def seed_paper_response(
    *,
    workspace: Path,
    request_id: str,
    body: bytes | str,
    snapshot_factory,
) -> WebConsoleResponse:
    """Record an optional seed paper before task approval."""

    try:
        run_root = resolve_workspace_ref(workspace, _run_ref(request_id))
        payload = _json_body(body, max_bytes=WEB_POST_MAX_BYTES)
        seed = SeedPaper(
            kind=_clean(payload.get("kind")),
            value=_clean(payload.get("value")),
            note=_clean(payload.get("note")),
        )
        approved = _is_approved(run_root)
        if approved:
            require_revise_lifecycle_action_allowed(workspace=workspace, request_id=request_id)
        else:
            _require_preapproval_seed_editable(run_root)
        previous_state = _seed_rollback_state(run_root) if approved else None
        state = add_project_seed_paper(run_root, request_id=request_id, seed_paper=seed)
        if approved:
            try:
                action = _record_seed_revision_action(workspace=workspace, request_id=request_id, state=state)
            except Exception:
                _restore_seed_inputs(run_root, previous_state=previous_state)
                raise
            return json_response(
                202,
                {
                    "schema_version": "missionforge_deepresearch.web_seed_paper_result.v1",
                    "status": "pending_revision",
                    "seed_inputs_ref": PROJECT_SEED_INPUTS_REF,
                    "seed_paper_count": len(state.get("seed_papers", [])),
                    "seed_pdf_count": len(state.get("seed_pdf_refs", [])),
                    "action": _sanitized_action(action),
                    "snapshot": snapshot_factory(workspace, request_id),
                },
            )
        _sync_frontdesk_research_request(run_root)
        return json_response(
            202,
            {
                "schema_version": "missionforge_deepresearch.web_seed_paper_result.v1",
                "status": "recorded",
                "seed_inputs_ref": PROJECT_SEED_INPUTS_REF,
                "seed_paper_count": len(state.get("seed_papers", [])),
                "seed_pdf_count": len(state.get("seed_pdf_refs", [])),
                "snapshot": snapshot_factory(workspace, request_id),
            },
        )
    except (json.JSONDecodeError, UnicodeDecodeError, Base64Error):
        return json_response(400, {"status": "error", "message": "invalid_json_body"})
    except mf.ContractValidationError as exc:
        return json_response(409, {"status": "error", "message": str(exc)})


def seed_pdf_response(
    *,
    workspace: Path,
    request_id: str,
    body: bytes | str,
    snapshot_factory,
) -> WebConsoleResponse:
    """Store an uploaded seed PDF before task approval."""

    try:
        run_root = resolve_workspace_ref(workspace, _run_ref(request_id))
        payload = _json_body(body, max_bytes=WEB_SEED_PDF_POST_MAX_BYTES)
        filename = _safe_pdf_filename(_clean(payload.get("filename")))
        encoded = _clean(payload.get("content_base64"))
        if not encoded:
            raise mf.ContractValidationError("seed PDF content_base64 is required")
        data = base64.b64decode(encoded, validate=True)
        _validate_pdf_data(data)
        approved = _is_approved(run_root)
        if approved:
            require_revise_lifecycle_action_allowed(workspace=workspace, request_id=request_id)
        else:
            _require_preapproval_seed_editable(run_root)
        previous_state = _seed_rollback_state(run_root) if approved else None
        pdf_ref = _next_seed_pdf_ref(run_root, filename)
        pdf_path = resolve_workspace_ref(run_root, pdf_ref)
        try:
            pdf_path.parent.mkdir(parents=True, exist_ok=True)
            pdf_path.write_bytes(data)
            state = add_project_seed_pdf_ref(run_root, request_id=request_id, seed_pdf_ref=pdf_ref)
            if approved:
                action = _record_seed_revision_action(workspace=workspace, request_id=request_id, state=state)
        except Exception:
            if approved:
                _restore_seed_inputs(run_root, previous_state=previous_state)
                _unlink_if_exists(pdf_path)
            raise
        if approved:
            return json_response(
                202,
                {
                    "schema_version": "missionforge_deepresearch.web_seed_pdf_result.v1",
                    "status": "pending_revision",
                    "seed_inputs_ref": PROJECT_SEED_INPUTS_REF,
                    "seed_pdf_ref": pdf_ref,
                    "seed_paper_count": len(state.get("seed_papers", [])),
                    "seed_pdf_count": len(state.get("seed_pdf_refs", [])),
                    "action": _sanitized_action(action),
                    "snapshot": snapshot_factory(workspace, request_id),
                },
            )
        _sync_frontdesk_research_request(run_root)
        return json_response(
            202,
            {
                "schema_version": "missionforge_deepresearch.web_seed_pdf_result.v1",
                "status": "recorded",
                "seed_inputs_ref": PROJECT_SEED_INPUTS_REF,
                "seed_pdf_ref": pdf_ref,
                "seed_paper_count": len(state.get("seed_papers", [])),
                "seed_pdf_count": len(state.get("seed_pdf_refs", [])),
                "snapshot": snapshot_factory(workspace, request_id),
            },
        )
    except (json.JSONDecodeError, UnicodeDecodeError, Base64Error):
        return json_response(400, {"status": "error", "message": "invalid_seed_pdf_body"})
    except mf.ContractValidationError as exc:
        return json_response(409, {"status": "error", "message": str(exc)})


def seed_snapshot(run_root: str | Path) -> dict[str, Any]:
    """Return seed summary for the web project snapshot."""

    return project_seed_summary(run_root)


def _sync_frontdesk_research_request(run_root: Path) -> None:
    if not ref_exists(run_root, FRONTDESK_RESEARCH_REQUEST_REF):
        return
    request_payload = read_json_ref(run_root, FRONTDESK_RESEARCH_REQUEST_REF, "deepresearch_frontdesk_research_request")
    request = apply_project_seed_inputs(run_root, AcademicResearchRequest.from_dict(request_payload))
    write_json_ref(run_root, FRONTDESK_RESEARCH_REQUEST_REF, request.to_dict())
    if not ref_exists(run_root, FRONTDESK_RESEARCH_PROJECTION_REF):
        return
    projection = read_json_ref(run_root, FRONTDESK_RESEARCH_PROJECTION_REF, "deepresearch_frontdesk_research_projection")
    projection["seed_inputs_ref"] = PROJECT_SEED_INPUTS_REF
    projection["seed_inputs_hash"] = project_seed_inputs_hash(run_root)
    write_json_ref(run_root, FRONTDESK_RESEARCH_PROJECTION_REF, projection)


def _record_seed_revision_action(
    *,
    workspace: Path,
    request_id: str,
    state: Mapping[str, Any],
) -> dict[str, Any]:
    return record_lifecycle_action(
        workspace=workspace,
        request_id=request_id,
        action="revise",
        text=_seed_revision_directive(state),
    )


def _seed_rollback_state(run_root: Path) -> dict[str, Any]:
    existed = ref_exists(run_root, PROJECT_SEED_INPUTS_REF)
    return {
        "existed": existed,
        "seed_inputs": read_json_ref(run_root, PROJECT_SEED_INPUTS_REF, "deepresearch_project_seed_inputs")
        if existed
        else read_project_seed_inputs(run_root),
    }


def _restore_seed_inputs(
    run_root: Path,
    *,
    previous_state: Mapping[str, Any] | None,
) -> None:
    if not previous_state:
        return
    if previous_state.get("existed"):
        seed_inputs = previous_state.get("seed_inputs")
        if not isinstance(seed_inputs, Mapping):
            return
        write_json_ref(run_root, PROJECT_SEED_INPUTS_REF, dict(seed_inputs))
        return
    _unlink_if_exists(resolve_workspace_ref(run_root, PROJECT_SEED_INPUTS_REF))


def _unlink_if_exists(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return


def _seed_revision_directive(state: Mapping[str, Any]) -> str:
    seed_papers = state.get("seed_papers", [])
    seed_pdf_refs = state.get("seed_pdf_refs", [])
    paper_count = len(seed_papers) if isinstance(seed_papers, list) else 0
    pdf_count = len(seed_pdf_refs) if isinstance(seed_pdf_refs, list) else 0
    return "\n".join(
        [
            "Apply the newly staged DeepResearch seed inputs to the next revised research request.",
            f"Seed inputs ref: {PROJECT_SEED_INPUTS_REF}.",
            f"Seed inputs hash: {mf.stable_json_hash(dict(state))}.",
            f"Seed paper count: {paper_count}.",
            f"Seed PDF count: {pdf_count}.",
            "Do not mutate the previously approved FrontDesk request; "
            "freeze a new revised request through the revision boundary.",
        ]
    )


def _sanitized_action(action: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "action_id": _clean(action.get("action_id")),
        "kind": _clean(action.get("kind")),
        "status": _clean(action.get("status")),
        "reason_ref": _clean(action.get("reason_ref")),
        "next_required_boundary": _clean(action.get("next_required_boundary")),
    }


def _require_preapproval_seed_editable(run_root: Path) -> None:
    if ref_exists(run_root, FRONTDESK_CONTROL_REF):
        control = read_json_ref(run_root, FRONTDESK_CONTROL_REF, "deepresearch_frontdesk_control")
        if control.get("decision") == "ready_for_approval" and ref_exists(run_root, FRONTDESK_REQUIREMENTS_REF):
            # Seed additions are allowed before approval, but they must update the
            # research request projection if it already exists.
            read_text_ref(run_root, FRONTDESK_REQUIREMENTS_REF)


def _is_approved(run_root: Path) -> bool:
    return ref_exists(run_root, FRONTDESK_APPROVAL_REF)


def _json_body(body: bytes | str, *, max_bytes: int) -> dict[str, Any]:
    if isinstance(body, bytes):
        if len(body) > max_bytes:
            raise mf.ContractValidationError("web seed request body is too large")
        text = body.decode("utf-8")
    else:
        if len(body.encode("utf-8")) > max_bytes:
            raise mf.ContractValidationError("web seed request body is too large")
        text = body
    payload = json.loads(text or "{}")
    return dict(payload) if isinstance(payload, Mapping) else {}


def _safe_pdf_filename(value: str) -> str:
    if "/" in value or "\\" in value:
        raise mf.ContractValidationError("seed PDF filename must not contain path separators")
    name = Path(value or "seed.pdf").name
    if not name.lower().endswith(".pdf"):
        raise mf.ContractValidationError("seed PDF filename must end with .pdf")
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", Path(name).stem).strip(".-") or "seed"
    return f"{stem[:80]}.pdf"


def _validate_pdf_data(data: bytes) -> None:
    if not data:
        raise mf.ContractValidationError("seed PDF upload is empty")
    if len(data) > WEB_SEED_PDF_MAX_BYTES:
        raise mf.ContractValidationError("seed PDF upload exceeds the 8MiB limit")
    if not data.startswith(b"%PDF-"):
        raise mf.ContractValidationError("seed PDF upload must be a PDF file")


def _next_seed_pdf_ref(run_root: Path, filename: str) -> str:
    for index in range(1, 1000):
        candidate = mf.validate_ref(
            f"inputs/seeds/{index:03d}-{filename}",
            "deepresearch_web_seed_pdf.ref",
        )
        if not ref_exists(run_root, candidate):
            return candidate
    raise mf.ContractValidationError("too many seed PDF uploads")


def _run_ref(request_id: str) -> str:
    if not isinstance(request_id, str) or not request_id.strip():
        raise mf.ContractValidationError("DeepResearch request_id is required")
    return mf.validate_ref(f"runs/{request_id.strip()}", "deepresearch_web_seed.run_ref")


def _clean(value: Any) -> str:
    return str(value).strip() if isinstance(value, str) else ""
