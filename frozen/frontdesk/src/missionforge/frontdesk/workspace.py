"""Workspace helpers for FrontDesk artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..contracts import ContractValidationError, require_mapping, validate_ref
from ..json_store import JsonWorkspaceStore


class FrontDeskWorkspace:
    """Refs-first FrontDesk artifact workspace."""

    def __init__(self, workspace: str | Path = ".") -> None:
        self.workspace = Path(workspace)
        self.store = JsonWorkspaceStore(self.workspace)

    def write_json(self, ref: str, payload: dict[str, Any]) -> str:
        return self.store.write_json(ref, payload)

    def read_json(self, ref: str) -> dict[str, Any]:
        return self.store.read_json(ref)

    def append_jsonl(self, ref: str, payload: dict[str, Any]) -> str:
        return self.store.write_jsonl(ref, [payload], append=True)

    def read_jsonl(self, ref: str) -> list[dict[str, Any]]:
        return self.store.read_jsonl(ref)

    def exists(self, ref: str) -> bool:
        return self.store.exists(ref)

    def write_text_provenance(self, ref: str, text: str) -> str:
        if not isinstance(text, str):
            raise ContractValidationError("frontdesk provenance text must be a string")
        return self.store.write_text(ref, text)

    def resolve_ref(self, ref: str) -> Path:
        safe_ref = validate_ref(ref, "frontdesk_workspace.ref")
        root = self.workspace.resolve()
        path = (root / safe_ref).resolve()
        if path != root and root not in path.parents:
            raise ContractValidationError("frontdesk workspace ref escapes workspace")
        return path


def write_json_ref(workspace: str | Path, ref: str, payload: dict[str, Any]) -> str:
    return FrontDeskWorkspace(workspace).write_json(ref, payload)


def read_json_ref(workspace: str | Path, ref: str, field_name: str = "frontdesk_ref") -> dict[str, Any]:
    return require_mapping(FrontDeskWorkspace(workspace).read_json(ref), field_name)


def stable_json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, indent=2) + "\n"
