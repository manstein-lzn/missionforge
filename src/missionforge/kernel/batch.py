"""Parallel Kernel Step batch wrapper.

This module schedules independent Step values through the existing run_step()
path. It does not add Flow-level parallel routing or merge semantics.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping

from ..contracts import (
    ContractValidationError,
    assert_refs_only_payload,
    ensure_json_value,
    require_mapping,
    stable_json_hash,
    validate_ref,
)
from ..piworker_runtime import PiWorkerCallAdapter
from ..permissions import ref_is_under
from ..ref_store import RefStore
from .compiler import StepCompileContext, compile_step
from .contracts import Artifact, KernelValidationError, Step, StepRecord, StepStatus, Toolset
from .io import write_json_ref
from .results import StepRunResult
from .runner import run_step
from .runtime_store import _record_store_for_run, _supports_file_materialization


@dataclass(frozen=True)
class StepBatchResult:
    """Structured result for a parallel Kernel Step batch."""

    batch_id: str
    status: str
    step_results: list[StepRunResult] = field(default_factory=list)
    step_record_refs: list[str] = field(default_factory=list)
    completed_step_ids: list[str] = field(default_factory=list)
    failed_step_ids: list[str] = field(default_factory=list)
    blocked_step_ids: list[str] = field(default_factory=list)
    output_refs: list[str] = field(default_factory=list)
    runtime_refs: list[str] = field(default_factory=list)
    failure_refs: list[str] = field(default_factory=list)
    metadata: Mapping[str, Any] = field(default_factory=dict)
    store: RefStore | None = field(default=None, repr=False, compare=False)

    def validate(self) -> None:
        _safe_id(self.batch_id, "kernel_step_batch_result.batch_id")
        if self.status not in {"completed", "partial", "failed", "cancelled"}:
            raise KernelValidationError("kernel_step_batch_result.status is unsupported")
        for result in self.step_results:
            if not isinstance(result, StepRunResult):
                raise KernelValidationError("kernel_step_batch_result.step_results must contain StepRunResult values")
            result.validate()
        _unique_refs(self.step_record_refs, "kernel_step_batch_result.step_record_refs")
        _unique_strings(self.completed_step_ids, "kernel_step_batch_result.completed_step_ids")
        _unique_strings(self.failed_step_ids, "kernel_step_batch_result.failed_step_ids")
        _unique_strings(self.blocked_step_ids, "kernel_step_batch_result.blocked_step_ids")
        _unique_refs(self.output_refs, "kernel_step_batch_result.output_refs")
        _unique_refs(self.runtime_refs, "kernel_step_batch_result.runtime_refs")
        _unique_refs(self.failure_refs, "kernel_step_batch_result.failure_refs")
        _metadata(self.metadata, "kernel_step_batch_result.metadata")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "batch_id": self.batch_id,
            "status": self.status,
            "step_record_refs": list(self.step_record_refs),
            "completed_step_ids": list(self.completed_step_ids),
            "failed_step_ids": list(self.failed_step_ids),
            "blocked_step_ids": list(self.blocked_step_ids),
            "output_refs": list(self.output_refs),
            "runtime_refs": list(self.runtime_refs),
            "failure_refs": list(self.failure_refs),
            "metadata": dict(self.metadata),
        }


def run_steps_batch(
    steps: list[Step],
    *,
    context: StepCompileContext,
    workspace: str | Path | None = None,
    store: RefStore | None = None,
    concurrency: int = 3,
    batch_id: str = "step-batch",
    adapter: PiWorkerCallAdapter | None = None,
    piworker_config: Any | None = None,
    runner: Any | None = None,
    evidence_store_factory: Any | None = None,
    toolsets: Mapping[str, Toolset] | None = None,
    artifacts: Mapping[str, Artifact] | None = None,
    extension_lock_ref: str | None = None,
    extension_lock_mode: str = "verify-installed",
    extension_installer: Any | None = None,
    extension_install_root_ref: str = ".missionforge/extensions",
    extension_lock_compiled_at: str | None = None,
    resume: bool = True,
    runtime_progress_sink_factory: Any | None = None,
    adapter_factory: Any | None = None,
) -> StepBatchResult:
    """Run independent Kernel steps concurrently through run_step()."""

    context.validate()
    safe_batch_id = _safe_id(batch_id, "kernel_step_batch.batch_id")
    record_store = _record_store_for_run(workspace=workspace, store=store)
    safe_extension_lock_ref = (
        validate_ref(extension_lock_ref, "kernel_step_batch.extension_lock_ref")
        if extension_lock_ref is not None
        else None
    )
    safe_extension_install_root_ref = validate_ref(
        extension_install_root_ref,
        "kernel_step_batch.extension_install_root_ref",
    )
    if not steps:
        raise KernelValidationError("kernel_step_batch.steps must not be empty")
    for step in steps:
        step.validate()
    concurrency = _positive_int(concurrency, "kernel_step_batch.concurrency")
    _validate_step_batch_conflicts(steps)
    _validate_unique_step_segments(steps)
    if adapter is not None and concurrency > 1 and len(steps) > 1:
        raise KernelValidationError("kernel_step_batch concurrent execution requires adapter_factory, not shared adapter")

    execution_plan = [
        (
            index,
            step,
            _step_context(
                base=context,
                batch_id=safe_batch_id,
                step=step,
                index=index,
            ),
            _adapter_for_step(step=step, adapter=adapter, adapter_factory=adapter_factory),
            evidence_store_factory(step) if evidence_store_factory is not None else None,
            runtime_progress_sink_factory(step) if runtime_progress_sink_factory is not None else None,
        )
        for index, step in enumerate(steps, start=1)
    ]
    if not _supports_file_materialization(record_store, workspace) and safe_extension_lock_ref is None:
        for _index, step, step_context, _step_adapter, _evidence_store, _progress_sink in execution_plan:
            compiled = compile_step(step, context=step_context, toolsets=toolsets, artifacts=artifacts)
            if compiled.permission_manifest.extension_grants:
                raise KernelValidationError("kernel_step_batch extension locks require an explicit filesystem workspace")

    max_workers = min(concurrency, len(steps))
    results: dict[int, StepRunResult] = {}
    failed_records: dict[int, StepRecord] = {}
    failed_record_refs: dict[int, str] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(
                run_step,
                step,
                context=step_context,
                workspace=None,
                store=record_store,
                adapter=step_adapter,
                piworker_config=piworker_config,
                runner=runner,
                evidence_store=evidence_store,
                toolsets=toolsets,
                artifacts=artifacts,
                extension_lock_ref=safe_extension_lock_ref,
                extension_lock_mode=extension_lock_mode,
                extension_installer=extension_installer,
                extension_install_root_ref=safe_extension_install_root_ref,
                extension_lock_compiled_at=extension_lock_compiled_at,
                resume=resume,
                runtime_progress_sink=progress_sink,
            ): index
            for index, step, step_context, step_adapter, evidence_store, progress_sink in execution_plan
        }
        for future in as_completed(futures):
            index = futures[future]
            try:
                results[index] = future.result()
            except (ContractValidationError, KernelValidationError):
                raise
            except Exception as exc:
                _failed_index, failed_step, failed_context, _failed_adapter, _failed_evidence, _failed_progress = (
                    execution_plan[index - 1]
                )
                failed_record, failed_ref = _write_failed_step_record(
                    workspace=record_store,
                    step=failed_step,
                    context=failed_context,
                    exc=exc,
                )
                failed_records[index] = failed_record
                failed_record_refs[index] = failed_ref

    ordered_results = [results[index] for index in sorted(results)]
    ordered_failed_records = [failed_records[index] for index in sorted(failed_records)]
    ordered_failed_refs = [failed_record_refs[index] for index in sorted(failed_record_refs)]
    batch_result = _build_step_batch_result(
        batch_id=safe_batch_id,
        step_results=ordered_results,
        failed_step_records=ordered_failed_records,
        failed_step_record_refs=ordered_failed_refs,
        store=record_store,
    )
    batch_result.validate()
    return batch_result


def _adapter_for_step(
    *,
    step: Step,
    adapter: PiWorkerCallAdapter | None,
    adapter_factory: Any | None,
) -> PiWorkerCallAdapter | None:
    if adapter_factory is not None:
        return adapter_factory(step)
    if adapter is not None:
        return adapter
    return None


def _step_context(*, base: StepCompileContext, batch_id: str, step: Step, index: int) -> StepCompileContext:
    step_segment = _step_segment(step.id)
    return replace(
        base,
        ref_prefix=f"kernel/{base.flow_id}/batches/{batch_id}/steps/{index:03d}-{step_segment}",
        call_id=f"{base.flow_id}-{batch_id}-{index:03d}-{step_segment}",
    )


def _build_step_batch_result(
    *,
    batch_id: str,
    step_results: list[StepRunResult],
    failed_step_records: list[StepRecord] | None = None,
    failed_step_record_refs: list[str] | None = None,
    store: RefStore | None = None,
) -> StepBatchResult:
    extra_failed_records = list(failed_step_records or [])
    extra_failed_refs = list(failed_step_record_refs or [])
    completed: list[str] = []
    failed: list[str] = []
    blocked: list[str] = []
    output_refs: list[str] = []
    runtime_refs: list[str] = []
    failure_refs: list[str] = []
    for result in step_results:
        status = result.step_record.status.value
        if status in {"completed", "skipped"}:
            completed.append(result.compiled.step.id)
        elif status == "blocked":
            blocked.append(result.compiled.step.id)
        else:
            failed.append(result.compiled.step.id)
        output_refs.extend(result.step_record.output_refs)
        runtime_value = result.step_record.metadata.get("runtime_refs")
        if isinstance(runtime_value, list):
            runtime_refs.extend([ref for ref in runtime_value if isinstance(ref, str)])
        runtime_refs.extend(_metadata_refs(result.step_record.metadata))
        failure_refs.extend(result.step_record.failure_refs)
    for record in extra_failed_records:
        if record.status is StepStatus.BLOCKED:
            blocked.append(record.step_id)
        else:
            failed.append(record.step_id)
        output_refs.extend(record.output_refs)
        runtime_refs.extend(_metadata_refs(record.metadata))
        failure_refs.extend(record.failure_refs)
    total_steps = len(step_results) + len(extra_failed_records)
    status = "completed" if len(completed) == total_steps else "partial" if completed else "failed"
    return StepBatchResult(
        batch_id=batch_id,
        status=status,
        step_results=list(step_results),
        step_record_refs=[result.step_record_ref for result in step_results] + extra_failed_refs,
        completed_step_ids=completed,
        failed_step_ids=failed,
        blocked_step_ids=blocked,
        output_refs=_dedupe_refs(output_refs),
        runtime_refs=_dedupe_refs(runtime_refs),
        failure_refs=_dedupe_refs(failure_refs),
        store=store,
        metadata={
            "step_count": total_steps,
            "completed_count": len(completed),
            "failed_count": len(failed),
            "blocked_count": len(blocked),
            "exception_count": len(extra_failed_records),
        },
    )


def _write_failed_step_record(
    *,
    workspace: RefStore | str | Path,
    step: Step,
    context: StepCompileContext,
    exc: BaseException,
) -> tuple[StepRecord, str]:
    ref_prefix = context.ref_prefix or f"kernel/{context.flow_id}/steps/{step.id}"
    step_record_ref = f"{ref_prefix}/step_record.json"
    error_ref = f"{ref_prefix}/batch_error.json"
    permission_manifest_ref = context.permission_manifest_ref or f"{ref_prefix}/permission_manifest.json"
    write_json_ref(
        workspace,
        error_ref,
        {
            "schema_version": "missionforge.kernel_step_batch_error.v1",
            "step_id": step.id,
            "error_type": type(exc).__name__,
            "message_hash": stable_json_hash({"exception_message": str(exc)}),
            "message_length": len(str(exc)),
        },
    )
    record = StepRecord(
        step_id=step.id,
        step_spec_hash=step.spec_hash,
        contract_ref=context.contract_ref,
        contract_hash=context.contract_hash,
        input_refs=list(step.inputs),
        output_refs=[],
        status=StepStatus.FAILED,
        permission_manifest_ref=permission_manifest_ref,
        failure_refs=[error_ref],
        metadata={
            "kernel_flow_id": context.flow_id,
            "batch_runtime_error_ref": error_ref,
        },
    )
    write_json_ref(workspace, step_record_ref, record.to_dict())
    return record, step_record_ref


def _validate_step_batch_conflicts(steps: list[Step]) -> None:
    output_owner: dict[str, str] = {}
    write_roots: list[tuple[str, str]] = []
    for step in steps:
        for ref in step.outputs:
            safe_ref = validate_ref(ref, "kernel_step_batch.outputs[]")
            owner = output_owner.get(safe_ref)
            if owner is not None:
                raise KernelValidationError(
                    f"kernel_step_batch duplicate output ref {safe_ref}: {owner}, {step.id}"
                )
            output_owner[safe_ref] = step.id
            if not any(ref_is_under(safe_ref, root) for root in step.write):
                raise KernelValidationError(f"kernel_step_batch output is outside write refs: {safe_ref}")
        for root in step.write:
            safe_root = validate_ref(root, "kernel_step_batch.write[]")
            for prior_root, prior_step_id in write_roots:
                if ref_is_under(safe_root, prior_root) or ref_is_under(prior_root, safe_root):
                    raise KernelValidationError(
                        f"kernel_step_batch write refs overlap: {prior_step_id}:{prior_root} and {step.id}:{safe_root}"
                    )
            write_roots.append((safe_root, step.id))


def _validate_unique_step_segments(steps: list[Step]) -> None:
    segments = [_step_segment(step.id) for step in steps]
    if len(segments) != len(set(segments)):
        raise KernelValidationError("kernel_step_batch step ids must map to unique path segments")


def _step_segment(step_id: str) -> str:
    text = _safe_id(step_id, "kernel_step_batch.step_id")
    segment = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in text)
    return segment.strip("_")[:96] or "step"


def _positive_int(value: Any, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise KernelValidationError(f"{field_name} must be an integer >= 1")
    return value


def _safe_id(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise KernelValidationError(f"{field_name} must be a non-empty string")
    if "/" in value or "\\" in value or value in {".", ".."}:
        raise KernelValidationError(f"{field_name} must be a single safe id segment")
    validate_ref(value, field_name)
    return value


def _metadata(value: Any, field_name: str) -> dict[str, Any]:
    return dict(ensure_json_value(assert_refs_only_payload(require_mapping(value, field_name), field_name), field_name))


def _unique_refs(values: list[str], field_name: str) -> list[str]:
    refs = [validate_ref(value, f"{field_name}[]") for value in values]
    if len(refs) != len(set(refs)):
        raise KernelValidationError(f"{field_name} must not contain duplicates")
    return refs


def _unique_strings(values: list[str], field_name: str) -> list[str]:
    strings: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value:
            raise KernelValidationError(f"{field_name} must contain non-empty strings")
        strings.append(value)
    if len(strings) != len(set(strings)):
        raise KernelValidationError(f"{field_name} must not contain duplicates")
    return strings


def _dedupe_refs(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        ref = validate_ref(value, "kernel_step_batch.ref")
        if ref not in seen:
            result.append(ref)
            seen.add(ref)
    return result


def _metadata_refs(metadata: Mapping[str, Any]) -> list[str]:
    refs: list[str] = []
    for key, value in metadata.items():
        if key.endswith("_ref") and isinstance(value, str) and value:
            refs.append(value)
        elif key.endswith("_refs") and isinstance(value, list):
            refs.extend([item for item in value if isinstance(item, str)])
    return refs
