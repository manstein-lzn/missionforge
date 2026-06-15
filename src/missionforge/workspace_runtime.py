"""Workspace runtime with permission-aware artifact access."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .contracts import ContractValidationError, ensure_json_value, require_mapping, validate_ref
from .permissions import PermissionEnforcer
from .task_contract import PermissionManifest, WorkspacePolicy


@dataclass(frozen=True)
class RunWorkspace:
    """Filesystem workspace guarded by WorkspacePolicy and PermissionManifest."""

    root: Path | str
    workspace_policy: WorkspacePolicy
    permission_manifest: PermissionManifest
    enforcer: PermissionEnforcer = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.workspace_policy, WorkspacePolicy):
            raise ContractValidationError("run_workspace.workspace_policy must be a WorkspacePolicy")
        if not isinstance(self.permission_manifest, PermissionManifest):
            raise ContractValidationError("run_workspace.permission_manifest must be a PermissionManifest")
        self.workspace_policy.validate()
        self.permission_manifest.validate()
        object.__setattr__(self, "root", Path(self.root))
        object.__setattr__(self, "permission_manifest", self._effective_permission_manifest())
        object.__setattr__(self, "enforcer", PermissionEnforcer(self.permission_manifest))

    def materialize(self) -> None:
        """Create declared workspace directories without granting new permissions."""

        self.workspace_root_path.mkdir(parents=True, exist_ok=True)
        refs = [
            *self.workspace_policy.input_refs,
            *self.workspace_policy.artifact_root_refs,
            *self.workspace_policy.scratch_root_refs,
        ]
        for ref in refs:
            self.resolve_ref(ref).mkdir(parents=True, exist_ok=True)

    @property
    def root_path(self) -> Path:
        return Path(self.root)

    @property
    def workspace_root_path(self) -> Path:
        return self._resolve_outer_ref(self.workspace_policy.workspace_root_ref)

    def resolve_ref(self, ref: str) -> Path:
        safe_ref = validate_ref(ref, "run_workspace.ref")
        root = self.workspace_root_path.resolve()
        path = (root / safe_ref).resolve()
        if path != root and root not in path.parents:
            raise ContractValidationError("workspace ref escapes root")
        return path

    def check_read_ref(self, ref: str):
        return self.enforcer.check_read(ref)

    def check_write_ref(self, ref: str):
        return self.enforcer.check_write(ref)

    def ensure_read_ref(self, ref: str) -> str:
        return self.enforcer.ensure_read(ref)

    def ensure_write_ref(self, ref: str) -> str:
        return self.enforcer.ensure_write(ref)

    def read_text(self, ref: str) -> str:
        safe_ref = self.ensure_read_ref(ref)
        return self.resolve_ref(safe_ref).read_text(encoding="utf-8")

    def write_text(self, ref: str, text: str) -> str:
        if not isinstance(text, str):
            raise ContractValidationError("workspace text payload must be a string")
        safe_ref = self.ensure_write_ref(ref)
        path = self.resolve_ref(safe_ref)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return safe_ref

    def read_json(self, ref: str) -> dict[str, Any]:
        return require_mapping(json.loads(self.read_text(ref)), ref)

    def write_json(self, ref: str, payload: dict[str, Any]) -> str:
        data = ensure_json_value(require_mapping(payload, ref), ref)
        return self.write_text(ref, json.dumps(data, sort_keys=True, indent=2) + "\n")

    def _resolve_outer_ref(self, ref: str) -> Path:
        safe_ref = validate_ref(ref, "run_workspace.outer_ref")
        root = self.root_path.resolve()
        path = (root / safe_ref).resolve()
        if path != root and root not in path.parents:
            raise ContractValidationError("workspace root ref escapes root")
        return path

    def _effective_permission_manifest(self) -> PermissionManifest:
        denied_refs = _unique_refs([*self.permission_manifest.denied_refs, *self.workspace_policy.denied_refs])
        return PermissionManifest(
            manifest_id=self.permission_manifest.manifest_id,
            workspace_policy_ref=self.permission_manifest.workspace_policy_ref,
            readable_refs=list(self.permission_manifest.readable_refs),
            writable_refs=list(self.permission_manifest.writable_refs),
            denied_refs=denied_refs,
            allowed_commands=list(self.permission_manifest.allowed_commands),
            network_policy=self.permission_manifest.network_policy,
            env_allowlist=list(self.permission_manifest.env_allowlist),
            secret_ref=self.permission_manifest.secret_ref,
            unsupported_hard_policies=list(self.permission_manifest.unsupported_hard_policies),
            extension_grants=list(self.permission_manifest.extension_grants),
            schema_version=self.permission_manifest.schema_version,
        )


def _unique_refs(refs: list[str]) -> list[str]:
    result: list[str] = []
    for ref in refs:
        safe_ref = validate_ref(ref, "run_workspace.denied_ref")
        if safe_ref not in result:
            result.append(safe_ref)
    return result
