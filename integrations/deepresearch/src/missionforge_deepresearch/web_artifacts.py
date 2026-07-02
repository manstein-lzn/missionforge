"""Artifact preview and access-policy helpers for the DeepResearch web UI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import missionforge as mf

from .frontdesk import FRONTDESK_DIALOGUE_REF
from .project_seeds import PROJECT_SEED_INPUTS_REF
from .workspace import resolve_workspace_ref


ARTIFACT_PREVIEW_MAX_CHARS = 60000
ARTIFACT_READ_MAX_BYTES = 2_000_000
SENSITIVE_ARTIFACT_REFS = {
    PROJECT_SEED_INPUTS_REF,
    FRONTDESK_DIALOGUE_REF,
    mf.USER_EVENTS_REF,
}
SENSITIVE_ARTIFACT_PREFIXES = (
    "context/",
    "inputs/seeds/",
    "project/lifecycle/action_text/",
    "sources/seed_pdfs/",
)


def read_project_artifact(
    workspace: str | Path,
    request_id: str,
    ref: str,
    *,
    max_bytes: int = ARTIFACT_READ_MAX_BYTES,
) -> dict[str, Any]:
    """Read one project artifact as a safe text preview."""

    workspace_root = Path(workspace).resolve()
    run_root = resolve_workspace_ref(workspace_root, _run_ref(request_id))
    safe_ref = mf.validate_ref(ref, "deepresearch_web.artifact_ref")
    path = resolve_workspace_ref(run_root, safe_ref)
    if not path.is_file():
        raise FileNotFoundError(safe_ref)
    byte_size = path.stat().st_size
    policy = artifact_access_policy(safe_ref)
    if policy["redacted"]:
        return {
            "ref": safe_ref,
            "byte_size": byte_size,
            "truncated": False,
            "binary": False,
            "content": "",
            "content_type": "text/plain; charset=utf-8",
            **policy,
        }
    data = path.read_bytes()[:max_bytes]
    truncated = byte_size > max_bytes
    content = ""
    binary = False
    try:
        content = data.decode("utf-8")
    except UnicodeDecodeError:
        binary = True
    if not binary and looks_like_json_ref(safe_ref):
        content = pretty_json_text(content)
    return {
        "ref": safe_ref,
        "byte_size": byte_size,
        "truncated": truncated,
        "binary": binary,
        "content": content,
        "content_type": artifact_content_type(safe_ref, binary=binary),
        **policy,
    }


def artifact_content_type(ref: str, *, binary: bool) -> str:
    if binary:
        return "application/octet-stream"
    if looks_like_json_ref(ref):
        return "application/json; charset=utf-8"
    return "text/plain; charset=utf-8"


def artifact_access_policy(ref: str) -> dict[str, Any]:
    safe_ref = _clean(ref)
    if safe_ref in SENSITIVE_ARTIFACT_REFS or any(
        safe_ref.startswith(prefix)
        for prefix in SENSITIVE_ARTIFACT_PREFIXES
    ):
        return {
            "access_level": "sensitive",
            "preview_policy": "metadata_only",
            "redacted": True,
            "redaction_reason": "raw user input, uploaded file, context package, or lifecycle directive",
        }
    return {
        "access_level": "standard",
        "preview_policy": "text_preview",
        "redacted": False,
        "redaction_reason": "",
    }


def looks_like_json_ref(ref: str) -> bool:
    return ref.endswith(".json") or ref.endswith(".jsonl")


def pretty_json_text(content: str) -> str:
    if not content.strip():
        return content
    if "\n" in content.strip() and not content.lstrip().startswith("{"):
        rows = []
        for line in content.splitlines():
            if not line.strip():
                continue
            try:
                rows.append(json.dumps(json.loads(line), ensure_ascii=False, sort_keys=True, indent=2))
            except json.JSONDecodeError:
                return content
        return "\n".join(rows)
    try:
        return json.dumps(json.loads(content), ensure_ascii=False, sort_keys=True, indent=2)
    except json.JSONDecodeError:
        return content


def _run_ref(request_id: str) -> str:
    if not isinstance(request_id, str) or not request_id.strip():
        raise mf.ContractValidationError("DeepResearch request_id is required")
    return mf.validate_ref(f"runs/{request_id.strip()}", "deepresearch_web.run_ref")


def _clean(value: Any) -> str:
    return str(value or "").strip()
