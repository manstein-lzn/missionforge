"""Parallel PiWorker call batch primitive.

The batch runner executes already-compiled PiWorkerCall objects in isolated
runtime namespaces. It does not compile ContextEngine turns, merge outputs, or
resolve semantic conflicts.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
from typing import Any, Callable, Mapping

from .contracts import (
    ContractValidationError,
    assert_refs_only_payload,
    ensure_json_value,
    require_int_at_least,
    require_mapping,
    require_non_empty_str,
    stable_json_hash,
    validate_ref,
)
from .evidence_store import EvidenceLedger, FileEvidenceStore
from .kernel.io import resolve_workspace_ref
from .permissions import ref_is_under
from .piworker_call import PiWorkerCall, PiWorkerCallResult, PiWorkerCallResultStatus
from .piworker_progress import PiWorkerProgressSink
from .piworker_runtime import PiWorkerCallAdapter, create_default_piworker_adapter, run_piworker_call
from .progress_stream import ProgressStreamWriter
from .ref_store import FileRefStore, MemoryRefStore, RefStore
from .runtime_results import ExecutionReport


PIWORKER_CALL_BATCH_SCHEMA_VERSION = "missionforge.piworker_call_batch.v1"
PIWORKER_CALL_BATCH_RESULT_SCHEMA_VERSION = "missionforge.piworker_call_batch_result.v1"


@dataclass(frozen=True)
class PiWorkerCallBatch:
    """Validated group of independent PiWorker calls."""

    batch_id: str
    calls: list[PiWorkerCall]
    concurrency: int = 3
    conflict_policy: str = "reject"
    failure_policy: str = "collect"
    metadata: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = PIWORKER_CALL_BATCH_SCHEMA_VERSION

    def __post_init__(self) -> None:
        self.validate()

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PiWorkerCallBatch":
        data = _refs_only_mapping(payload, "piworker_call_batch")
        batch = cls(
            batch_id=_safe_id(data.get("batch_id"), "piworker_call_batch.batch_id"),
            calls=[
                PiWorkerCall.from_dict(require_mapping(item, "piworker_call_batch.calls[]"))
                for item in _list(data.get("calls", []), "piworker_call_batch.calls")
            ],
            concurrency=require_int_at_least(
                data.get("concurrency", 3),
                "piworker_call_batch.concurrency",
                1,
            ),
            conflict_policy=_policy(data.get("conflict_policy", "reject"), "piworker_call_batch.conflict_policy"),
            failure_policy=_policy(data.get("failure_policy", "collect"), "piworker_call_batch.failure_policy"),
            metadata=_metadata(data.get("metadata", {}), "piworker_call_batch.metadata"),
            schema_version=require_non_empty_str(
                data.get("schema_version", PIWORKER_CALL_BATCH_SCHEMA_VERSION),
                "piworker_call_batch.schema_version",
            ),
        )
        batch.validate()
        return batch

    def validate(self) -> None:
        _require_schema(self.schema_version, PIWORKER_CALL_BATCH_SCHEMA_VERSION, "piworker_call_batch.schema_version")
        _safe_id(self.batch_id, "piworker_call_batch.batch_id")
        if not self.calls:
            raise ContractValidationError("piworker_call_batch.calls must not be empty")
        call_ids: list[str] = []
        call_segments: list[str] = []
        for call in self.calls:
            if not isinstance(call, PiWorkerCall):
                raise ContractValidationError("piworker_call_batch.calls must contain PiWorkerCall values")
            call.validate()
            call_ids.append(call.call_id)
            call_segments.append(_call_segment(call.call_id))
        if len(call_ids) != len(set(call_ids)):
            raise ContractValidationError("piworker_call_batch calls must have unique call_id values")
        if len(call_segments) != len(set(call_segments)):
            raise ContractValidationError("piworker_call_batch call_id values must map to unique path segments")
        require_int_at_least(self.concurrency, "piworker_call_batch.concurrency", 1)
        if self.conflict_policy != "reject":
            raise ContractValidationError("piworker_call_batch.conflict_policy only supports reject")
        if self.failure_policy != "collect":
            raise ContractValidationError("piworker_call_batch.failure_policy only supports collect")
        _metadata(self.metadata, "piworker_call_batch.metadata")
        validate_piworker_call_batch_conflicts(self.calls)

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "batch_id": self.batch_id,
            "calls": [call.to_dict() for call in self.calls],
            "concurrency": self.concurrency,
            "conflict_policy": self.conflict_policy,
            "failure_policy": self.failure_policy,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class PiWorkerCallBatchResult:
    """Structured fan-in result for a PiWorker call batch."""

    batch_id: str
    status: str
    call_result_refs: list[str]
    completed_call_ids: list[str]
    failed_call_ids: list[str]
    blocked_call_ids: list[str]
    invalid_call_ids: list[str]
    output_refs: list[str]
    runtime_refs: list[str]
    batch_result_ref: str
    metadata: Mapping[str, Any] = field(default_factory=dict)
    store: RefStore | None = field(default=None, repr=False, compare=False)
    schema_version: str = PIWORKER_CALL_BATCH_RESULT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        self.validate()

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PiWorkerCallBatchResult":
        data = _refs_only_mapping(payload, "piworker_call_batch_result")
        result = cls(
            batch_id=_safe_id(data.get("batch_id"), "piworker_call_batch_result.batch_id"),
            status=_batch_status(data.get("status"), "piworker_call_batch_result.status"),
            call_result_refs=_unique_refs(
                data.get("call_result_refs", []),
                "piworker_call_batch_result.call_result_refs",
            ),
            completed_call_ids=_unique_strings(
                data.get("completed_call_ids", []),
                "piworker_call_batch_result.completed_call_ids",
            ),
            failed_call_ids=_unique_strings(data.get("failed_call_ids", []), "piworker_call_batch_result.failed_call_ids"),
            blocked_call_ids=_unique_strings(
                data.get("blocked_call_ids", []),
                "piworker_call_batch_result.blocked_call_ids",
            ),
            invalid_call_ids=_unique_strings(
                data.get("invalid_call_ids", []),
                "piworker_call_batch_result.invalid_call_ids",
            ),
            output_refs=_unique_refs(data.get("output_refs", []), "piworker_call_batch_result.output_refs"),
            runtime_refs=_unique_refs(data.get("runtime_refs", []), "piworker_call_batch_result.runtime_refs"),
            batch_result_ref=validate_ref(
                data.get("batch_result_ref"),
                "piworker_call_batch_result.batch_result_ref",
            ),
            metadata=_metadata(data.get("metadata", {}), "piworker_call_batch_result.metadata"),
            schema_version=require_non_empty_str(
                data.get("schema_version", PIWORKER_CALL_BATCH_RESULT_SCHEMA_VERSION),
                "piworker_call_batch_result.schema_version",
            ),
        )
        result.validate()
        return result

    def validate(self) -> None:
        _require_schema(
            self.schema_version,
            PIWORKER_CALL_BATCH_RESULT_SCHEMA_VERSION,
            "piworker_call_batch_result.schema_version",
        )
        _safe_id(self.batch_id, "piworker_call_batch_result.batch_id")
        _batch_status(self.status, "piworker_call_batch_result.status")
        _unique_refs(self.call_result_refs, "piworker_call_batch_result.call_result_refs")
        _unique_strings(self.completed_call_ids, "piworker_call_batch_result.completed_call_ids")
        _unique_strings(self.failed_call_ids, "piworker_call_batch_result.failed_call_ids")
        _unique_strings(self.blocked_call_ids, "piworker_call_batch_result.blocked_call_ids")
        _unique_strings(self.invalid_call_ids, "piworker_call_batch_result.invalid_call_ids")
        _unique_refs(self.output_refs, "piworker_call_batch_result.output_refs")
        _unique_refs(self.runtime_refs, "piworker_call_batch_result.runtime_refs")
        validate_ref(self.batch_result_ref, "piworker_call_batch_result.batch_result_ref")
        _metadata(self.metadata, "piworker_call_batch_result.metadata")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "batch_id": self.batch_id,
            "status": self.status,
            "call_result_refs": list(self.call_result_refs),
            "completed_call_ids": list(self.completed_call_ids),
            "failed_call_ids": list(self.failed_call_ids),
            "blocked_call_ids": list(self.blocked_call_ids),
            "invalid_call_ids": list(self.invalid_call_ids),
            "output_refs": list(self.output_refs),
            "runtime_refs": list(self.runtime_refs),
            "batch_result_ref": self.batch_result_ref,
            "metadata": dict(self.metadata),
        }


def validate_piworker_call_batch_conflicts(calls: list[PiWorkerCall]) -> None:
    """Reject shared write/output refs before starting any call."""

    call_list = list(calls)
    output_owner: dict[str, str] = {}
    write_roots: list[tuple[str, str]] = []
    for call in call_list:
        call.validate()
        for ref in call.expected_output_refs:
            safe_ref = validate_ref(ref, "piworker_call_batch.expected_output_refs[]")
            owner = output_owner.get(safe_ref)
            if owner is not None:
                raise ContractValidationError(
                    f"piworker_call_batch duplicate expected_output_ref {safe_ref}: {owner}, {call.call_id}"
                )
            output_owner[safe_ref] = call.call_id
            if not any(ref_is_under(safe_ref, root) for root in call.writable_refs):
                raise ContractValidationError(
                    f"piworker_call_batch expected output is outside writable refs: {safe_ref}"
                )
        for root in call.writable_refs:
            safe_root = validate_ref(root, "piworker_call_batch.writable_refs[]")
            for prior_root, prior_call_id in write_roots:
                if ref_is_under(safe_root, prior_root) or ref_is_under(prior_root, safe_root):
                    raise ContractValidationError(
                        "piworker_call_batch writable_refs overlap: "
                        f"{prior_call_id}:{prior_root} and {call.call_id}:{safe_root}"
                    )
            write_roots.append((safe_root, call.call_id))


def run_piworker_call_batch(
    batch: PiWorkerCallBatch,
    *,
    workspace: str | Path | None = None,
    store: RefStore | None = None,
    piworker_config: Any | None = None,
    adapter_factory: Callable[[PiWorkerCall], PiWorkerCallAdapter] | None = None,
    evidence_store_factory: Callable[[PiWorkerCall], EvidenceLedger] | None = None,
    runtime_progress_sink_factory: Callable[[PiWorkerCall], PiWorkerProgressSink] | None = None,
) -> PiWorkerCallBatchResult:
    """Run independent PiWorker calls concurrently and collect structured refs."""

    batch.validate()
    record_store = _record_store_for_batch(workspace=workspace, store=store)
    adapter_workspace = _adapter_workspace_for_batch(workspace=workspace, store=record_store)
    batch_root_ref = f"piworker_batches/{batch.batch_id}"
    batch_spec_ref = f"{batch_root_ref}/batch_spec.json"
    batch_result_ref = f"{batch_root_ref}/batch_result.json"
    _write_json_atomic(record_store, batch_spec_ref, batch.to_dict())

    max_workers = min(batch.concurrency, len(batch.calls))
    results: dict[str, PiWorkerCallResult] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(
                _run_one_call,
                call,
                workspace=record_store,
                adapter_workspace=adapter_workspace,
                piworker_config=piworker_config,
                adapter_factory=adapter_factory,
                evidence_store_factory=evidence_store_factory,
                runtime_progress_sink_factory=runtime_progress_sink_factory,
                batch_root_ref=batch_root_ref,
            ): call
            for call in batch.calls
        }
        for future in as_completed(futures):
            call = futures[future]
            try:
                results[call.call_id] = future.result()
            except Exception as exc:
                results[call.call_id] = _write_runtime_error_result(
                    workspace=record_store,
                    batch_root_ref=batch_root_ref,
                    call=call,
                    exc=exc,
                )

    ordered = [results[call.call_id] for call in batch.calls]
    default_progress_refs = []
    if runtime_progress_sink_factory is None and _supports_file_materialization(record_store, workspace):
        default_progress_refs = [
            f"{batch_root_ref}/calls/{_call_segment(call.call_id)}/progress.jsonl"
            for call in batch.calls
        ]
    result = _build_batch_result(
        batch=batch,
        results=ordered,
        batch_result_ref=batch_result_ref,
        runtime_refs=default_progress_refs,
        store=record_store,
    )
    _write_json_atomic(record_store, batch_result_ref, result.to_dict())
    return result


def _run_one_call(
    call: PiWorkerCall,
    *,
    workspace: RefStore | str | Path,
    adapter_workspace: Any,
    piworker_config: Any | None,
    adapter_factory: Callable[[PiWorkerCall], PiWorkerCallAdapter] | None,
    evidence_store_factory: Callable[[PiWorkerCall], EvidenceLedger] | None,
    runtime_progress_sink_factory: Callable[[PiWorkerCall], PiWorkerProgressSink] | None,
    batch_root_ref: str,
) -> PiWorkerCallResult:
    call.validate()
    call_segment = _call_segment(call.call_id)
    result_ref = f"{batch_root_ref}/calls/{call_segment}/piworker_call_result.json"
    adapter = adapter_factory(call) if adapter_factory is not None else create_default_piworker_adapter(piworker_config)
    file_workspace = _file_workspace_for_batch(workspace)
    evidence_store = (
        evidence_store_factory(call)
        if evidence_store_factory is not None
        else None
        if file_workspace is None
        else FileEvidenceStore(
            resolve_workspace_ref(file_workspace, f"{batch_root_ref}/calls/{call_segment}/evidence"),
            ref_prefix=f"{batch_root_ref}/calls/{call_segment}/evidence",
        )
    )
    progress_writer: ProgressStreamWriter | None = None
    progress_sink = runtime_progress_sink_factory(call) if runtime_progress_sink_factory is not None else None
    if progress_sink is None and file_workspace is not None:
        progress_writer = ProgressStreamWriter(
            file_workspace,
            stream_ref=f"{batch_root_ref}/calls/{call_segment}/progress.jsonl",
        )

        def progress_sink(event: dict[str, Any]) -> None:
            progress_writer.emit(
                stage=_progress_text(event.get("stage"), default="piworker_batch_runtime"),
                state=_progress_state(event.get("state")),
                message=_progress_text(event.get("message"), default=f"PiWorker call {call.call_id} progressed."),
                detail=_progress_text(event.get("detail"), default=""),
                progress_hint=_progress_text(event.get("progress_hint"), default=call.call_id),
                refs=_progress_refs(event.get("refs")),
            )

    if progress_writer is not None:
        progress_writer.emit(
            stage="piworker_batch_runtime",
            state="running",
            message=f"PiWorker call {call.call_id} started.",
            progress_hint=call.call_id,
            refs=[result_ref],
        )
    try:
        result = run_piworker_call(
            call,
            workspace=adapter_workspace,
            store=workspace if _looks_like_ref_store(workspace) else None,
            adapter=adapter,
            evidence_store=evidence_store,
            runtime_progress_sink=progress_sink,
        )
    except Exception as exc:
        if progress_writer is not None:
            progress_writer.emit(
                stage="piworker_batch_runtime",
                state="failed",
                message=f"PiWorker call {call.call_id} failed.",
                progress_hint=call.call_id,
                refs=[result_ref],
            )
        return _write_runtime_error_result(workspace=workspace, batch_root_ref=batch_root_ref, call=call, exc=exc)
    _write_json_atomic(workspace, result_ref, result.to_dict())
    if progress_writer is not None:
        progress_writer.emit(
            stage="piworker_batch_runtime",
            state="completed" if result.status is PiWorkerCallResultStatus.COMPLETED else "failed",
            message=f"PiWorker call {call.call_id} finished.",
            progress_hint=call.call_id,
            refs=[result_ref],
        )
    return result


def _write_runtime_error_result(
    *,
    workspace: RefStore | str | Path,
    batch_root_ref: str,
    call: PiWorkerCall,
    exc: BaseException,
) -> PiWorkerCallResult:
    call_segment = _call_segment(call.call_id)
    call_root_ref = f"{batch_root_ref}/calls/{call_segment}"
    error_ref = f"{call_root_ref}/error.json"
    report_ref = f"{call_root_ref}/execution_report.json"
    result_ref = f"{call_root_ref}/piworker_call_result.json"
    error_payload = {
        "schema_version": "missionforge.piworker_batch_call_error.v1",
        "call_id": call.call_id,
        "error_type": type(exc).__name__,
        "message_hash": stable_json_hash({"exception_message": str(exc)}),
        "message_length": len(str(exc)),
    }
    _write_json_atomic(workspace, error_ref, error_payload)
    report = ExecutionReport(
        report_id=f"R-{call.call_id}-batch-runtime-error",
        call_id=call.call_id,
        status="failed",
        produced_artifacts=[],
        changed_refs=[error_ref],
        evidence_refs=[error_ref],
        metrics={
            "batch_runtime_error_ref": error_ref,
            "batch_runtime_error_type": type(exc).__name__,
        },
    )
    _write_json_atomic(workspace, report_ref, report.to_dict())
    result = PiWorkerCallResult(
        result_id=f"{call.call_id}-batch-runtime-error",
        call_id=call.call_id,
        role=call.role,
        contract_id=call.contract_id,
        contract_hash=call.contract_hash,
        contract_ref=call.contract_ref,
        status=PiWorkerCallResultStatus.RUNTIME_ERROR,
        execution_report_ref=report_ref,
        output_refs=[],
        runtime_refs=[report_ref, error_ref],
        evidence_refs=[error_ref],
        error_ref=error_ref,
        metadata={
            "batch_runtime_error_ref": error_ref,
            "batch_runtime_error_type": type(exc).__name__,
        },
    )
    result.validate_against_call(call)
    _write_json_atomic(workspace, result_ref, result.to_dict())
    return result


def _build_batch_result(
    *,
    batch: PiWorkerCallBatch,
    results: list[PiWorkerCallResult],
    batch_result_ref: str,
    runtime_refs: list[str] | None = None,
    store: RefStore | None = None,
) -> PiWorkerCallBatchResult:
    completed: list[str] = []
    failed: list[str] = []
    blocked: list[str] = []
    invalid: list[str] = []
    for result in results:
        if result.status is PiWorkerCallResultStatus.COMPLETED:
            completed.append(result.call_id)
        elif result.status is PiWorkerCallResultStatus.BLOCKED:
            blocked.append(result.call_id)
        elif result.status in {PiWorkerCallResultStatus.INVALID_OUTPUT, PiWorkerCallResultStatus.UNAUTHORIZED_OUTPUT}:
            invalid.append(result.call_id)
        else:
            failed.append(result.call_id)
    status = _status_for_call_sets(total=len(results), completed=len(completed), incomplete=len(results) - len(completed))
    call_result_refs = [
        _call_result_ref_for_batch(batch.batch_id, result.call_id)
        for result in results
    ]
    output_refs = _dedupe_refs([ref for result in results for ref in result.output_refs])
    collected_runtime_refs = _dedupe_refs([
        *[ref for result in results for ref in result.runtime_refs],
        *(runtime_refs or []),
    ])
    batch_result = PiWorkerCallBatchResult(
        batch_id=batch.batch_id,
        status=status,
        call_result_refs=call_result_refs,
        completed_call_ids=completed,
        failed_call_ids=failed,
        blocked_call_ids=blocked,
        invalid_call_ids=invalid,
        output_refs=output_refs,
        runtime_refs=collected_runtime_refs,
        batch_result_ref=batch_result_ref,
        store=store,
        metadata={
            "call_count": len(results),
            "completed_count": len(completed),
            "failed_count": len(failed),
            "blocked_count": len(blocked),
            "invalid_count": len(invalid),
        },
    )
    batch_result.validate()
    return batch_result


def _status_for_call_sets(*, total: int, completed: int, incomplete: int) -> str:
    if total > 0 and completed == total:
        return "completed"
    if completed > 0 and incomplete > 0:
        return "partial"
    return "failed"


def _call_result_ref_for_batch(batch_id: str, call_id: str) -> str:
    return f"piworker_batches/{_safe_id(batch_id, 'batch_id')}/calls/{_call_segment(call_id)}/piworker_call_result.json"


def _record_store_for_batch(*, workspace: str | Path | None, store: RefStore | None) -> RefStore:
    if store is not None:
        return store
    if workspace is not None:
        return FileRefStore(workspace)
    return MemoryRefStore()


def _adapter_workspace_for_batch(*, workspace: str | Path | None, store: RefStore) -> Any:
    if workspace is not None:
        return workspace
    if isinstance(store, FileRefStore):
        return store.root
    return None


def _file_workspace_for_batch(workspace: RefStore | str | Path) -> str | Path | None:
    if isinstance(workspace, (str, Path)):
        return workspace
    if isinstance(workspace, FileRefStore):
        return workspace.root
    return None


def _supports_file_materialization(store: RefStore, workspace: str | Path | None) -> bool:
    return workspace is not None or isinstance(store, FileRefStore)


def _looks_like_ref_store(value: Any) -> bool:
    return (
        hasattr(value, "exists")
        and hasattr(value, "read_bytes")
        and hasattr(value, "write_bytes")
        and hasattr(value, "hash_ref")
    )


def _write_json_atomic(workspace: RefStore | str | Path, ref: str, payload: Mapping[str, Any]) -> str:
    safe_ref = validate_ref(ref, "piworker_batch.output_ref")
    if _looks_like_ref_store(workspace):
        workspace.write_json(safe_ref, dict(payload))
        return safe_ref
    target = resolve_workspace_ref(workspace, safe_ref)
    target.parent.mkdir(parents=True, exist_ok=True)
    compatible = ensure_json_value(dict(payload), safe_ref)
    tmp = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(compatible, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, target)
    return safe_ref


def _call_segment(call_id: str) -> str:
    text = require_non_empty_str(call_id, "piworker_call_batch.call_id")
    segment = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in text)
    segment = segment.strip("_") or stable_json_hash({"call_id": text})[-12:]
    return segment[:96]


def _refs_only_mapping(payload: Mapping[str, Any], field_name: str) -> dict[str, Any]:
    return dict(assert_refs_only_payload(require_mapping(payload, field_name), field_name))


def _metadata(value: Any, field_name: str) -> dict[str, Any]:
    return dict(ensure_json_value(assert_refs_only_payload(require_mapping(value, field_name), field_name), field_name))


def _safe_id(value: Any, field_name: str) -> str:
    text = require_non_empty_str(value, field_name)
    if "/" in text or "\\" in text or text in {".", ".."}:
        raise ContractValidationError(f"{field_name} must be a single safe id segment")
    return validate_ref(text, field_name)


def _policy(value: Any, field_name: str) -> str:
    return _safe_id(value, field_name)


def _batch_status(value: Any, field_name: str) -> str:
    text = _safe_id(value, field_name)
    if text not in {"completed", "partial", "failed", "cancelled"}:
        raise ContractValidationError(f"{field_name} is unsupported")
    return text


def _unique_refs(values: Any, field_name: str) -> list[str]:
    refs = [validate_ref(value, f"{field_name}[]") for value in _list(values, field_name)]
    if len(refs) != len(set(refs)):
        raise ContractValidationError(f"{field_name} must not contain duplicates")
    return refs


def _unique_strings(values: Any, field_name: str) -> list[str]:
    strings = [require_non_empty_str(value, f"{field_name}[]") for value in _list(values, field_name)]
    if len(strings) != len(set(strings)):
        raise ContractValidationError(f"{field_name} must not contain duplicates")
    return strings


def _dedupe_refs(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        ref = validate_ref(value, "piworker_batch.ref")
        if ref not in seen:
            result.append(ref)
            seen.add(ref)
    return result


def _progress_state(value: Any) -> str:
    if value in {"pending", "running", "completed", "failed", "blocked"}:
        return str(value)
    return "running"


def _progress_text(value: Any, *, default: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()[:500]
    return default


def _progress_refs(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    refs: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        try:
            refs.append(validate_ref(item, "piworker_batch.progress.refs[]"))
        except ContractValidationError:
            continue
    return _dedupe_refs(refs)


def _list(value: Any, field_name: str) -> list[Any]:
    if not isinstance(value, list):
        raise ContractValidationError(f"{field_name} must be a list")
    return value


def _require_schema(value: str, expected: str, field_name: str) -> None:
    if require_non_empty_str(value, field_name) != expected:
        raise ContractValidationError(f"{field_name} must be {expected}")
