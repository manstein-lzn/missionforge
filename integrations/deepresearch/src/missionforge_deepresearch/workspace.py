"""Workspace helpers for the DeepResearch integration."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import missionforge as mf


def resolve_workspace_ref(workspace: str | Path, ref: str) -> Path:
    root = Path(workspace).resolve()
    safe_ref = mf.validate_ref(ref, "workspace_ref")
    path = (root / safe_ref).resolve()
    if root not in path.parents and path != root:
        raise mf.ContractValidationError("DeepResearch workspace ref escapes workspace")
    return path


def read_json_ref(workspace: str | Path, ref: str, field_name: str) -> dict[str, Any]:
    path = resolve_workspace_ref(workspace, ref)
    if not path.exists():
        raise mf.ContractValidationError(f"{field_name} ref does not exist: {ref}")
    return mf.require_mapping(json.loads(path.read_text(encoding="utf-8")), field_name)


def write_json_ref(workspace: str | Path, ref: str, payload: Mapping[str, Any]) -> str:
    data = mf.ensure_json_value(mf.require_mapping(payload, ref), ref)
    path = resolve_workspace_ref(workspace, ref)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return mf.validate_ref(ref, "workspace_ref")


def write_text_ref(workspace: str | Path, ref: str, text: str) -> str:
    path = resolve_workspace_ref(workspace, ref)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return mf.validate_ref(ref, "workspace_ref")


def read_text_ref(workspace: str | Path, ref: str) -> str:
    path = resolve_workspace_ref(workspace, ref)
    if not path.exists():
        raise mf.ContractValidationError(f"text ref does not exist: {ref}")
    return path.read_text(encoding="utf-8")


def ref_exists(workspace: str | Path, ref: str) -> bool:
    return resolve_workspace_ref(workspace, ref).exists()


def ref_is_non_empty_file(workspace: str | Path, ref: str) -> bool:
    path = resolve_workspace_ref(workspace, ref)
    return path.exists() and path.is_file() and path.stat().st_size > 0


def sha256_ref(workspace: str | Path, ref: str) -> str:
    path = resolve_workspace_ref(workspace, ref)
    if not path.exists() or not path.is_file():
        raise mf.ContractValidationError(f"hash ref does not exist: {ref}")
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"
