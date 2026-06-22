"""Workspace IO helpers for Kernel runtime records."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from ..contracts import ContractValidationError, ensure_json_value, stable_json_hash, validate_ref


def resolve_workspace_ref(workspace: str | Path, ref: str) -> Path:
    safe_ref = validate_ref(ref, "kernel_workspace.ref")
    root = Path(workspace).resolve()
    path = (root / safe_ref).resolve()
    if path != root and root not in path.parents:
        raise ContractValidationError("kernel workspace ref escapes workspace")
    return path


def ref_exists(workspace: str | Path, ref: str) -> bool:
    return resolve_workspace_ref(workspace, ref).is_file()


def hash_refs(workspace: str | Path, refs: list[str]) -> dict[str, str]:
    return {validate_ref(ref, "kernel_ref_hash.ref"): hash_ref(workspace, ref) for ref in refs}


def hash_ref(workspace: str | Path, ref: str) -> str:
    safe_ref = validate_ref(ref, "kernel_ref_hash.ref")
    path = resolve_workspace_ref(workspace, safe_ref)
    if not path.is_file():
        return stable_json_hash({"missing_ref": safe_ref})
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def write_projection_value(workspace: str | Path, ref: str, value: Any) -> str:
    path = resolve_workspace_ref(workspace, ref)
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(value, str):
        path.write_text(value, encoding="utf-8")
    else:
        compatible = ensure_json_value(value, "kernel_projection.value")
        path.write_text(json.dumps(compatible, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return validate_ref(ref, "kernel_projection.output")


def write_json_ref(workspace: str | Path, ref: str, value: Any) -> str:
    path = resolve_workspace_ref(workspace, ref)
    compatible = ensure_json_value(value, ref)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(compatible, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return validate_ref(ref, "kernel_json.output")


def read_json_ref(workspace: str | Path, ref: str) -> Any:
    path = resolve_workspace_ref(workspace, ref)
    return json.loads(path.read_text(encoding="utf-8"))


def write_jsonl_ref(workspace: str | Path, ref: str, values: list[Any]) -> str:
    path = resolve_workspace_ref(workspace, ref)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for value in values:
            compatible = ensure_json_value(value, f"{ref}[]")
            handle.write(json.dumps(compatible, sort_keys=True) + "\n")
    return validate_ref(ref, "kernel_jsonl.output")
