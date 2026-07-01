"""Minimal Kernel Step runner."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Mapping

from ..contracts import ContractValidationError, stable_json_hash, validate_ref
from ..context_engine import compile_context_request
from ..context_policy import ContextManagementPolicy
from ..evidence_store import EvidenceLedger
from ..extensions import ExtensionLock
from ..interaction import InteractionPort, InteractionDelivery, UserEvent, UserEventKind
from ..observation import (
    RunEvent,
    RunEventKind,
    RunSnapshot,
    RunSnapshotStatus,
)
from ..piworker_call import PiWorkerCall, PiWorkerCallResult, PiWorkerCallResultStatus
from ..piworker_progress import PiWorkerProgressSink
from ..piworker_runtime import PiWorkerCallAdapter, run_piworker_call
from ..permissions import ReadGate
from ..ref_store import RefStore
from .compiler import CompiledStep, StepCompileContext, compile_step
from .contracts import (
    Artifact,
    Flow,
    FlowLedgerEvent,
    FlowLedgerEventKind,
    FlowResult,
    FlowStop,
    KernelValidationError,
    Step,
    StepRecord,
    StepStatus,
    Toolset,
)
from .context_runtime import (
    _build_context_compile_request,
    _compiled_step_with_context_metadata,
    _compiled_step_with_context_read_authority,
    _context_preflight_block_result,
    _hash_authorized_refs,
    _next_context_feed_refs,
    _next_context_thrash_diagnostics_refs,
    _rewrite_context_package_permission_hash,
    _token_estimates_for_authorized_refs,
    _write_context_engine_records,
)
from .context_reduction_runtime import _maybe_reduce_context_before_provider_turn
from .extensions import ExtensionInstaller, prepare_extension_lock
from .io import (
    hash_refs,
    list_refs,
    read_json_ref,
    ref_exists,
    write_json_ref,
    write_jsonl_ref,
)
from .projections import ProjectionProjector, ProjectionRunResult, run_projections
from .results import FlowRunResult, StepRunResult
from .routing import route_value_for_step
from .runtime_store import (
    _adapter_workspace_for_run,
    _extension_workspace_for_run,
    _looks_like_ref_store,
    _record_store_for_run,
    _requires_extension_lock_filesystem_boundary,
    _validate_extension_lock_store_boundary,
)


@dataclass(frozen=True)
class _PiWorkerAttemptResult:
    call_result: PiWorkerCallResult
    attempt_call_refs: list[str]
    attempt_result_refs: list[str]


FlowEventSink = Callable[[FlowLedgerEvent], None]


@dataclass
class _RunObservationRecorder:
    workspace: Any
    events_ref: str
    run_id: str
    count: int = 0
    latest_event_id: str = ""

    def emit(
        self,
        *,
        kind: RunEventKind,
        status: str = "",
        step_id: str = "",
        role: str = "",
        refs: list[str] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        self.count += 1
        self.latest_event_id = f"{self.count:06d}-{kind.value}"
        _append_run_observation_event(
            self.workspace,
            events_ref=self.events_ref,
            run_id=self.run_id,
            sequence=self.count,
            kind=kind,
            status=status,
            step_id=step_id,
            role=role,
            refs=refs or [],
            metadata=metadata or {},
        )


def run_step(
    step: Step,
    *,
    context: StepCompileContext,
    workspace: str | Path | None = None,
    store: RefStore | None = None,
    adapter: PiWorkerCallAdapter | None = None,
    piworker_config: Any | None = None,
    runner: Any | None = None,
    evidence_store: EvidenceLedger | None = None,
    toolsets: Mapping[str, Toolset] | None = None,
    artifacts: Mapping[str, Artifact] | None = None,
    extension_lock_ref: str | None = None,
    extension_lock_mode: str = "verify-installed",
    extension_installer: ExtensionInstaller | None = None,
    extension_install_root_ref: str = ".missionforge/extensions",
    extension_lock_compiled_at: str | None = None,
    resume: bool = True,
    runtime_progress_sink: PiWorkerProgressSink | None = None,
) -> StepRunResult:
    """Compile, persist, and execute one Kernel Step through PiWorker."""

    record_store = _record_store_for_run(workspace=workspace, store=store)
    adapter_workspace = _adapter_workspace_for_run(workspace=workspace, store=record_store)
    compiled = compile_step(step, context=context, toolsets=toolsets, artifacts=artifacts)
    ref_prefix = context.ref_prefix or f"kernel/{context.flow_id}/steps/{step.id}"
    safe_extension_lock_ref = (
        validate_ref(extension_lock_ref, "kernel_run_step.extension_lock_ref")
        if extension_lock_ref is not None
        else None
    )
    safe_extension_install_root_ref = validate_ref(
        extension_install_root_ref,
        "kernel_run_step.extension_install_root_ref",
    )
    _validate_extension_lock_store_boundary(
        compiled=compiled,
        workspace=workspace,
        store=record_store,
        extension_lock_ref=safe_extension_lock_ref,
    )
    prevalidated_extension_lock = None
    if safe_extension_lock_ref is not None:
        prevalidated_extension_lock = prepare_extension_lock(
            compiled.permission_manifest,
            source_permission_manifest_ref=compiled.permission_manifest_ref,
            workspace=_extension_workspace_for_run(workspace=workspace, store=record_store),
            ref_prefix=ref_prefix,
            extension_lock_ref=safe_extension_lock_ref,
            install_root_ref=safe_extension_install_root_ref,
            mode=extension_lock_mode,
            installer=extension_installer,
            compiled_at=extension_lock_compiled_at,
        )
    step_spec_ref = f"{ref_prefix}/step_spec.json"
    piworker_call_ref = f"{ref_prefix}/piworker_call.json"
    piworker_call_result_ref = f"{ref_prefix}/piworker_call_result.json"
    step_record_ref = f"{ref_prefix}/step_record.json"
    context_projection_ref = f"{ref_prefix}/context_projection.json"

    write_json_ref(record_store, step_spec_ref, step.to_dict())
    base_permission_manifest = compiled.permission_manifest
    write_json_ref(record_store, compiled.permission_manifest_ref, base_permission_manifest.to_dict())
    read_gate = ReadGate(base_permission_manifest)
    input_hashes = _hash_authorized_refs(record_store, step.inputs, read_gate)
    input_token_estimates = _token_estimates_for_authorized_refs(record_store, step.inputs, read_gate)
    base_permission_manifest_hash = stable_json_hash(base_permission_manifest.to_dict())
    context_policy = ContextManagementPolicy.default()
    context_request = _build_context_compile_request(
        compiled=compiled,
        context=context,
        workspace=record_store,
        read_gate=read_gate,
        input_hashes=input_hashes,
        input_token_estimates=input_token_estimates,
        permission_manifest_hash=base_permission_manifest_hash,
    )
    compiled_context = compile_context_request(
        request=context_request,
        read_gate=read_gate,
        view_ref=context_projection_ref,
        pressure_ref=f"{ref_prefix}/context/pressure.json",
        cache_layout_ref=f"{ref_prefix}/context/cache_layout.json",
        result_id=f"{compiled.piworker_call.call_id}-context-compile",
        layout_id=f"{compiled.piworker_call.call_id}-cache-layout",
        soft_ratio=context_policy.soft_pressure_ratio,
        hard_ratio=context_policy.hard_pressure_ratio,
    )
    context_view = compiled_context.view
    context_engine_metadata = _write_context_engine_records(
        workspace=record_store,
        compiled=compiled,
        context=context,
        ref_prefix=ref_prefix,
        context_projection_ref=context_projection_ref,
        compiled_context=compiled_context,
        context_policy=context_policy,
    )
    reduction_attempt = _maybe_reduce_context_before_provider_turn(
        workspace=record_store,
        adapter_workspace=adapter_workspace,
        compiled=compiled,
        context=context,
        ref_prefix=ref_prefix,
        context_projection_ref=context_projection_ref,
        compiled_context=compiled_context,
        context_engine_metadata=context_engine_metadata,
        read_gate=read_gate,
        context_policy=context_policy,
        adapter=adapter,
        piworker_config=piworker_config,
        runner=runner,
        evidence_store=evidence_store,
        runtime_progress_sink=runtime_progress_sink,
    )
    if reduction_attempt is not None:
        compiled_context = reduction_attempt.compiled_context
        context_view = compiled_context.view
        context_engine_metadata = reduction_attempt.context_engine_metadata
    active_context_projection_ref = context_engine_metadata.get("context_projection_ref", context_projection_ref)
    compiled = _compiled_step_with_context_metadata(
        compiled,
        {
            "context_projection_ref": active_context_projection_ref,
            "context_hash": context_view.context_hash,
            "context_feed_refs": list(context.context_feed_refs or []),
            "context_feed_ref_count": len(context.context_feed_refs or []),
            "context_thrash_diagnostics_refs": list(context.context_thrash_diagnostics_refs or []),
            "context_thrash_diagnostics_ref_count": len(context.context_thrash_diagnostics_refs or []),
            "context_policy_hash": context_policy.policy_hash,
            **context_engine_metadata,
            **(reduction_attempt.runtime_metadata if reduction_attempt is not None else {}),
        },
    )
    compiled = _compiled_step_with_context_read_authority(compiled, context_engine_metadata)
    permission_manifest_hash = stable_json_hash(compiled.permission_manifest.to_dict())
    write_json_ref(record_store, compiled.permission_manifest_ref, compiled.permission_manifest.to_dict())
    context_package_ref = context_engine_metadata.get("context_package_ref", "")
    if context_package_ref:
        context_engine_metadata = {
            **dict(context_engine_metadata),
            "context_package_hash": _rewrite_context_package_permission_hash(
                workspace=record_store,
                context_package_ref=context_package_ref,
                permission_manifest_hash=permission_manifest_hash,
            ),
        }
        compiled = _compiled_step_with_context_metadata(
            compiled,
            {"context_package_hash": context_engine_metadata["context_package_hash"]},
        )
    write_json_ref(record_store, piworker_call_ref, compiled.piworker_call.to_dict())
    skip_lock_ref = _expected_extension_lock_ref(
        compiled=compiled,
        ref_prefix=ref_prefix,
        extension_lock_ref=safe_extension_lock_ref,
    )
    skip_lock_hash = _existing_extension_lock_hash(record_store, skip_lock_ref)

    if resume:
        skipped = _skip_result_if_current(
            workspace=record_store,
            compiled=compiled,
            step_record_ref=step_record_ref,
            step_spec_ref=step_spec_ref,
            piworker_call_ref=piworker_call_ref,
            piworker_call_result_ref=piworker_call_result_ref,
            input_hashes=input_hashes,
            permission_manifest_hash=permission_manifest_hash,
            context_projection_ref=active_context_projection_ref,
            context_hash=context_view.context_hash,
            context_engine_metadata=context_engine_metadata,
            extension_lock_ref=skip_lock_ref,
            extension_lock_hash=skip_lock_hash,
        )
        if skipped is not None:
            return skipped

    preflight_block = _context_preflight_block_result(
        workspace=record_store,
        compiled=compiled,
        context=context,
        ref_prefix=ref_prefix,
        piworker_call_ref=piworker_call_ref,
        piworker_call_result_ref=piworker_call_result_ref,
        step_record_ref=step_record_ref,
        step_spec_ref=step_spec_ref,
        input_hashes=input_hashes,
        permission_manifest_hash=permission_manifest_hash,
        context_projection_ref=active_context_projection_ref,
        context_view=context_view,
        context_engine_metadata=context_engine_metadata,
    )
    if preflight_block is not None:
        return preflight_block

    extension_lock = prevalidated_extension_lock or prepare_extension_lock(
        compiled.permission_manifest,
        source_permission_manifest_ref=compiled.permission_manifest_ref,
        workspace=_extension_workspace_for_run(workspace=workspace, store=record_store),
        ref_prefix=ref_prefix,
        extension_lock_ref=safe_extension_lock_ref,
        install_root_ref=safe_extension_install_root_ref,
        mode=extension_lock_mode,
        installer=extension_installer,
        compiled_at=extension_lock_compiled_at,
    )
    attempt_result = _run_piworker_with_failure_policy(
        compiled=compiled,
        context=context,
        workspace=record_store,
        adapter_workspace=adapter_workspace,
        adapter=adapter,
        piworker_config=piworker_config,
        runner=runner,
        evidence_store=evidence_store,
        extension_lock_ref=extension_lock.extension_lock_ref,
        ref_prefix=ref_prefix,
        step_record_ref=step_record_ref,
        runtime_progress_sink=runtime_progress_sink,
    )
    call_result = attempt_result.call_result
    write_json_ref(record_store, piworker_call_result_ref, call_result.to_dict())
    provider_input_hashes = dict(input_hashes)
    post_turn_context = _write_post_turn_context_package(
        workspace=record_store,
        compiled=compiled,
        context=context,
        ref_prefix=ref_prefix,
        context_policy=context_policy,
    )
    if post_turn_context is not None:
        context_engine_metadata = {
            **dict(context_engine_metadata),
            "post_turn_context_projection_ref": post_turn_context["metadata"].get("context_projection_ref", ""),
            "post_turn_context_hash": post_turn_context["context_view"].context_hash,
            "post_turn_context_compile_result_ref": post_turn_context["metadata"].get("context_compile_result_ref", ""),
            "post_turn_context_package_ref": post_turn_context["metadata"].get("context_package_ref", ""),
            "post_turn_context_package_hash": post_turn_context["metadata"].get("context_package_hash", ""),
            "post_turn_context_package_phase": "post_turn",
        }
        input_hashes = post_turn_context["input_hashes"]

    step_record = StepRecord(
        step_id=step.id,
        step_spec_hash=step.spec_hash,
        contract_ref=context.contract_ref,
        contract_hash=context.contract_hash,
        input_refs=list(step.inputs),
        output_refs=list(call_result.output_refs),
        status=_step_status_from_call_result(call_result.status, step.failure.on_exhausted),
        permission_manifest_ref=compiled.permission_manifest_ref,
        permission_manifest_hash=permission_manifest_hash,
        extension_lock_ref=extension_lock.extension_lock_ref,
        extension_lock_hash=extension_lock.extension_lock_hash,
        input_hashes=input_hashes,
        output_hashes=hash_refs(record_store, call_result.output_refs),
        piworker_call_ref=piworker_call_ref,
        piworker_call_result_ref=piworker_call_result_ref,
        execution_report_ref=call_result.execution_report_ref,
        metric_refs=list(call_result.metric_refs),
        failure_refs=_failure_refs_from_call_result(call_result),
        metadata={
            "kernel_flow_id": context.flow_id,
            "expected_output_refs": list(step.outputs),
            "failure_policy": step.failure.to_dict(),
            "attempt_count": len(attempt_result.attempt_result_refs),
            "attempt_call_refs": list(attempt_result.attempt_call_refs),
            "attempt_result_refs": list(attempt_result.attempt_result_refs),
            "final_attempt_result_ref": attempt_result.attempt_result_refs[-1],
            "retry_exhausted": call_result.status != PiWorkerCallResultStatus.COMPLETED,
            "runtime_refs": list(call_result.runtime_refs),
            "evidence_refs": list(call_result.evidence_refs),
            "context_feed_refs": list(context.context_feed_refs or []),
            "context_projection_ref": active_context_projection_ref,
            "context_hash": context_view.context_hash,
            "provider_input_hashes": provider_input_hashes,
            **context_engine_metadata,
            **(reduction_attempt.runtime_metadata if reduction_attempt is not None else {}),
            **_call_result_diagnostic_metadata(call_result),
        },
    )
    write_json_ref(record_store, step_record_ref, step_record.to_dict())
    result = StepRunResult(
        compiled=compiled,
        call_result=call_result,
        step_record=step_record,
        step_spec_ref=step_spec_ref,
        piworker_call_ref=piworker_call_ref,
        piworker_call_result_ref=piworker_call_result_ref,
        step_record_ref=step_record_ref,
        store=record_store,
    )
    result.validate()
    return result


































































def _run_piworker_with_failure_policy(
    *,
    compiled: CompiledStep,
    context: StepCompileContext,
    workspace: Any,
    adapter_workspace: Any,
    adapter: PiWorkerCallAdapter | None,
    piworker_config: Any | None,
    runner: Any | None,
    evidence_store: EvidenceLedger | None,
    extension_lock_ref: str | None,
    ref_prefix: str,
    step_record_ref: str,
    runtime_progress_sink: PiWorkerProgressSink | None,
) -> _PiWorkerAttemptResult:
    max_attempts = compiled.step.failure.retries + 1
    attempt_call_refs: list[str] = []
    attempt_result_refs: list[str] = []
    final_result: PiWorkerCallResult | None = None
    for attempt_index in range(1, max_attempts + 1):
        attempt_call = _attempt_call(compiled, attempt_index=attempt_index, max_attempts=max_attempts)
        attempt_call_ref = f"{ref_prefix}/attempts/{attempt_index:03d}/piworker_call.json"
        attempt_ref = f"{ref_prefix}/attempts/{attempt_index:03d}/piworker_call_result.json"
        result_id = f"{context.flow_id}-{compiled.step.id}-result"
        if max_attempts > 1:
            result_id = f"{context.flow_id}-{compiled.step.id}-attempt-{attempt_index:03d}-result"
        write_json_ref(workspace, attempt_call_ref, attempt_call.to_dict())
        call_result = run_piworker_call(
            attempt_call,
            workspace=adapter_workspace,
            store=workspace,
            adapter=adapter,
            piworker_config=piworker_config,
            runner=runner,
            evidence_store=evidence_store,
            extension_lock_ref=extension_lock_ref,
            result_id=result_id,
            metadata={
                "kernel_flow_id": context.flow_id,
                "kernel_step_id": compiled.step.id,
                "kernel_step_record_ref": step_record_ref,
                "attempt_index": attempt_index,
                "max_attempts": max_attempts,
            },
            runtime_progress_sink=runtime_progress_sink,
        )
        call_result = _validate_attempt_output_boundary(
            call_result,
            call=attempt_call,
            workspace=workspace,
            validation_report_ref=f"{ref_prefix}/attempts/{attempt_index:03d}/output_validation.json",
        )
        write_json_ref(workspace, attempt_ref, call_result.to_dict())
        attempt_call_refs.append(attempt_call_ref)
        attempt_result_refs.append(attempt_ref)
        final_result = call_result
        if call_result.status == PiWorkerCallResultStatus.COMPLETED:
            break
        if _call_result_has_non_retryable_provider_error(call_result):
            break
    if final_result is None:
        raise ContractValidationError("kernel step did not produce a PiWorker call result")
    return _PiWorkerAttemptResult(
        call_result=_normalize_attempt_result(final_result, compiled=compiled, attempt_result_refs=attempt_result_refs),
        attempt_call_refs=attempt_call_refs,
        attempt_result_refs=attempt_result_refs,
    )


def _call_result_has_non_retryable_provider_error(result: PiWorkerCallResult) -> bool:
    value = result.metadata.get("non_retryable_provider_error")
    if isinstance(value, bool):
        return value
    summary = result.metadata.get("failure_summary")
    if not isinstance(summary, str):
        return False
    normalized = summary.lower()
    return (
        "openai api error (401)" in normalized
        or "openai api error (403)" in normalized
        or "authentication" in normalized
        or "authorization" in normalized
        or "api key" in normalized
        or "quota" in normalized
        or "insufficient_quota" in normalized
        or "余额不足" in normalized
    )


def _call_result_diagnostic_metadata(result: PiWorkerCallResult) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    failure_summary = result.metadata.get("failure_summary")
    if isinstance(failure_summary, str) and failure_summary:
        metadata["failure_summary"] = failure_summary
    non_retryable = result.metadata.get("non_retryable_provider_error")
    if isinstance(non_retryable, bool):
        metadata["non_retryable_provider_error"] = non_retryable
    return metadata


def _validate_attempt_output_boundary(
    result: PiWorkerCallResult,
    *,
    call: PiWorkerCall,
    workspace: Any,
    validation_report_ref: str,
) -> PiWorkerCallResult:
    if result.status != PiWorkerCallResultStatus.COMPLETED:
        return result
    missing_expected = [ref for ref in call.expected_output_refs if not ref_exists(workspace, ref)]
    missing_reported = [ref for ref in result.output_refs if not ref_exists(workspace, ref)]
    if not missing_expected and not missing_reported:
        return result
    report = {
        "schema_version": "kernel_output_validation.v1",
        "status": "invalid_output",
        "call_id": call.call_id,
        "expected_output_refs": list(call.expected_output_refs),
        "reported_output_refs": list(result.output_refs),
        "missing_expected_output_refs": missing_expected,
        "missing_reported_output_refs": missing_reported,
    }
    write_json_ref(workspace, validation_report_ref, report)
    invalid = replace(
        result,
        status=PiWorkerCallResultStatus.INVALID_OUTPUT,
        output_refs=[ref for ref in result.output_refs if ref_exists(workspace, ref)],
        validation_report_ref=validation_report_ref,
        metadata={
            **dict(result.metadata),
            "kernel_output_validation_ref": validation_report_ref,
            "missing_expected_output_refs": missing_expected,
            "missing_reported_output_refs": missing_reported,
        },
    )
    invalid.validate_against_call(call)
    return invalid


def _attempt_call(compiled: CompiledStep, *, attempt_index: int, max_attempts: int):
    if max_attempts == 1:
        return compiled.piworker_call
    parent_metadata = dict(compiled.piworker_call.metadata)
    context_metadata = _attempt_context_boundary_metadata(
        parent_metadata,
        parent_call_id=compiled.piworker_call.call_id,
    )
    return replace(
        compiled.piworker_call,
        call_id=f"{compiled.piworker_call.call_id}-attempt-{attempt_index:03d}",
        metadata={
            **parent_metadata,
            "kernel_parent_call_id": compiled.piworker_call.call_id,
            "attempt_index": attempt_index,
            "max_attempts": max_attempts,
            **context_metadata,
        },
    )


def _attempt_context_boundary_metadata(metadata: Mapping[str, Any], *, parent_call_id: str) -> dict[str, Any]:
    if not metadata.get("context_compile_result_ref"):
        return {}
    return {
        "context_boundary_reuse": "same_preflight_boundary",
        "context_parent_call_id": parent_call_id,
        "context_parent_compile_result_ref": metadata["context_compile_result_ref"],
        "context_parent_turn_boundary_ref": metadata.get("context_turn_boundary_ref", ""),
        "context_parent_epoch_ref": metadata.get("context_epoch_ref", ""),
    }


def _context_feed_metadata_refs(metadata: Mapping[str, Any]) -> list[str]:
    value = metadata.get("context_feed_refs")
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        if isinstance(item, str) and item:
            result.append(validate_ref(item, "kernel_context_feed.context_feed_refs[]"))
    return _dedupe_refs(result)


def _normalize_attempt_result(
    result: PiWorkerCallResult,
    *,
    compiled: CompiledStep,
    attempt_result_refs: list[str],
) -> PiWorkerCallResult:
    if result.call_id == compiled.piworker_call.call_id:
        return result
    normalized = replace(
        result,
        result_id=f"{compiled.piworker_call.call_id}-result",
        call_id=compiled.piworker_call.call_id,
        metadata={
            **dict(result.metadata),
            "kernel_parent_call_id": compiled.piworker_call.call_id,
            "final_attempt_call_id": result.call_id,
            "final_attempt_result_ref": attempt_result_refs[-1],
        },
    )
    normalized.validate_against_call(compiled.piworker_call)
    return normalized


def _write_post_turn_context_package(
    *,
    workspace: Any,
    compiled: CompiledStep,
    context: StepCompileContext,
    ref_prefix: str,
    context_policy: ContextManagementPolicy,
) -> dict[str, Any]:
    """Compile a post-provider safe-point package without another model call."""

    read_gate = ReadGate(compiled.permission_manifest)
    input_hashes = _hash_authorized_refs(workspace, compiled.step.inputs, read_gate)
    input_token_estimates = _token_estimates_for_authorized_refs(workspace, compiled.step.inputs, read_gate)
    permission_manifest_hash = stable_json_hash(compiled.permission_manifest.to_dict())
    context_request = _build_context_compile_request(
        compiled=compiled,
        context=context,
        workspace=workspace,
        read_gate=read_gate,
        input_hashes=input_hashes,
        input_token_estimates=input_token_estimates,
        permission_manifest_hash=permission_manifest_hash,
    )
    post_turn_root_ref = f"{ref_prefix}/context/post_turn"
    post_turn_projection_ref = f"{post_turn_root_ref}/context_view.json"
    compiled_context = compile_context_request(
        request=context_request,
        read_gate=read_gate,
        view_ref=post_turn_projection_ref,
        pressure_ref=f"{post_turn_root_ref}/pressure.json",
        cache_layout_ref=f"{post_turn_root_ref}/cache_layout.json",
        result_id=f"{compiled.piworker_call.call_id}-post-turn-context-compile",
        layout_id=f"{compiled.piworker_call.call_id}-post-turn-cache-layout",
        soft_ratio=context_policy.soft_pressure_ratio,
        hard_ratio=context_policy.hard_pressure_ratio,
    )
    metadata = _write_context_engine_records(
        workspace=workspace,
        compiled=compiled,
        context=context,
        ref_prefix=ref_prefix,
        context_projection_ref=post_turn_projection_ref,
        compiled_context=compiled_context,
        context_policy=context_policy,
        context_root_ref=post_turn_root_ref,
    )
    return {
        "metadata": metadata,
        "context_view": compiled_context.view,
        "input_hashes": input_hashes,
    }


def run_flow(
    flow: Flow,
    *,
    context: StepCompileContext,
    workspace: str | Path | None = None,
    store: RefStore | None = None,
    adapter: PiWorkerCallAdapter | None = None,
    piworker_config: Any | None = None,
    runner: Any | None = None,
    evidence_store: EvidenceLedger | None = None,
    max_steps: int | None = None,
    extension_lock_ref: str | None = None,
    extension_lock_mode: str = "verify-installed",
    extension_installer: ExtensionInstaller | None = None,
    extension_install_root_ref: str = ".missionforge/extensions",
    extension_lock_compiled_at: str | None = None,
    resume: bool = True,
    projectors: Mapping[str, ProjectionProjector] | None = None,
    event_sink: FlowEventSink | None = None,
    interaction_port: InteractionPort | None = None,
    runtime_progress_sink: PiWorkerProgressSink | None = None,
) -> FlowRunResult:
    """Execute a Flow through explicit Step boundaries and decision refs."""

    flow.validate()
    context.validate()
    step_by_id = {step.id: step for step in flow.steps}
    artifact_by_ref = {artifact.ref: artifact for artifact in flow.artifacts}
    toolsets = {toolset.id: toolset for toolset in flow.toolsets}
    run_id = context.flow_id
    limit = max_steps if max_steps is not None else max(len(flow.steps) * 2, 1)
    if limit < 1:
        raise KernelValidationError("kernel_flow max_steps must be >= 1")
    record_store = _record_store_for_run(workspace=workspace, store=store)
    safe_extension_lock_ref = (
        validate_ref(extension_lock_ref, "kernel_run_flow.extension_lock_ref")
        if extension_lock_ref is not None
        else None
    )
    safe_extension_install_root_ref = validate_ref(
        extension_install_root_ref,
        "kernel_run_flow.extension_install_root_ref",
    )
    for step in flow.steps:
        _requires_extension_lock_filesystem_boundary(
            step=step,
            context=context,
            toolsets=toolsets,
            artifacts=artifact_by_ref,
            workspace=workspace,
            store=record_store,
            extension_lock_ref=safe_extension_lock_ref,
        )
    if safe_extension_lock_ref is not None:
        for index, step in enumerate(flow.steps, start=1):
            step_context = StepCompileContext(
                flow_id=context.flow_id,
                contract_id=context.contract_id,
                contract_hash=context.contract_hash,
                contract_ref=context.contract_ref,
                workspace_policy_ref=context.workspace_policy_ref,
                denied_refs=context.denied_refs,
                ref_prefix=f"kernel/{context.flow_id}/runs/{run_id}/steps/{index:03d}-{step.id}",
                call_id=f"{context.flow_id}-{index:03d}-{step.id}",
            )
            compiled = compile_step(step, context=step_context, toolsets=toolsets, artifacts=artifact_by_ref)
            if compiled.permission_manifest.extension_grants:
                prepare_extension_lock(
                    compiled.permission_manifest,
                    source_permission_manifest_ref=compiled.permission_manifest_ref,
                    workspace=_extension_workspace_for_run(workspace=workspace, store=record_store),
                    ref_prefix=step_context.ref_prefix or f"kernel/{context.flow_id}/steps/{step.id}",
                    extension_lock_ref=safe_extension_lock_ref,
                    install_root_ref=safe_extension_install_root_ref,
                    mode=extension_lock_mode,
                    installer=extension_installer,
                    compiled_at=extension_lock_compiled_at,
                )
    current = flow.steps[0]
    execution_id = _next_flow_execution_id(record_store, context.flow_id, run_id)
    flow_run_prefix = f"kernel/{context.flow_id}/runs/{run_id}/executions/{execution_id}"
    flow_ledger_ref = f"{flow_run_prefix}/flow_ledger.jsonl"
    flow_result_ref = f"{flow_run_prefix}/flow_result.json"
    run_events_ref = f"{flow_run_prefix}/observation/run_events.jsonl"
    run_snapshot_ref = f"{flow_run_prefix}/observation/run_snapshot.json"
    ledger_events: list[FlowLedgerEvent] = []
    observation = _RunObservationRecorder(workspace=record_store, events_ref=run_events_ref, run_id=run_id)
    observation.emit(
        kind=RunEventKind.RUN_STARTED,
        status="running",
        refs=[context.contract_ref],
        metadata={"max_steps": limit, "flow_execution_id": execution_id},
    )
    _write_kernel_run_snapshot(
        record_store,
        latest_event_id=observation.latest_event_id,
        snapshot_ref=run_snapshot_ref,
        events_ref=run_events_ref,
        run_id=run_id,
        status="running",
        current_step=current,
        interaction_port=interaction_port,
        flow_ledger_ref=flow_ledger_ref,
        flow_result_ref=flow_result_ref,
        step_record_refs=[],
        final_artifact_refs=[],
        last_safe_point_ref="",
        metadata={"flow_execution_id": execution_id, "phase": "started"},
    )
    _append_flow_ledger_event(
        ledger_events,
        _flow_ledger_event(
            "001-started",
            flow=flow,
            run_id=run_id,
            kind=FlowLedgerEventKind.STARTED,
            status="running",
            refs=[context.contract_ref],
            metadata={"max_steps": limit, "flow_execution_id": execution_id},
        ),
        event_sink=event_sink,
    )
    step_results: list[StepRunResult] = []
    step_record_refs: list[str] = []
    decision_refs: list[str] = []
    final_artifact_refs: list[str] = []
    context_projection_refs: list[str] = []
    context_feed_refs: list[str] = []
    context_thrash_diagnostics_refs: list[str] = []
    last_safe_point_ref = ""
    status = "failed"
    stop_reason = "unknown"

    for index in range(1, limit + 1):
        interaction_snapshot_ref = ""
        interaction_snapshot_events: list[UserEvent] = []
        if interaction_port is not None:
            interaction_snapshot_ref, interaction_snapshot_events = _prepare_interaction_snapshot(
                interaction_port=interaction_port,
                run_id=run_id,
                step_id=current.id,
                step_index=index,
                ref_prefix=f"{flow_run_prefix}/interaction/safe_points",
            )
            if interaction_snapshot_ref:
                last_safe_point_ref = interaction_snapshot_ref
            observation.emit(
                kind=RunEventKind.SAFE_POINT_REACHED,
                status="running",
                step_id=current.id,
                role=current.role.value,
                refs=[interaction_snapshot_ref] if interaction_snapshot_ref else [],
                metadata={"step_index": index, "pending_user_event_count": len(interaction_snapshot_events)},
            )
            if interaction_snapshot_events:
                observation.emit(
                    kind=RunEventKind.USER_INTERVENTION_RECEIVED,
                    status="running",
                    step_id=current.id,
                    role=current.role.value,
                    refs=[interaction_snapshot_ref] if interaction_snapshot_ref else [],
                    metadata={
                        "step_index": index,
                        "event_count": len(interaction_snapshot_events),
                        "event_ids": [event.event_id for event in interaction_snapshot_events],
                    },
                )
            _write_kernel_run_snapshot(
                record_store,
                latest_event_id=observation.latest_event_id,
                snapshot_ref=run_snapshot_ref,
                events_ref=run_events_ref,
                run_id=run_id,
                status="running",
                current_step=current,
                interaction_port=interaction_port,
                flow_ledger_ref=flow_ledger_ref,
                flow_result_ref=flow_result_ref,
                step_record_refs=step_record_refs,
                final_artifact_refs=final_artifact_refs,
                context_projection_refs=context_projection_refs,
                last_safe_point_ref=interaction_snapshot_ref,
                metadata={"flow_execution_id": execution_id, "phase": "safe_point", "step_index": index},
            )
            interaction_stop = _interaction_stop_decision(interaction_snapshot_events)
            if interaction_stop is not None:
                status, stop_reason = interaction_stop
                _append_flow_ledger_event(
                    ledger_events,
                    _flow_ledger_event(
                        f"{len(ledger_events) + 1:03d}-interaction",
                        flow=flow,
                        run_id=run_id,
                        kind=FlowLedgerEventKind.INTERACTION_RECORDED,
                        step_id=current.id,
                        status=status,
                        refs=[interaction_snapshot_ref] if interaction_snapshot_ref else [],
                        metadata={
                            "stop_reason": stop_reason,
                            "delivery": "next_safe_point",
                            "event_count": len(interaction_snapshot_events),
                            "event_ids": [event.event_id for event in interaction_snapshot_events],
                        },
                    ),
                    event_sink=event_sink,
                )
                break
        step_context = StepCompileContext(
            flow_id=context.flow_id,
            contract_id=context.contract_id,
            contract_hash=context.contract_hash,
            contract_ref=context.contract_ref,
            workspace_policy_ref=context.workspace_policy_ref,
            denied_refs=context.denied_refs,
            ref_prefix=f"kernel/{context.flow_id}/runs/{run_id}/steps/{index:03d}-{current.id}",
            call_id=f"{context.flow_id}-{index:03d}-{current.id}",
            context_feed_refs=list(context_feed_refs),
            context_thrash_diagnostics_refs=list(context_thrash_diagnostics_refs),
        )
        observation.emit(
            kind=RunEventKind.STEP_COMPILED,
            status="running",
            step_id=current.id,
            role=current.role.value,
            refs=[f"{step_context.ref_prefix}/step_spec.json", f"{step_context.ref_prefix}/permission_manifest.json"],
            metadata={
                "step_index": index,
                "context_feed_ref_count": len(context_feed_refs),
                "context_thrash_diagnostics_ref_count": len(context_thrash_diagnostics_refs),
            },
        )
        _append_flow_ledger_event(
            ledger_events,
            _flow_ledger_event(
                f"{len(ledger_events) + 1:03d}-step-started",
                flow=flow,
                run_id=run_id,
                kind=FlowLedgerEventKind.STEP_STARTED,
                step_id=current.id,
                status="running",
                refs=[*current.inputs, *current.outputs],
                metadata={"step_index": index},
            ),
            event_sink=event_sink,
        )
        executable_step = _step_with_interaction_snapshot(current, interaction_snapshot_ref)
        if interaction_snapshot_ref:
            _append_flow_ledger_event(
                ledger_events,
                _flow_ledger_event(
                    f"{len(ledger_events) + 1:03d}-interaction",
                    flow=flow,
                    run_id=run_id,
                    kind=FlowLedgerEventKind.INTERACTION_RECORDED,
                    step_id=current.id,
                    status="running",
                    refs=[interaction_snapshot_ref],
                    metadata={"step_index": index, "event_count": len(interaction_snapshot_events)},
                ),
                event_sink=event_sink,
            )
        step_result = run_step(
            executable_step,
            context=step_context,
            workspace=None,
            store=record_store,
            adapter=adapter,
            piworker_config=piworker_config,
            runner=runner,
            evidence_store=evidence_store,
            toolsets=toolsets,
            artifacts=artifact_by_ref,
            extension_lock_ref=safe_extension_lock_ref,
            extension_lock_mode=extension_lock_mode,
            extension_installer=extension_installer,
            extension_install_root_ref=safe_extension_install_root_ref,
            extension_lock_compiled_at=extension_lock_compiled_at,
            resume=resume,
            runtime_progress_sink=_runtime_progress_sink_for_step(
                runtime_progress_sink,
                step_id=current.id,
                step_index=index,
            ),
        )
        step_results.append(step_result)
        step_record_refs.append(step_result.step_record_ref)
        final_artifact_refs.extend(step_result.step_record.output_refs)
        context_feed_refs = _next_context_feed_refs(record_store, step_result)
        context_thrash_diagnostics_refs = _next_context_thrash_diagnostics_refs(record_store, step_result)
        context_projection_ref = _metadata_ref(step_result.step_record.metadata, "context_projection_ref")
        if context_projection_ref:
            context_projection_refs.append(context_projection_ref)
            observation.emit(
                kind=RunEventKind.CONTEXT_PROJECTED,
                status=step_result.step_record.status.value,
                step_id=current.id,
                role=current.role.value,
                refs=[context_projection_ref],
                metadata={
                    "step_index": index,
                    "context_hash_ref": context_projection_ref,
                },
            )
        observation.emit(
            kind=RunEventKind.STEP_COMPLETED,
            status=step_result.step_record.status.value,
            step_id=current.id,
            role=current.role.value,
            refs=[step_result.step_record_ref, *step_result.step_record.output_refs],
            metadata={"step_index": index},
        )
        _write_kernel_run_snapshot(
            record_store,
            latest_event_id=observation.latest_event_id,
            snapshot_ref=run_snapshot_ref,
            events_ref=run_events_ref,
            run_id=run_id,
            status="running",
            current_step=current,
            interaction_port=interaction_port,
            flow_ledger_ref=flow_ledger_ref,
            flow_result_ref=flow_result_ref,
            step_record_refs=step_record_refs,
            final_artifact_refs=final_artifact_refs,
            context_projection_refs=context_projection_refs,
            last_safe_point_ref=interaction_snapshot_ref,
            metadata={"flow_execution_id": execution_id, "phase": "step_completed", "step_index": index},
        )
        _append_flow_ledger_event(
            ledger_events,
            _flow_ledger_event(
                f"{len(ledger_events) + 1:03d}-step",
                flow=flow,
                run_id=run_id,
                kind=FlowLedgerEventKind.STEP_RECORDED,
                step_id=current.id,
                status=step_result.step_record.status.value,
                step_record_ref=step_result.step_record_ref,
                refs=[step_result.step_record_ref],
                metadata={"step_index": index},
            ),
            event_sink=event_sink,
        )
        if step_result.step_record.status not in {StepStatus.COMPLETED, StepStatus.SKIPPED}:
            status = step_result.step_record.status.value
            stop_reason = "step_not_completed"
            break
        if interaction_port is not None and interaction_snapshot_events:
            interaction_port.acknowledge(
                interaction_snapshot_events,
                consumed_by=f"{index:03d}-{current.id}",
                snapshot_ref=interaction_snapshot_ref,
                step_record_ref=step_result.step_record_ref,
            )
        if _stop_after_current_turn_requested(interaction_snapshot_events):
            status = "blocked"
            stop_reason = "user_stop_after_current_turn_requested"
            break
        if current.route_on is None:
            status = "completed"
            stop_reason = "step_without_route"
            break
        decision_refs.append(current.route_on)
        try:
            route_value = route_value_for_step(record_store, current)
        except (OSError, json.JSONDecodeError, ContractValidationError, KernelValidationError) as exc:
            status = "blocked"
            stop_reason = "invalid_decision_artifact"
            observation.emit(
                kind=RunEventKind.ROUTE_DECIDED,
                status=status,
                step_id=current.id,
                role=current.role.value,
                refs=[current.route_on],
                metadata={"route_target": "blocked", "route_value": "invalid", "stop_reason": stop_reason},
            )
            _append_flow_ledger_event(
                ledger_events,
                _flow_ledger_event(
                    f"{len(ledger_events) + 1:03d}-routed",
                    flow=flow,
                    run_id=run_id,
                    kind=FlowLedgerEventKind.ROUTED,
                    step_id=current.id,
                    status=status,
                    decision_ref=current.route_on,
                    route_value="invalid",
                    route_target="blocked",
                    refs=[current.route_on],
                    metadata={
                        "route_error_type": type(exc).__name__,
                        "stop_reason": stop_reason,
                    },
                ),
                event_sink=event_sink,
            )
            break
        target = flow.routes.get(f"{current.id}.{route_value}")
        if target is None:
            status = "blocked"
            stop_reason = "unrouted_decision"
            observation.emit(
                kind=RunEventKind.ROUTE_DECIDED,
                status=status,
                step_id=current.id,
                role=current.role.value,
                refs=[current.route_on],
                metadata={"route_target": "unrouted", "route_value": route_value, "stop_reason": stop_reason},
            )
            _append_flow_ledger_event(
                ledger_events,
                _flow_ledger_event(
                    f"{len(ledger_events) + 1:03d}-routed",
                    flow=flow,
                    run_id=run_id,
                    kind=FlowLedgerEventKind.ROUTED,
                    step_id=current.id,
                    status=status,
                    decision_ref=current.route_on,
                    route_value=route_value,
                    route_target="unrouted",
                    refs=[current.route_on],
                ),
                event_sink=event_sink,
            )
            break
        if isinstance(target, FlowStop):
            status = target.status
            stop_reason = "terminal_route"
            observation.emit(
                kind=_terminal_route_event_kind(status),
                status=status,
                step_id=current.id,
                role=current.role.value,
                refs=[current.route_on],
                metadata={"route_target": target.status, "route_value": route_value, "stop_reason": stop_reason},
            )
            _append_flow_ledger_event(
                ledger_events,
                _flow_ledger_event(
                    f"{len(ledger_events) + 1:03d}-routed",
                    flow=flow,
                    run_id=run_id,
                    kind=FlowLedgerEventKind.ROUTED,
                    step_id=current.id,
                    status=status,
                    decision_ref=current.route_on,
                    route_value=route_value,
                    route_target=target.status,
                    refs=[current.route_on],
                ),
                event_sink=event_sink,
            )
            break
        observation.emit(
            kind=RunEventKind.ROUTE_DECIDED,
            status="running",
            step_id=current.id,
            role=current.role.value,
            refs=[current.route_on],
            metadata={"route_target": target, "route_value": route_value},
        )
        _append_flow_ledger_event(
            ledger_events,
            _flow_ledger_event(
                f"{len(ledger_events) + 1:03d}-routed",
                flow=flow,
                run_id=run_id,
                kind=FlowLedgerEventKind.ROUTED,
                step_id=current.id,
                status="running",
                decision_ref=current.route_on,
                route_value=route_value,
                route_target=target,
                refs=[current.route_on],
            ),
            event_sink=event_sink,
        )
        current = step_by_id[target]
    else:
        status = "blocked"
        stop_reason = "max_steps_exhausted"

    projection_results: list[ProjectionRunResult] = []
    projection_record_refs: list[str] = []
    if flow.projections and status not in {"failed", "blocked"}:
        projection_results = run_projections(
            list(flow.projections),
            workspace=record_store,
            projectors=projectors or {},
            record_prefix=f"{flow_run_prefix}/projections",
        )
        final_artifact_refs.extend(result.record.output_ref for result in projection_results)
        projection_record_refs.extend(result.record_ref for result in projection_results)
        _append_flow_ledger_event(
            ledger_events,
            _flow_ledger_event(
                f"{len(ledger_events) + 1:03d}-projections",
                flow=flow,
                run_id=run_id,
                kind=FlowLedgerEventKind.PROJECTIONS_RECORDED,
                status="completed",
                refs=list(projection_record_refs),
                metadata={"projection_count": len(projection_results)},
            ),
            event_sink=event_sink,
        )

    _append_flow_ledger_event(
        ledger_events,
        _flow_ledger_event(
            f"{len(ledger_events) + 1:03d}-stopped",
            flow=flow,
            run_id=run_id,
            kind=FlowLedgerEventKind.STOPPED,
            status=status,
            stop_reason=stop_reason,
            refs=[flow_result_ref, *step_record_refs, *decision_refs],
        ),
        event_sink=event_sink,
    )
    observation.emit(
        kind=RunEventKind.RUN_STOPPED,
        status=status,
        refs=[flow_result_ref, *step_record_refs, *decision_refs],
        metadata={"stop_reason": stop_reason, "flow_execution_id": execution_id},
    )
    _write_kernel_run_snapshot(
        record_store,
        latest_event_id=observation.latest_event_id,
        snapshot_ref=run_snapshot_ref,
        events_ref=run_events_ref,
        run_id=run_id,
        status=_snapshot_status(status, stop_reason),
        current_step=current if status not in {"accepted", "completed"} else None,
        interaction_port=interaction_port,
        flow_ledger_ref=flow_ledger_ref,
        flow_result_ref=flow_result_ref,
        step_record_refs=step_record_refs,
        final_artifact_refs=final_artifact_refs,
        context_projection_refs=context_projection_refs,
        last_safe_point_ref=last_safe_point_ref,
        metadata={"flow_execution_id": execution_id, "phase": "stopped", "stop_reason": stop_reason},
    )
    write_jsonl_ref(record_store, flow_ledger_ref, [event.to_dict() for event in ledger_events])

    flow_result = FlowResult(
        flow_id=flow.id,
        run_id=run_id,
        contract_ref=context.contract_ref,
        contract_hash=context.contract_hash,
        status=status,
        step_record_refs=step_record_refs,
        final_artifact_refs=_dedupe_refs(final_artifact_refs),
        decision_refs=_dedupe_refs(decision_refs),
        ledger_refs=_dedupe_refs([flow_ledger_ref, *projection_record_refs]),
        metadata={
            "max_steps": limit,
            "executed_steps": len(step_results),
            "flow_execution_id": execution_id,
            "projection_count": len(projection_results),
            "context_feed_refs": list(context_feed_refs),
            "context_thrash_diagnostics_refs": list(context_thrash_diagnostics_refs),
            "stop_reason": stop_reason,
            "run_events_ref": run_events_ref,
            "run_snapshot_ref": run_snapshot_ref,
        },
    )
    write_json_ref(record_store, flow_result_ref, flow_result.to_dict())
    result = FlowRunResult(
        flow=flow,
        flow_result=flow_result,
        flow_result_ref=flow_result_ref,
        step_results=step_results,
        projection_results=projection_results,
        store=record_store,
    )
    result.validate()
    return result


def _next_flow_execution_id(workspace: Any, flow_id: str, run_id: str) -> str:
    executions_root_ref = f"kernel/{flow_id}/runs/{run_id}/executions"
    indexes: list[int] = []
    for ref in list_refs(workspace, executions_root_ref):
        suffix = ref.removeprefix(f"{executions_root_ref}/")
        segment = suffix.split("/", 1)[0]
        if segment.isdigit():
            indexes.append(int(segment))
    if not indexes:
        return "001"
    return f"{max(indexes) + 1:03d}"


def _prepare_interaction_snapshot(
    *,
    interaction_port: InteractionPort,
    run_id: str,
    step_id: str,
    step_index: int,
    ref_prefix: str,
) -> tuple[str, list[UserEvent]]:
    events = interaction_port.pending_user_events(run_id=run_id, target=step_id)
    if not events:
        return "", []
    safe_prefix = validate_ref(ref_prefix, "kernel_flow.interaction_snapshot_prefix").rstrip("/")
    ref = f"{safe_prefix}/{step_index:03d}-{step_id}-user_events.json"
    interaction_port.write_pending_projection(
        run_id=run_id,
        target=step_id,
        step_id=step_id,
        ref=ref,
    )
    return ref, events


def _step_with_interaction_snapshot(step: Step, snapshot_ref: str) -> Step:
    if not snapshot_ref:
        return step
    safe_ref = validate_ref(snapshot_ref, "kernel_flow.interaction_snapshot_ref")
    brief = "\n".join(
        [
            step.brief.rstrip(),
            "",
            "User interaction safe-point snapshot:",
            f"- Read `{safe_ref}` before deciding the next action.",
            "- Treat user events as interventions, not task authority.",
            "- Scope, success criteria, or acceptance changes require an explicit contract revision request.",
        ]
    )
    return replace(
        step,
        brief=brief,
        inputs=_dedupe_refs([*step.inputs, safe_ref]),
        read=_dedupe_refs([*step.read, safe_ref]),
    )


def _interaction_stop_decision(events: list[UserEvent]) -> tuple[str, str] | None:
    for event in events:
        if event.kind is UserEventKind.CANCEL_REQUEST and event.delivery in {
            InteractionDelivery.NEXT_SAFE_POINT,
            InteractionDelivery.AFTER_CURRENT_TURN,
            InteractionDelivery.IMMEDIATE_CANCEL,
        }:
            return "blocked", "user_cancel_requested"
        if event.kind is UserEventKind.PAUSE_REQUEST:
            return "blocked", "user_pause_requested"
        if event.kind is UserEventKind.CONTRACT_REVISION_REQUEST:
            return "blocked", "user_contract_revision_requested"
    return None


def _stop_after_current_turn_requested(events: list[UserEvent]) -> bool:
    return any(
        event.kind is UserEventKind.STOP_AFTER_CURRENT_TURN
        and event.delivery in {InteractionDelivery.AFTER_CURRENT_TURN, InteractionDelivery.NEXT_SAFE_POINT}
        for event in events
    )


def _append_run_observation_event(
    workspace: Any,
    *,
    events_ref: str,
    run_id: str,
    sequence: int,
    kind: RunEventKind,
    status: str = "",
    step_id: str = "",
    role: str = "",
    refs: list[str] | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> None:
    event = RunEvent.create(
        event_id=f"{sequence:06d}-{kind.value}",
        run_id=run_id,
        kind=kind,
        status=status,
        step_id=step_id,
        role=role,
        refs=_dedupe_refs(refs or []),
        metadata=metadata or {},
    )
    _append_jsonl_item_ref(workspace, events_ref, event.to_dict())


def _append_jsonl_item_ref(workspace: Any, ref: str, item: Mapping[str, Any]) -> None:
    if isinstance(workspace, (str, Path)):
        FileRefStore(workspace).append_jsonl(ref, item)
        return
    workspace.append_jsonl(ref, item)


def _write_kernel_run_snapshot(
    workspace: Any,
    *,
    snapshot_ref: str,
    events_ref: str,
    run_id: str,
    status: RunSnapshotStatus | str,
    latest_event_id: str,
    current_step: Step | None,
    interaction_port: InteractionPort | None,
    flow_ledger_ref: str,
    flow_result_ref: str,
    step_record_refs: list[str],
    final_artifact_refs: list[str],
    context_projection_refs: list[str] | None = None,
    last_safe_point_ref: str = "",
    metadata: Mapping[str, Any] | None = None,
) -> None:
    pending_count = 0
    if interaction_port is not None and current_step is not None:
        pending_count = len(interaction_port.pending_user_events(run_id=run_id, target=current_step.id))
    snapshot = RunSnapshot(
        run_id=run_id,
        status=status,
        current_step_id=current_step.id if current_step is not None else "",
        current_role=current_step.role.value if current_step is not None else "",
        latest_event_id=latest_event_id,
        latest_event_ref=events_ref,
        flow_ledger_ref=flow_ledger_ref,
        flow_result_ref=flow_result_ref,
        last_safe_point_ref=last_safe_point_ref,
        pending_user_event_count=pending_count,
        step_record_refs=list(step_record_refs),
        context_projection_refs=list(context_projection_refs or []),
        artifact_refs=_dedupe_refs(final_artifact_refs),
        metadata=metadata or {},
    )
    write_json_ref(workspace, snapshot_ref, snapshot.to_dict())


def _snapshot_status(status: str, stop_reason: str = "") -> RunSnapshotStatus:
    if status == "accepted":
        return RunSnapshotStatus.ACCEPTED
    if status == "rejected":
        return RunSnapshotStatus.REJECTED
    if status == "completed":
        return RunSnapshotStatus.COMPLETED
    if status == "failed":
        return RunSnapshotStatus.FAILED
    if status == "blocked":
        if stop_reason == "user_pause_requested":
            return RunSnapshotStatus.PAUSED
        return RunSnapshotStatus.BLOCKED
    return RunSnapshotStatus.RUNNING


def _terminal_route_event_kind(status: str) -> RunEventKind:
    if status == "accepted":
        return RunEventKind.JUDGE_ACCEPTED
    if status == "rejected":
        return RunEventKind.JUDGE_REJECTED
    return RunEventKind.ROUTE_DECIDED


def _metadata_ref(metadata: Mapping[str, Any], key: str) -> str:
    value = metadata.get(key)
    if not isinstance(value, str) or not value:
        return ""
    return validate_ref(value, f"kernel_step_record.metadata.{key}")


def _metadata_refs(metadata: Mapping[str, Any], key: str) -> list[str]:
    value = metadata.get(key)
    if not isinstance(value, list):
        return []
    refs: list[str] = []
    for item in value:
        if isinstance(item, str) and item:
            refs.append(validate_ref(item, f"kernel_step_record.metadata.{key}[]"))
    return _dedupe_refs(refs)


def _append_flow_ledger_event(
    events: list[FlowLedgerEvent],
    event: FlowLedgerEvent,
    *,
    event_sink: FlowEventSink | None,
) -> None:
    event.validate()
    events.append(event)
    if event_sink is not None:
        event_sink(event)


def _runtime_progress_sink_for_step(
    sink: PiWorkerProgressSink | None,
    *,
    step_id: str,
    step_index: int,
) -> PiWorkerProgressSink | None:
    if sink is None:
        return None

    def emit(event: dict[str, Any]) -> None:
        payload = dict(event)
        payload["stage"] = f"kernel_{step_id}_runtime"
        payload["progress_hint"] = f"kernel {step_index}"
        sink(payload)

    return emit


def _flow_ledger_event(
    event_id: str,
    *,
    flow: Flow,
    run_id: str,
    kind: FlowLedgerEventKind,
    step_id: str | None = None,
    status: str | None = None,
    step_record_ref: str | None = None,
    decision_ref: str | None = None,
    route_value: str | None = None,
    route_target: str | None = None,
    stop_reason: str | None = None,
    refs: list[str] | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> FlowLedgerEvent:
    return FlowLedgerEvent(
        event_id=event_id,
        flow_id=flow.id,
        run_id=run_id,
        kind=kind,
        step_id=step_id,
        status=status,
        step_record_ref=step_record_ref,
        decision_ref=decision_ref,
        route_value=route_value,
        route_target=route_target,
        stop_reason=stop_reason,
        refs=_dedupe_refs(refs or []),
        metadata=metadata or {},
    )


def _step_status_from_call_result(status: PiWorkerCallResultStatus, on_exhausted: StepStatus = StepStatus.FAILED) -> StepStatus:
    if status == PiWorkerCallResultStatus.COMPLETED:
        return StepStatus.COMPLETED
    if status == PiWorkerCallResultStatus.BLOCKED:
        return StepStatus.BLOCKED
    return on_exhausted


def _failure_refs_from_call_result(result: PiWorkerCallResult) -> list[str]:
    refs: list[str] = []
    if result.error_ref is not None:
        refs.append(result.error_ref)
    if result.validation_report_ref is not None and result.status != PiWorkerCallResultStatus.COMPLETED:
        refs.append(result.validation_report_ref)
    return refs


def _skip_result_if_current(
    *,
    workspace: Any,
    compiled: CompiledStep,
    step_record_ref: str,
    step_spec_ref: str,
    piworker_call_ref: str,
    piworker_call_result_ref: str,
    input_hashes: Mapping[str, str],
    permission_manifest_hash: str,
    context_projection_ref: str,
    context_hash: str,
    context_engine_metadata: Mapping[str, str],
    extension_lock_ref: str | None,
    extension_lock_hash: str | None,
) -> StepRunResult | None:
    if not ref_exists(workspace, step_record_ref):
        return None
    existing = StepRecord.from_dict(read_json_ref(workspace, step_record_ref))
    if not _can_skip_from_record(
        existing,
        compiled=compiled,
        workspace=workspace,
        input_hashes=input_hashes,
        permission_manifest_hash=permission_manifest_hash,
        extension_lock_ref=extension_lock_ref,
        extension_lock_hash=extension_lock_hash,
    ):
        return None
    if existing.piworker_call_result_ref is None or not ref_exists(workspace, existing.piworker_call_result_ref):
        return None
    call_result = PiWorkerCallResult.from_dict(read_json_ref(workspace, existing.piworker_call_result_ref))
    try:
        call_result.validate_against_call(compiled.piworker_call)
    except ContractValidationError:
        return None
    if existing.status not in {StepStatus.COMPLETED, StepStatus.SKIPPED}:
        expected_outputs = set(compiled.step.outputs)
        if not expected_outputs.issubset(set(call_result.output_refs)):
            return None
    output_hashes = hash_refs(workspace, existing.output_refs)
    record_status_recovered = existing.status not in {StepStatus.COMPLETED, StepStatus.SKIPPED}
    skip_reason = "artifact_boundary_recovered_after_step_failure" if record_status_recovered else "artifact_boundary_current"
    skipped_record = StepRecord(
        step_id=compiled.step.id,
        step_spec_hash=compiled.step.spec_hash,
        contract_ref=compiled.piworker_call.contract_ref,
        contract_hash=compiled.piworker_call.contract_hash,
        input_refs=list(compiled.step.inputs),
        output_refs=list(existing.output_refs),
        status=StepStatus.SKIPPED,
        permission_manifest_ref=compiled.permission_manifest_ref,
        permission_manifest_hash=permission_manifest_hash,
        extension_lock_ref=extension_lock_ref,
        extension_lock_hash=extension_lock_hash,
        input_hashes=dict(input_hashes),
        output_hashes=output_hashes,
        piworker_call_ref=existing.piworker_call_ref or piworker_call_ref,
        piworker_call_result_ref=existing.piworker_call_result_ref,
        execution_report_ref=existing.execution_report_ref,
        metric_refs=list(existing.metric_refs),
        failure_refs=[],
        metadata={
            "kernel_flow_id": compiled.piworker_call.metadata.get("kernel_flow_id", ""),
            "expected_output_refs": list(compiled.step.outputs),
            "skip_reason": skip_reason,
            "resumed_from_step_record_ref": step_record_ref,
            "recovered_from_step_status": existing.status.value if record_status_recovered else "",
            "context_feed_refs": _context_feed_metadata_refs(compiled.piworker_call.metadata),
            "context_projection_ref": context_projection_ref,
            "context_hash": context_hash,
            **dict(context_engine_metadata),
        },
    )
    skipped_record_ref = _skip_record_ref(workspace, step_record_ref)
    write_json_ref(workspace, skipped_record_ref, skipped_record.to_dict())
    result = StepRunResult(
        compiled=compiled,
        call_result=call_result,
        step_record=skipped_record,
        step_spec_ref=step_spec_ref,
        piworker_call_ref=piworker_call_ref,
        piworker_call_result_ref=piworker_call_result_ref,
        step_record_ref=skipped_record_ref,
        store=workspace if _looks_like_ref_store(workspace) else None,
    )
    result.validate()
    return result


def _skip_record_ref(workspace: Any, step_record_ref: str) -> str:
    if step_record_ref.endswith("/step_record.json"):
        prefix = step_record_ref.removesuffix("/step_record.json")
    else:
        prefix = step_record_ref
    reuse_root_ref = f"{prefix}/reuse_records"
    indexes: list[int] = []
    for ref in list_refs(workspace, reuse_root_ref):
        name = ref.removeprefix(f"{reuse_root_ref}/")
        if "/" in name or not name.endswith(".json"):
            continue
        stem = name.removesuffix(".json")
        if stem.isdigit():
            indexes.append(int(stem))
    next_index = max(indexes, default=0) + 1
    return f"{reuse_root_ref}/{next_index:03d}.json"


def _can_skip_from_record(
    record: StepRecord,
    *,
    compiled: CompiledStep,
    workspace: Any,
    input_hashes: Mapping[str, str],
    permission_manifest_hash: str,
    extension_lock_ref: str | None,
    extension_lock_hash: str | None,
) -> bool:
    if record.status not in {StepStatus.COMPLETED, StepStatus.SKIPPED, StepStatus.FAILED, StepStatus.BLOCKED}:
        return False
    if record.step_id != compiled.step.id:
        return False
    if record.step_spec_hash != compiled.step.spec_hash:
        return False
    if record.contract_ref != compiled.piworker_call.contract_ref:
        return False
    if record.contract_hash != compiled.piworker_call.contract_hash:
        return False
    if record.permission_manifest_ref != compiled.permission_manifest_ref:
        return False
    if record.permission_manifest_hash != permission_manifest_hash:
        return False
    if record.extension_lock_ref != extension_lock_ref:
        return False
    if record.extension_lock_hash != extension_lock_hash:
        return False
    if extension_lock_ref is not None and extension_lock_hash is None:
        return False
    if list(record.input_refs) != list(compiled.step.inputs):
        return False
    if dict(record.input_hashes) != dict(input_hashes):
        return False
    expected_outputs = set(compiled.step.outputs)
    if not expected_outputs.issubset(set(record.output_refs)):
        return False
    for ref in expected_outputs:
        if not ref_exists(workspace, ref):
            return False
    output_hashes = hash_refs(workspace, record.output_refs)
    if dict(record.output_hashes) != output_hashes:
        return False
    if record.status not in {StepStatus.COMPLETED, StepStatus.SKIPPED} and not _has_recoverable_route_decision(
        workspace,
        compiled.step,
    ):
        return False
    return True


def _has_recoverable_route_decision(workspace: Any, step: Step) -> bool:
    if step.route_on is None:
        return True
    if not ref_exists(workspace, step.route_on):
        return False
    try:
        route_value_for_step(workspace, step)
    except (OSError, json.JSONDecodeError, ContractValidationError, KernelValidationError):
        return False
    return True


def _expected_extension_lock_ref(
    *,
    compiled: CompiledStep,
    ref_prefix: str,
    extension_lock_ref: str | None,
) -> str | None:
    if extension_lock_ref is not None:
        return validate_ref(extension_lock_ref, "kernel_run_step.extension_lock_ref")
    if compiled.permission_manifest.extension_grants:
        return f"{ref_prefix}/extension_lock.json"
    return None


def _existing_extension_lock_hash(workspace: Any, ref: str | None) -> str | None:
    if ref is None:
        return None
    if not ref_exists(workspace, ref):
        return None
    try:
        return ExtensionLock.from_dict(read_json_ref(workspace, ref)).lock_hash
    except (OSError, json.JSONDecodeError, ContractValidationError):
        return None


def _dedupe_refs(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        ref = validate_ref(value, "kernel_flow.ref")
        if ref not in seen:
            result.append(ref)
            seen.add(ref)
    return result


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
