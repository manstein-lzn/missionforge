"""RefStore and workspace IO helpers for Kernel runtime records."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..contracts import ContractValidationError, ensure_json_value, validate_ref
from ..ref_store import FileRefStore, RefStore


RefStoreTarget = RefStore | str | Path


def resolve_workspace_ref(workspace: str | Path, ref: str) -> Path:
    safe_ref = validate_ref(ref, "kernel_workspace.ref")
    root = Path(workspace).resolve()
    path = (root / safe_ref).resolve()
    if path != root and root not in path.parents:
        raise ContractValidationError("kernel workspace ref escapes workspace")
    return path


def ref_exists(workspace: RefStoreTarget, ref: str) -> bool:
    return _store_for(workspace).exists(validate_ref(ref, "kernel_ref.exists"))


def hash_refs(workspace: RefStoreTarget, refs: list[str]) -> dict[str, str]:
    return {validate_ref(ref, "kernel_ref_hash.ref"): hash_ref(workspace, ref) for ref in refs}


def hash_ref(workspace: RefStoreTarget, ref: str) -> str:
    safe_ref = validate_ref(ref, "kernel_ref_hash.ref")
    return _store_for(workspace).hash_ref(safe_ref)


def read_bytes_ref(workspace: RefStoreTarget, ref: str) -> bytes:
    return _store_for(workspace).read_bytes(validate_ref(ref, "kernel_bytes.ref"))


def write_projection_value(workspace: RefStoreTarget, ref: str, value: Any) -> str:
    safe_ref = validate_ref(ref, "kernel_projection.output")
    if isinstance(value, str):
        _store_for(workspace).write_text(safe_ref, value)
        return safe_ref
    compatible = ensure_json_value(value, "kernel_projection.value")
    _store_for(workspace).write_bytes(
        safe_ref,
        (json.dumps(compatible, sort_keys=True, indent=2) + "\n").encode("utf-8"),
        media_type="application/json",
    )
    return safe_ref


def write_json_ref(workspace: RefStoreTarget, ref: str, value: Any) -> str:
    safe_ref = validate_ref(ref, "kernel_json.output")
    compatible = ensure_json_value(value, safe_ref)
    _store_for(workspace).write_bytes(
        safe_ref,
        (json.dumps(compatible, sort_keys=True, indent=2) + "\n").encode("utf-8"),
        media_type="application/json",
    )
    return safe_ref


def read_json_ref(workspace: RefStoreTarget, ref: str) -> Any:
    return _store_for(workspace).read_json(validate_ref(ref, "kernel_json.input"))


def read_jsonl_ref(workspace: RefStoreTarget, ref: str) -> list[Any]:
    return _store_for(workspace).read_jsonl(validate_ref(ref, "kernel_jsonl.input"))


def write_jsonl_ref(workspace: RefStoreTarget, ref: str, values: list[Any]) -> str:
    safe_ref = validate_ref(ref, "kernel_jsonl.output")
    store = _store_for(workspace)
    body = b"".join(
        (json.dumps(ensure_json_value(value, f"{safe_ref}[]"), sort_keys=True) + "\n").encode("utf-8")
        for value in values
    )
    store.write_bytes(safe_ref, body, media_type="application/jsonl")
    return safe_ref


def list_refs(workspace: RefStoreTarget, prefix: str = "") -> list[str]:
    return _store_for(workspace).list_refs(prefix)


def _store_for(workspace: RefStoreTarget) -> RefStore:
    if isinstance(workspace, (str, Path)):
        return FileRefStore(workspace)
    return workspace
