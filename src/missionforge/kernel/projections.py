"""Runtime-owned Kernel projection execution."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from ..contracts import validate_ref
from ..ref_store import FileRefStore, RefStore
from .contracts import KernelValidationError, Projection, ProjectionRecord
from .io import hash_ref, hash_refs, ref_exists, resolve_workspace_ref, write_projection_value


ProjectionProjector = Callable[[Mapping[str, str], Projection], Any]


@dataclass(frozen=True)
class ProjectionRunResult:
    """Refs-first result for one runtime projection."""

    projection: Projection
    record: ProjectionRecord
    record_ref: str

    def validate(self) -> None:
        self.projection.validate()
        self.record.validate()
        validate_ref(self.record_ref, "kernel_projection_run_result.record_ref")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "output_ref": self.record.output_ref,
            "projector": self.record.projector,
            "record_ref": self.record_ref,
            "source_refs": list(self.record.source_refs),
        }


def run_projection(
    projection: Projection,
    *,
    workspace: RefStore | str | Path,
    projectors: Mapping[str, ProjectionProjector],
    record_ref: str | None = None,
) -> ProjectionRunResult:
    """Run one runtime-owned projection using a product-supplied projector."""

    projection.validate()
    effective_record_ref = (
        validate_ref(record_ref, "kernel_projection.record_ref")
        if record_ref is not None
        else _projection_record_ref(projection.output)
    )
    projector = projectors.get(projection.projector)
    if projector is None:
        raise KernelValidationError(f"kernel_projection projector is not registered: {projection.projector}")
    missing = [ref for ref in projection.from_ if not ref_exists(workspace, ref)]
    if missing:
        raise KernelValidationError(f"kernel_projection source refs are missing: {missing}")
    source_hashes = hash_refs(workspace, projection.from_)
    value = projector(_projector_sources(workspace, projection.from_), projection)
    write_projection_value(workspace, projection.output, value)
    output_hash = hash_ref(workspace, projection.output)
    record = ProjectionRecord(
        output_ref=projection.output,
        projector=projection.projector,
        source_refs=list(projection.from_),
        source_hashes=source_hashes,
        output_hash=output_hash,
        metadata={"projection_metadata": dict(projection.metadata)},
    )
    write_projection_value(workspace, effective_record_ref, record.to_dict())
    result = ProjectionRunResult(projection=projection, record=record, record_ref=effective_record_ref)
    result.validate()
    return result


def run_projections(
    projections: list[Projection],
    *,
    workspace: RefStore | str | Path,
    projectors: Mapping[str, ProjectionProjector],
    record_prefix: str = "kernel/projections",
) -> list[ProjectionRunResult]:
    """Run runtime-owned projections in declaration order."""

    results: list[ProjectionRunResult] = []
    for index, projection in enumerate(projections, start=1):
        record_ref = f"{validate_ref(record_prefix, 'kernel_projection.record_prefix')}/{index:03d}-{projection.projector}.json"
        results.append(run_projection(projection, workspace=workspace, projectors=projectors, record_ref=record_ref))
    return results


def _projector_sources(workspace: RefStore | str | Path, refs: list[str]) -> dict[str, str]:
    if isinstance(workspace, (str, Path)):
        return {ref: str(resolve_workspace_ref(workspace, ref)) for ref in refs}
    if isinstance(workspace, FileRefStore):
        return {ref: str(resolve_workspace_ref(workspace.root, ref)) for ref in refs}
    return {ref: ref for ref in refs}


def _projection_record_ref(output_ref: str) -> str:
    safe = validate_ref(output_ref, "kernel_projection.output")
    stem = safe.rsplit(".", 1)[0]
    return f"kernel/projections/{stem.replace('/', '_')}.json"
