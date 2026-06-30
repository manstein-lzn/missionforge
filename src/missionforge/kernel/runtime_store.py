"""Kernel runtime store and materialization boundaries."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

from ..contracts import ContractValidationError
from ..ref_store import FileRefStore, MemoryRefStore, RefStore
from .compiler import CompiledStep, StepCompileContext, compile_step
from .contracts import Artifact, KernelValidationError, Step, Toolset


class _NoFilesystemWorkspace:
    """Fail closed if a RefStore-only run attempts filesystem materialization."""

    def __fspath__(self) -> str:
        raise ContractValidationError("filesystem workspace is unavailable for RefStore-only run")

    def __str__(self) -> str:
        raise ContractValidationError("filesystem workspace is unavailable for RefStore-only run")

    def __repr__(self) -> str:
        return "<missionforge-refstore-only-workspace>"


_NO_FILESYSTEM_WORKSPACE = _NoFilesystemWorkspace()


def _record_store_for_run(*, workspace: str | Path | None, store: RefStore | None) -> RefStore:
    if workspace is not None and store is not None:
        raise ContractValidationError("kernel runtime requires either workspace or store, not both")
    if store is not None:
        return store
    if workspace is not None:
        return FileRefStore(workspace)
    return MemoryRefStore()


def _adapter_workspace_for_run(*, workspace: str | Path | None, store: RefStore) -> object:
    if workspace is not None:
        return workspace
    if isinstance(store, FileRefStore):
        return store.root
    return _NO_FILESYSTEM_WORKSPACE


def _extension_workspace_for_run(*, workspace: str | Path | None, store: RefStore) -> object:
    if workspace is not None:
        return workspace
    return store


def _validate_extension_lock_store_boundary(
    *,
    compiled: CompiledStep,
    workspace: str | Path | None,
    store: RefStore,
    extension_lock_ref: str | None,
) -> None:
    if isinstance(store, FileRefStore) or workspace is not None:
        return
    if extension_lock_ref is None and compiled.permission_manifest.extension_grants:
        raise KernelValidationError("kernel run_step extension locks require an explicit filesystem workspace")


def _requires_extension_lock_filesystem_boundary(
    *,
    step: Step,
    context: StepCompileContext,
    toolsets: Mapping[str, Toolset] | None,
    artifacts: Mapping[str, Artifact] | None,
    workspace: str | Path | None,
    store: RefStore,
    extension_lock_ref: str | None,
) -> None:
    if isinstance(store, FileRefStore) or workspace is not None or extension_lock_ref is not None:
        return
    compiled = compile_step(step, context=context, toolsets=toolsets, artifacts=artifacts)
    if compiled.permission_manifest.extension_grants:
        raise KernelValidationError("kernel run_step extension locks require an explicit filesystem workspace")


def _supports_file_materialization(store: RefStore, workspace: str | Path | None) -> bool:
    return workspace is not None or isinstance(store, FileRefStore)


def _looks_like_ref_store(value: object) -> bool:
    return (
        hasattr(value, "exists")
        and hasattr(value, "read_bytes")
        and hasattr(value, "write_bytes")
        and hasattr(value, "hash_ref")
    )
