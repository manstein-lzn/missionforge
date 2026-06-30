"""Managed ContextEngine reduction runtime for Kernel execution."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from typing import Any, Mapping

from ..contracts import ContractValidationError, stable_json_hash
from ..context import ContextCachePolicy, ContextInlinePolicy
from ..context_engine import (
    CompiledContext,
    ContextCompileAction,
    ContextCompileRequest,
    ContextReductionReason,
    ContextReductionRequest,
    ContextReductionResult,
    ContextReductionStatus,
    ContextSource,
    ContextSourceKind,
    compile_context_request,
)
from ..context_policy import ContextManagementPolicy
from ..context_reducer import (
    build_context_reduction_state_transition,
    build_managed_context_reducer_call,
    validate_context_reduction_result_boundary,
)
from ..evidence_store import EvidenceLedger
from ..permissions import ReadGate
from ..piworker_call import PiWorkerCallResultStatus
from ..piworker_progress import PiWorkerProgressSink
from ..piworker_runtime import PiWorkerCallAdapter, run_piworker_call
from .compiler import CompiledStep, StepCompileContext
from .context_runtime import (
    _active_context_thrash_diagnostics_refs,
    _context_reduction_reason,
    _dedupe_refs,
    _write_context_checkpoint_if_needed,
    _write_context_engine_records,
)
from .io import read_json_ref, ref_exists, write_json_ref


@dataclass(frozen=True)
class ContextReductionAttempt:
    compiled_context: CompiledContext
    context_engine_metadata: dict[str, Any]
    runtime_metadata: dict[str, Any]


def _maybe_reduce_context_before_provider_turn(
    *,
    workspace: Any,
    adapter_workspace: Any,
    compiled: CompiledStep,
    context: StepCompileContext,
    ref_prefix: str,
    context_projection_ref: str,
    compiled_context: CompiledContext,
    context_engine_metadata: Mapping[str, str],
    read_gate: ReadGate,
    context_policy: ContextManagementPolicy,
    adapter: PiWorkerCallAdapter | None,
    piworker_config: Any | None,
    runner: Any | None,
    evidence_store: EvidenceLedger | None,
    runtime_progress_sink: PiWorkerProgressSink | None,
) -> ContextReductionAttempt | None:
    thrash_diagnostics_refs = _active_context_thrash_diagnostics_refs(
        workspace,
        list(context.context_thrash_diagnostics_refs or []),
    )
    reduction_reason = _context_reduction_reason(
        compiled_context=compiled_context,
        context_policy=context_policy,
        thrash_diagnostics_refs=thrash_diagnostics_refs,
    )
    if reduction_reason is None:
        return None
    context_engine_metadata = {
        **dict(context_engine_metadata),
        "context_thrash_diagnostics_refs": thrash_diagnostics_refs,
    }
    if not context_engine_metadata.get("context_checkpoint_ref"):
        checkpoint_ref = _write_context_checkpoint_if_needed(
            workspace=workspace,
            compiled=compiled,
            context=context,
            checkpoint_ref=f"{ref_prefix}/context/checkpoint.json",
            context_pressure_ref=context_engine_metadata["context_pressure_ref"],
            source_snapshot_ref=context_engine_metadata["context_source_snapshot_ref"],
            context_projection_ref=context_projection_ref,
            context_view=compiled_context.view,
            compiled_context=compiled_context,
            force_reason_code=reduction_reason.value,
            force_metadata={"context_thrash_diagnostics_refs": thrash_diagnostics_refs},
        )
        if checkpoint_ref:
            context_engine_metadata["context_checkpoint_ref"] = checkpoint_ref
    maintenance_root_ref = f"{ref_prefix}/context/maintenance"
    request_ref = f"{maintenance_root_ref}/reduction_request.json"
    reducer_permission_manifest_ref = f"{maintenance_root_ref}/permission_manifest.json"
    reducer_call_ref = f"{maintenance_root_ref}/piworker_call.json"
    reducer_call_result_ref = f"{maintenance_root_ref}/piworker_call_result.json"
    reduction_result_ref = f"{maintenance_root_ref}/reduction_result.json"
    transition_ref = f"{maintenance_root_ref}/state_transition.json"
    compaction_record_ref = f"{maintenance_root_ref}/compaction_record.json"
    recompiled_root_ref = f"{maintenance_root_ref}/recompiled"
    recompiled_view_ref = f"{recompiled_root_ref}/context_view.json"
    request = _build_context_reduction_request(
        compiled=compiled,
        context=context,
        context_engine_metadata=context_engine_metadata,
        compiled_context=compiled_context,
        request_ref=request_ref,
        reducer_permission_manifest_ref=reducer_permission_manifest_ref,
        maintenance_root_ref=maintenance_root_ref,
        reduction_result_ref=reduction_result_ref,
        reason=reduction_reason,
        thrash_diagnostics_refs=thrash_diagnostics_refs,
    )
    write_json_ref(workspace, request_ref, request.to_dict())
    reducer_call = build_managed_context_reducer_call(
        request=request,
        request_ref=request_ref,
        permission_manifest_ref=reducer_permission_manifest_ref,
        maintenance_root_ref=maintenance_root_ref,
    )
    write_json_ref(workspace, reducer_permission_manifest_ref, reducer_call.permission_manifest.to_dict())
    write_json_ref(workspace, reducer_call_ref, reducer_call.call.to_dict())
    call_result = run_piworker_call(
        reducer_call.call,
        workspace=adapter_workspace,
        store=workspace,
        adapter=adapter,
        piworker_config=piworker_config,
        runner=runner,
        evidence_store=evidence_store,
        result_id=f"{request.reduction_id}-result",
        metadata={
            "kernel_flow_id": context.flow_id,
            "kernel_step_id": compiled.step.id,
            "context_reduction_request_ref": request_ref,
            "context_reduction_reason": request.reason.value,
        },
        runtime_progress_sink=runtime_progress_sink,
    )
    write_json_ref(workspace, reducer_call_result_ref, call_result.to_dict())
    runtime_metadata = {
        "context_reduction_request_ref": request_ref,
        "context_reduction_reason": request.reason.value,
        "context_thrash_diagnostics_refs": thrash_diagnostics_refs,
        "context_reducer_permission_manifest_ref": reducer_permission_manifest_ref,
        "context_reducer_call_ref": reducer_call_ref,
        "context_reducer_call_result_ref": reducer_call_result_ref,
        "context_reduction_input_compile_result_ref": context_engine_metadata["context_compile_result_ref"],
        "context_reduction_input_turn_boundary_ref": context_engine_metadata["context_turn_boundary_ref"],
        "context_reduction_input_checkpoint_ref": context_engine_metadata.get("context_checkpoint_ref", ""),
    }
    if call_result.status is not PiWorkerCallResultStatus.COMPLETED:
        return _failed_context_reduction_attempt(
            workspace=workspace,
            request=request,
            compiled_context=compiled_context,
            request_ref=request_ref,
            reducer_permission_manifest_ref=reducer_permission_manifest_ref,
            result_ref=reduction_result_ref,
            transition_ref=transition_ref,
            compaction_record_ref=compaction_record_ref,
            context_engine_metadata=context_engine_metadata,
            runtime_metadata={
                **runtime_metadata,
                "context_reduction_status": ContextReductionStatus.FAILED.value,
            },
        )
    try:
        result = ContextReductionResult.from_dict(read_json_ref(workspace, reduction_result_ref))
        validate_context_reduction_result_boundary(
            result=result,
            request=request,
            reducer_permission_manifest=reducer_call.permission_manifest,
        )
    except (ContractValidationError, OSError, json.JSONDecodeError) as exc:
        return _failed_context_reduction_attempt(
            workspace=workspace,
            request=request,
            compiled_context=compiled_context,
            request_ref=request_ref,
            reducer_permission_manifest_ref=reducer_permission_manifest_ref,
            result_ref=reduction_result_ref,
            transition_ref=transition_ref,
            compaction_record_ref=compaction_record_ref,
            context_engine_metadata=context_engine_metadata,
            runtime_metadata={
                **runtime_metadata,
                "context_reduction_result_ref": reduction_result_ref,
                "context_reduction_status": ContextReductionStatus.INVALID_OUTPUT.value,
                "context_reduction_error_ref": _write_context_reduction_error(
                    workspace,
                    f"{maintenance_root_ref}/invalid_output.json",
                    request=request,
                    status=ContextReductionStatus.INVALID_OUTPUT,
                    message=str(exc),
                ),
            },
        )
    if result.status is not ContextReductionStatus.COMPLETED:
        return _failed_context_reduction_attempt(
            workspace=workspace,
            request=request,
            compiled_context=compiled_context,
            request_ref=request_ref,
            reducer_permission_manifest_ref=reducer_permission_manifest_ref,
            result_ref=reduction_result_ref,
            transition_ref=transition_ref,
            compaction_record_ref=compaction_record_ref,
            context_engine_metadata=context_engine_metadata,
            runtime_metadata={
                **runtime_metadata,
                "context_reduction_result_ref": reduction_result_ref,
                "context_reduction_status": result.status.value,
            },
        )
    reduction_output_refs = _context_reduction_output_refs(result)
    reduced_request = _context_compile_request_after_reduction(
        compiled_context.request,
        result=result,
        request_ref=request_ref,
    )
    recompile_read_gate = ReadGate(
        replace(
            compiled.permission_manifest,
            readable_refs=_dedupe_refs([*compiled.permission_manifest.readable_refs, *reduction_output_refs]),
        )
    )
    recompiled = compile_context_request(
        request=reduced_request,
        read_gate=recompile_read_gate,
        view_ref=recompiled_view_ref,
        pressure_ref=f"{recompiled_root_ref}/pressure.json",
        cache_layout_ref=f"{recompiled_root_ref}/cache_layout.json",
        result_id=f"{compiled.piworker_call.call_id}-context-compile-after-reduction",
        layout_id=f"{compiled.piworker_call.call_id}-cache-layout-after-reduction",
        soft_ratio=context_policy.soft_pressure_ratio,
        hard_ratio=context_policy.hard_pressure_ratio,
    )
    recompiled_metadata = _write_context_engine_records(
        workspace=workspace,
        compiled=compiled,
        context=context,
        ref_prefix=ref_prefix,
        context_projection_ref=recompiled_view_ref,
        compiled_context=recompiled,
        context_policy=context_policy,
        context_root_ref=recompiled_root_ref,
    )
    if recompiled.result.action is not ContextCompileAction.CONTINUE:
        return _failed_context_reduction_attempt(
            workspace=workspace,
            request=request,
            compiled_context=compiled_context,
            request_ref=request_ref,
            reducer_permission_manifest_ref=reducer_permission_manifest_ref,
            result_ref=reduction_result_ref,
            transition_ref=transition_ref,
            compaction_record_ref=compaction_record_ref,
            context_engine_metadata=context_engine_metadata,
            runtime_metadata={
                **runtime_metadata,
                "context_reduction_result_ref": reduction_result_ref,
                "context_reduction_status": ContextReductionStatus.FAILED.value,
                "context_reduction_recompile_result_ref": recompiled_metadata["context_compile_result_ref"],
            },
        )
    transition = build_context_reduction_state_transition(
        request=request,
        result=result,
        request_ref=request_ref,
        result_ref=reduction_result_ref,
        input_epoch_ref=context_engine_metadata["context_epoch_ref"],
        input_context_view_ref=context_projection_ref,
        output_epoch_ref=recompiled_metadata["context_epoch_ref"],
        output_context_view_ref=recompiled_view_ref,
        permission_manifest_ref=reducer_permission_manifest_ref,
    )
    write_json_ref(workspace, transition_ref, _context_reduction_transition_payload(transition))
    if transition.compaction_record is not None:
        write_json_ref(workspace, compaction_record_ref, transition.compaction_record.to_dict())
    return ContextReductionAttempt(
        compiled_context=recompiled,
        context_engine_metadata={
            **recompiled_metadata,
            "context_reduction_request_ref": request_ref,
            "context_reducer_permission_manifest_ref": reducer_permission_manifest_ref,
            "context_reducer_call_ref": reducer_call_ref,
            "context_reducer_call_result_ref": reducer_call_result_ref,
            "context_reduction_result_ref": reduction_result_ref,
            "context_reduction_transition_ref": transition_ref,
            "context_compaction_record_ref": compaction_record_ref,
            "context_reduction_input_compile_result_ref": context_engine_metadata["context_compile_result_ref"],
            "context_reduction_input_turn_boundary_ref": context_engine_metadata["context_turn_boundary_ref"],
            "context_reduction_input_checkpoint_ref": context_engine_metadata.get("context_checkpoint_ref", ""),
            "context_reduction_output_refs": reduction_output_refs,
            "context_reduction_reason": request.reason.value,
            "context_thrash_diagnostics_refs": thrash_diagnostics_refs,
            "context_compile_action": recompiled.result.action.value,
        },
        runtime_metadata={
            **runtime_metadata,
            "context_reduction_result_ref": reduction_result_ref,
            "context_reduction_transition_ref": transition_ref,
            "context_compaction_record_ref": compaction_record_ref,
            "context_reduction_output_refs": reduction_output_refs,
            "context_reduction_status": result.status.value,
            "context_reduction_recompiled": True,
        },
    )


def _build_context_reduction_request(
    *,
    compiled: CompiledStep,
    context: StepCompileContext,
    context_engine_metadata: Mapping[str, str],
    compiled_context: CompiledContext,
    request_ref: str,
    reducer_permission_manifest_ref: str,
    maintenance_root_ref: str,
    reduction_result_ref: str,
    reason: ContextReductionReason,
    thrash_diagnostics_refs: list[str],
) -> ContextReductionRequest:
    source_refs = _dedupe_refs(
        [
            ref
            for source in compiled_context.request.context_sources
            for ref in source.source_refs
        ]
    )
    recent_projection_refs = _dedupe_refs(
        [
            source.projection_ref
            for source in compiled_context.request.context_sources
            if source.projection_ref
        ]
    )
    expected_output_refs = _dedupe_refs(
        [
            reduction_result_ref,
            f"{maintenance_root_ref}/checkpoint.json",
            f"{maintenance_root_ref}/working_set.json",
            f"{maintenance_root_ref}/summary.json",
            f"{maintenance_root_ref}/validation_report.json",
            f"{maintenance_root_ref}/compaction_record.json",
        ]
    )
    return ContextReductionRequest(
        reduction_id=f"{compiled.piworker_call.call_id}-context-reduction",
        reason=reason,
        role=compiled.piworker_call.role.value,
        contract_ref=compiled.piworker_call.contract_ref,
        contract_hash=compiled.piworker_call.contract_hash,
        permission_manifest_ref=compiled.permission_manifest_ref,
        context_view_ref=context_engine_metadata["context_compile_result_ref"]
        and context_engine_metadata["context_projection_ref"],
        context_hash=compiled_context.view.context_hash,
        source_snapshot_ref=context_engine_metadata["context_source_snapshot_ref"],
        expected_output_refs=expected_output_refs,
        pressure_ref=context_engine_metadata.get("context_pressure_ref"),
        current_working_set_ref=compiled_context.request.working_set_ref,
        thrash_diagnostics_refs=_dedupe_refs(thrash_diagnostics_refs),
        recent_projection_refs=recent_projection_refs,
        source_refs=source_refs,
        tool_observation_refs=list(compiled_context.request.tool_observation_refs),
        checkpoint_refs=_dedupe_refs(
            [
                *compiled_context.request.checkpoint_refs,
                *([context_engine_metadata["context_checkpoint_ref"]] if context_engine_metadata.get("context_checkpoint_ref") else []),
            ]
        ),
        metadata={
            "kernel_flow_id": context.flow_id,
            "kernel_step_id": compiled.step.id,
            "context_reduction_request_ref": request_ref,
            "context_policy_ref": context_engine_metadata.get("context_policy_ref", ""),
            "context_reduction_reason": reason.value,
        },
    )


def _context_compile_request_after_reduction(
    request: ContextCompileRequest,
    *,
    result: ContextReductionResult,
    request_ref: str,
) -> ContextCompileRequest:
    result.validate()
    omitted_refs = set(result.omitted_refs) | set(result.evicted_refs)
    sources: list[ContextSource] = []
    for source in request.context_sources:
        filtered_refs = [ref for ref in source.source_refs if ref not in omitted_refs]
        if source.kind is ContextSourceKind.AUTHORITY:
            filtered_refs = list(source.source_refs)
        if not filtered_refs and source.kind is not ContextSourceKind.AUTHORITY:
            continue
        projection_ref = source.projection_ref
        projection_hash = source.projection_hash
        if projection_ref in omitted_refs:
            projection_ref = None
            projection_hash = None
        sources.append(
            replace(
                source,
                source_refs=filtered_refs,
                source_hashes={ref: value for ref, value in source.source_hashes.items() if ref in filtered_refs},
                projection_ref=projection_ref,
                projection_hash=projection_hash,
                token_estimate=0 if set(source.source_refs).issubset(omitted_refs) else source.token_estimate,
                metadata={
                    **dict(source.metadata),
                    "context_reduction_request_ref": request_ref,
                    "context_reduction_omitted": bool(set(source.source_refs) & omitted_refs),
                },
            )
        )
    next_working_set_ref = result.working_set_ref or request.working_set_ref
    if next_working_set_ref and not any(source.source_refs == [next_working_set_ref] for source in sources):
        sources.append(
            ContextSource(
                source_key="context_reduction/working_set",
                kind=ContextSourceKind.WORKING_SET,
                source_refs=[next_working_set_ref],
                cache_policy=ContextCachePolicy.SEMI_STABLE,
                inline_policy=ContextInlinePolicy.REF_ONLY,
                required=False,
                priority=780,
                metadata={
                    "source_kind": "context_reduction_working_set",
                    "context_reduction_request_ref": request_ref,
                },
            )
        )
    for index, summary_ref in enumerate(result.summary_refs):
        sources.append(
            ContextSource(
                source_key=f"context_reduction/summary/{index:03d}",
                kind=ContextSourceKind.SUMMARY,
                source_refs=[summary_ref],
                projection_ref=summary_ref,
                cache_policy=ContextCachePolicy.SEMI_STABLE,
                inline_policy=ContextInlinePolicy.PREVIEW,
                required=False,
                priority=760,
                metadata={
                    "source_kind": "context_reduction_summary",
                    "context_reduction_request_ref": request_ref,
                },
            )
        )
    checkpoint_refs = _dedupe_refs(
        [
            *request.checkpoint_refs,
            *([result.checkpoint_ref] if result.checkpoint_ref else []),
        ]
    )
    return replace(
        request,
        request_id=f"{request.request_id}-after-reduction",
        context_sources=sources,
        working_set_ref=next_working_set_ref,
        summary_refs=_dedupe_refs([*request.summary_refs, *result.summary_refs]),
        checkpoint_refs=checkpoint_refs,
        metadata={
            **dict(request.metadata),
            "context_reduction_request_ref": request_ref,
            "context_reduction_result_status": result.status.value,
        },
    )


def _context_reduction_output_refs(result: ContextReductionResult) -> list[str]:
    result.validate()
    return _dedupe_refs(
        [
            *([result.checkpoint_ref] if result.checkpoint_ref else []),
            *([result.working_set_ref] if result.working_set_ref else []),
            *result.summary_refs,
            *([result.compaction_record_ref] if result.compaction_record_ref else []),
            *([result.validation_report_ref] if result.validation_report_ref else []),
        ]
    )


def _failed_context_reduction_attempt(
    *,
    workspace: Any,
    request: ContextReductionRequest,
    compiled_context: CompiledContext,
    request_ref: str,
    reducer_permission_manifest_ref: str,
    result_ref: str,
    transition_ref: str,
    compaction_record_ref: str,
    context_engine_metadata: Mapping[str, str],
    runtime_metadata: Mapping[str, Any],
) -> ContextReductionAttempt:
    status = ContextReductionStatus(runtime_metadata.get("context_reduction_status", ContextReductionStatus.FAILED.value))
    checkpoint_ref = context_engine_metadata.get("context_checkpoint_ref")
    if not checkpoint_ref:
        return ContextReductionAttempt(
            compiled_context=compiled_context,
            context_engine_metadata=dict(context_engine_metadata),
            runtime_metadata=dict(runtime_metadata),
        )
    if not ref_exists(workspace, result_ref):
        result = ContextReductionResult(
            reduction_id=request.reduction_id,
            status=status,
            request_ref=request_ref,
            permission_manifest_ref=reducer_permission_manifest_ref,
            checkpoint_ref=checkpoint_ref,
            validation_report_ref=runtime_metadata.get("context_reduction_error_ref")
            if isinstance(runtime_metadata.get("context_reduction_error_ref"), str)
            else None,
        )
        write_json_ref(workspace, result_ref, result.to_dict())
    else:
        try:
            result = ContextReductionResult.from_dict(read_json_ref(workspace, result_ref))
        except (ContractValidationError, OSError, json.JSONDecodeError):
            result = ContextReductionResult(
                reduction_id=request.reduction_id,
                status=ContextReductionStatus.INVALID_OUTPUT,
                request_ref=request_ref,
                permission_manifest_ref=reducer_permission_manifest_ref,
                checkpoint_ref=checkpoint_ref,
            )
            write_json_ref(workspace, result_ref, result.to_dict())
    transition = build_context_reduction_state_transition(
        request=request,
        result=result,
        request_ref=request_ref,
        result_ref=result_ref,
        input_epoch_ref=context_engine_metadata["context_epoch_ref"],
        input_context_view_ref=context_engine_metadata["context_projection_ref"],
        permission_manifest_ref=reducer_permission_manifest_ref,
    )
    write_json_ref(workspace, transition_ref, _context_reduction_transition_payload(transition))
    if transition.compaction_record is not None:
        write_json_ref(workspace, compaction_record_ref, transition.compaction_record.to_dict())
    augmented_metadata = {
        **dict(context_engine_metadata),
        **dict(runtime_metadata),
        "context_reduction_request_ref": request_ref,
        "context_reducer_permission_manifest_ref": reducer_permission_manifest_ref,
        "context_reduction_result_ref": result_ref,
        "context_reduction_transition_ref": transition_ref,
        "context_compaction_record_ref": compaction_record_ref,
        "context_reduction_status": result.status.value,
    }
    return ContextReductionAttempt(
        compiled_context=compiled_context,
        context_engine_metadata=augmented_metadata,
        runtime_metadata={
            **dict(runtime_metadata),
            "context_reduction_result_ref": result_ref,
            "context_reduction_transition_ref": transition_ref,
            "context_compaction_record_ref": compaction_record_ref,
            "context_reduction_status": result.status.value,
            "context_reduction_recompiled": False,
        },
    )


def _write_context_reduction_error(
    workspace: Any,
    ref: str,
    *,
    request: ContextReductionRequest,
    status: ContextReductionStatus,
    message: str,
) -> str:
    return write_json_ref(
        workspace,
        ref,
        {
            "schema_version": "missionforge.context_reduction_error.v1",
            "reduction_id": request.reduction_id,
            "status": status.value,
            "message_hash": stable_json_hash({"message": message}),
        },
    )


def _context_reduction_transition_payload(transition: Any) -> dict[str, Any]:
    transition.validate()
    return {
        "schema_version": "missionforge.context_reduction_state_transition.v1",
        "reduction_id": transition.reduction_id,
        "status": transition.status.value,
        "request_ref": transition.request_ref,
        "result_ref": transition.result_ref,
        "input_epoch_ref": transition.input_epoch_ref,
        "input_context_view_ref": transition.input_context_view_ref,
        "output_epoch_ref": transition.output_epoch_ref,
        "output_context_view_ref": transition.output_context_view_ref,
        "checkpoint_ref": transition.checkpoint_ref,
        "working_set_ref": transition.working_set_ref,
        "summary_refs": list(transition.summary_refs or []),
        "compaction_record": transition.compaction_record.to_dict() if transition.compaction_record else None,
    }
