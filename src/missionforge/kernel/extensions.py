"""Kernel extension lock preparation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from ..contracts import ContractValidationError, validate_ref
from ..extensions import ExtensionLock, compile_extension_lock, npm_install_extension, read_extension_lock, verify_extension_lock, write_extension_lock
from ..ref_store import FileRefStore, RefStore
from ..task_contract import ExtensionGrant, PermissionManifest
from .io import resolve_workspace_ref


ExtensionInstaller = Callable[[ExtensionGrant, Path], Mapping[str, Any]]
ExtensionWorkspace = RefStore | str | Path


@dataclass(frozen=True)
class KernelExtensionLockResult:
    """Refs-first result for a prepared extension lock."""

    extension_lock_ref: str | None = None
    extension_lock_hash: str | None = None


def prepare_extension_lock(
    permission_manifest: PermissionManifest,
    *,
    source_permission_manifest_ref: str,
    workspace: ExtensionWorkspace,
    ref_prefix: str,
    extension_lock_ref: str | None = None,
    install_root_ref: str = ".missionforge/extensions",
    mode: str = "verify-installed",
    installer: ExtensionInstaller | None = None,
    compiled_at: str | None = None,
) -> KernelExtensionLockResult:
    """Write or verify the extension lock for one Kernel step.

    Kernel compiles tool authority into the existing MissionForge
    ``ExtensionLock`` schema. It does not invent a second tool schema.
    """

    permission_manifest.validate()
    if extension_lock_ref is not None:
        lock = _read_extension_lock_ref(workspace, extension_lock_ref)
        if lock.source_permission_manifest_ref != source_permission_manifest_ref:
            raise ContractValidationError(
                f"kernel extension lock {extension_lock_ref} source_permission_manifest_ref does not match"
            )
        _assert_lock_satisfies_manifest(permission_manifest, lock, extension_lock_ref)
        return KernelExtensionLockResult(extension_lock_ref=extension_lock_ref, extension_lock_hash=lock.lock_hash)
    if not permission_manifest.extension_grants:
        return KernelExtensionLockResult()
    filesystem_workspace = _filesystem_workspace(workspace)
    if filesystem_workspace is None:
        raise ContractValidationError("kernel extension lock compilation requires an explicit filesystem workspace")

    lock_ref = validate_ref(f"{ref_prefix}/extension_lock.json", "kernel_extension_lock.ref")
    previous_compiled_at = _existing_compiled_at(workspace, lock_ref)
    effective_installer = installer
    if mode == "install" and effective_installer is None:
        effective_installer = npm_install_extension
    lock = compile_extension_lock(
        permission_manifest,
        source_permission_manifest_ref=source_permission_manifest_ref,
        install_root_ref=install_root_ref,
        workspace_root=filesystem_workspace,
        mode=mode,
        installer=effective_installer,
        compiled_at=compiled_at or previous_compiled_at,
    )
    write_extension_lock(workspace, lock, ref=lock_ref)
    return KernelExtensionLockResult(extension_lock_ref=lock_ref, extension_lock_hash=lock.lock_hash)


def _read_extension_lock_ref(workspace: ExtensionWorkspace, ref: str) -> ExtensionLock:
    if isinstance(workspace, (str, Path)):
        return read_extension_lock(resolve_workspace_ref(workspace, ref))
    return read_extension_lock(workspace, ref)


def _existing_compiled_at(workspace: ExtensionWorkspace, ref: str) -> str | None:
    safe_ref = validate_ref(ref, "kernel_extension_lock.ref")
    if isinstance(workspace, (str, Path)):
        path = resolve_workspace_ref(workspace, safe_ref)
        if not path.is_file():
            return None
    elif not workspace.exists(safe_ref):
        return None
    try:
        return _read_extension_lock_ref(workspace, safe_ref).compiled_at
    except (OSError, ContractValidationError):
        return None


def _filesystem_workspace(workspace: ExtensionWorkspace) -> Path | None:
    if isinstance(workspace, (str, Path)):
        return Path(workspace)
    if isinstance(workspace, FileRefStore):
        return workspace.root
    return None


def _assert_lock_satisfies_manifest(
    permission_manifest: PermissionManifest,
    lock: ExtensionLock,
    lock_ref: str,
) -> None:
    report = verify_extension_lock(permission_manifest, lock)
    if report.rejected_extensions:
        reasons = ", ".join(f"{record.grant_id}:{record.reason}" for record in report.rejected_extensions)
        raise ContractValidationError(f"kernel extension lock {lock_ref} does not satisfy permission manifest: {reasons}")
