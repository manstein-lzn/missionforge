"""ContextEngine runtime helpers for Kernel execution."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any, Mapping

from ..contracts import ContractValidationError, stable_json_hash, validate_ref
from ..context import ContextCachePolicy, ContextInlinePolicy, ContextPressureAction, ContextView
from ..context_engine import (
    CompiledContext,
    ContextCheckpoint,
    ContextCheckpointCreator,
    ContextCompileAction,
    ContextEpoch,
    ContextCompileRequest,
    ContextPackage,
    ContextReductionReason,
    ContextReductionStatus,
    ContextSource,
    ContextSourceKind,
    ContextSourceSnapshot,
    ContextThrashDiagnostics,
    ContextTurnBoundary,
    ContextTurnBoundaryStatus,
    ContextWorkingSet,
    ContextWorkingSetEntry,
    reconcile_context_epoch,
)
from ..context_policy import ContextManagementPolicy
from ..permissions import ReadGate
from ..piworker_call import PiWorkerCallResult, PiWorkerCallResultStatus
from ..runtime_results import ExecutionReport
from ..tool_projection import ToolOutputProjection
from .compiler import CompiledStep, StepCompileContext
from .contracts import StepRecord, StepStatus
from .io import hash_ref, read_bytes_ref, read_json_ref, ref_exists, write_json_ref
from .results import StepRunResult
from .runtime_store import _looks_like_ref_store


def _dedupe_refs(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        ref = validate_ref(value, "kernel_ref")
        if ref not in seen:
            result.append(ref)
            seen.add(ref)
    return result


def _utc_now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()


def _build_context_compile_request(
    *,
    compiled: CompiledStep,
    context: StepCompileContext,
    workspace: Any,
    read_gate: ReadGate,
    input_hashes: Mapping[str, str],
    input_token_estimates: Mapping[str, int],
    permission_manifest_hash: str,
) -> ContextCompileRequest:
    call = compiled.piworker_call
    role = call.role.value
    sources: list[ContextSource] = [
        ContextSource(
            source_key="authority/contract",
            kind=ContextSourceKind.AUTHORITY,
            source_refs=[call.contract_ref],
            source_hashes={call.contract_ref: call.contract_hash},
            permission_manifest_ref=compiled.permission_manifest_ref,
            cache_policy=ContextCachePolicy.STABLE,
            inline_policy=ContextInlinePolicy.REF_ONLY,
            required=True,
            token_estimate=_source_token_estimate([call.contract_ref], input_token_estimates),
            priority=1000,
            metadata={"role": role},
        ),
    ]
    input_refs = [ref for ref in call.visible_refs if ref != call.contract_ref]
    if input_refs:
        sources.append(
            ContextSource(
                source_key="inputs/visible_refs",
                kind=ContextSourceKind.PRODUCT_STATE,
                source_refs=list(input_refs),
                source_hashes={ref: input_hashes[ref] for ref in input_refs if ref in input_hashes},
                permission_manifest_ref=compiled.permission_manifest_ref,
                cache_policy=ContextCachePolicy.VOLATILE,
                inline_policy=ContextInlinePolicy.REF_ONLY,
                required=True,
                token_estimate=_source_token_estimate(input_refs, input_token_estimates),
                priority=500,
                metadata={"expected_output_refs": list(call.expected_output_refs)},
            )
        )
    working_set_ref = compiled.step.context_working_set_ref
    evidence_refs = [
        ref
        for ref in call.evidence_refs
        if ref not in input_refs and ref != working_set_ref
    ]
    if evidence_refs:
        sources.append(
            ContextSource(
                source_key="evidence/ref_stubs",
                kind=ContextSourceKind.PRODUCT_STATE,
                source_refs=list(evidence_refs),
                permission_manifest_ref=compiled.permission_manifest_ref,
                cache_policy=ContextCachePolicy.VOLATILE,
                inline_policy=ContextInlinePolicy.OMITTED,
                required=False,
                token_estimate=_source_token_estimate(evidence_refs, input_token_estimates),
                priority=300,
            )
        )
    if working_set_ref:
        sources.extend(
            _context_sources_for_working_set(
                workspace=workspace,
                read_gate=read_gate,
                working_set_ref=working_set_ref,
                permission_manifest_ref=compiled.permission_manifest_ref,
            )
        )
    context_feed_refs = _dedupe_refs(list(context.context_feed_refs or []))
    if context_feed_refs:
        sources.extend(
            _context_sources_for_feed_refs(
                workspace=workspace,
                read_gate=read_gate,
                feed_refs=context_feed_refs,
                permission_manifest_ref=compiled.permission_manifest_ref,
            )
        )
    token_budget = _context_token_budget(call.runtime_budget)
    return ContextCompileRequest(
        request_id=f"{call.call_id}-context",
        role=role,
        contract_ref=call.contract_ref,
        contract_hash=call.contract_hash,
        permission_manifest_ref=compiled.permission_manifest_ref,
        context_sources=sources,
        working_set_ref=working_set_ref,
        token_budget=token_budget,
        provider_cache_profile={
            "kernel_flow_id": context.flow_id,
            "kernel_step_id": compiled.step.id,
        },
        metadata={
            "piworker_call_ref": f"kernel/{context.flow_id}/steps/{compiled.step.id}/piworker_call.json"
            if context.ref_prefix is None
            else f"{context.ref_prefix}/piworker_call.json",
            "expected_output_refs": list(call.expected_output_refs),
            "authorized_input_ref_count": len(input_hashes),
            "context_feed_ref_count": len(context_feed_refs),
            "context_thrash_diagnostics_ref_count": len(context.context_thrash_diagnostics_refs or []),
        },
    )


def _hash_authorized_refs(workspace: Any, refs: list[str], read_gate: ReadGate) -> dict[str, str]:
    """Hash only refs that have passed the role read gate."""

    result: dict[str, str] = {}
    for ref in refs:
        safe_ref = validate_ref(ref, "kernel_context.input_ref")
        if not read_gate.check(safe_ref).allowed:
            continue
        result[safe_ref] = hash_ref(workspace, safe_ref)
    return result


def _token_estimates_for_authorized_refs(workspace: Any, refs: list[str], read_gate: ReadGate) -> dict[str, int]:
    estimates: dict[str, int] = {}
    for ref in refs:
        safe_ref = validate_ref(ref, "kernel_context.input_ref")
        if not read_gate.check(safe_ref).allowed:
            continue
        estimates[safe_ref] = _estimate_ref_tokens(workspace, safe_ref)
    return estimates


def _source_token_estimate(refs: list[str], estimates: Mapping[str, int]) -> int:
    return sum(estimates.get(ref, 0) for ref in refs)


def _context_sources_for_working_set(
    *,
    workspace: Any,
    read_gate: ReadGate,
    working_set_ref: str,
    permission_manifest_ref: str,
) -> list[ContextSource]:
    safe_working_set_ref = validate_ref(working_set_ref, "kernel_context.working_set_ref")
    if not read_gate.check(safe_working_set_ref).allowed:
        return [
            ContextSource(
                source_key="working_set/active",
                kind=ContextSourceKind.WORKING_SET,
                source_refs=[safe_working_set_ref],
                permission_manifest_ref=permission_manifest_ref,
                cache_policy=ContextCachePolicy.SEMI_STABLE,
                inline_policy=ContextInlinePolicy.REF_ONLY,
                required=True,
                priority=700,
            )
        ]
    try:
        working_set = ContextWorkingSet.from_dict(read_json_ref(workspace, safe_working_set_ref))
    except (ContractValidationError, OSError, json.JSONDecodeError):
        return [
            ContextSource(
                source_key="working_set/active",
                kind=ContextSourceKind.WORKING_SET,
                source_refs=[safe_working_set_ref],
                permission_manifest_ref=permission_manifest_ref,
                cache_policy=ContextCachePolicy.SEMI_STABLE,
                inline_policy=ContextInlinePolicy.REF_ONLY,
                required=True,
                priority=700,
                metadata={"unavailable": True, "reason_code": "working_set_unavailable"},
            )
        ]
    sources: list[ContextSource] = [
        ContextSource(
            source_key="working_set/index",
            kind=ContextSourceKind.WORKING_SET,
            source_refs=[safe_working_set_ref],
            source_hashes={safe_working_set_ref: hash_ref(workspace, safe_working_set_ref)},
            permission_manifest_ref=permission_manifest_ref,
            cache_policy=ContextCachePolicy.SEMI_STABLE,
            inline_policy=ContextInlinePolicy.REF_ONLY,
            required=True,
            token_estimate=0,
            priority=760,
            metadata={
                "working_set_id": working_set.working_set_id,
                "phase_label": working_set.phase_label,
                "entry_count": len(working_set.entries),
            },
        )
    ]
    for index, entry in enumerate(working_set.entries):
        sources.append(_context_source_for_working_set_entry(entry, permission_manifest_ref=permission_manifest_ref, index=index))
    return sources


def _context_source_for_working_set_entry(
    entry: ContextWorkingSetEntry,
    *,
    permission_manifest_ref: str,
    index: int,
) -> ContextSource:
    entry.validate()
    source_refs = _dedupe_refs([entry.source_ref, entry.projection_ref, *entry.claim_link_refs])
    if entry.why_ref:
        source_refs = _dedupe_refs([*source_refs, entry.why_ref])
    return ContextSource(
        source_key=f"working_set/{index:03d}-{entry.entry_id}",
        kind=ContextSourceKind.WORKING_SET,
        source_refs=source_refs,
        source_hashes={
            entry.source_ref: entry.source_hash,
            entry.projection_ref: entry.projection_hash,
        },
        projection_ref=entry.projection_ref,
        projection_hash=entry.projection_hash,
        permission_manifest_ref=permission_manifest_ref,
        cache_policy=ContextCachePolicy.SEMI_STABLE,
        inline_policy=ContextInlinePolicy.REF_ONLY,
        required=True,
        token_estimate=entry.token_estimate,
        priority=740,
        metadata={
            "entry_id": entry.entry_id,
            "phase_label": entry.phase_label,
            "freshness": entry.freshness.value,
            "pin_policy": entry.pin_policy.value,
            "why_ref": entry.why_ref or "",
            "claim_link_refs": list(entry.claim_link_refs),
        },
    )


def _context_sources_for_feed_refs(
    *,
    workspace: Any,
    read_gate: ReadGate,
    feed_refs: list[str],
    permission_manifest_ref: str,
) -> list[ContextSource]:
    sources: list[ContextSource] = []
    for index, ref in enumerate(feed_refs):
        safe_ref = validate_ref(ref, "kernel_context.feed_ref")
        if not read_gate.check(safe_ref).allowed:
            sources.append(
                ContextSource(
                    source_key=f"context_feed/{index:03d}",
                    kind=ContextSourceKind.TOOL_OBSERVATION,
                    source_refs=[safe_ref],
                    permission_manifest_ref=permission_manifest_ref,
                    cache_policy=ContextCachePolicy.VOLATILE,
                    inline_policy=ContextInlinePolicy.PREVIEW,
                    required=False,
                    priority=360,
                    metadata={"feed_ref_denied": True},
                )
            )
            continue
        try:
            projection = ToolOutputProjection.from_dict(read_json_ref(workspace, safe_ref))
        except (ContractValidationError, OSError, json.JSONDecodeError):
            sources.append(
                ContextSource(
                    source_key=f"context_feed/{index:03d}",
                    kind=ContextSourceKind.TOOL_OBSERVATION,
                    source_refs=[safe_ref],
                    permission_manifest_ref=permission_manifest_ref,
                    cache_policy=ContextCachePolicy.VOLATILE,
                    inline_policy=ContextInlinePolicy.PREVIEW,
                    required=False,
                    priority=360,
                    metadata={"feed_ref_unavailable": True},
                )
            )
            continue
        projection_allowed = read_gate.check(projection.projection_ref).allowed
        source_refs = _dedupe_refs([safe_ref, *([projection.projection_ref] if projection_allowed else [])])
        source_hashes = {
            safe_ref: hash_ref(workspace, safe_ref),
            **({projection.projection_ref: projection.projection_hash} if projection_allowed else {}),
        }
        sources.append(
            ContextSource(
                source_key=f"context_feed/{index:03d}-{projection.projection_id}",
                kind=ContextSourceKind.TOOL_OBSERVATION,
                source_refs=source_refs,
                source_hashes=source_hashes,
                projection_ref=projection.projection_ref if projection_allowed else None,
                projection_hash=projection.projection_hash if projection_allowed else None,
                permission_manifest_ref=permission_manifest_ref,
                cache_policy=ContextCachePolicy.VOLATILE,
                inline_policy=ContextInlinePolicy.PREVIEW,
                required=False,
                token_estimate=_estimate_ref_tokens(workspace, projection.projection_ref) if projection_allowed else 0,
                priority=360,
                metadata={
                    "tool_observation_id": projection.tool_observation_id,
                    "projection_policy": projection.policy.value,
                    "projection_record_ref": safe_ref,
                    "raw_ref": projection.raw_ref or "",
                    "structured_ref": projection.structured_ref or "",
                    "source_kind": "tool_output_projection",
                },
            )
        )
    return sources


def _estimate_ref_tokens(workspace: Any, ref: str) -> int:
    try:
        size = len(read_bytes_ref(workspace, ref))
    except (ContractValidationError, OSError):
        return 0
    return max(1, (size + 3) // 4)


def _context_token_budget(runtime_budget: Mapping[str, Any]) -> int | None:
    value = runtime_budget.get("context_token_budget")
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    value = runtime_budget.get("max_input_tokens")
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    return None


def _next_context_feed_refs(workspace: Any, result: StepRunResult) -> list[str]:
    """Return bounded projection record refs that may feed the next provider turn."""

    index_refs = _tool_output_projection_index_refs(workspace, result)
    feed_refs: list[str] = []
    for index_ref in index_refs:
        try:
            payload = read_json_ref(workspace, index_ref)
        except (ContractValidationError, OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, Mapping):
            continue
        if payload.get("schema_version") != "missionforge.tool_output_projection_index.v1":
            continue
        record_refs = payload.get("record_refs", [])
        if not isinstance(record_refs, list):
            continue
        for ref in record_refs:
            if not isinstance(ref, str):
                continue
            safe_ref = validate_ref(ref, "kernel_context_feed.record_refs[]")
            if ref_exists(workspace, safe_ref):
                feed_refs.append(safe_ref)
    return _dedupe_refs(feed_refs)


def _next_context_thrash_diagnostics_refs(workspace: Any, result: StepRunResult) -> list[str]:
    """Return active repeated-read diagnostics refs for the next provider turn."""

    ref = _metric_context_thrash_diagnostics_ref(workspace, result.step_record.execution_report_ref)
    if not ref:
        return []
    return _active_context_thrash_diagnostics_refs(workspace, [ref])


def _tool_output_projection_index_refs(workspace: Any, result: StepRunResult) -> list[str]:
    refs: list[str] = []
    metric_ref = _metric_tool_projection_index_ref(workspace, result.step_record.execution_report_ref)
    if metric_ref:
        refs.append(metric_ref)
    return _dedupe_refs(refs)


def _metric_tool_projection_index_ref(workspace: Any, execution_report_ref: str | None) -> str:
    if not execution_report_ref:
        return ""
    try:
        report = ExecutionReport.from_dict(read_json_ref(workspace, execution_report_ref))
    except (ContractValidationError, OSError, json.JSONDecodeError):
        return ""
    value = report.metrics.get("tool_output_projection_index_ref")
    if not isinstance(value, str) or not value:
        return ""
    safe_ref = validate_ref(value, "kernel_context_feed.tool_output_projection_index_ref")
    return safe_ref if ref_exists(workspace, safe_ref) else ""


def _metric_context_thrash_diagnostics_ref(workspace: Any, execution_report_ref: str | None) -> str:
    if not execution_report_ref:
        return ""
    try:
        report = ExecutionReport.from_dict(read_json_ref(workspace, execution_report_ref))
    except (ContractValidationError, OSError, json.JSONDecodeError):
        return ""
    value = report.metrics.get("context_thrash_diagnostics_ref")
    if not isinstance(value, str) or not value:
        return ""
    safe_ref = validate_ref(value, "kernel_context_feed.context_thrash_diagnostics_ref")
    return safe_ref if ref_exists(workspace, safe_ref) else ""


def _compiled_step_with_context_metadata(compiled: CompiledStep, metadata: Mapping[str, Any]) -> CompiledStep:
    call = replace(
        compiled.piworker_call,
        metadata={
            **dict(compiled.piworker_call.metadata),
            **dict(metadata),
        },
    )
    updated = replace(compiled, piworker_call=call)
    updated.validate()
    return updated


def _compiled_step_with_context_read_authority(compiled: CompiledStep, metadata: Mapping[str, Any]) -> CompiledStep:
    """Grant the trusted runtime read access to ContextEngine records it must lower."""

    context_refs = _context_engine_metadata_refs({**dict(compiled.piworker_call.metadata), **dict(metadata)})
    if not context_refs:
        return compiled
    permission_manifest = replace(
        compiled.permission_manifest,
        readable_refs=_dedupe_refs([*compiled.permission_manifest.readable_refs, *context_refs]),
    )
    updated = replace(compiled, permission_manifest=permission_manifest)
    updated.validate()
    return updated


def _context_engine_metadata_refs(metadata: Mapping[str, Any]) -> list[str]:
    ref_keys = (
        "context_projection_ref",
        "context_policy_ref",
        "context_compile_request_ref",
        "context_baseline_ref",
        "context_source_snapshot_ref",
        "context_epoch_ref",
        "context_cache_layout_ref",
        "context_pressure_ref",
        "context_checkpoint_ref",
        "context_turn_safe_point_ref",
        "context_turn_boundary_ref",
        "context_compile_result_ref",
        "context_package_ref",
        "context_reduction_request_ref",
        "context_reducer_permission_manifest_ref",
        "context_reducer_call_ref",
        "context_reducer_call_result_ref",
        "context_reduction_result_ref",
        "context_reduction_transition_ref",
        "context_compaction_record_ref",
        "context_reduction_error_ref",
        "context_reduction_recompile_result_ref",
        "context_reduction_input_compile_result_ref",
        "context_reduction_input_turn_boundary_ref",
        "context_reduction_input_checkpoint_ref",
    )
    refs: list[str] = []
    for key in ref_keys:
        value = metadata.get(key)
        if isinstance(value, str) and value:
            refs.append(validate_ref(value, f"kernel_context_engine.{key}"))
    list_ref_keys = (
        "context_reduction_output_refs",
        "context_thrash_diagnostics_refs",
    )
    for key in list_ref_keys:
        value = metadata.get(key)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, str) and item:
                    refs.append(validate_ref(item, f"kernel_context_engine.{key}[]"))
    return _dedupe_refs(refs)


def _active_context_thrash_diagnostics_refs(workspace: Any, refs: list[str]) -> list[str]:
    active: list[str] = []
    for ref in _dedupe_refs(list(refs)):
        if not ref_exists(workspace, ref):
            continue
        try:
            diagnostics = ContextThrashDiagnostics.from_dict(read_json_ref(workspace, ref))
        except (ContractValidationError, OSError, json.JSONDecodeError):
            continue
        if (
            diagnostics.recommended_action is not ContextPressureAction.CONTINUE
            and diagnostics.repeated_observation_ids
        ):
            active.append(ref)
    return _dedupe_refs(active)


def _context_reduction_reason(
    *,
    compiled_context: CompiledContext,
    context_policy: ContextManagementPolicy,
    thrash_diagnostics_refs: list[str],
) -> ContextReductionReason | None:
    if not (context_policy.reducer_enabled and context_policy.max_reducer_attempts > 0):
        return None
    if compiled_context.result.action is ContextCompileAction.CHECKPOINT_BEFORE_NEXT_TURN:
        return ContextReductionReason.PRESSURE_HARD if context_policy.reducer_on_hard_pressure else None
    if thrash_diagnostics_refs and context_policy.reducer_on_thrashing:
        return ContextReductionReason.REPEATED_READ_THRASHING
    return None


def _write_context_checkpoint_if_needed(
    *,
    workspace: Any,
    compiled: CompiledStep,
    context: StepCompileContext,
    checkpoint_ref: str,
    context_pressure_ref: str,
    source_snapshot_ref: str,
    context_projection_ref: str,
    context_view: ContextView,
    compiled_context: CompiledContext,
    force_reason_code: str = "",
    force_metadata: Mapping[str, Any] | None = None,
) -> str:
    action = compiled_context.result.action
    pressure_action = compiled_context.pressure.recommended_action
    if (
        not force_reason_code
        and action not in {ContextCompileAction.PREPARE_CHECKPOINT, ContextCompileAction.CHECKPOINT_BEFORE_NEXT_TURN}
    ):
        return ""
    reason_code = (
        force_reason_code
        or (
            "pressure_hard"
            if pressure_action is ContextPressureAction.CHECKPOINT_BEFORE_NEXT_TURN
            else "pressure_soft"
        )
    )
    refs = _dedupe_refs(
        [
            *compiled_context.result.admitted_update_refs,
            *compiled_context.request.summary_refs,
            *compiled_context.request.checkpoint_refs,
        ]
    )
    checkpoint = ContextCheckpoint(
        checkpoint_id=f"{compiled.piworker_call.call_id}-context-checkpoint",
        reason_code=reason_code,
        role=compiled.piworker_call.role.value,
        run_id=context.flow_id,
        call_id=compiled.piworker_call.call_id,
        source_snapshot_ref=source_snapshot_ref,
        context_view_ref=context_projection_ref,
        context_hash=context_view.context_hash,
        summary_refs=list(compiled_context.request.summary_refs),
        recent_refs=refs,
        tool_observation_refs=list(compiled_context.request.tool_observation_refs),
        permission_manifest_ref=compiled.permission_manifest_ref,
        created_by=ContextCheckpointCreator.RUNTIME,
        metadata={
            "pressure_action": pressure_action.value,
            "context_compile_action": action.value,
            "context_pressure_ref": context_pressure_ref,
            **dict(force_metadata or {}),
        },
        created_at=_utc_now(),
    )
    write_json_ref(workspace, checkpoint_ref, checkpoint.to_dict())
    return checkpoint_ref


def _context_preflight_block_result(
    *,
    workspace: Any,
    compiled: CompiledStep,
    context: StepCompileContext,
    ref_prefix: str,
    piworker_call_ref: str,
    piworker_call_result_ref: str,
    step_record_ref: str,
    step_spec_ref: str,
    input_hashes: Mapping[str, str],
    permission_manifest_hash: str,
    context_projection_ref: str,
    context_view: ContextView,
    context_engine_metadata: Mapping[str, str],
) -> StepRunResult | None:
    action = context_engine_metadata.get("context_compile_action")
    reduction_status = context_engine_metadata.get("context_reduction_status")
    reduction_blocks = reduction_status in {
        ContextReductionStatus.FAILED.value,
        ContextReductionStatus.INVALID_OUTPUT.value,
    }
    if action not in {
        ContextCompileAction.BLOCKED_BY_DENIED_REQUIRED_SOURCE.value,
        ContextCompileAction.BLOCKED_BY_UNAVAILABLE_AUTHORITY.value,
        ContextCompileAction.CHECKPOINT_BEFORE_NEXT_TURN.value,
    } and not reduction_blocks:
        return None
    block_action = action
    if reduction_blocks and action not in {
        ContextCompileAction.BLOCKED_BY_DENIED_REQUIRED_SOURCE.value,
        ContextCompileAction.BLOCKED_BY_UNAVAILABLE_AUTHORITY.value,
        ContextCompileAction.CHECKPOINT_BEFORE_NEXT_TURN.value,
    }:
        block_action = "context_reduction_failed"
    report_ref = f"{ref_prefix}/context/preflight_execution_report.json"
    error_ref = f"{ref_prefix}/context/preflight_block.json"
    context_runtime_refs = _context_engine_metadata_refs(context_engine_metadata)
    report = ExecutionReport(
        report_id=f"{compiled.piworker_call.call_id}-context-preflight",
        call_id=compiled.piworker_call.call_id,
        status="blocked",
        produced_artifacts=[],
        changed_refs=[],
        evidence_refs=_dedupe_refs([
            context_engine_metadata["context_compile_result_ref"],
            context_engine_metadata["context_turn_boundary_ref"],
            *([context_engine_metadata["context_checkpoint_ref"]] if context_engine_metadata.get("context_checkpoint_ref") else []),
            *context_runtime_refs,
        ]),
        worker_claims=[],
        metrics={},
    )
    block_payload = {
        "schema_version": "missionforge.context_preflight_block.v1",
        "call_id": compiled.piworker_call.call_id,
        "action": block_action,
        "context_compile_result_ref": context_engine_metadata["context_compile_result_ref"],
        "context_pressure_ref": context_engine_metadata["context_pressure_ref"],
        "context_checkpoint_ref": context_engine_metadata.get("context_checkpoint_ref", ""),
        "context_turn_boundary_ref": context_engine_metadata["context_turn_boundary_ref"],
        "context_reduction_status": reduction_status or "",
        "context_reduction_result_ref": context_engine_metadata.get("context_reduction_result_ref", ""),
    }
    write_json_ref(workspace, report_ref, report.to_dict())
    write_json_ref(workspace, error_ref, block_payload)
    call_result = PiWorkerCallResult(
        result_id=f"{compiled.piworker_call.call_id}-result",
        call_id=compiled.piworker_call.call_id,
        role=compiled.piworker_call.role,
        contract_id=compiled.piworker_call.contract_id,
        contract_hash=compiled.piworker_call.contract_hash,
        contract_ref=compiled.piworker_call.contract_ref,
        status=PiWorkerCallResultStatus.BLOCKED,
        execution_report_ref=report_ref,
        output_refs=[],
        runtime_refs=_dedupe_refs([
            context_engine_metadata["context_compile_result_ref"],
            context_engine_metadata["context_pressure_ref"],
            *([context_engine_metadata["context_checkpoint_ref"]] if context_engine_metadata.get("context_checkpoint_ref") else []),
            context_engine_metadata["context_turn_boundary_ref"],
            *context_runtime_refs,
        ]),
        evidence_refs=_dedupe_refs([
            context_engine_metadata["context_source_snapshot_ref"],
            *([context_engine_metadata["context_checkpoint_ref"]] if context_engine_metadata.get("context_checkpoint_ref") else []),
            *context_runtime_refs,
        ]),
        error_ref=error_ref,
        metadata={
            "context_compile_action": action,
            "context_preflight_action": block_action,
            "context_reduction_status": reduction_status or "",
            "context_preflight_block_ref": error_ref,
        },
    )
    call_result.validate_against_call(compiled.piworker_call)
    write_json_ref(workspace, piworker_call_result_ref, call_result.to_dict())
    step_record = StepRecord(
        step_id=compiled.step.id,
        step_spec_hash=compiled.step.spec_hash,
        contract_ref=context.contract_ref,
        contract_hash=context.contract_hash,
        input_refs=list(compiled.step.inputs),
        output_refs=[],
        status=StepStatus.BLOCKED,
        permission_manifest_ref=compiled.permission_manifest_ref,
        permission_manifest_hash=permission_manifest_hash,
        input_hashes=dict(input_hashes),
        output_hashes={},
        piworker_call_ref=piworker_call_ref,
        piworker_call_result_ref=piworker_call_result_ref,
        execution_report_ref=report_ref,
        failure_refs=[error_ref],
        metadata={
            "kernel_flow_id": context.flow_id,
            "expected_output_refs": list(compiled.step.outputs),
            "failure_policy": compiled.step.failure.to_dict(),
            "attempt_count": 0,
            "attempt_call_refs": [],
            "attempt_result_refs": [],
            "final_attempt_result_ref": piworker_call_result_ref,
            "retry_exhausted": False,
            "runtime_refs": list(call_result.runtime_refs),
            "evidence_refs": list(call_result.evidence_refs),
            "context_feed_refs": list(context.context_feed_refs or []),
            "context_thrash_diagnostics_refs": list(context.context_thrash_diagnostics_refs or []),
            "context_projection_ref": context_projection_ref,
            "context_hash": context_view.context_hash,
            **dict(context_engine_metadata),
        },
    )
    write_json_ref(workspace, step_record_ref, step_record.to_dict())
    result = StepRunResult(
        compiled=compiled,
        call_result=call_result,
        step_record=step_record,
        step_spec_ref=step_spec_ref,
        piworker_call_ref=piworker_call_ref,
        piworker_call_result_ref=piworker_call_result_ref,
        step_record_ref=step_record_ref,
        store=workspace if _looks_like_ref_store(workspace) else None,
    )
    result.validate()
    return result


def _write_context_engine_records(
    *,
    workspace: Any,
    compiled: CompiledStep,
    context: StepCompileContext,
    ref_prefix: str,
    context_projection_ref: str,
    compiled_context: CompiledContext,
    context_policy: ContextManagementPolicy,
    context_root_ref: str | None = None,
) -> dict[str, str]:
    context_root_ref = context_root_ref or f"{ref_prefix}/context"
    context_policy_ref = f"{context_root_ref}/policy.json"
    context_compile_request_ref = f"{context_root_ref}/compile_request.json"
    context_baseline_ref = f"{context_root_ref}/baseline.json"
    source_snapshot_ref = f"{context_root_ref}/source_snapshot.json"
    context_epoch_ref = f"{context_root_ref}/epoch.json"
    context_cache_layout_ref = f"{context_root_ref}/cache_layout.json"
    context_pressure_ref = f"{context_root_ref}/pressure.json"
    context_turn_safe_point_ref = f"{context_root_ref}/turn_safe_point.json"
    context_turn_boundary_ref = f"{context_root_ref}/turn_boundary.json"
    context_checkpoint_ref = f"{context_root_ref}/checkpoint.json"
    context_compile_result_ref = f"{context_root_ref}/compile_result.json"
    context_package_ref = f"{context_root_ref}/package.json"
    call_id = compiled.piworker_call.call_id
    role = compiled.piworker_call.role.value
    context_view = compiled_context.view

    write_json_ref(workspace, context_policy_ref, context_policy.to_dict())
    write_json_ref(workspace, context_compile_request_ref, compiled_context.request.to_dict())
    write_json_ref(workspace, context_projection_ref, context_view.to_dict())
    stable_prefix = [segment.to_dict() for segment in sorted(context_view.stable_prefix, key=_context_segment_sort_key)]
    stable_baseline_hash = stable_json_hash(stable_prefix)
    write_json_ref(
        workspace,
        context_baseline_ref,
        {
            "schema_version": "missionforge.context_epoch_baseline.v1",
            "view_ref": context_projection_ref,
            "baseline_hash": stable_baseline_hash,
            "stable_prefix": stable_prefix,
        },
    )
    source_snapshot_payload = _context_source_snapshot_payload(
        context_view=context_view,
        view_ref=context_projection_ref,
        snapshots=compiled_context.source_snapshots,
    )
    write_json_ref(workspace, source_snapshot_ref, source_snapshot_payload)

    previous_epoch = _read_previous_context_epoch(workspace, context_epoch_ref)
    epoch = reconcile_context_epoch(
        epoch_id=f"{call_id}-epoch",
        request=compiled_context.request,
        view=context_view,
        baseline_ref=context_baseline_ref,
        source_snapshot_ref=source_snapshot_ref,
        previous_epoch=previous_epoch,
    )
    write_json_ref(workspace, context_epoch_ref, epoch.to_dict())
    write_json_ref(workspace, context_cache_layout_ref, compiled_context.cache_layout.to_dict())
    write_json_ref(workspace, context_pressure_ref, compiled_context.pressure.to_dict())
    checkpoint_ref = _write_context_checkpoint_if_needed(
        workspace=workspace,
        compiled=compiled,
        context=context,
        checkpoint_ref=context_checkpoint_ref,
        context_pressure_ref=context_pressure_ref,
        source_snapshot_ref=source_snapshot_ref,
        context_projection_ref=context_projection_ref,
        context_view=context_view,
        compiled_context=compiled_context,
    )

    turn_safe_point_payload = {
        "schema_version": "missionforge.context_turn_safe_point.v1",
        "run_id": context.flow_id,
        "step_id": compiled.step.id,
        "call_id": call_id,
        "pre_view_ref": context_projection_ref,
        "context_epoch_ref": context_epoch_ref,
        "context_cache_layout_ref": context_cache_layout_ref,
        "context_pressure_ref": context_pressure_ref,
        "context_checkpoint_ref": checkpoint_ref,
    }
    write_json_ref(workspace, context_turn_safe_point_ref, turn_safe_point_payload)

    boundary_status = (
        ContextTurnBoundaryStatus.CHECKPOINT_REQUIRED
        if compiled_context.result.action is ContextCompileAction.CHECKPOINT_BEFORE_NEXT_TURN
        else ContextTurnBoundaryStatus.BLOCKED
        if compiled_context.result.action
        in {
            ContextCompileAction.BLOCKED_BY_DENIED_REQUIRED_SOURCE,
            ContextCompileAction.BLOCKED_BY_UNAVAILABLE_AUTHORITY,
        }
        else ContextTurnBoundaryStatus.READY
    )
    turn_boundary = ContextTurnBoundary(
        boundary_id=f"{call_id}-turn-boundary",
        run_id=context.flow_id,
        call_id=call_id,
        turn_id=f"{call_id}-turn-001",
        role=role,
        safe_point_ref=context_turn_safe_point_ref,
        pre_view_ref=context_projection_ref,
        status=boundary_status,
        context_epoch_ref=context_epoch_ref,
        checkpoint_ref=checkpoint_ref,
        metadata={
            "context_cache_layout_ref": context_cache_layout_ref,
            "context_pressure_ref": context_pressure_ref,
            "context_checkpoint_ref": checkpoint_ref,
            "context_compile_action": compiled_context.result.action.value,
        },
    )
    write_json_ref(workspace, context_turn_boundary_ref, turn_boundary.to_dict())

    compile_result = replace(
        compiled_context.result,
        epoch_ref=context_epoch_ref,
        pressure_ref=context_pressure_ref,
        cache_layout_ref=context_cache_layout_ref,
        diagnostics_refs=[
            source_snapshot_ref,
            context_cache_layout_ref,
            context_pressure_ref,
            *([checkpoint_ref] if checkpoint_ref else []),
            context_turn_boundary_ref,
        ],
        metadata={
            **dict(compiled_context.result.metadata),
            "source_snapshot_ref": source_snapshot_ref,
            "context_policy_ref": context_policy_ref,
            "context_policy_hash": context_policy.policy_hash,
            "checkpoint_ref": checkpoint_ref,
            "turn_boundary_ref": context_turn_boundary_ref,
            "turn_safe_point_ref": context_turn_safe_point_ref,
        },
    )
    write_json_ref(workspace, context_compile_result_ref, compile_result.to_dict())
    context_package = _build_context_package(
        workspace=workspace,
        compiled=compiled,
        context=context,
        context_policy_ref=context_policy_ref,
        context_policy_hash=context_policy.policy_hash,
        context_compile_request_ref=context_compile_request_ref,
        context_projection_ref=context_projection_ref,
        context_baseline_ref=context_baseline_ref,
        source_snapshot_ref=source_snapshot_ref,
        context_epoch_ref=context_epoch_ref,
        context_cache_layout_ref=context_cache_layout_ref,
        context_pressure_ref=context_pressure_ref,
        context_checkpoint_ref=checkpoint_ref,
        context_turn_safe_point_ref=context_turn_safe_point_ref,
        context_turn_boundary_ref=context_turn_boundary_ref,
        context_compile_result_ref=context_compile_result_ref,
        context_view=context_view,
        compiled_context=compiled_context,
        compile_result=compile_result,
    )
    write_json_ref(workspace, context_package_ref, context_package.to_dict())

    return {
        "context_policy_ref": context_policy_ref,
        "context_policy_hash": context_policy.policy_hash,
        "context_projection_ref": context_projection_ref,
        "context_compile_request_ref": context_compile_request_ref,
        "context_baseline_ref": context_baseline_ref,
        "context_source_snapshot_ref": source_snapshot_ref,
        "context_epoch_ref": context_epoch_ref,
        "context_cache_layout_ref": context_cache_layout_ref,
        "context_pressure_ref": context_pressure_ref,
        "context_checkpoint_ref": checkpoint_ref,
        "context_turn_safe_point_ref": context_turn_safe_point_ref,
        "context_turn_boundary_ref": context_turn_boundary_ref,
        "context_compile_result_ref": context_compile_result_ref,
        "context_package_ref": context_package_ref,
        "context_package_hash": context_package.context_package_hash,
        "context_compile_action": compile_result.action.value,
    }


def _build_context_package(
    *,
    workspace: Any,
    compiled: CompiledStep,
    context: StepCompileContext,
    context_policy_ref: str,
    context_policy_hash: str,
    context_compile_request_ref: str,
    context_projection_ref: str,
    context_baseline_ref: str,
    source_snapshot_ref: str,
    context_epoch_ref: str,
    context_cache_layout_ref: str,
    context_pressure_ref: str,
    context_checkpoint_ref: str,
    context_turn_safe_point_ref: str,
    context_turn_boundary_ref: str,
    context_compile_result_ref: str,
    context_view: ContextView,
    compiled_context: CompiledContext,
    compile_result: Any,
) -> ContextPackage:
    context_record_refs = _dedupe_refs(
        [
            context_policy_ref,
            context_compile_request_ref,
            context_projection_ref,
            context_baseline_ref,
            source_snapshot_ref,
            context_epoch_ref,
            context_cache_layout_ref,
            context_pressure_ref,
            *([context_checkpoint_ref] if context_checkpoint_ref else []),
            context_turn_safe_point_ref,
            context_turn_boundary_ref,
            context_compile_result_ref,
        ]
    )
    step_spec_ref = compiled.piworker_call.metadata.get("kernel_step_spec_ref")
    safe_step_spec_ref = (
        validate_ref(step_spec_ref, "context_package.step_spec_ref")
        if isinstance(step_spec_ref, str) and step_spec_ref
        else None
    )
    return ContextPackage(
        package_id=f"{compiled.piworker_call.call_id}-context-package",
        role=compiled.piworker_call.role.value,
        run_id=context.flow_id,
        step_id=compiled.step.id,
        call_id=compiled.piworker_call.call_id,
        contract_ref=compiled.piworker_call.contract_ref,
        contract_hash=compiled.piworker_call.contract_hash,
        permission_manifest_ref=compiled.permission_manifest_ref,
        permission_manifest_hash=stable_json_hash(compiled.permission_manifest.to_dict()),
        context_view_ref=context_projection_ref,
        context_hash=context_view.context_hash,
        policy_ref=context_policy_ref,
        policy_hash=context_policy_hash,
        compile_request_ref=context_compile_request_ref,
        compile_result_ref=context_compile_result_ref,
        source_snapshot_ref=source_snapshot_ref,
        epoch_ref=context_epoch_ref,
        baseline_ref=context_baseline_ref,
        cache_layout_ref=context_cache_layout_ref,
        pressure_ref=context_pressure_ref,
        turn_safe_point_ref=context_turn_safe_point_ref,
        turn_boundary_ref=context_turn_boundary_ref,
        step_spec_ref=safe_step_spec_ref,
        step_spec_hash=compiled.step.spec_hash if safe_step_spec_ref else None,
        tool_schema_hash=stable_json_hash({"allowed_tools": list(compiled.permission_manifest.allowed_tools)}),
        checkpoint_ref=context_checkpoint_ref or None,
        working_set_ref=compiled_context.request.working_set_ref,
        visible_refs=list(compiled.piworker_call.visible_refs),
        visible_ref_hashes=_hash_existing_refs(workspace, list(compiled.piworker_call.visible_refs)),
        context_record_refs=context_record_refs,
        context_record_hashes=_hash_existing_refs(workspace, context_record_refs),
        context_feed_refs=list(context.context_feed_refs or []),
        diagnostics_refs=list(compile_result.diagnostics_refs),
        metadata={
            "context_compile_action": compile_result.action.value,
            "pressure_action": compiled_context.pressure.recommended_action.value,
            "context_record_ref_count": len(context_record_refs),
        },
        created_at=_utc_now(),
    )


def _hash_existing_refs(workspace: Any, refs: list[str]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for ref in _dedupe_refs(refs):
        if ref_exists(workspace, ref):
            hashes[ref] = hash_ref(workspace, ref)
    return hashes


def _context_source_snapshot_payload(
    *,
    context_view: ContextView,
    view_ref: str,
    snapshots: list[ContextSourceSnapshot] | None = None,
) -> dict[str, Any]:
    context_view.validate()
    snapshot_records = (
        list(snapshots)
        if snapshots is not None
        else [
            ContextSourceSnapshot(
                source_key=segment.segment_id,
                source_refs=list(segment.source_refs),
                source_hashes=dict(segment.source_hashes),
                projection_ref=segment.body_ref,
                token_estimate=segment.token_estimate,
                sequence=index,
                metadata={
                    "segment_kind": segment.kind.value,
                    "cache_policy": segment.cache_policy.value,
                    "inline_policy": segment.inline_policy.value,
                },
            )
            for index, segment in enumerate(context_view.all_segments)
        ]
    )
    source_refs = _dedupe_refs(
        [ref for segment in context_view.all_segments for ref in [*segment.source_refs, segment.body_ref] if ref]
    )
    payload = {
        "schema_version": "missionforge.context_source_snapshot_index.v1",
        "view_ref": view_ref,
        "context_hash": context_view.context_hash,
        "source_refs": source_refs,
        "snapshots": [snapshot.to_dict() for snapshot in snapshot_records],
    }
    payload["snapshot_index_hash"] = stable_json_hash(payload)
    return payload


def _read_previous_context_epoch(workspace: Any, ref: str) -> ContextEpoch | None:
    if not ref_exists(workspace, ref):
        return None
    try:
        return ContextEpoch.from_dict(read_json_ref(workspace, ref))
    except ContractValidationError:
        return None


def _context_segment_sort_key(segment: Any) -> tuple[int, str]:
    return (-int(segment.priority), str(segment.segment_id))
